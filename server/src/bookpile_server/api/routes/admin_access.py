import json
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from secrets import compare_digest, token_bytes, token_urlsafe
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from ...config import get_settings
from ...models import PlatformAdminAccess
from ...repositories.auth import AuthRepository
from ...services.auth import hash_session_secret, utc_value
from ...services.rate_limits import (
    RateLimitDecisionUnavailableError,
    RateLimitExceededError,
    RateLimitPolicy,
)
from ..dependencies import (
    CsrfDependency,
    CurrentAuthDependency,
    RateLimiterDependency,
    SessionDependency,
)


ADMIN_COOKIE = "__Host-bookpile_admin"
ADMIN_CSRF_COOKIE = "__Host-bookpile_admin_csrf"
IDLE = timedelta(minutes=15)
ABSOLUTE = timedelta(minutes=30)
CHALLENGE_LIFETIME = timedelta(minutes=2)
STEP_UP_LIFETIME = timedelta(minutes=5)
UV_REQUIRED = UserVerificationRequirement.REQUIRED
PROOF_ERRORS = (WebAuthnException, ValueError, TypeError, AttributeError, KeyError, IndexError,
                OverflowError, RecursionError)


def require_admin_origin(request: Request, response: Response) -> None:
    settings = get_settings()
    if not settings.admin_access_enabled:
        raise HTTPException(404)
    if request.headers.getlist("origin") != [settings.public_origin]:
        raise HTTPException(403, "Invalid admin request origin")
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/admin/access", tags=["platform authentication"],
    dependencies=[Depends(require_admin_origin)],
)


def get_access(session: SessionDependency, context: CurrentAuthDependency) -> PlatformAdminAccess:
    # The row is created by the host and references the explicit role. Lock it
    # across challenge/session transitions, including while revocation waits.
    access = session.scalar(
        select(PlatformAdminAccess)
        .where(PlatformAdminAccess.user_id == context.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if access is None:
        raise HTTPException(403, "Platform access is unavailable")
    return access


AdminAccess = Annotated[PlatformAdminAccess, Depends(get_access)]


def limit_attempt(request: Request, context: CurrentAuthDependency, limiter: RateLimiterDependency,
                  _csrf: CsrfDependency) -> None:
    phase = request.scope["route"].name
    try:
        address = str(ip_address(request.client.host)) if request.client else "unknown"
    except ValueError:
        address = "unknown"
    try:
        for dimension, key, attempts in (("ip", address, 30), ("identity", str(context.user_id), 10)):
            limiter.apply(
                RateLimitPolicy(f"{phase}_{dimension}", attempts, IDLE),
                key=key, mode="enforce",
            )
    except RateLimitExceededError as exc:
        raise HTTPException(429, "Too many requests", headers={"Retry-After": str(exc.retry_after)}) from exc
    except RateLimitDecisionUnavailableError as exc:
        raise HTTPException(503, "Admin request limiting is unavailable") from exc


async def read_proof(request: Request) -> dict:
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 32_768:
            raise HTTPException(413, "WebAuthn response is too large")
        data.extend(chunk)
    try:
        proof = json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(400, "Invalid WebAuthn response") from exc
    if not isinstance(proof, dict):
        raise HTTPException(400, "Invalid WebAuthn response")
    return proof


def rp_id() -> str:
    return urlsplit(get_settings().public_origin).hostname or ""


def matches_secret(stored: str | None, supplied: object) -> bool:
    return bool(stored and isinstance(supplied, str) and len(supplied) <= 128 and
                compare_digest(stored, hash_session_secret(supplied)))


def authentication_options(access: PlatformAdminAccess, challenge: bytes) -> dict:
    if access.credential_id is None:
        raise HTTPException(403, "Platform credential is unavailable")
    options = generate_authentication_options(
        rp_id=rp_id(), challenge=challenge, user_verification=UV_REQUIRED,
        allow_credentials=[PublicKeyCredentialDescriptor(id=access.credential_id)],
        timeout=int(CHALLENGE_LIFETIME.total_seconds() * 1000),
    )
    return {"ceremony": "authentication", "public_key": json.loads(options_to_json(options))}


@router.post("/options", dependencies=[Depends(limit_attempt)], name="admin_webauthn_options")
def start_access(access: AdminAccess, context: CurrentAuthDependency, session: SessionDependency) -> dict:
    now = datetime.now(UTC)
    challenge = token_bytes(32)
    if access.credential_id is None:
        if now >= utc_value(access.bootstrap_expires_at):
            raise HTTPException(403, "Platform credential enrolment is unavailable")
        options = generate_registration_options(
            rp_id=rp_id(), rp_name="BOOKPILE Server", user_id=context.user_id.bytes,
            user_name=context.username, challenge=challenge,
            timeout=int(CHALLENGE_LIFETIME.total_seconds() * 1000),
            authenticator_selection=AuthenticatorSelectionCriteria(user_verification=UV_REQUIRED),
        )
        result = {"ceremony": "registration", "public_key": json.loads(options_to_json(options))}
    else:
        result = authentication_options(access, challenge)
    access.challenge = challenge
    access.challenge_session_id = context.user_session.id
    access.challenge_expires_at = now + CHALLENGE_LIFETIME
    session.commit()
    return result


def consume_challenge(access: PlatformAdminAccess, session_id: UUID, now: datetime) -> bytes:
    if (
        access.challenge is None
        or access.challenge_session_id != session_id
        or access.challenge_expires_at is None
        or now >= utc_value(access.challenge_expires_at)
    ):
        raise HTTPException(403, "WebAuthn challenge is unavailable")
    challenge = access.challenge
    access.challenge = access.challenge_session_id = access.challenge_expires_at = None
    return challenge


def proof_parameters(proof: dict, challenge: bytes) -> dict:
    credential = proof.get("credential")
    if not isinstance(credential, dict):
        raise ValueError
    client_data = json.loads(base64url_to_bytes(credential["response"]["clientDataJSON"]))
    if not isinstance(client_data, dict) or client_data.get("crossOrigin", False) is not False:
        raise ValueError
    return dict(credential=credential, expected_challenge=challenge, expected_rp_id=rp_id(),
                expected_origin=get_settings().public_origin, require_user_verification=True)


def verify_assertion(access: PlatformAdminAccess, verifier: dict) -> int:
    if access.credential_id is None or access.public_key is None or access.sign_count is None:
        raise ValueError
    assertion = verify_authentication_response(
        **verifier, credential_public_key=access.public_key,
        credential_current_sign_count=access.sign_count,
    )
    if assertion.credential_id != access.credential_id:
        raise ValueError
    return assertion.new_sign_count


def clear_step_up(access: PlatformAdminAccess) -> None:
    access.step_up_session_hash = access.step_up_verified_at = None
    access.step_up_challenge = access.step_up_challenge_expires_at = None


@router.post("/verify", dependencies=[Depends(limit_attempt)], name="admin_webauthn_verify")
def finish_access(
    proof: Annotated[dict, Depends(read_proof)], access: AdminAccess, context: CurrentAuthDependency,
    session: SessionDependency, response: Response,
) -> dict:
    now = datetime.now(UTC)
    challenge = consume_challenge(access, context.user_session.id, now)
    audit = AuthRepository(session)
    try:
        verifier = proof_parameters(proof, challenge)
        if access.credential_id is None:
            if now >= utc_value(access.bootstrap_expires_at) or not matches_secret(
                access.bootstrap_hash, proof.get("confirmation")
            ):
                raise ValueError
            registration = verify_registration_response(**verifier)
            # Flush the consumed challenge outside the savepoint. A duplicate
            # credential must not restore the challenge on constraint failure.
            with session.begin_nested():
                access.credential_id = registration.credential_id
                access.public_key = registration.credential_public_key
                access.sign_count = registration.sign_count
            audit.add_security_event("admin_passkey_registered", user_id=context.user_id, ip_address=None)
            session.commit()
            return {"registered": True}
        access.sign_count = verify_assertion(access, verifier)
    except (*PROOF_ERRORS, IntegrityError) as exc:
        audit.add_security_event("admin_webauthn_rejected", user_id=context.user_id, ip_address=None)
        session.commit()
        raise HTTPException(403, "WebAuthn proof or confirmation was rejected") from exc

    token, csrf = token_urlsafe(32), token_urlsafe(32)
    now = datetime.now(UTC)
    access.session_hash = hash_session_secret(token)
    access.csrf_hash = hash_session_secret(csrf)
    access.parent_session_id = context.user_session.id
    access.last_active_at = now
    access.absolute_expires_at = now + ABSOLUTE
    clear_step_up(access)
    audit.add_security_event("admin_session_started", user_id=context.user_id, ip_address=None)
    session.commit()
    for name, secret, http_only in ((ADMIN_COOKIE, token, True), (ADMIN_CSRF_COOKIE, csrf, False)):
        response.set_cookie(name, secret, path="/", max_age=int(ABSOLUTE.total_seconds()),
                            secure=True, httponly=http_only, samesite="strict")
    return {"registered": False}


def session_deadline(access: PlatformAdminAccess) -> datetime | None:
    if access.last_active_at is None or access.absolute_expires_at is None:
        return None
    return min(utc_value(access.last_active_at) + IDLE, utc_value(access.absolute_expires_at))


def require_admin_session(
    request: Request, _origin: Annotated[None, Depends(require_admin_origin)],
    context: CurrentAuthDependency, _csrf: CsrfDependency, access: AdminAccess,
) -> PlatformAdminAccess:
    deadline = session_deadline(access)
    if (
        access.parent_session_id != context.user_session.id
        or not matches_secret(access.session_hash, request.cookies.get(ADMIN_COOKIE))
        or deadline is None or datetime.now(UTC) >= deadline
    ):
        raise HTTPException(401, "Platform session required")
    csrf = request.headers.get("X-Admin-CSRF-Token")
    if csrf != request.cookies.get(ADMIN_CSRF_COOKIE) or not matches_secret(access.csrf_hash, csrf):
        raise HTTPException(403, "Invalid platform CSRF token")
    return access


AdminSession = Annotated[PlatformAdminAccess, Depends(require_admin_session)]


def require_admin_step_up(access: AdminSession) -> PlatformAdminAccess:
    """Keep the admin row locked through the protected action's transaction."""
    verified_at = access.step_up_verified_at
    now = datetime.now(UTC)
    if (
        access.step_up_session_hash != access.session_hash
        or verified_at is None
        or not utc_value(verified_at) <= now < utc_value(verified_at) + STEP_UP_LIFETIME
    ):
        raise HTTPException(403, "Recent WebAuthn reverification required")
    return access


AdminStepUp = Annotated[PlatformAdminAccess, Depends(require_admin_step_up)]


@router.post("/step-up/options", dependencies=[Depends(limit_attempt)], name="admin_step_up_options")
def start_step_up(access: AdminSession, session: SessionDependency) -> dict:
    challenge = token_bytes(32)
    result = authentication_options(access, challenge)
    if access.step_up_session_hash != access.session_hash:
        clear_step_up(access)
    # The admin token binds this state to the ordinary session in the same row.
    access.step_up_session_hash = access.session_hash
    access.step_up_challenge = challenge
    access.step_up_challenge_expires_at = datetime.now(UTC) + CHALLENGE_LIFETIME
    session.commit()
    return result


@router.post("/step-up/verify", dependencies=[Depends(limit_attempt)], name="admin_step_up_verify")
def finish_step_up(
    proof: Annotated[dict, Depends(read_proof)], access: AdminSession, session: SessionDependency,
) -> dict:
    challenge = access.step_up_challenge
    expires_at = access.step_up_challenge_expires_at
    if (
        access.step_up_session_hash != access.session_hash or challenge is None
        or expires_at is None or datetime.now(UTC) >= utc_value(expires_at)
    ):
        raise HTTPException(403, "WebAuthn challenge is unavailable")
    access.step_up_challenge = access.step_up_challenge_expires_at = None
    audit = AuthRepository(session)
    try:
        sign_count = verify_assertion(access, proof_parameters(proof, challenge))
    except PROOF_ERRORS as exc:
        audit.add_security_event("admin_step_up_rejected", user_id=access.user_id, ip_address=None)
        session.commit()
        raise HTTPException(403, "WebAuthn proof was rejected") from exc

    verified_at = datetime.now(UTC)
    deadline = session_deadline(access)
    if deadline is None or verified_at >= deadline:
        session.commit()
        raise HTTPException(401, "Platform session required")
    if verified_at >= utc_value(expires_at):
        session.commit()
        raise HTTPException(403, "WebAuthn challenge is unavailable")
    access.sign_count = sign_count
    access.step_up_verified_at = verified_at
    audit.add_security_event("admin_step_up_verified", user_id=access.user_id, ip_address=None)
    session.commit()
    return {"expires_at": min(verified_at + STEP_UP_LIFETIME, deadline)}


@router.post("/session")
def admin_session(access: AdminSession, session: SessionDependency) -> dict:
    access.last_active_at = datetime.now(UTC)
    expires_at = min(access.last_active_at + IDLE, utc_value(access.absolute_expires_at))
    session.commit()
    return {"expires_at": expires_at, "absolute_expires_at": utc_value(access.absolute_expires_at)}


@router.post("/logout", status_code=204)
def admin_logout(access: AdminSession, session: SessionDependency, response: Response) -> None:
    access.session_hash = access.csrf_hash = access.parent_session_id = None
    access.last_active_at = access.absolute_expires_at = None
    clear_step_up(access)
    AuthRepository(session).add_security_event("admin_session_ended", user_id=access.user_id, ip_address=None)
    session.commit()
    for name in (ADMIN_COOKIE, ADMIN_CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=True, httponly=name == ADMIN_COOKIE,
                               samesite="strict")

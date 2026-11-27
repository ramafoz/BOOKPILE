from datetime import UTC, datetime
from hmac import compare_digest, digest
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from ..config import Settings, get_settings
from ..models import PlatformRole, User, UserSession
from ..services.auth import utc_value
from .dependencies import SessionDependency


PAGE_PATH = "/admin-access"
PAGE_COOKIE = "__Secure-bookpile_admin_page"
router = APIRouter(include_in_schema=False)


def _page_signature(settings: Settings, session_id: UUID, token_hash: str) -> str:
    # Bind this proof to one ordinary session and one purpose. Neither the
    # ordinary bearer token nor its stored hash is sent to the browser here.
    return digest(
        settings.rate_limit_key_secret.encode(),
        f"admin-page\0{session_id.hex}\0{token_hash}".encode(),
        "sha256",
    ).hex()


def set_admin_page_cookie(
    response: Response, session_id: UUID, token_hash: str, absolute_expires_at: datetime
) -> None:
    settings = get_settings()
    if settings.admin_access_enabled:
        signature = _page_signature(settings, session_id, token_hash)
        remaining = utc_value(absolute_expires_at) - datetime.now(UTC)
        response.set_cookie(
            PAGE_COOKIE,
            f"{session_id.hex}.{signature}",
            path=PAGE_PATH,
            max_age=max(0, int(remaining.total_seconds())),
            httponly=True,
            secure=True,
            samesite="lax",
        )


@router.get("/internal/admin-page-eligibility", status_code=204)
def check_admin_page(request: Request, session: SessionDependency) -> Response:
    settings = get_settings()
    proof = request.cookies.get(PAGE_COOKIE, "")
    # Caddy forwards this request before serving the SPA. A missing or invalid
    # proof gets the same response as a disabled or revoked assignment.
    if not settings.admin_access_enabled or len(proof) != 97 or not proof.isascii():
        raise HTTPException(404)
    selector, separator, signature = proof.partition(".")
    if not separator or len(selector) != 32:
        raise HTTPException(404)
    try:
        session_id = UUID(hex=selector)
    except ValueError:
        raise HTTPException(404) from None

    now = datetime.now(UTC)
    token_hash = session.scalar(
        select(UserSession.token_hash)
        .join(User, User.id == UserSession.user_id)
        .join(PlatformRole, PlatformRole.user_id == User.id)
        .where(
            UserSession.id == session_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            UserSession.absolute_expires_at > now,
            User.state == "active",
            User.email_verified_at.is_not(None),
            PlatformRole.role == "SYSTEM_ADMIN",
        )
    )
    if token_hash is None or not compare_digest(
        signature, _page_signature(settings, session_id, token_hash)
    ):
        raise HTTPException(404)
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})

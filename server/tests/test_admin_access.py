from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from uuid import uuid4

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Response
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete

from bookpile_server.api.admin_page import PAGE_COOKIE
from bookpile_server.api.routes import admin_access
from bookpile_server.config import get_settings
from bookpile_server.database import get_session
from bookpile_server.main import create_app
from bookpile_server.models import (
    AccountStorageEntitlement, Library, LibraryMembership, LibraryStorageAllocation,
    PlatformAdminAccess, PlatformRole, SecurityEvent, User, UserProfile, UserSession,
)
from bookpile_server.services.auth import hash_session_secret
from bookpile_server.services.storage_accounting import calculate_account_data_bytes


ORIGIN = "https://testserver"
PREFIX = "/api/v1/admin/access"
CODE = "synthetic-operator-confirmation"
CSRF = "synthetic-normal-csrf"


def encoded(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode()


class Authenticator:
    """Generate a real P-256 registration and signed WebAuthn assertions."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = uuid4().bytes
        self.counter = 0

    def proof(self, options, *, origin=ORIGIN, rp="testserver", verified=True, cross_origin=False):
        registration = options["ceremony"] == "registration"
        client = json.dumps({
            "type": "webauthn.create" if registration else "webauthn.get",
            "challenge": options["public_key"]["challenge"],
            "origin": origin,
            "crossOrigin": cross_origin,
        }).encode()
        rp_hash = sha256(rp.encode()).digest()
        flags = 1 | (4 if verified else 0) | (64 if registration else 0)
        auth_data = rp_hash + bytes([flags]) + self.counter.to_bytes(4, "big")
        response = {"clientDataJSON": encoded(client)}
        if registration:
            numbers = self.key.public_key().public_numbers()
            cose_key = cbor2.dumps({1: 2, 3: -7, -1: 1,
                                   -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})
            auth_data += bytes(16) + len(self.credential_id).to_bytes(2, "big") + self.credential_id + cose_key
            response["attestationObject"] = encoded(cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data}))
        else:
            response["authenticatorData"] = encoded(auth_data)
            response["signature"] = encoded(self.key.sign(auth_data + sha256(client).digest(), ec.ECDSA(hashes.SHA256())))
        self.counter += 1
        return {"credential": {"id": encoded(self.credential_id), "rawId": encoded(self.credential_id),
                               "type": "public-key", "response": response}}


@pytest.fixture
def operator(session, monkeypatch):
    monkeypatch.setenv("BOOKPILE_SERVER_PUBLIC_BASE_URL", ORIGIN)
    monkeypatch.setenv("BOOKPILE_SERVER_ADMIN_WEBAUTHN_ENABLED", "true")
    get_settings.cache_clear()
    settings = get_settings()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session

    @app.post(f"{PREFIX}/test-protected-action", status_code=204)
    def protected_action(_step_up: admin_access.AdminStepUp):
        return Response(status_code=204)

    now = datetime.now(UTC)
    user = User(username="test_operator", email="operator@example.test", password_hash="unused",
                state="active", email_verified_at=now)
    session.add(user)
    session.flush()
    library = Library(name="Operator library", slug="operator-library", created_by_user_id=user.id)
    foreign = Library(name="Other library", slug="other-library")
    session.add_all([library, foreign])
    session.flush()
    session.add(LibraryMembership(user_id=user.id, library_id=library.id, role="OWNER"))
    session.add_all(UserSession(user_id=user.id, token_hash=hash_session_secret(raw),
                                csrf_token_hash=hash_session_secret(CSRF), last_seen_at=now,
                                expires_at=now + timedelta(days=1), absolute_expires_at=now + timedelta(days=1))
                    for raw in ("primary", "alternate"))
    session.commit()
    try:
        with TestClient(app, base_url=ORIGIN, client=("192.0.2.8", 12345),
                        headers={"Origin": ORIGIN, "X-CSRF-Token": CSRF}) as browser:
            browser.cookies.set(settings.session_cookie_name, "primary")
            yield browser, user.id, library.id, foreign.id
    finally:
        get_settings.cache_clear()


def prepare(session, user_id):
    session.add(PlatformRole(user_id=user_id, role="SYSTEM_ADMIN"))
    session.flush()
    access = PlatformAdminAccess(user_id=user_id, bootstrap_hash=hash_session_secret(CODE),
                                 bootstrap_expires_at=datetime.now(UTC) + timedelta(minutes=10))
    session.add(access)
    session.commit()
    return access


def options(browser):
    response = browser.post(f"{PREFIX}/options")
    assert response.status_code == 200, response.json()
    return response.json()


def open_session(browser, key=None):
    key = key or Authenticator()
    registration = key.proof(options(browser))
    registered = browser.post(f"{PREFIX}/verify", json={**registration, "confirmation": CODE})
    assert registered.json() == {"registered": True}
    assert not registered.headers.get_list("set-cookie")
    assert browser.post(f"{PREFIX}/verify", json={**registration, "confirmation": CODE}).status_code == 403
    assertion = key.proof(options(browser))
    authenticated = browser.post(f"{PREFIX}/verify", json=assertion)
    assert authenticated.json() == {"registered": False}
    cookie = next(value for value in authenticated.headers.get_list("set-cookie")
                  if value.startswith(f"{admin_access.ADMIN_COOKIE}="))
    assert {"HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age=1800"} <= set(cookie.split("; ")[1:])
    assert browser.post(f"{PREFIX}/verify", json=assertion).status_code == 403
    return {"X-Admin-CSRF-Token": browser.cookies[admin_access.ADMIN_CSRF_COOKIE]}


def test_explicit_role_and_webauthn_preserve_library_permissions(operator, session):
    browser, user_id, library_id, foreign_id = operator
    own = f"/api/v1/libraries/{library_id}/members"
    foreign = f"/api/v1/libraries/{foreign_id}/members"
    before = browser.get(own)
    assert before.status_code == 200
    assert browser.get(foreign).status_code == 404
    assert browser.post(f"{PREFIX}/options").status_code == 403
    prepare(session, user_id)
    assert browser.get("/api/v1/auth/me").status_code == 200
    page_proof = {"Cookie": f"{PAGE_COOKIE}={browser.cookies[PAGE_COOKIE]}"}
    page_gate = "/internal/admin-page-eligibility"
    assert browser.get(page_gate, headers=page_proof).status_code == 204
    assert browser.post(f"{PREFIX}/session").status_code == 401
    assert browser.post(f"{PREFIX}/options", headers={"Origin": "https://other.example"}).status_code == 403
    assert browser.post(f"{PREFIX}/options", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    headers = open_session(browser)
    assert browser.post(f"{PREFIX}/session").status_code == 403
    assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 200
    assert browser.get(own).json() == before.json()
    assert browser.get(foreign).status_code == 404
    assert browser.post(f"{PREFIX}/logout", headers=headers).status_code == 204
    assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 401
    assert browser.get(page_gate, headers=page_proof).status_code == 204
    assert options(browser)["ceremony"] == "authentication"
    assert browser.get(own).json() == before.json()


@pytest.mark.parametrize("absolute", [False, True])
def test_admin_session_expires_at_both_limits(operator, session, monkeypatch, absolute):
    browser, user_id, *_ = operator
    access = prepare(session, user_id)
    headers = open_session(browser)
    started = admin_access.utc_value(access.last_active_at)

    class Clock(datetime):
        current = started

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(admin_access, "datetime", Clock)
    Clock.current = started + timedelta(minutes=14)
    assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 200
    if absolute:
        Clock.current = started + timedelta(minutes=28)
        assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 200
        Clock.current = started + timedelta(minutes=30)
    else:
        Clock.current = started + timedelta(minutes=29)
    assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 401
    assert browser.get("/api/v1/auth/me").status_code == 200


def test_challenge_and_admin_session_are_bound_to_the_normal_session(operator, session):
    browser, user_id, *_ = operator
    prepare(session, user_id)
    cookie = get_settings().session_cookie_name
    registration = Authenticator().proof(options(browser))
    browser.cookies.set(cookie, "alternate")
    assert browser.post(f"{PREFIX}/verify", json={**registration, "confirmation": CODE}).status_code == 403
    browser.cookies.set(cookie, "primary")
    headers = open_session(browser)
    browser.cookies.set(cookie, "alternate")
    assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 401
    browser.cookies.set(cookie, "primary")
    session.execute(delete(PlatformRole).where(PlatformRole.user_id == user_id))
    session.commit()
    assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 403


def test_registration_confirmation_and_proof_limits(operator, session):
    browser, user_id, *_ = operator
    access = prepare(session, user_id)
    key = Authenticator()
    for proof, code in (
        ({}, "invalid"), ({"origin": "https://different.example"}, CODE),
        ({"verified": False}, CODE), ({"cross_origin": True}, CODE),
    ):
        payload = key.proof(options(browser), **proof)
        assert browser.post(f"{PREFIX}/verify", json={**payload, "confirmation": code}).status_code == 403
    assert access.credential_id is None
    for _ in range(6):
        assert browser.post(f"{PREFIX}/verify", json={}).status_code == 403
    # Forwarding headers from an untrusted peer cannot evade the limit.
    assert browser.post(f"{PREFIX}/verify", json={}, headers={"X-Forwarded-For": "192.0.2.9"}).status_code == 429


def step_up_proof(browser, headers, key, **kwargs):
    response = browser.post(f"{PREFIX}/step-up/options", headers=headers)
    assert response.status_code == 200
    public_key = response.json()["public_key"]
    assert public_key["userVerification"] == "required"
    assert public_key["allowCredentials"] == [{"id": encoded(key.credential_id), "type": "public-key"}]
    return key.proof(response.json(), **kwargs)


def freeze_admin_clock(monkeypatch, start):
    class Clock(datetime):
        current = start

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(admin_access, "datetime", Clock)
    return Clock


def test_step_up_requires_its_own_assertion_and_expires_at_five_minutes(operator, session, monkeypatch):
    browser, user_id, *_ = operator
    access = prepare(session, user_id)
    key = Authenticator()
    protected = f"{PREFIX}/test-protected-action"
    verify = f"{PREFIX}/step-up/verify"
    assert browser.post(f"{PREFIX}/step-up/options").status_code == 401
    assert browser.post(verify, json={}).status_code == 401
    assert browser.post(protected).status_code == 401
    headers = open_session(browser, key)
    started = admin_access.utc_value(access.last_active_at)
    clock = freeze_admin_clock(monkeypatch, started)
    assert browser.post(protected, headers=headers).status_code == 403
    proof = step_up_proof(browser, headers, key)
    assert browser.post(protected, headers=headers).status_code == 403
    clock.current += timedelta(seconds=10)
    verified = browser.post(verify, headers=headers, json=proof)
    assert verified.status_code == 200
    assert not verified.headers.get_list("set-cookie")
    expires = clock.current + timedelta(minutes=5)
    assert datetime.fromisoformat(verified.json()["expires_at"]) == expires
    assert browser.post(verify, headers=headers, json=proof).status_code == 403
    assert browser.post(protected, headers=headers).status_code == 204
    clock.current = expires - timedelta(microseconds=1)
    assert browser.get("/api/v1/auth/me").status_code == 200
    assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 200
    assert browser.post(protected, headers=headers).status_code == 204
    clock.current = expires
    assert browser.post(protected, headers=headers).status_code == 403
    assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 200


def test_step_up_enforces_origin_csrf_rp_and_user_verification(operator, session):
    browser, user_id, *_ = operator
    prepare(session, user_id)
    key = Authenticator()
    headers = open_session(browser, key)
    verify = f"{PREFIX}/step-up/verify"
    protected = f"{PREFIX}/test-protected-action"
    valid = step_up_proof(browser, headers, key)
    for invalid in ({"Origin": "https://other.example"}, {"X-CSRF-Token": "wrong"}, {"X-Admin-CSRF-Token": "wrong"}):
        for route in ("step-up/options", "step-up/verify"):
            assert browser.post(f"{PREFIX}/{route}", headers=headers | invalid, json=valid).status_code == 403
    assert browser.post(verify, headers=headers, json=valid).status_code == 200
    for invalid in ({"Origin": "https://other.example"}, {"X-CSRF-Token": "wrong"}, {"X-Admin-CSRF-Token": "wrong"}):
        assert browser.post(protected, headers=headers | invalid).status_code == 403

    for invalid in ({"origin": "https://other.example"}, {"rp": "other.example"},
                    {"verified": False}, {"cross_origin": True}):
        proof = step_up_proof(browser, headers, key, **invalid)
        assert browser.post(verify, headers=headers, json=proof).json()["detail"] == "WebAuthn proof was rejected"
        assert browser.post(verify, headers=headers, json=proof).json()["detail"] == "WebAuthn challenge is unavailable"


def test_step_up_challenge_and_proof_follow_the_admin_session_and_role(operator, session):
    browser, user_id, *_ = operator
    prepare(session, user_id)
    key = Authenticator()
    headers = open_session(browser, key)
    verify = f"{PREFIX}/step-up/verify"
    protected = f"{PREFIX}/test-protected-action"
    proof = step_up_proof(browser, headers, key)
    normal_cookie = get_settings().session_cookie_name
    browser.cookies.set(normal_cookie, "alternate")
    assert browser.post(verify, headers=headers, json=proof).status_code == 401
    browser.cookies.set(normal_cookie, "primary")
    assert browser.post(verify, headers=headers, json=proof).status_code == 200
    pending = step_up_proof(browser, headers, key)
    browser.cookies.set(normal_cookie, "alternate")
    assert browser.post(protected, headers=headers).status_code == 401
    browser.cookies.set(normal_cookie, "primary")
    assert browser.post(f"{PREFIX}/verify", json=key.proof(options(browser))).status_code == 200
    headers = {"X-Admin-CSRF-Token": browser.cookies[admin_access.ADMIN_CSRF_COOKIE]}
    assert browser.post(verify, headers=headers, json=pending).status_code == 403
    assert browser.post(protected, headers=headers).status_code == 403
    assert browser.post(verify, headers=headers, json=step_up_proof(browser, headers, key)).status_code == 200
    pending = step_up_proof(browser, headers, key)
    session.execute(delete(PlatformRole).where(PlatformRole.user_id == user_id))
    session.commit()
    assert browser.post(verify, headers=headers, json=pending).status_code == 403
    assert browser.post(protected, headers=headers).status_code == 403


@pytest.mark.parametrize("absolute", [False, True])
def test_step_up_respects_admin_idle_and_absolute_deadlines(operator, session, monkeypatch, absolute):
    browser, user_id, *_ = operator
    access = prepare(session, user_id)
    key = Authenticator()
    headers = open_session(browser, key)
    started = admin_access.utc_value(access.last_active_at)
    clock = freeze_admin_clock(monkeypatch, started)
    deadline = started + timedelta(minutes=30 if absolute else 15)
    if absolute:
        clock.current = started + timedelta(minutes=14)
        assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 200
        clock.current += timedelta(minutes=14)
        assert browser.post(f"{PREFIX}/session", headers=headers).status_code == 200
    last_active_at = admin_access.utc_value(access.last_active_at)
    clock.current = deadline - timedelta(seconds=30)
    verify = f"{PREFIX}/step-up/verify"
    result = browser.post(verify, headers=headers, json=step_up_proof(browser, headers, key))
    assert result.status_code == 200
    assert datetime.fromisoformat(result.json()["expires_at"]) == deadline
    assert admin_access.utc_value(access.last_active_at) == last_active_at
    pending = step_up_proof(browser, headers, key)
    protected = f"{PREFIX}/test-protected-action"
    assert browser.post(protected, headers=headers).status_code == 204
    clock.current = deadline
    assert browser.post(protected, headers=headers).status_code == 401
    assert browser.post(verify, headers=headers, json=pending).status_code == 401
    assert browser.post(f"{PREFIX}/step-up/options", headers=headers).status_code == 401


def test_step_up_challenge_cannot_be_used_for_sign_in_and_expires(operator, session, monkeypatch):
    browser, user_id, *_ = operator
    access = prepare(session, user_id)
    key = Authenticator()
    headers = open_session(browser, key)
    clock = freeze_admin_clock(monkeypatch, admin_access.utc_value(access.last_active_at))
    proof = step_up_proof(browser, headers, key)
    login_options = options(browser)
    assert browser.post(f"{PREFIX}/verify", json=proof).status_code == 403
    verify = f"{PREFIX}/step-up/verify"
    assert browser.post(verify, headers=headers, json=key.proof(login_options)).status_code == 403
    proof = step_up_proof(browser, headers, key)
    clock.current += admin_access.CHALLENGE_LIFETIME
    assert browser.post(verify, headers=headers, json=proof).status_code == 403
    assert browser.post(f"{PREFIX}/test-protected-action", headers=headers).status_code == 403


def test_account_invitation_revocation_checks_role_session_csrf_and_origin(operator, session):
    browser, user_id, *_ = operator
    path = "/api/v1/admin/account-invitations/revoke"
    payload = {"invitation_id": str(uuid4())}
    normal_cookie = get_settings().session_cookie_name
    browser.cookies.delete(normal_cookie)
    assert browser.post(path, json=payload).status_code == 401
    browser.cookies.set(normal_cookie, "primary")
    assert browser.post(path, json=payload).status_code == 403
    prepare(session, user_id)
    assert browser.post(path, json=payload).status_code == 401
    key = Authenticator()
    headers = open_session(browser, key)
    assert browser.post(path, headers=headers, json=payload).status_code == 403
    proof = step_up_proof(browser, headers, key)
    assert browser.post(f"{PREFIX}/step-up/verify", headers=headers, json=proof).status_code == 200
    for invalid in ({"Origin": "https://other.example"}, {"X-CSRF-Token": "wrong"}, {"X-Admin-CSRF-Token": "wrong"}):
        assert browser.post(path, headers=headers | invalid, json=payload).status_code == 403
    session.execute(delete(PlatformRole).where(PlatformRole.user_id == user_id))
    session.commit()
    assert browser.post(path, headers=headers, json=payload).status_code == 403


@pytest.mark.parametrize("absolute", [False, True])
def test_account_invitation_creation_rejects_unauthorized_requests(operator, session, monkeypatch, absolute):
    browser, user_id, library_id, _ = operator
    path = "/api/v1/admin/account-invitations/create"
    normal_cookie = get_settings().session_cookie_name
    browser.cookies.delete(normal_cookie)
    assert browser.post(path).status_code == 401
    browser.cookies.set(normal_cookie, "primary")
    assert browser.post(path).status_code == 403  # Owner
    membership = session.query(LibraryMembership).filter_by(user_id=user_id, library_id=library_id).one()
    membership.role = "VIEWER"
    membership.viewer_scope = "CATALOG_ONLY"
    session.commit()
    assert browser.post(path).status_code == 403
    session.delete(membership)
    session.commit()
    assert browser.post(path).status_code == 403  # Ordinary account

    access = prepare(session, user_id)
    assert browser.post(path).status_code == 401
    headers = open_session(browser)
    for invalid in (
        {"Origin": "https://other.example"}, {"Origin": ""},
        {"X-CSRF-Token": "wrong"}, {"X-Admin-CSRF-Token": "wrong"},
    ):
        assert browser.post(path, headers=headers | invalid).status_code == 403
    assert browser.post(path).status_code == 403  # Missing admin CSRF header
    browser.cookies.set(normal_cookie, "alternate")
    assert browser.post(path, headers=headers).status_code == 401
    browser.cookies.set(normal_cookie, "primary")

    session.refresh(access)
    if absolute:
        access.last_active_at = admin_access.utc_value(access.absolute_expires_at) - timedelta(minutes=1)
        session.commit()
    with monkeypatch.context() as clock:
        freeze_admin_clock(clock, admin_access.session_deadline(access))
        assert browser.post(path, headers=headers).status_code == 401
    session.execute(delete(PlatformRole).where(PlatformRole.user_id == user_id))
    session.commit()
    assert browser.post(path, headers=headers).status_code == 403


@pytest.mark.parametrize("query", ["list", "detail"])
@pytest.mark.parametrize("absolute", [False, True])
def test_account_directory_enforces_admin_session_on_each_query(operator, session, monkeypatch, query, absolute):
    browser, user_id, library_id, _ = operator
    path = f"/api/v1/admin/accounts/{query}"
    payload = {} if query == "list" else {"account_id": str(user_id)}
    normal_cookie = get_settings().session_cookie_name
    browser.cookies.delete(normal_cookie)
    assert browser.post(path, json=payload).status_code == 401
    browser.cookies.set(normal_cookie, "primary")
    assert browser.post(path, json=payload).status_code == 403  # Owner
    membership = session.query(LibraryMembership).filter_by(user_id=user_id, library_id=library_id).one()
    membership.role = "VIEWER"
    membership.viewer_scope = "CATALOG_ONLY"
    session.commit()
    assert browser.post(path, json=payload).status_code == 403  # Viewer
    session.delete(membership)
    session.commit()
    assert browser.post(path, json=payload).status_code == 403  # Ordinary user without membership

    access = prepare(session, user_id)
    assert browser.post(path, json=payload).status_code == 401  # Assignment with ordinary session only
    headers = open_session(browser)
    assert browser.post(path, json=payload).status_code == 403
    for invalid in (
        {"Origin": "https://other.example"}, {"X-CSRF-Token": "wrong"}, {"X-Admin-CSRF-Token": "wrong"},
    ):
        assert browser.post(path, headers=headers | invalid, json=payload).status_code == 403
    browser.cookies.set(normal_cookie, "alternate")
    assert browser.post(path, headers=headers, json=payload).status_code == 401
    browser.cookies.set(normal_cookie, "primary")

    response = browser.post(path, headers=headers, json=payload)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    session.refresh(access)
    if absolute:
        access.last_active_at = admin_access.utc_value(access.absolute_expires_at) - timedelta(minutes=1)
        session.commit()
    with monkeypatch.context() as clock:
        freeze_admin_clock(clock, admin_access.session_deadline(access))
        assert browser.post(path, headers=headers, json=payload).status_code == 401
    session.execute(delete(PlatformRole).where(PlatformRole.user_id == user_id))
    session.commit()
    assert browser.post(path, headers=headers, json=payload).status_code == 403


def test_account_directory_paginates_and_returns_only_account_facts(operator, session):
    browser, user_id, library_id, inactive_library_id = operator
    now = datetime.now(UTC).replace(microsecond=0)
    last_success = now - timedelta(days=2)
    candidates = [
        User(username=f"synthetic_{idx:02}", email=f"synthetic_{idx:02}@example.test", password_hash="unused")
        for idx in range(25)
    ]
    owner, viewer = candidates[:2]
    owner.state = "suspended"
    session.add_all(candidates)
    session.get(Library, inactive_library_id).state = "pending_deletion"
    session.flush()
    session.add_all([
        LibraryMembership(user_id=owner.id, library_id=library_id, role="OWNER"),
        LibraryMembership(user_id=owner.id, library_id=inactive_library_id, role="OWNER"),
        LibraryMembership(user_id=viewer.id, library_id=library_id, role="VIEWER", viewer_scope="CATALOG_ONLY"),
        AccountStorageEntitlement(user_id=owner.id, limit_bytes=100_000_000),
        AccountStorageEntitlement(user_id=viewer.id, limit_bytes=100_000_000),
        UserProfile(user_id=owner.id, display_name="Synthetic private profile"),
        SecurityEvent(user_id=owner.id, event_type="login_succeeded", occurred_at=now - timedelta(days=8)),
        SecurityEvent(user_id=owner.id, event_type="login_succeeded", occurred_at=last_success,
                      ip_address="192.0.2.10", details={"synthetic_private_detail": True}),
        SecurityEvent(user_id=owner.id, event_type="login_failed", occurred_at=now),
        SecurityEvent(user_id=viewer.id, event_type="login_succeeded", occurred_at=now),
    ])
    session.flush()
    session.add_all([
        LibraryStorageAllocation(user_id=owner.id, library_id=library_id, allocated_bytes=320),
        LibraryStorageAllocation(user_id=user_id, library_id=library_id, allocated_bytes=680),
        LibraryStorageAllocation(user_id=owner.id, library_id=inactive_library_id, allocated_bytes=900),
    ])
    session.commit()
    prepare(session, user_id)
    headers = open_session(browser)
    directory = "/api/v1/admin/accounts"

    first = browser.post(f"{directory}/list", headers=headers, json={}).json()
    assert len(first["accounts"]) == first["next_offset"] == 25
    assert [item["username"] for item in first["accounts"]] == [account.username for account in candidates]
    assert first["accounts"][0] == {
        "account_id": str(owner.id), "username": owner.username, "state": "suspended", "is_system_admin": False,
    }
    second = browser.post(f"{directory}/list", headers=headers, json={"offset": first["next_offset"]}).json()
    assert second == {"accounts": [{
        "account_id": str(user_id), "username": "test_operator", "state": "active", "is_system_admin": True,
    }], "next_offset": None}
    assert browser.post(f"{directory}/list", headers=headers, json={"offset": -1}).status_code == 422

    def detail(account_id):
        return browser.post(f"{directory}/detail", headers=headers, json={"account_id": str(account_id)})

    owner_detail = detail(owner.id).json()
    assert datetime.fromisoformat(owner_detail["last_successful_login_at"]) == last_success
    assert owner_detail == {
        **first["accounts"][0],
        "last_successful_login_at": owner_detail["last_successful_login_at"],
        "storage_used_bytes": 320 + calculate_account_data_bytes(session, owner.id),
        "storage_limit_bytes": 100_000_000,
    }
    assert detail(viewer.id).json()["storage_used_bytes"] == calculate_account_data_bytes(session, viewer.id) == 0
    missing = detail(candidates[2].id).json()
    assert missing["last_successful_login_at"] is missing["storage_used_bytes"] is missing["storage_limit_bytes"] is None
    assert detail(uuid4()).status_code == 404
    assert detail("invalid-id").status_code == 422

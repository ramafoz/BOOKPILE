import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import Popen
from threading import Thread
from time import monotonic, sleep

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.api.admin_page import PAGE_COOKIE, PAGE_PATH
from bookpile_server.config import get_settings
from bookpile_server.database import get_session
from bookpile_server.main import create_app
from bookpile_server.models import PlatformRole, User, UserSession
from bookpile_server.security.passwords import hash_password


ELIGIBILITY_PATH = "/internal/admin-page-eligibility"
LOGIN = {"identifier": "test_operator", "password": "disposable test password"}
SPA = "<html>Server SPA fixture</html>"


@pytest.fixture(params=["api", "caddy"])
def browser(request, session, monkeypatch, tmp_path):
    caddy = os.getenv("BOOKPILE_TEST_CADDY")
    through_edge = request.param == "caddy"
    if through_edge and not caddy:
        pytest.skip("Set BOOKPILE_TEST_CADDY to exercise the real Caddy route")

    with socket.socket() as upstream, socket.socket() as edge:
        if through_edge:
            upstream.bind(("127.0.0.1", 0))
            edge.bind(("127.0.0.1", 0))
            origin = f"https://127.0.0.1:{edge.getsockname()[1]}"
            edge.close()
        else:
            origin = "https://testserver"
        monkeypatch.setenv("BOOKPILE_SERVER_PUBLIC_BASE_URL", origin)
        monkeypatch.setenv("BOOKPILE_SERVER_ADMIN_WEBAUTHN_ENABLED", "true")
        monkeypatch.setenv("BOOKPILE_SERVER_SESSION_COOKIE_SECURE", "true")
        get_settings.cache_clear()
        try:
            app = create_app()

            def get_test_session():
                with Session(session.get_bind()) as db:
                    yield db

            app.dependency_overrides[get_session] = get_test_session
            if not through_edge:
                with TestClient(app, base_url=origin) as client:
                    yield client, ELIGIBILITY_PATH
                return

            web_root = tmp_path / "srv"
            web_root.mkdir()
            (web_root / "index.html").write_text(SPA, encoding="utf-8")
            source = Path(__file__).resolve().parents[1] / "docker" / "Caddyfile"
            config = source.read_text(encoding="utf-8").replace(
                "api:8100", f"127.0.0.1:{upstream.getsockname()[1]}"
            ).replace(
                "root * /srv", f'root * "{web_root.as_posix()}"'
            ).replace(
                "/data/access.log", f'"{(tmp_path / "access.log").as_posix()}"'
            ).replace(
                "/var/log/bookpile/defensive-events.log",
                f'"{(tmp_path / "defensive-events.log").as_posix()}"',
            ).replace(
                "admin off", "admin off\n\tauto_https disable_redirects\n\tskip_install_trust"
            ).replace("{$BOOKPILE_SITE_ADDRESS} {", "{$BOOKPILE_SITE_ADDRESS} {\n\ttls internal")
            caddyfile = tmp_path / "Caddyfile"
            caddyfile.write_text(config, encoding="utf-8")
            server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
            thread = Thread(target=server.run, kwargs={"sockets": [upstream]}, daemon=True)
            with (tmp_path / "caddy.log").open("wb") as log, Popen(
                [caddy, "run", "--config", str(caddyfile), "--adapter", "caddyfile"],
                stdout=log, stderr=log,
                env={
                    **os.environ,
                    "BOOKPILE_SITE_ADDRESS": origin,
                    "BOOKPILE_TLS_EMAIL": "fixture@example.invalid",
                    "BOOKPILE_DEPLOYMENT_REVISION": "test",
                    "XDG_DATA_HOME": str(tmp_path / "caddy-data"),
                    "XDG_CONFIG_HOME": str(tmp_path / "caddy-config"),
                },
            ) as proxy:
                thread.start()
                try:
                    # The edge creates an isolated CA for the loopback fixture.
                    with httpx.Client(
                        base_url=origin, verify=False, trust_env=False, timeout=30,
                    ) as client:
                        deadline = monotonic() + 10
                        while monotonic() < deadline and proxy.poll() is None:
                            try:
                                if server.started and client.get("/").status_code == 200:
                                    break
                            except httpx.TransportError:
                                pass
                            sleep(0.05)
                        else:
                            pytest.fail("Caddy or the disposable API did not start")
                        yield client, PAGE_PATH
                finally:
                    proxy.terminate()
                    server.should_exit = True
                    thread.join(timeout=5)
        finally:
            get_settings.cache_clear()


def test_admin_page_eligibility(browser, session, monkeypatch):
    client, path = browser
    through_edge = path == PAGE_PATH
    settings = get_settings()
    now = datetime.now(UTC)
    user = User(
        username=LOGIN["identifier"], email="operator@example.test",
        password_hash=hash_password(LOGIN["password"]), state="active",
        email_verified_at=now,
    )
    session.add(user)
    session.commit()

    def denied(**kwargs):
        response = client.get(path, **kwargs)
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
        assert "no-store" in response.headers["Cache-Control"]
        assert "location" not in response.headers

    denied()
    login = client.post("/api/v1/auth/login", json=LOGIN)
    assert login.status_code == 200
    jar = {cookie.name: cookie for cookie in client.cookies.jar}
    assert jar[settings.session_cookie_name].path == "/api/v1"
    page_cookie = jar[PAGE_COOKIE]
    assert page_cookie.path == PAGE_PATH and page_cookie.secure
    assert any(
        {"HttpOnly", "Secure", "Path=/admin-access", "SameSite=lax"} <= set(value.split("; ")[1:])
        for value in login.headers.get_list("set-cookie")
        if value.startswith(f"{PAGE_COOKIE}=")
    )
    denied(headers={"Cookie": f"{PAGE_COOKIE}={page_cookie.value}"})
    assert client.get("/api/v1/auth/me").status_code == 200

    role = PlatformRole(user_id=user.id, role="SYSTEM_ADMIN")
    session.add(role)
    session.commit()
    proof = f"{PAGE_COOKIE}={page_cookie.value}"
    if through_edge:
        page_cookies = client.build_request("GET", path).headers["Cookie"]
        api_cookies = client.build_request("GET", "/api/v1/auth/me").headers["Cookie"]
        assert {part.partition("=")[0] for part in page_cookies.split("; ")} == {
            PAGE_COOKIE, settings.csrf_cookie_name,
        }
        assert PAGE_COOKIE not in {part.partition("=")[0] for part in api_cookies.split("; ")}
        response = client.get(path)
        assert response.status_code == 200 and response.text == SPA
        assert response.headers["Cache-Control"] == "private, no-store"
        assert client.head(path).status_code == 200
        assert client.get(f"{path}/?entry=direct").status_code == 200
        assert client.get(ELIGIBILITY_PATH, headers={"Cookie": proof}).text == SPA
        denied(headers={"Cookie": ""})
        assert client.get(f"{path}/?entry=direct", headers={"Cookie": ""}).status_code == 404
    else:
        assert client.get(path, headers={"Cookie": proof}).status_code == 204

    denied(headers={"Cookie": f"{proof[:-1]}{'1' if proof.endswith('0') else '0'}"})
    # A proof for the page cannot act as an ordinary/API session.
    api_headers = {"Origin": settings.public_origin, "Cookie": proof}
    assert client.get("/api/v1/auth/me", headers=api_headers).status_code == 401
    assert client.post("/api/v1/admin/access/options", headers=api_headers).status_code == 401

    user.email_verified_at = None
    session.commit()
    denied(headers={"Cookie": proof})
    user.email_verified_at = now
    user.state = "suspended"
    session.commit()
    denied(headers={"Cookie": proof})
    user.state = "active"
    session.commit()

    ordinary_session = session.scalar(select(UserSession).where(UserSession.user_id == user.id))
    expires_at = ordinary_session.expires_at
    ordinary_session.expires_at = now - timedelta(seconds=1)
    session.commit()
    denied(headers={"Cookie": proof})
    ordinary_session.expires_at = expires_at
    session.commit()

    with monkeypatch.context() as disabled:
        disabled.setenv("BOOKPILE_SERVER_ADMIN_WEBAUTHN_ENABLED", "false")
        get_settings.cache_clear()
        denied(headers={"Cookie": proof})
    get_settings.cache_clear()

    session.delete(role)
    session.commit()
    denied(headers={"Cookie": proof})
    assert client.get("/api/v1/auth/me").status_code == 200

    session.add(PlatformRole(user_id=user.id, role="SYSTEM_ADMIN"))
    session.commit()
    csrf = client.cookies[settings.csrf_cookie_name]
    rotated = client.post("/api/v1/auth/session/rotate", headers={"X-CSRF-Token": csrf})
    assert rotated.status_code == 200
    denied(headers={"Cookie": proof})
    rotated_proof = f"{PAGE_COOKIE}={client.cookies[PAGE_COOKIE]}"
    assert client.get(path, headers={"Cookie": rotated_proof}).status_code == (200 if through_edge else 204)

    csrf = client.cookies[settings.csrf_cookie_name]
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert PAGE_COOKIE not in client.cookies
    denied(headers={"Cookie": rotated_proof})

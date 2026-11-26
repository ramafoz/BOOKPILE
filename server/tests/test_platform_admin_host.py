from pathlib import Path
import sys
from uuid import uuid4

import pytest

from bookpile_server.cli import platform_admin
from bookpile_server.email_delivery import EmailDeliveryError
from bookpile_server.platform_enrolment import EnrolmentRequest


@pytest.fixture
def request_to_enrol() -> EnrolmentRequest:
    return EnrolmentRequest("enrol", uuid4(), "operator-01", "bootstrap", uuid4())


@pytest.mark.parametrize(
    ("elapsed", "match", "expected"),
    [(599, True, True), (600, True, False), (1, False, False)],
)
def test_operator_code_is_bound_to_one_prompt_and_expires(
    monkeypatch, capsys, email_sender, request_to_enrol, elapsed, match, expected
) -> None:
    tested_code = "synthetic-mail-confirmation"
    times = iter([0, elapsed])
    monkeypatch.setattr(platform_admin, "token_urlsafe", lambda _size: tested_code)
    monkeypatch.setattr(platform_admin, "monotonic", lambda: next(times))

    def read_code(prompt):
        assert str(request_to_enrol.correlation_id) in prompt
        assert len(email_sender.emails) == 1
        return tested_code if match else "incorrect"

    monkeypatch.setattr(platform_admin, "getpass", read_code)
    assert platform_admin._confirm_by_email(
        request_to_enrol, "test", "operator@example.com", email_sender
    ) is expected
    email = email_sender.emails[0]
    assert email.recipient == "operator@example.com"
    assert tested_code in email.text
    assert str(request_to_enrol.target) not in email.text
    assert tested_code not in capsys.readouterr().out


def test_failed_delivery_cannot_fall_back_to_a_terminal_code(monkeypatch, request_to_enrol) -> None:
    class FailedSender:
        def send(self, _email):
            raise EmailDeliveryError("simulated failure")

    monkeypatch.setattr(platform_admin, "getpass", lambda _prompt: pytest.fail("prompt reached"))
    assert not platform_admin._confirm_by_email(
        request_to_enrol, "test", "operator@example.com", FailedSender()
    )


def test_command_requires_tty_and_exact_confirmation_before_connecting(
    monkeypatch, capsys
) -> None:
    target = uuid4()
    monkeypatch.setattr(
        sys, "argv",
        ["bookpile-platform-admin", "revoke", str(target),
         "--operator", "operator-01", "--reason", "access-retirement"],
    )
    monkeypatch.setattr(platform_admin, "create_engine", lambda *_args, **_kw: pytest.fail("connected"))
    with monkeypatch.context() as tty:
        tty.setattr(sys.stdin, "isatty", lambda: False)
        assert platform_admin.main() == 1
        assert "interactive terminal" in capsys.readouterr().err

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setenv("BOOKPILE_PLATFORM_ADMIN_ENVIRONMENT", "test")
    monkeypatch.setenv(
        "BOOKPILE_PLATFORM_ADMIN_DATABASE_URL", "postgresql://localhost/bookpile_test"
    )
    monkeypatch.setenv("BOOKPILE_PLATFORM_ADMIN_OPERATOR_EMAIL", "operator@example.com")
    monkeypatch.setenv("BOOKPILE_SERVER_SMTP_STARTTLS", "true")
    monkeypatch.setenv("BOOKPILE_SERVER_SMTP_USERNAME", "synthetic-sender")
    monkeypatch.setenv("BOOKPILE_SERVER_SMTP_PASSWORD", "synthetic-secret")
    monkeypatch.setattr("builtins.input", lambda prompt: f"revoke {target}")
    assert platform_admin.main() == 1
    assert "Typed confirmation did not match" in capsys.readouterr().err


def test_compose_host_command_is_only_an_explicit_one_shot_service() -> None:
    server = Path(__file__).resolve().parents[1]
    compose = (server / "compose.production.yaml").read_text(encoding="utf-8")
    before, service = compose.split("  platform-admin:\n", 1)
    service, after = service.split("  admin-audit:\n", 1)
    for variable in ("BOOKPILE_PLATFORM_ADMIN_DATABASE_URL", "BOOKPILE_PLATFORM_ADMIN_ENV_FILE"):
        assert variable in service
        assert variable not in before + after
    assert 'profiles: ["platform-administration"]' in service
    assert 'entrypoint: ["bookpile-platform-admin"]' in service
    assert 'command: ["--help"]' in service
    assert 'driver: "none"' in service

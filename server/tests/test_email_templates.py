import pytest

from bookpile_server.email_templates import (
    account_recovery_email,
    password_reset_email,
    resolve_email_locale,
    verification_email,
)


@pytest.mark.parametrize(
    ("renderer", "subject", "label", "expiry"),
    (
        (verification_email, "BOOKPILE: Verify your email", "Verify email", "24 hours"),
        (password_reset_email, "BOOKPILE: Reset your password", "Choose a new password", "30 minutes"),
        (account_recovery_email, "BOOKPILE: Recover your account", "Recover account", "48 hours"),
    ),
)
def test_transactional_templates_have_equivalent_private_text_and_html(
    renderer, subject: str, label: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"

    rendered = renderer(url)

    assert rendered.subject == subject
    assert rendered.subject.isascii()
    assert label in rendered.text
    assert label in rendered.html
    assert expiry in rendered.text
    assert expiry in rendered.html
    assert url in rendered.text
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert "BOOKPILE" in rendered.text and "BOOKPILE" in rendered.html
    assert "does not load external content" in rendered.html
    assert "<img" not in rendered.html
    assert "src=\"http" not in rendered.html
    assert "display:none" not in rendered.html
    assert "opacity:0" not in rendered.html
    assert "visibility:hidden" not in rendered.html
    assert "font-size:0" not in rendered.html
    assert "#173d35" in rendered.html


def test_template_escapes_action_url_in_html_but_preserves_plain_text() -> None:
    url = 'https://bookpile.test/action?token=<private>&next="quoted"'

    rendered = verification_email(url)

    assert url in rendered.text
    assert "token=&lt;private&gt;&amp;next=&quot;quoted&quot;" in rendered.html
    assert url not in rendered.html


@pytest.mark.parametrize(
    ("renderer", "subject", "expiry"),
    (
        (verification_email, "BOOKPILE: Verifica o teu correo", "24 horas"),
        (password_reset_email, "BOOKPILE: Restablece o contrasinal", "30 minutos"),
        (account_recovery_email, "BOOKPILE: Recupera a túa conta", "48 horas"),
    ),
)
def test_galician_transactional_templates_are_complete_and_private(
    renderer, subject: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"
    rendered = renderer(url, locale="gl")
    assert rendered.subject == subject
    assert expiry in rendered.text and expiry in rendered.html
    assert '<html lang="gl">' in rendered.html
    assert "Non carga contido externo" in rendered.html
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert url in rendered.text
    assert "Your personal library" not in rendered.text + rendered.html
    assert "does not load external content" not in rendered.html


def test_email_locale_falls_back_safely_for_untranslated_languages() -> None:
    assert resolve_email_locale("gl") == "gl"
    assert resolve_email_locale("pt") == "en"

import pytest

from bookpile_server.email_templates import (
    account_recovery_email,
    password_reset_email,
    verification_email,
)


@pytest.mark.parametrize(
    ("renderer", "subject", "label", "expiry"),
    (
        (verification_email, "BOOKPILE — Verify your email", "Verify email", "24 hours"),
        (password_reset_email, "BOOKPILE — Reset your password", "Choose a new password", "30 minutes"),
        (account_recovery_email, "BOOKPILE — Recover your account", "Recover account", "48 hours"),
    ),
)
def test_transactional_templates_have_equivalent_private_text_and_html(
    renderer, subject: str, label: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"

    rendered = renderer(url)

    assert rendered.subject == subject
    assert label in rendered.text
    assert label in rendered.html
    assert expiry in rendered.text
    assert expiry in rendered.html
    assert url in rendered.text
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert "BOOKPILE" in rendered.text and "BOOKPILE" in rendered.html
    assert "tracking pixels" in rendered.html
    assert "<img" not in rendered.html
    assert "src=\"http" not in rendered.html
    assert "#173d35" in rendered.html


def test_template_escapes_action_url_in_html_but_preserves_plain_text() -> None:
    url = 'https://bookpile.test/action?token=<private>&next="quoted"'

    rendered = verification_email(url)

    assert url in rendered.text
    assert "token=&lt;private&gt;&amp;next=&quot;quoted&quot;" in rendered.html
    assert url not in rendered.html

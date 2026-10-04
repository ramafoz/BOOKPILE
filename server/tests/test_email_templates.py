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


@pytest.mark.parametrize(
    ("renderer", "subject", "expiry"),
    (
        (verification_email, "BOOKPILE: Verifica tu correo", "24 horas"),
        (password_reset_email, "BOOKPILE: Restablece tu contraseña", "30 minutos"),
        (account_recovery_email, "BOOKPILE: Recupera tu cuenta", "48 horas"),
    ),
)
def test_prepared_spanish_transactional_templates_are_complete_and_private(
    renderer, subject: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"
    rendered = renderer(url, locale="es")
    assert rendered.subject == subject
    assert expiry in rendered.text and expiry in rendered.html
    assert '<html lang="es">' in rendered.html
    assert "No carga contenido externo" in rendered.html
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert url in rendered.text
    assert "Your personal library" not in rendered.text + rendered.html
    assert "does not load external content" not in rendered.html


@pytest.mark.parametrize(
    ("renderer", "subject", "expiry"),
    (
        (verification_email, "BOOKPILE: Verifique o seu correio eletrónico", "24 horas"),
        (password_reset_email, "BOOKPILE: Redefina a sua palavra-passe", "30 minutos"),
        (account_recovery_email, "BOOKPILE: Recupere a sua conta", "48 horas"),
    ),
)
def test_portuguese_transactional_templates_are_complete_and_private(
    renderer, subject: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"
    rendered = renderer(url, locale="pt")
    assert rendered.subject == subject
    assert expiry in rendered.text and expiry in rendered.html
    assert '<html lang="pt">' in rendered.html
    assert "Não carrega conteúdo externo" in rendered.html
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert url in rendered.text
    assert "Your personal library" not in rendered.text + rendered.html
    assert "does not load external content" not in rendered.html


@pytest.mark.parametrize(
    ("renderer", "subject", "expiry"),
    (
        (verification_email, "BOOKPILE: Verifica el teu correu", "24 hores"),
        (password_reset_email, "BOOKPILE: Restableix la contrasenya", "30 minuts"),
        (account_recovery_email, "BOOKPILE: Recupera el teu compte", "48 hores"),
    ),
)
def test_prepared_catalan_transactional_templates_are_complete_and_private(
    renderer, subject: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"
    rendered = renderer(url, locale="ca")
    assert rendered.subject == subject
    assert expiry in rendered.text and expiry in rendered.html
    assert '<html lang="ca">' in rendered.html
    assert "No carrega contingut extern" in rendered.html
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert url in rendered.text
    assert "Your personal library" not in rendered.text + rendered.html
    assert "does not load external content" not in rendered.html


@pytest.mark.parametrize(
    ("renderer", "subject", "expiry"),
    (
        (verification_email, "BOOKPILE: Verifica il tuo indirizzo email", "24 ore"),
        (password_reset_email, "BOOKPILE: Reimposta la password", "30 minuti"),
        (account_recovery_email, "BOOKPILE: Recupera il tuo account", "48 ore"),
    ),
)
def test_italian_transactional_templates_are_complete_and_private(
    renderer, subject: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"
    rendered = renderer(url, locale="it")
    assert rendered.subject == subject
    assert expiry in rendered.text and expiry in rendered.html
    assert '<html lang="it">' in rendered.html
    assert "Non carica contenuti esterni" in rendered.html
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert url in rendered.text
    assert "Your personal library" not in rendered.text + rendered.html
    assert "does not load external content" not in rendered.html


@pytest.mark.parametrize(
    ("renderer", "subject", "expiry"),
    (
        (verification_email, "BOOKPILE : vérifiez votre adresse e-mail", "24 heures"),
        (password_reset_email, "BOOKPILE : réinitialisez votre mot de passe", "30 minutes"),
        (account_recovery_email, "BOOKPILE : récupérez votre compte", "48 heures"),
    ),
)
def test_french_transactional_templates_are_complete_and_private(
    renderer, subject: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"
    rendered = renderer(url, locale="fr")
    assert rendered.subject == subject
    assert expiry in rendered.text and expiry in rendered.html
    assert '<html lang="fr">' in rendered.html
    assert "Il ne charge aucun contenu externe" in rendered.html
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert url in rendered.text
    assert "Your personal library" not in rendered.text + rendered.html
    assert "does not load external content" not in rendered.html


@pytest.mark.parametrize(
    ("renderer", "subject", "expiry"),
    (
        (verification_email, "BOOKPILE: egiaztatu zure helbide elektronikoa", "24 ordura"),
        (password_reset_email, "BOOKPILE: berrezarri pasahitza", "30 minutura"),
        (account_recovery_email, "BOOKPILE: berreskuratu zure kontua", "48 ordura"),
    ),
)
def test_basque_transactional_templates_are_complete_and_private(
    renderer, subject: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"
    rendered = renderer(url, locale="eu")
    assert rendered.subject == subject
    assert expiry in rendered.text and expiry in rendered.html
    assert '<html lang="eu">' in rendered.html
    assert "Ez du kanpoko edukirik kargatzen" in rendered.html
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert url in rendered.text
    assert "Your personal library" not in rendered.text + rendered.html
    assert "does not load external content" not in rendered.html


@pytest.mark.parametrize(
    ("renderer", "subject", "expiry"),
    (
        (verification_email, "BOOKPILE: verifica era tua adreça de corrèu", "24 ores"),
        (password_reset_email, "BOOKPILE: restablís eth tòn senhal", "30 minutes"),
        (account_recovery_email, "BOOKPILE: recupèra eth tòn compde", "48 ores"),
    ),
)
def test_aranese_transactional_templates_are_complete_and_private(
    renderer, subject: str, expiry: str
) -> None:
    url = "https://staging.bookpile.gal/action?token=secret-token&next=%2F"
    rendered = renderer(url, locale="oc")
    assert rendered.subject == subject
    assert expiry in rendered.text and expiry in rendered.html
    assert '<html lang="oc">' in rendered.html
    assert "Non cargue contengut extèrne" in rendered.html
    assert "token=secret-token&amp;next=%2F" in rendered.html
    assert url in rendered.text
    assert "Your personal library" not in rendered.text + rendered.html
    assert "does not load external content" not in rendered.html


def test_email_locale_falls_back_safely_for_untranslated_languages() -> None:
    assert resolve_email_locale("gl") == "gl"
    assert resolve_email_locale("es") == "es"
    assert resolve_email_locale("pt") == "pt"
    assert resolve_email_locale("ca") == "ca"
    assert resolve_email_locale("it") == "it"
    assert resolve_email_locale("fr") == "fr"
    assert resolve_email_locale("eu") == "eu"
    assert resolve_email_locale("oc") == "oc"
    assert resolve_email_locale("de") == "en"

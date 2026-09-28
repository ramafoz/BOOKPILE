"""Privacy-safe transactional email presentation shared by every account flow."""

from dataclasses import dataclass
from html import escape
from typing import Literal


EmailLocale = Literal["en", "gl"]


def resolve_email_locale(preferred_locale: str) -> EmailLocale:
    return "gl" if preferred_locale == "gl" else "en"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


@dataclass(frozen=True)
class EmailCopy:
    subject: str
    eyebrow: str
    heading: str
    introduction: str
    action_label: str
    expiry: str
    fallback: str
    closing: str


_SHARED_COPY = {
    "en": {
        "tagline": "Your personal library, securely mapped.",
        "footer": "This automated service message was sent in response to a BOOKPILE account action. It does not load external content.",
        "fallback": "If the button does not work, copy and paste this address into your browser:",
    },
    "gl": {
        "tagline": "A túa biblioteca persoal, situada con seguridade.",
        "footer": "Esta mensaxe automática enviouse por unha acción na túa conta de BOOKPILE. Non carga contido externo.",
        "fallback": "Se o botón non funciona, copia e pega este enderezo no navegador:",
    },
}


_EMAIL_COPY: dict[str, dict[EmailLocale, EmailCopy]] = {
    "verification": {
        "en": EmailCopy(
            "BOOKPILE: Verify your email", "One last step", "Verify your email",
            "Confirm that this email address belongs to you to activate your BOOKPILE account.",
            "Verify email", "This single-use link expires 24 hours after the message is delivered.",
            _SHARED_COPY["en"]["fallback"],
            "If you did not create a BOOKPILE account, you can safely ignore this message.",
        ),
        "gl": EmailCopy(
            "BOOKPILE: Verifica o teu correo", "Un último paso", "Verifica o teu correo",
            "Confirma que este enderezo de correo é teu para activar a conta de BOOKPILE.",
            "Verificar o correo", "Esta ligazón dun só uso caduca 24 horas despois da entrega da mensaxe.",
            _SHARED_COPY["gl"]["fallback"],
            "Se non creaches unha conta de BOOKPILE, podes ignorar esta mensaxe.",
        ),
    },
    "password_reset": {
        "en": EmailCopy(
            "BOOKPILE: Reset your password", "Account security", "Reset your password",
            "A password reset was requested for your BOOKPILE account.",
            "Choose a new password", "This single-use link expires 30 minutes after the message is delivered.",
            _SHARED_COPY["en"]["fallback"],
            "If you did not request a password reset, ignore this message. Your password has not changed.",
        ),
        "gl": EmailCopy(
            "BOOKPILE: Restablece o contrasinal", "Seguridade da conta", "Restablece o contrasinal",
            "Solicitouse restablecer o contrasinal da túa conta de BOOKPILE.",
            "Escoller outro contrasinal", "Esta ligazón dun só uso caduca 30 minutos despois da entrega da mensaxe.",
            _SHARED_COPY["gl"]["fallback"],
            "Se non solicitaches restablecer o contrasinal, ignora esta mensaxe. O teu contrasinal non cambiou.",
        ),
    },
    "account_recovery": {
        "en": EmailCopy(
            "BOOKPILE: Recover your account", "Account recovery", "Recover your account",
            "Your BOOKPILE account is scheduled for permanent deletion.",
            "Recover account", "This single-use recovery link expires 48 hours after the message is delivered.",
            _SHARED_COPY["en"]["fallback"],
            "If you intended to delete the account, no action is required. Its remaining personal data will be removed after the recovery window closes.",
        ),
        "gl": EmailCopy(
            "BOOKPILE: Recupera a túa conta", "Recuperación da conta", "Recupera a túa conta",
            "A túa conta de BOOKPILE está programada para a eliminación definitiva.",
            "Recuperar a conta", "Esta ligazón de recuperación dun só uso caduca 48 horas despois da entrega da mensaxe.",
            _SHARED_COPY["gl"]["fallback"],
            "Se querías eliminar a conta, non tes que facer nada. Os datos persoais restantes eliminaranse ao rematar o prazo de recuperación.",
        ),
    },
}


def _render(
    *,
    locale: EmailLocale,
    subject: str,
    eyebrow: str,
    heading: str,
    introduction: str,
    action_label: str,
    action_url: str,
    expiry: str,
    fallback: str,
    closing: str,
) -> RenderedEmail:
    shared = _SHARED_COPY[locale]
    text = (
        f"{heading}\n\n"
        f"{introduction}\n\n"
        f"{action_label}:\n{action_url}\n\n"
        f"{expiry}\n\n"
        f"{closing}\n\n"
        "BOOKPILE\n"
        f"{shared['tagline']}"
    )
    safe_url = escape(action_url, quote=True)
    html = f"""<!doctype html>
<html lang="{locale}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>{escape(subject)}</title>
  </head>
  <body style="margin:0;padding:0;background:#f5f0e7;color:#1d2c28;font-family:Arial,Helvetica,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f5f0e7;">
      <tr>
        <td align="center" style="padding:32px 16px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;background:#fffaf3;border:1px solid #ded2c1;border-radius:16px;overflow:hidden;box-shadow:0 12px 36px rgba(23,61,53,.10);">
            <tr>
              <td style="padding:24px 32px;background:#173d35;color:#f7f1e6;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td width="44" height="44" align="center" valign="middle" style="border:1px solid #d6ab67;border-radius:50%;">
                      <table role="presentation" cellspacing="2" cellpadding="0" border="0" aria-hidden="true">
                        <tr>
                          <td width="3" height="19" style="background:#d6ab67;border-radius:1px;"></td>
                          <td width="3" height="19" style="background:#f7f1e6;border-radius:1px;"></td>
                          <td width="3" height="19" style="background:#a85835;border-radius:1px;"></td>
                        </tr>
                      </table>
                    </td>
                    <td style="padding-left:14px;font-size:17px;font-weight:700;letter-spacing:.16em;">BOOKPILE</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:38px 32px 18px;">
                <p style="margin:0 0 10px;color:#a85835;font-size:12px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;">{escape(eyebrow)}</p>
                <h1 style="margin:0 0 18px;color:#173d35;font-family:Georgia,'Times New Roman',serif;font-size:34px;line-height:1.15;">{escape(heading)}</h1>
                <p style="margin:0;color:#40514b;font-size:16px;line-height:1.65;">{escape(introduction)}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:14px 32px 22px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="border-radius:8px;background:#28574d;">
                      <a href="{safe_url}" style="display:inline-block;padding:14px 22px;color:#ffffff;font-size:16px;font-weight:700;text-decoration:none;">{escape(action_label)}</a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 34px;">
                <p style="margin:0 0 18px;padding:14px 16px;border-left:3px solid #d6ab67;background:#f7ebd5;color:#5f513d;font-size:14px;line-height:1.55;">{escape(expiry)}</p>
                <p style="margin:0 0 8px;color:#65716d;font-size:13px;line-height:1.55;">{escape(fallback)}</p>
                <p style="margin:0;word-break:break-all;color:#6c5143;font-size:12px;line-height:1.5;">{safe_url}</p>
                <p style="margin:22px 0 0;color:#65716d;font-size:13px;line-height:1.55;">{escape(closing)}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;border-top:1px solid #e5dacb;background:#f8f3ea;color:#6f7875;font-size:12px;line-height:1.5;">
                {escape(shared['footer'])}<br>
                BOOKPILE · {escape(shared['tagline'])}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return RenderedEmail(subject=subject, text=text, html=html)


def _account_email(kind: str, action_url: str, locale: EmailLocale) -> RenderedEmail:
    copy = _EMAIL_COPY[kind][locale]
    return _render(
        locale=locale,
        subject=copy.subject,
        eyebrow=copy.eyebrow,
        heading=copy.heading,
        introduction=copy.introduction,
        action_label=copy.action_label,
        action_url=action_url,
        expiry=copy.expiry,
        fallback=copy.fallback,
        closing=copy.closing,
    )


def verification_email(action_url: str, locale: EmailLocale = "en") -> RenderedEmail:
    return _account_email("verification", action_url, locale)


def password_reset_email(action_url: str, locale: EmailLocale = "en") -> RenderedEmail:
    return _account_email("password_reset", action_url, locale)


def account_recovery_email(action_url: str, locale: EmailLocale = "en") -> RenderedEmail:
    return _account_email("account_recovery", action_url, locale)

"""Privacy-safe transactional email presentation shared by every account flow."""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


def _render(
    *,
    subject: str,
    preheader: str,
    eyebrow: str,
    heading: str,
    introduction: str,
    action_label: str,
    action_url: str,
    expiry: str,
    fallback: str,
    closing: str,
) -> RenderedEmail:
    text = (
        f"{heading}\n\n"
        f"{introduction}\n\n"
        f"{action_label}:\n{action_url}\n\n"
        f"{expiry}\n\n"
        f"{closing}\n\n"
        "BOOKPILE\n"
        "Your personal library, securely mapped."
    )
    safe_url = escape(action_url, quote=True)
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>{escape(subject)}</title>
  </head>
  <body style="margin:0;padding:0;background:#f5f0e7;color:#1d2c28;font-family:Arial,Helvetica,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{escape(preheader)}</div>
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
                This automated message contains no tracking pixels or remote images.<br>
                BOOKPILE · Your personal library, securely mapped.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return RenderedEmail(subject=subject, text=text, html=html)


def verification_email(action_url: str) -> RenderedEmail:
    return _render(
        subject="BOOKPILE — Verify your email",
        preheader="Confirm your email address to activate your BOOKPILE account.",
        eyebrow="One last step",
        heading="Verify your email",
        introduction="Confirm that this email address belongs to you to activate your BOOKPILE account.",
        action_label="Verify email",
        action_url=action_url,
        expiry="This single-use link expires 24 hours after the message is delivered.",
        fallback="If the button does not work, copy and paste this address into your browser:",
        closing="If you did not create a BOOKPILE account, you can safely ignore this message.",
    )


def password_reset_email(action_url: str) -> RenderedEmail:
    return _render(
        subject="BOOKPILE — Reset your password",
        preheader="Use this secure link to choose a new BOOKPILE password.",
        eyebrow="Account security",
        heading="Reset your password",
        introduction="A password reset was requested for your BOOKPILE account.",
        action_label="Choose a new password",
        action_url=action_url,
        expiry="This single-use link expires 30 minutes after the message is delivered.",
        fallback="If the button does not work, copy and paste this address into your browser:",
        closing="If you did not request a password reset, ignore this message. Your password has not changed.",
    )


def account_recovery_email(action_url: str) -> RenderedEmail:
    return _render(
        subject="BOOKPILE — Recover your account",
        preheader="Your BOOKPILE account can still be recovered for 48 hours.",
        eyebrow="Account recovery",
        heading="Recover your account",
        introduction="Your BOOKPILE account is scheduled for permanent deletion.",
        action_label="Recover account",
        action_url=action_url,
        expiry="This single-use recovery link expires 48 hours after the message is delivered.",
        fallback="If the button does not work, copy and paste this address into your browser:",
        closing="If you intended to delete the account, no action is required. Its remaining personal data will be removed after the recovery window closes.",
    )

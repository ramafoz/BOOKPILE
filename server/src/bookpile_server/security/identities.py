import re

from email_validator import EmailNotValidError, validate_email


USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,30}$", re.ASCII)
RESERVED_USERNAMES = frozenset(
    {
        "admin",
        "administrator",
        "bookpile",
        "moderator",
        "rama",
        "ramafoz",
        "root",
        "security",
        "support",
        "system",
    }
)


class IdentityValidationError(ValueError):
    pass


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise IdentityValidationError(
            "Username must contain 3 to 30 ASCII letters, numbers, or underscores."
        )
    if normalized in RESERVED_USERNAMES:
        raise IdentityValidationError("This username is reserved.")
    return normalized


def normalize_email(email: str) -> str:
    try:
        normalized = validate_email(
            email.strip(), check_deliverability=False
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise IdentityValidationError("Enter a valid email address.") from exc
    if len(normalized) > 320:
        raise IdentityValidationError("Enter a valid email address.")
    return normalized

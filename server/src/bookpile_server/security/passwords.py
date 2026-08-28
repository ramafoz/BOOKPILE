from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()
_dummy_hash = _hasher.hash("bookpile-dummy-password-never-used")


class PasswordPolicyError(ValueError):
    pass


def validate_new_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must contain {MIN_PASSWORD_LENGTH} to "
            f"{MAX_PASSWORD_LENGTH} characters."
        )


def hash_password(password: str) -> str:
    validate_new_password(password)
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Verify a password while doing comparable work for unknown users."""

    candidate_hash = password_hash or _dummy_hash
    try:
        verified = _hasher.verify(candidate_hash, password)
    except (InvalidHashError, VerificationError):
        return False
    return bool(password_hash) and verified


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)

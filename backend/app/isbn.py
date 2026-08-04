import re


class InvalidISBN(ValueError):
    """Raised when an ISBN cannot be normalized and validated."""


ISBN_PREFIX = re.compile(r"^ISBN(?:-1[03])?\s*:?\s*", re.IGNORECASE)
ISBN_SEPARATORS = re.compile(r"[\s\-\u2010-\u2015]+")


def normalize_isbn(value: str) -> str:
    """Return a valid ISBN-10 or ISBN-13 without display separators."""

    if not isinstance(value, str):
        raise InvalidISBN("ISBN must be text")

    normalized = ISBN_PREFIX.sub("", value.strip()).upper()
    normalized = ISBN_SEPARATORS.sub("", normalized)

    if len(normalized) == 10:
        if not re.fullmatch(r"\d{9}[\dX]", normalized):
            raise InvalidISBN("ISBN-10 must contain nine digits and a digit or X")
        if not _has_valid_isbn_10_checksum(normalized):
            raise InvalidISBN("ISBN-10 checksum is invalid")
        return normalized

    if len(normalized) == 13:
        if not normalized.isdigit():
            raise InvalidISBN("ISBN-13 must contain thirteen digits")
        if not normalized.startswith(("978", "979")):
            raise InvalidISBN("The code is not an ISBN-13 book prefix")
        if not _has_valid_isbn_13_checksum(normalized):
            raise InvalidISBN("ISBN-13 checksum is invalid")
        return normalized

    raise InvalidISBN("ISBN must contain 10 or 13 characters")


def is_valid_isbn(value: str) -> bool:
    """Return whether a value can be normalized as a valid book ISBN."""

    try:
        normalize_isbn(value)
    except InvalidISBN:
        return False
    return True


def _has_valid_isbn_10_checksum(isbn: str) -> bool:
    values = [int(character) for character in isbn[:9]]
    values.append(10 if isbn[-1] == "X" else int(isbn[-1]))
    return sum(weight * value for weight, value in zip(range(10, 0, -1), values)) % 11 == 0


def _has_valid_isbn_13_checksum(isbn: str) -> bool:
    weighted_sum = sum(
        int(character) * (1 if index % 2 == 0 else 3)
        for index, character in enumerate(isbn[:12])
    )
    expected_check_digit = (10 - weighted_sum % 10) % 10
    return expected_check_digit == int(isbn[-1])

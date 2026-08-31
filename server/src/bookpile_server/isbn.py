import re


class InvalidISBN(ValueError):
    """Raised when an ISBN cannot be normalized and validated."""


ISBN_PREFIX = re.compile(r"^ISBN(?:-1[03])?\s*:?\s*", re.IGNORECASE)
ISBN_SEPARATORS = re.compile(r"[\s\-\u2010-\u2015]+")


def normalize_isbn(value: str) -> str:
    normalized = ISBN_PREFIX.sub("", value.strip()).upper()
    normalized = ISBN_SEPARATORS.sub("", normalized)
    if len(normalized) == 10:
        if not re.fullmatch(r"\d{9}[\dX]", normalized):
            raise InvalidISBN("ISBN-10 must contain nine digits and a digit or X")
        values = [int(character) for character in normalized[:9]]
        values.append(10 if normalized[-1] == "X" else int(normalized[-1]))
        if sum(weight * item for weight, item in zip(range(10, 0, -1), values)) % 11:
            raise InvalidISBN("ISBN-10 checksum is invalid")
        return normalized
    if len(normalized) == 13:
        if not normalized.isdigit():
            raise InvalidISBN("ISBN-13 must contain thirteen digits")
        if not normalized.startswith(("978", "979")):
            raise InvalidISBN("The code is not an ISBN-13 book prefix")
        weighted = sum(
            int(character) * (1 if index % 2 == 0 else 3)
            for index, character in enumerate(normalized[:12])
        )
        if (10 - weighted % 10) % 10 != int(normalized[-1]):
            raise InvalidISBN("ISBN-13 checksum is invalid")
        return normalized
    raise InvalidISBN("ISBN must contain 10 or 13 characters")

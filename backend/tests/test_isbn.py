import pytest

from app.isbn import (
    InvalidISBN,
    equivalent_isbns,
    is_valid_isbn,
    isbn_10_to_isbn_13,
    normalize_isbn,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0-306-40615-2", "0306406152"),
        ("978-0-306-40615-7", "9780306406157"),
        ("0-8044-2957-X", "080442957X"),
        ("isbn 0 8044 2957 x", "080442957X"),
        ("ISBN-13: 978 0 306 40615 7", "9780306406157"),
        ("978\u20110\u2011306\u201140615\u20117", "9780306406157"),
    ],
)
def test_normalize_isbn_accepts_valid_display_formats(
    value: str, expected: str
) -> None:
    assert normalize_isbn(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "10 or 13"),
        ("123456789", "10 or 13"),
        ("0-306-40615-3", "checksum"),
        ("978-0-306-40615-8", "checksum"),
        ("0-8044-295X-7", "nine digits"),
        ("97803064061X7", "thirteen digits"),
        ("4006381333931", "book prefix"),
    ],
)
def test_normalize_isbn_rejects_invalid_values(value: str, message: str) -> None:
    with pytest.raises(InvalidISBN, match=message):
        normalize_isbn(value)


def test_normalize_isbn_requires_text() -> None:
    with pytest.raises(InvalidISBN, match="must be text"):
        normalize_isbn(9780306406157)  # type: ignore[arg-type]


def test_is_valid_isbn_returns_a_boolean() -> None:
    assert is_valid_isbn("9780306406157") is True
    assert is_valid_isbn("9780306406158") is False


def test_isbn_10_and_isbn_13_equivalence() -> None:
    assert isbn_10_to_isbn_13("0-306-40615-2") == "9780306406157"
    assert equivalent_isbns("0306406152") == {
        "0306406152",
        "9780306406157",
    }

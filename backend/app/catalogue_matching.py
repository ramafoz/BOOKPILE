import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from .database import connect
from .isbn import equivalent_isbns


MATCHABLE_BOOKS = """
SELECT
    b.id,
    b.title,
    b.author,
    b.isbn_10,
    b.isbn_13,
    b.status,
    b.cover_filename,
    bc.name AS bookcase_name,
    s.shelf_number,
    c.container_type,
    c.layer,
    c.container_number,
    b.position
FROM books b
LEFT JOIN containers c ON c.id = b.container_id
LEFT JOIN shelves s ON s.id = c.shelf_id
LEFT JOIN bookcases bc ON bc.id = s.bookcase_id
ORDER BY b.title COLLATE NOCASE, b.author COLLATE NOCASE
"""


def add_catalogue_matches(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach read-only Title/Author catalogue matches to lookup candidates."""

    with connect() as connection:
        books = [dict(row) for row in connection.execute(MATCHABLE_BOOKS)]

    return [
        {
            **candidate,
            "catalogue_matches": match_candidate(candidate, books),
        }
        for candidate in candidates
    ]


def find_catalogue_matches(title: str, authors: list[str]) -> list[dict[str, Any]]:
    """Find current-catalogue matches for user-reviewed bibliographic text."""

    with connect() as connection:
        books = [dict(row) for row in connection.execute(MATCHABLE_BOOKS)]
    return match_candidate({"title": title, "authors": authors}, books)


def find_isbn_catalogue_matches(isbn: str) -> list[dict[str, Any]]:
    """Find exact local matches without depending on metadata providers."""

    with connect() as connection:
        books = [dict(row) for row in connection.execute(MATCHABLE_BOOKS)]
    identifier_key = f"isbn_{len(isbn)}"
    return match_candidate(
        {
            "title": "",
            "authors": [],
            "identifiers": {identifier_key: isbn},
        },
        books,
    )


def match_candidate(
    candidate: dict[str, Any],
    books: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate_title = comparison_text(candidate.get("title"))
    candidate_authors = [
        comparison_text(author)
        for author in candidate.get("authors", [])
        if comparison_text(author)
    ]
    candidate_isbns = equivalent_isbns(
        candidate.get("identifiers", {}).get("isbn_10"),
        candidate.get("identifiers", {}).get("isbn_13"),
    )
    matches = []

    for book in books:
        book_title = comparison_text(book.get("title"))
        book_author = comparison_text(book.get("author"))
        title_similarity = SequenceMatcher(None, candidate_title, book_title).ratio()
        authors_overlap = any(
            author_text_matches(author, book_author)
            for author in candidate_authors
        )
        book_isbns = equivalent_isbns(book.get("isbn_10"), book.get("isbn_13"))

        if candidate_isbns & book_isbns:
            match_class = "strong"
            reason = "Exact ISBN already stored in BOOKPILE"
        elif candidate_title == book_title and authors_overlap:
            match_class = "strong"
            reason = "Same normalized title and matching author text"
        elif candidate_title == book_title:
            match_class = "possible"
            reason = "Same normalized title; author text differs"
        elif title_similarity >= 0.88 and authors_overlap:
            match_class = "possible"
            reason = "Very similar title and matching author text"
        else:
            continue

        matches.append(
            {
                "book_id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "status": book["status"],
                "cover_filename": book.get("cover_filename"),
                "location_label": location_label(book),
                "match_class": match_class,
                "reason": reason,
            }
        )

    return sorted(
        matches,
        key=lambda match: (
            0 if match["match_class"] == "strong" else 1,
            comparison_text(match["title"]),
            comparison_text(match["author"]),
        ),
    )[:5]


def comparison_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^\w]+", " ", without_marks).split())


def author_text_matches(candidate_author: str, book_author: str) -> bool:
    if (
        candidate_author == book_author
        or candidate_author in book_author
        or book_author in candidate_author
    ):
        return True
    candidate_tokens = set(candidate_author.split())
    book_tokens = set(book_author.split())
    shared_tokens = candidate_tokens & book_tokens
    return (
        len(shared_tokens) >= 2
        and bool(candidate_tokens)
        and bool(book_tokens)
        and candidate_author.split()[-1] == book_author.split()[-1]
    )


def location_label(book: dict[str, Any]) -> str | None:
    if book.get("bookcase_name") is None:
        return None
    return (
        f'{book["bookcase_name"]} · Shelf {book["shelf_number"]} · '
        f'{str(book["layer"]).title()} {str(book["container_type"]).title()} '
        f'{book["container_number"]} · Position {book["position"]}'
    )

from collections.abc import Iterable
import os
from typing import Any

import httpx

from .isbn import InvalidISBN, normalize_isbn


OPEN_LIBRARY_ISBN_URL = "https://openlibrary.org/isbn/{isbn}.json"
GOOGLE_BOOKS_VOLUMES_URL = "https://www.googleapis.com/books/v1/volumes"
LOOKUP_TIMEOUT_SECONDS = 10.0


class BibliographicProvidersUnavailable(RuntimeError):
    """Raised when every configured provider fails to return a valid response."""


def lookup_isbn(
    value: str,
    *,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Look up a validated ISBN and return normalized bibliographic candidates."""

    isbn = normalize_isbn(value)
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=LOOKUP_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "BOOKPILE/1.0 (personal library manager)"},
        )

    failures: list[str] = []
    successful_providers = 0
    try:
        try:
            candidates = _lookup_open_library_isbn(client, isbn)
            successful_providers += 1
            if candidates:
                return candidates
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            failures.append(f"Open Library: {exc}")

        try:
            candidates = _lookup_google_books(client, isbn)
            successful_providers += 1
            return candidates
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            failures.append(f"Google Books: {exc}")

        if successful_providers:
            return []
        raise BibliographicProvidersUnavailable("; ".join(failures))
    finally:
        if owns_client:
            client.close()


def _lookup_open_library_isbn(
    client: httpx.Client,
    isbn: str,
) -> list[dict[str, Any]]:
    response = client.get(
        OPEN_LIBRARY_ISBN_URL.format(isbn=isbn),
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("response is not an object")

    title = _clean_text(payload.get("title"))
    authors = _open_library_authors(client, payload.get("authors"))
    if not title or not authors:
        return []
    identifiers = _isbn_identifiers(
        [
            isbn,
            *_list_values(payload.get("isbn_10")),
            *_list_values(payload.get("isbn_13")),
        ]
    )
    return [
        _candidate(
            source="OPEN_LIBRARY",
            source_record_id=_clean_text(payload.get("key")),
            identifiers=identifiers,
            title=title,
            subtitle=_clean_text(payload.get("subtitle")),
            authors=authors,
            publisher=_first_text(payload.get("publishers")),
            published_date=_clean_text(payload.get("publish_date")),
            page_count=_positive_int(payload.get("number_of_pages")),
            subjects=_clean_text_list(payload.get("subjects")),
            language=_open_library_language(payload.get("languages")),
        )
    ]


def _open_library_authors(client: httpx.Client, value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    authors = []
    for reference in value[:8]:
        if not isinstance(reference, dict):
            continue
        if name := _clean_text(reference.get("name")):
            authors.append(name)
            continue
        key = _clean_text(reference.get("key"))
        if not key or not key.startswith("/authors/"):
            continue
        try:
            response = client.get(f"https://openlibrary.org{key}.json")
            response.raise_for_status()
            author = response.json()
            if isinstance(author, dict) and (name := _clean_text(author.get("name"))):
                authors.append(name)
        except (httpx.HTTPError, ValueError, TypeError):
            continue
    return authors


def _open_library_language(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    for language in value:
        if isinstance(language, dict) and (key := _clean_text(language.get("key"))):
            return key.rsplit("/", 1)[-1]
        if cleaned := _clean_text(language):
            return cleaned
    return None


def _lookup_google_books(
    client: httpx.Client,
    isbn: str,
) -> list[dict[str, Any]]:
    parameters = {"q": f"isbn:{isbn}", "maxResults": 5, "printType": "books"}
    if api_key := os.getenv("GOOGLE_BOOKS_API_KEY"):
        parameters["key"] = api_key
    response = client.get(
        GOOGLE_BOOKS_VOLUMES_URL,
        params=parameters,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("response has no item list")

    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        volume = item.get("volumeInfo", {})
        if not isinstance(volume, dict):
            continue
        title = _clean_text(volume.get("title"))
        authors = _clean_text_list(volume.get("authors"))
        if not title or not authors:
            continue
        identifiers = _isbn_identifiers(
            identifier.get("identifier")
            for identifier in volume.get("industryIdentifiers", [])
            if isinstance(identifier, dict)
        )
        candidates.append(
            _candidate(
                source="GOOGLE_BOOKS",
                source_record_id=_clean_text(item.get("id")),
                identifiers=identifiers,
                title=title,
                subtitle=_clean_text(volume.get("subtitle")),
                authors=authors,
                publisher=_clean_text(volume.get("publisher")),
                published_date=_clean_text(volume.get("publishedDate")),
                page_count=_positive_int(volume.get("pageCount")),
                subjects=_clean_text_list(volume.get("categories")),
                language=_clean_text(volume.get("language")),
            )
        )
    return _deduplicate(candidates)


def _candidate(
    *,
    source: str,
    source_record_id: str | None,
    identifiers: dict[str, str | None],
    title: str,
    subtitle: str | None,
    authors: list[str],
    publisher: str | None,
    published_date: str | None,
    page_count: int | None,
    subjects: list[str],
    language: str | None,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_record_id": source_record_id,
        "identifiers": identifiers,
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "publisher": publisher,
        "published_date": published_date,
        "page_count": page_count,
        "subjects": subjects,
        "language": language,
        "edition": None,
        "genres": [],
        "category": None,
        "format": None,
        "confidence_or_match_notes": None,
    }


def _isbn_identifiers(values: Iterable[Any]) -> dict[str, str | None]:
    identifiers: dict[str, str | None] = {"isbn_10": None, "isbn_13": None}
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            isbn = normalize_isbn(value)
        except InvalidISBN:
            continue
        identifiers[f"isbn_{len(isbn)}"] = isbn
    return identifiers


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, (str, int)):
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _clean_text_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [cleaned for item in values if (cleaned := _clean_text(item))]


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, list):
            for item in value:
                if cleaned := _clean_text(item):
                    return cleaned
        elif cleaned := _clean_text(value):
            return cleaned
    return None


def _list_values(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _deduplicate(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for candidate in candidates:
        key = (
            candidate["title"].casefold(),
            tuple(author.casefold() for author in candidate["authors"]),
        )
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique

from collections.abc import Iterable
import os
import re
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
            edition_number=_edition_number(payload.get("edition_name")),
            binding=_binding(payload.get("physical_format")),
            series_name=_first_text(payload.get("series")),
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
            return _language_name(key.rsplit("/", 1)[-1])
        if cleaned := _clean_text(language):
            return _language_name(cleaned)
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
                edition_number=None,
                binding=None,
                series_name=None,
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
    edition_number: int | None,
    binding: str | None,
    series_name: str | None,
) -> dict[str, Any]:
    current_ed_year = _publication_year(published_date)
    fiction_category = _fiction_category(subjects)
    publication_type = _publication_type(subjects)
    return {
        "source": source,
        "source_record_id": source_record_id,
        "identifiers": identifiers,
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "publisher": publisher,
        "current_ed_year": current_ed_year,
        "original_publication_year": None,
        "page_count": page_count,
        "subjects": subjects,
        "language": _language_name(language),
        "edition_number": edition_number,
        "fiction_category": fiction_category,
        "binding": binding,
        "publication_type": publication_type,
        "genre_text": ", ".join(subjects) or None,
        "series_name": series_name,
        "series_volume": None,
        "confidence_or_match_notes": None,
    }


LANGUAGE_NAMES = {
    "en": "English",
    "eng": "English",
    "es": "Spanish",
    "spa": "Spanish",
    "gl": "Galician",
    "glg": "Galician",
    "ca": "Catalan",
    "cat": "Catalan",
    "fr": "French",
    "fre": "French",
    "fra": "French",
    "de": "German",
    "ger": "German",
    "deu": "German",
    "it": "Italian",
    "ita": "Italian",
    "pt": "Portuguese",
    "por": "Portuguese",
}


def _language_name(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return LANGUAGE_NAMES.get(cleaned.casefold(), cleaned)


def _publication_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", value)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1000 <= year <= 9999 else None


def _edition_number(value: Any) -> int | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    match = re.search(r"(?<!\d)(\d+)(?:st|nd|rd|th|ª|a)?", cleaned, re.IGNORECASE)
    if not match:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def _binding(value: Any) -> str | None:
    cleaned = (_clean_text(value) or "").casefold()
    if not cleaned:
        return None
    if any(term in cleaned for term in ("hardcover", "hardback", "tapa dura")):
        return "HARDCOVER"
    if any(term in cleaned for term in ("paperback", "softcover", "tapa blanda")):
        return "PAPERBACK"
    if "flexibound" in cleaned or "flexible" in cleaned:
        return "FLEXIBOUND"
    if "spiral" in cleaned:
        return "SPIRAL"
    if "stapled" in cleaned or "grapado" in cleaned:
        return "STAPLED"
    return "OTHER"


def _fiction_category(subjects: list[str]) -> str | None:
    text = " ".join(subjects).casefold()
    if "nonfiction" in text or "non-fiction" in text:
        return "NON_FICTION"
    if re.search(r"\bfiction\b", text):
        return "FICTION"
    return None


def _publication_type(subjects: list[str]) -> str | None:
    text = " ".join(subjects).casefold()
    if any(term in text for term in ("graphic novel", "comic book", "comics")):
        return "COMIC_GRAPHIC_NOVEL"
    if "atlas" in text:
        return "ATLAS"
    if any(term in text for term in ("dictionary", "encyclopedia", "reference")):
        return "REFERENCE"
    if any(term in text for term in ("photography", "art book", "illustrated")):
        return "ART_PHOTOGRAPHY_ILLUSTRATED"
    return None


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

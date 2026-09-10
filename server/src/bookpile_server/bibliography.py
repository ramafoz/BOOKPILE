from collections.abc import Iterable
import os
import re
from typing import Any

import httpx

from .isbn import InvalidISBN, normalize_isbn


OPEN_LIBRARY_URL = "https://openlibrary.org/isbn/{isbn}.json"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


class BibliographicProvidersUnavailable(RuntimeError):
    pass


def lookup_isbn(value: str, *, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    isbn = normalize_isbn(value)
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "BOOKPILE Server (bibliographic lookup)"},
        )
    failures: list[str] = []
    successful = 0
    try:
        try:
            candidates = _open_library(client, isbn)
            successful += 1
            if candidates:
                return candidates
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            failures.append(f"Open Library: {exc}")
        try:
            candidates = _google_books(client, isbn)
            successful += 1
            return candidates
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            failures.append(f"Google Books: {exc}")
        if successful:
            return []
        raise BibliographicProvidersUnavailable("; ".join(failures))
    finally:
        if owns_client:
            client.close()


def _open_library(client: httpx.Client, isbn: str) -> list[dict[str, Any]]:
    response = client.get(OPEN_LIBRARY_URL.format(isbn=isbn))
    if response.status_code == 404:
        return []
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("response is not an object")
    title = _text(payload.get("title"))
    authors = _open_library_authors(client, payload.get("authors"))
    if not title or not authors:
        return []
    return [_candidate(
        source="OPEN_LIBRARY",
        record_id=_text(payload.get("key")),
        isbn=isbn,
        title=title,
        subtitle=_text(payload.get("subtitle")),
        authors=authors,
        publisher=_first(payload.get("publishers")),
        published=_text(payload.get("publish_date")),
        pages=_positive_int(payload.get("number_of_pages")),
        subjects=_texts(payload.get("subjects")),
        language=_open_library_language(payload.get("languages")),
        edition=_positive_number(payload.get("edition_name")),
        binding=_binding(payload.get("physical_format")),
        series=_first(payload.get("series")),
        identifiers=[*_items(payload.get("isbn_10")), *_items(payload.get("isbn_13"))],
    )]


def _open_library_authors(client: httpx.Client, value: Any) -> list[str]:
    authors: list[str] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        if name := _text(item.get("name")):
            authors.append(name)
        elif (key := _text(item.get("key"))) and key.startswith("/authors/"):
            try:
                response = client.get(f"https://openlibrary.org{key}.json")
                response.raise_for_status()
                if isinstance(data := response.json(), dict) and (name := _text(data.get("name"))):
                    authors.append(name)
            except (httpx.HTTPError, ValueError, TypeError):
                pass
    return authors[:8]


def _open_library_language(value: Any) -> str | None:
    for item in value if isinstance(value, list) else []:
        raw = item.get("key") if isinstance(item, dict) else item
        if cleaned := _text(raw):
            return _language(cleaned.rsplit("/", 1)[-1])
    return None


def _google_books(client: httpx.Client, isbn: str) -> list[dict[str, Any]]:
    params = {"q": f"isbn:{isbn}", "maxResults": 5, "printType": "books"}
    if key := os.getenv("GOOGLE_BOOKS_API_KEY"):
        params["key"] = key
    response = client.get(GOOGLE_BOOKS_URL, params=params)
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", []) if isinstance(payload, dict) else []
    candidates: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        volume = item.get("volumeInfo", {}) if isinstance(item, dict) else {}
        title = _text(volume.get("title")) if isinstance(volume, dict) else None
        authors = _texts(volume.get("authors")) if isinstance(volume, dict) else []
        if title and authors:
            identifiers = [
                value.get("identifier") for value in volume.get("industryIdentifiers", [])
                if isinstance(value, dict)
            ]
            candidates.append(_candidate(
                source="GOOGLE_BOOKS", record_id=_text(item.get("id")), isbn=isbn,
                title=title, subtitle=_text(volume.get("subtitle")), authors=authors,
                publisher=_text(volume.get("publisher")), published=_text(volume.get("publishedDate")),
                pages=_positive_int(volume.get("pageCount")), subjects=_texts(volume.get("categories")),
                language=_language(_text(volume.get("language"))), edition=None,
                binding=None, series=None, identifiers=identifiers,
            ))
    return candidates


def _candidate(*, source: str, record_id: str | None, isbn: str, title: str,
               subtitle: str | None, authors: list[str], publisher: str | None,
               published: str | None, pages: int | None, subjects: list[str],
               language: str | None, edition: int | None, binding: str | None,
               series: str | None, identifiers: Iterable[Any]) -> dict[str, Any]:
    ids = {"isbn_10": None, "isbn_13": None}
    for raw in [isbn, *identifiers]:
        if not isinstance(raw, str):
            continue
        try:
            normalized = normalize_isbn(raw)
            ids[f"isbn_{len(normalized)}"] = normalized
        except InvalidISBN:
            pass
    genre = ", ".join(subjects) or None
    subject_text = " ".join(subjects).casefold()
    fiction = "NON_FICTION" if "non-fiction" in subject_text or "nonfiction" in subject_text else "FICTION" if re.search(r"\bfiction\b", subject_text) else None
    publication = "COMIC_GRAPHIC_NOVEL" if any(word in subject_text for word in ("graphic novel", "comic")) else "ATLAS" if "atlas" in subject_text else "REFERENCE" if any(word in subject_text for word in ("dictionary", "encyclopedia", "reference")) else None
    year_match = re.search(r"(?<!\d)(\d{4})(?!\d)", published or "")
    return {
        "source": source, "source_record_id": record_id, "identifiers": ids,
        "title": title, "subtitle": subtitle, "authors": authors,
        "publisher": publisher, "current_ed_year": int(year_match.group(1)) if year_match else None,
        "original_publication_year": None, "page_count": pages, "subjects": subjects,
        "language": language, "edition_number": edition, "fiction_category": fiction,
        "binding": binding, "publication_type": publication, "genre_text": genre,
        "series_name": series, "series_volume": None, "confidence_or_match_notes": None,
        "catalogue_matches": [],
    }


LANGUAGES = {"en": "English", "eng": "English", "es": "Spanish", "spa": "Spanish", "gl": "Galician", "glg": "Galician", "ca": "Catalan", "cat": "Catalan", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese"}


def _language(value: str | None) -> str | None:
    return LANGUAGES.get(value.casefold(), value) if value else None


def _binding(value: Any) -> str | None:
    text = (_text(value) or "").casefold()
    if any(word in text for word in ("hardcover", "hardback", "tapa dura")):
        return "HARDCOVER"
    if any(word in text for word in ("paperback", "softcover", "tapa blanda")):
        return "PAPERBACK"
    return "OTHER" if text else None


def _text(value: Any) -> str | None:
    cleaned = " ".join(str(value).split()) if isinstance(value, (str, int)) else ""
    return cleaned or None


def _texts(value: Any) -> list[str]:
    return [text for item in value if (text := _text(item))] if isinstance(value, list) else []


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value is None else [value])


def _first(value: Any) -> str | None:
    return next((text for item in _items(value) if (text := _text(item))), None)


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _positive_number(value: Any) -> int | None:
    match = re.search(r"\d+", _text(value) or "")
    return int(match.group()) if match and int(match.group()) > 0 else None

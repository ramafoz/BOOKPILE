import httpx
import pytest

from app.bibliography import BibliographicProvidersUnavailable, lookup_isbn


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_open_library_result_is_normalized_without_google_fallback() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "key": "/books/OL1M",
                "title": " Example   Book ",
                "subtitle": "A subtitle",
                "authors": [
                    {"name": "First Author"},
                    {"name": "Second Author"},
                ],
                "isbn_10": ["0-306-40615-2"],
                "isbn_13": ["9780306406157", "bad"],
                "publishers": ["Example Press"],
                "publish_date": "2001",
                "number_of_pages": 320,
                "languages": [{"key": "/languages/eng"}],
                "subjects": ["History", "Libraries"],
            },
            request=request,
        )

    with mock_client(handler) as client:
        results = lookup_isbn("978-0-306-40615-7", client=client)

    assert len(requests) == 1
    assert requests[0].url.host == "openlibrary.org"
    assert results == [
        {
            "source": "OPEN_LIBRARY",
            "source_record_id": "/books/OL1M",
            "identifiers": {
                "isbn_10": "0306406152",
                "isbn_13": "9780306406157",
            },
            "title": "Example Book",
            "subtitle": "A subtitle",
            "authors": ["First Author", "Second Author"],
            "publisher": "Example Press",
            "current_ed_year": 2001,
            "original_publication_year": None,
            "page_count": 320,
            "subjects": ["History", "Libraries"],
            "language": "English",
            "edition_number": None,
            "fiction_category": None,
            "binding": None,
            "publication_type": None,
            "genre_text": "History, Libraries",
            "series_name": None,
            "series_volume": None,
            "confidence_or_match_notes": None,
        }
    ]


def test_google_books_is_used_when_open_library_has_no_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openlibrary.org":
            return httpx.Response(404, request=request)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "google-id",
                        "volumeInfo": {
                            "title": "Fallback Book",
                            "authors": ["Fallback Author"],
                            "industryIdentifiers": [
                                {
                                    "type": "ISBN_13",
                                    "identifier": "9780306406157",
                                }
                            ],
                            "publisher": "Fallback Press",
                            "publishedDate": "1999-05",
                            "pageCount": 201,
                            "categories": ["Fiction"],
                            "language": "en",
                        },
                    }
                ]
            },
            request=request,
        )

    with mock_client(handler) as client:
        results = lookup_isbn("9780306406157", client=client)

    assert results[0]["source"] == "GOOGLE_BOOKS"
    assert results[0]["title"] == "Fallback Book"
    assert results[0]["authors"] == ["Fallback Author"]


def test_google_books_is_used_when_open_library_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openlibrary.org":
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "available-fallback",
                        "volumeInfo": {
                            "title": "Available Book",
                            "authors": ["Available Author"],
                        },
                    }
                ]
            },
            request=request,
        )

    with mock_client(handler) as client:
        results = lookup_isbn("9780306406157", client=client)

    assert results[0]["source"] == "GOOGLE_BOOKS"


def test_incomplete_records_are_ignored_and_duplicates_removed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openlibrary.org":
            return httpx.Response(
                200,
                json={"title": "No author"},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {"volumeInfo": {"title": "No author"}},
                    {"volumeInfo": {"authors": ["No title"]}},
                    {"volumeInfo": {"title": "Same", "authors": ["Author"]}},
                    {"volumeInfo": {"title": "same", "authors": ["author"]}},
                ]
            },
            request=request,
        )

    with mock_client(handler) as client:
        results = lookup_isbn("9780306406157", client=client)

    assert [(result["title"], result["authors"]) for result in results] == [
        ("Same", ["Author"])
    ]


def test_no_results_from_available_providers_returns_empty_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openlibrary.org":
            return httpx.Response(404, request=request)
        return httpx.Response(200, json={}, request=request)

    with mock_client(handler) as client:
        assert lookup_isbn("9780306406157", client=client) == []


def test_both_provider_failures_raise_a_normalized_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with mock_client(handler) as client:
        with pytest.raises(BibliographicProvidersUnavailable) as error:
            lookup_isbn("9780306406157", client=client)

    assert "Open Library" in str(error.value)
    assert "Google Books" in str(error.value)

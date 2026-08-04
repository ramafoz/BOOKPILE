from app.catalogue_matching import comparison_text, match_candidate


def book(book_id: int, title: str, author: str) -> dict:
    return {
        "id": book_id,
        "title": title,
        "author": author,
        "status": "PENDING",
        "cover_filename": None,
        "bookcase_name": None,
        "shelf_number": None,
        "container_type": None,
        "layer": None,
        "container_number": None,
        "position": None,
    }


def test_comparison_text_ignores_case_diacritics_and_punctuation() -> None:
    assert comparison_text("  Cien años: de SOLEDAD! ") == "cien anos de soledad"


def test_exact_normalized_title_and_author_is_a_strong_match() -> None:
    matches = match_candidate(
        {"title": "Cien anos de soledad", "authors": ["Gabriel García Márquez"]},
        [book(1, "Cien años de soledad", "Gabriel Garcia Marquez")],
    )

    assert len(matches) == 1
    assert matches[0]["book_id"] == 1
    assert matches[0]["match_class"] == "strong"


def test_same_title_with_different_author_is_only_possible() -> None:
    matches = match_candidate(
        {"title": "Collected Stories", "authors": ["Author One"]},
        [book(2, "Collected Stories", "Author Two")],
    )

    assert matches[0]["match_class"] == "possible"
    assert "author text differs" in matches[0]["reason"]


def test_similar_title_needs_matching_author() -> None:
    candidate = {"title": "The Left Hand of Darkness", "authors": ["Ursula Le Guin"]}
    matches = match_candidate(
        candidate,
        [
            book(3, "Left Hand of Darkness", "Ursula K. Le Guin"),
            book(4, "Left Hand of Darkness", "Another Author"),
        ],
    )

    assert [match["book_id"] for match in matches] == [3]
    assert matches[0]["match_class"] == "possible"


def test_multiple_external_authors_can_match_free_text_author() -> None:
    matches = match_candidate(
        {"title": "A Shared Book", "authors": ["Jane Smith", "John Doe"]},
        [book(5, "A Shared Book", "Jane Smith & John Doe")],
    )

    assert matches[0]["match_class"] == "strong"

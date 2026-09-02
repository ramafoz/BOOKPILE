from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bookpile_server.models import (
    Book,
    BookContributor,
    Bookcase,
    Container,
    ContributorRole,
    Library,
    Shelf,
    VisualBookcaseLayout,
    VisualContainerLayout,
    VisualOutsideArea,
    VisualShelfLayout,
)


def add_library(session: Session, name: str, slug: str) -> Library:
    library = Library(name=name, slug=slug)
    session.add(library)
    session.flush()
    return library


def add_hierarchy(
    session: Session,
    library: Library,
    *,
    suffix: str,
    container_type: str = "ROW",
) -> tuple[Bookcase, Shelf, Container]:
    bookcase = Bookcase(
        library_id=library.id,
        name=f"Bookcase {suffix}",
        height_mm=2100,
        width_mm=800,
        depth_mm=300,
    )
    session.add(bookcase)
    session.flush()
    shelf = Shelf(
        library_id=library.id,
        bookcase_id=bookcase.id,
        shelf_number=1,
        usable_height_mm=320,
        usable_width_mm=760,
        usable_depth_mm=280,
    )
    session.add(shelf)
    session.flush()
    container = Container(
        library_id=library.id,
        shelf_id=shelf.id,
        container_type=container_type,
        layer="BACKGROUND",
        container_number=1,
    )
    session.add(container)
    session.flush()
    return bookcase, shelf, container


def add_role(session: Session, code: str, label: str, order: int) -> None:
    session.add(
        ContributorRole(
            code=code,
            label=label,
            sort_order=order,
            is_active=True,
        )
    )


def test_shared_catalogue_accepts_metadata_contributors_and_layout(
    session: Session,
) -> None:
    library = add_library(session, "Measured home", "measured-home")
    bookcase, shelf, container = add_hierarchy(
        session, library, suffix="measured"
    )
    add_role(session, "AUTHOR", "Author", 1)
    add_role(session, "INKER", "Inker", 2)
    book = Book(
        library_id=library.id,
        title="A translated graphic novel",
        author="Multiple authors",
        isbn_13="9781234567897",
        page_count=240,
        publisher="Example Press",
        current_ed_year=2026,
        original_publication_year=2024,
        language="Galician",
        original_language="French",
        translation_status="TRANSLATED",
        fiction_category="FICTION",
        binding="HARDCOVER",
        publication_type="COMIC_GRAPHIC_NOVEL",
        acquisition_date=date(2026, 8, 31),
        height_mm=260,
        width_mm=190,
        thickness_mm=24,
        container_id=container.id,
        position=1,
    )
    session.add(book)
    session.flush()
    session.add_all(
        [
            BookContributor(
                library_id=library.id,
                book_id=book.id,
                role_code="AUTHOR",
                position=1,
                name="Example Writer",
            ),
            BookContributor(
                library_id=library.id,
                book_id=book.id,
                role_code="INKER",
                position=1,
                name="Example Inker",
            ),
            VisualBookcaseLayout(
                library_id=library.id,
                bookcase_id=bookcase.id,
                x_mm=Decimal("-510.0000"),
                floor_y_mm=Decimal("1580.0000"),
                width_mm=Decimal("440.0000"),
                height_mm=Decimal("1500.0000"),
            ),
            VisualShelfLayout(
                library_id=library.id,
                shelf_id=shelf.id,
                height_weight=Decimal("1.2500"),
            ),
            VisualContainerLayout(
                library_id=library.id,
                container_id=container.id,
                x=Decimal("0"),
                y=Decimal("0"),
                width=Decimal("100"),
                height=Decimal("100"),
                row_anchor="LEFT",
            ),
            VisualOutsideArea(
                library_id=library.id,
                area_kind="READING",
                x_mm=Decimal("900"),
                y_mm=Decimal("1400"),
                width_mm=Decimal("400"),
                height_mm=Decimal("360"),
            ),
        ]
    )

    session.commit()

    assert book.translation_status == "TRANSLATED"
    assert book.thickness_mm == 24
    assert book.container_id == container.id


def test_database_rejects_cross_library_hierarchy(session: Session) -> None:
    first = add_library(session, "First", "schema-first")
    second = add_library(session, "Second", "schema-second")
    first_bookcase, _, _ = add_hierarchy(session, first, suffix="first")
    session.commit()

    session.add(
        Shelf(
            library_id=second.id,
            bookcase_id=first_bookcase.id,
            shelf_number=2,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_book_in_another_library_container(
    session: Session,
) -> None:
    first = add_library(session, "First", "book-first")
    second = add_library(session, "Second", "book-second")
    _, _, second_container = add_hierarchy(session, second, suffix="second")
    session.commit()

    session.add(
        Book(
            library_id=first.id,
            title="Wrong room",
            author="Example",
            container_id=second_container.id,
            position=1,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_cross_library_contributor(session: Session) -> None:
    first = add_library(session, "First", "contributor-first")
    second = add_library(session, "Second", "contributor-second")
    add_role(session, "AUTHOR", "Author", 1)
    book = Book(library_id=first.id, title="One", author="Writer")
    session.add(book)
    session.commit()

    session.add(
        BookContributor(
            library_id=second.id,
            book_id=book.id,
            role_code="AUTHOR",
            position=1,
            name="Writer",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_normalized_duplicate_contributor(
    session: Session,
) -> None:
    library = add_library(session, "Contributors", "contributors")
    add_role(session, "AUTHOR", "Author", 1)
    book = Book(library_id=library.id, title="One", author="Multiple authors")
    session.add(book)
    session.flush()
    session.add_all(
        [
            BookContributor(
                library_id=library.id,
                book_id=book.id,
                role_code="AUTHOR",
                position=1,
                name="Example Writer",
            ),
            BookContributor(
                library_id=library.id,
                book_id=book.id,
                role_code="AUTHOR",
                position=2,
                name=" example writer ",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_contributor_role_vocabulary_can_grow_additively(session: Session) -> None:
    library = add_library(session, "Cartography", "cartography")
    add_role(session, "CARTOGRAPHER", "Cartographer", 100)
    book = Book(library_id=library.id, title="An atlas", author="Map Team")
    session.add(book)
    session.flush()
    session.add(
        BookContributor(
            library_id=library.id,
            book_id=book.id,
            role_code="CARTOGRAPHER",
            position=1,
            name="Example Cartographer",
        )
    )

    session.commit()

    assert session.get(ContributorRole, "CARTOGRAPHER") is not None


def test_database_rejects_cross_library_pile_support(session: Session) -> None:
    first = add_library(session, "First", "visual-first")
    second = add_library(session, "Second", "visual-second")
    _, first_shelf, first_pile = add_hierarchy(
        session, first, suffix="first-pile", container_type="PILE"
    )
    _, _, second_row = add_hierarchy(
        session, second, suffix="second-row", container_type="ROW"
    )
    session.commit()
    assert first_shelf.library_id == first.id

    session.add(
        VisualContainerLayout(
            library_id=first.id,
            container_id=first_pile.id,
            x=Decimal("10"),
            y=Decimal("20"),
            width=Decimal("30"),
            height=Decimal("40"),
            row_anchor="LEFT",
            support_kind="CONTAINER",
            support_container_id=second_row.id,
            pile_alignment="RIGHT",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "book",
    [
        Book(library_id=None, title="Bad pages", author="A", page_count=0),
        Book(library_id=None, title="Bad size", author="A", thickness_mm=0),
        Book(library_id=None, title="Half placed", author="A", position=1),
        Book(
            library_id=None,
            title="Bad translation",
            author="A",
            translation_status="MAYBE",
        ),
    ],
)
def test_database_rejects_invalid_book_metadata(
    session: Session, book: Book
) -> None:
    library = add_library(session, f"Library {book.title}", book.title.lower().replace(" ", "-"))
    book.library_id = library.id
    session.add(book)

    with pytest.raises(IntegrityError):
        session.commit()

"""Insert a tiny synthetic catalogue for local Server development only."""
from sqlalchemy import select
from sqlalchemy.engine import make_url

from bookpile_server.config import get_settings
from bookpile_server.database import SessionFactory
from bookpile_server.models import Book, Library


ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


def assert_safe_target() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    if settings.environment != "development":
        raise RuntimeError("Synthetic seeding is allowed only in development")
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Synthetic seeding requires PostgreSQL")
    if url.host not in ALLOWED_HOSTS or url.database != "bookpile":
        raise RuntimeError(
            "Synthetic seeding is restricted to the local 'bookpile' database"
        )


def seed() -> None:
    assert_safe_target()
    with SessionFactory.begin() as session:
        libraries = []
        for name, slug, books in (
            (
                "Demo Home Library",
                "demo-home",
                (
                    ("Piranesi", "Susanna Clarke"),
                    ("The Dispossessed", "Ursula K. Le Guin"),
                ),
            ),
            (
                "Demo Office Library",
                "demo-office",
                (("Dune", "Frank Herbert"),),
            ),
        ):
            library = session.scalar(select(Library).where(Library.slug == slug))
            if library is None:
                library = Library(name=name, slug=slug)
                session.add(library)
                session.flush()
            libraries.append(library)
            for title, author in books:
                exists = session.scalar(
                    select(Book.id).where(
                        Book.library_id == library.id,
                        Book.title == title,
                        Book.author == author,
                    )
                )
                if exists is None:
                    session.add(
                        Book(library_id=library.id, title=title, author=author)
                    )

    for library in libraries:
        print(f"{library.name}: {library.id}")


if __name__ == "__main__":
    seed()

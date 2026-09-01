from io import BytesIO
from uuid import UUID

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import BookCover, LibraryAuditEvent
from test_catalogue_services import (
    add_user,
    authenticate,
    create_library_with_members,
    csrf,
    payload,
    seed_roles,
)


def image_bytes(*, size: tuple[int, int] = (1200, 1800), colour: str = "navy", format: str = "JPEG") -> bytes:
    image = Image.new("RGB", size, colour)
    exif = image.getexif()
    exif[315] = "Private photographer metadata"
    output = BytesIO()
    image.save(output, format=format, exif=exif)
    return output.getvalue()


def create_book(client: TestClient, session: Session, username: str = "cover_owner"):
    seed_roles(session)
    owner = add_user(session, username)
    library = create_library_with_members(session, owner)
    authenticate(client, session, owner)
    response = client.post(
        f"/api/v1/libraries/{library.id}/catalogue", json=payload("Private cover"), headers=csrf()
    )
    assert response.status_code == 201
    return owner, library, response.json()


def test_owner_uploads_sanitized_private_cover_and_can_replace_and_remove(client: TestClient, session: Session) -> None:
    owner, library, book = create_book(client, session)
    path = f"/api/v1/libraries/{library.id}/catalogue/{book['id']}/cover"
    uploaded = client.put(path, files={"cover": ("cover.jpg", image_bytes(), "image/jpeg")}, headers=csrf())
    assert uploaded.status_code == 200
    assert uploaded.json()["width_px"] <= 900
    assert uploaded.json()["height_px"] <= 1400

    fetched = client.get(path)
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/webp"
    assert "no-store" in fetched.headers["cache-control"]
    with Image.open(BytesIO(fetched.content)) as image:
        assert image.format == "WEBP"
        assert not image.getexif()

    book_id = UUID(book["id"])
    first = session.scalar(select(BookCover).where(BookCover.book_id == book_id))
    assert first and first.uploaded_by_user_id == owner.id
    first_key = first.object_key
    replaced = client.put(path, files={"cover": ("cover.png", image_bytes(colour="red", format="PNG"), "image/png")}, headers=csrf())
    assert replaced.status_code == 200
    session.expire_all()
    current = session.scalar(select(BookCover).where(BookCover.book_id == book_id))
    assert current and current.object_key != first_key

    removed = client.delete(path, headers=csrf())
    assert removed.status_code == 204
    assert client.get(path).status_code == 404
    events = list(session.scalars(select(LibraryAuditEvent.event_type).where(LibraryAuditEvent.library_id == library.id)))
    assert "cover_uploaded" in events
    assert "cover_replaced" in events
    assert "cover_removed" in events


def test_viewer_reads_cover_but_cannot_change_it_and_outsider_gets_404(client: TestClient, session: Session) -> None:
    seed_roles(session)
    owner = add_user(session, "cover_access_owner")
    viewer = add_user(session, "cover_access_viewer")
    outsider = add_user(session, "cover_access_outsider")
    library = create_library_with_members(session, owner, viewer)
    authenticate(client, session, owner)
    created = client.post(f"/api/v1/libraries/{library.id}/catalogue", json=payload("Access cover"), headers=csrf()).json()
    path = f"/api/v1/libraries/{library.id}/catalogue/{created['id']}/cover"
    assert client.put(path, files={"cover": ("cover.jpg", image_bytes(), "image/jpeg")}, headers=csrf()).status_code == 200

    client.cookies.clear(); authenticate(client, session, viewer)
    assert client.get(path).status_code == 200
    assert client.put(path, files={"cover": ("cover.jpg", image_bytes(), "image/jpeg")}, headers=csrf()).status_code == 404
    assert client.delete(path, headers=csrf()).status_code == 404

    client.cookies.clear(); authenticate(client, session, outsider)
    assert client.get(path).status_code == 404


def test_cover_rejects_non_image_and_missing_csrf(client: TestClient, session: Session) -> None:
    _, library, book = create_book(client, session, "cover_validation_owner")
    path = f"/api/v1/libraries/{library.id}/catalogue/{book['id']}/cover"
    assert client.put(path, files={"cover": ("fake.jpg", b"not an image", "image/jpeg")}, headers=csrf()).status_code == 422
    assert client.put(path, files={"cover": ("cover.jpg", image_bytes(), "image/jpeg")}).status_code == 403

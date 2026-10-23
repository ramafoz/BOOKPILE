from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bookpile_server.api import dependencies
from bookpile_server.api.routes import catalogue as catalogue_routes
from bookpile_server.config import Settings
from bookpile_server.models import (
    BookCover,
    LibraryAuditEvent,
    RateLimitBucket,
    SecurityEvent,
)
from bookpile_server.repositories.rate_limits import RateLimitRepository
from bookpile_server.services.rate_limits import (
    RateLimitDecisionUnavailableError,
    RateLimitExceededError,
    RateLimiter,
)
from bookpile_server.services.specific_operation_limits import (
    SpecificOperationRateLimiter,
)
from test_bibliography import _authenticate
from test_mutation_limits import add_library, add_user, authenticate
from test_private_covers import create_book, csrf, image_bytes


def selected_settings(**updates) -> Settings:
    return Settings(
        environment="test",
        deployment_revision="git-specific-limits",
        rate_limit_key_secret="specific-operation-secret",
    ).model_copy(update=updates)


def stored_buckets(session: Session, scope: str) -> list[RateLimitBucket]:
    session.expire_all()
    return list(
        session.scalars(
            select(RateLimitBucket).where(RateLimitBucket.scope == scope)
        )
    )


@pytest.mark.parametrize(
    ("scope", "mode_field", "threshold_field", "method_name", "identity"),
    (
        (
            "bibliographic_lookup_ip",
            "bibliographic_lookup_limit_mode",
            "bibliographic_lookup_attempts_per_ip_per_hour",
            "check_bibliographic_ip",
            "203.0.113.10",
        ),
        (
            "bibliographic_lookup_library",
            "bibliographic_lookup_limit_mode",
            "bibliographic_lookup_attempts_per_library_per_hour",
            "check_bibliographic_library",
            uuid4(),
        ),
        (
            "cover_upload_library",
            "cover_upload_library_limit_mode",
            "cover_upload_attempts_per_library_per_hour",
            "check_cover_library",
            uuid4(),
        ),
        (
            "rearrangement_user",
            "rearrangement_limit_mode",
            "rearrangement_attempts_per_user_per_minute",
            "check_rearrangement_user",
            uuid4(),
        ),
        (
            "rearrangement_library",
            "rearrangement_limit_mode",
            "rearrangement_attempts_per_library_per_minute",
            "check_rearrangement_library",
            uuid4(),
        ),
    ),
)
@pytest.mark.parametrize(
    ("mode", "event_type", "raises"),
    (
        ("observe", "rate_limit_observed", False),
        ("enforce", "rate_limit_blocked", True),
    ),
)
def test_specific_operation_policies_share_counters_and_emit_safe_evidence(
    session: Session,
    scope: str,
    mode_field: str,
    threshold_field: str,
    method_name: str,
    identity,
    mode: str,
    event_type: str,
    raises: bool,
) -> None:
    settings = selected_settings(**{mode_field: mode, threshold_field: 1})
    limiter = SpecificOperationRateLimiter(
        RateLimiter(
            RateLimitRepository(session),
            settings.rate_limit_key_secret,
            settings.deployment_revision,
        ),
        settings,
    )
    check = getattr(limiter, method_name)

    check(identity)
    if raises:
        with pytest.raises(RateLimitExceededError):
            check(identity)
    else:
        check(identity)

    bucket = stored_buckets(session, scope)[0]
    assert bucket.attempt_count == 2
    assert len(bucket.key_hash) == 64
    assert str(identity) not in bucket.key_hash
    event = session.scalar(
        select(SecurityEvent).where(SecurityEvent.event_type == event_type)
    )
    assert event is not None
    assert event.ip_address is None
    assert event.details == {
        "scope": scope,
        "mode": mode,
        "deployment_revision": settings.deployment_revision,
    }


def test_existing_user_limits_remain_enforced_when_new_policies_are_off(
    session: Session,
) -> None:
    settings = selected_settings(
        bibliographic_lookup_attempts_per_user_per_hour=1,
        cover_upload_attempts_per_hour=1,
    )
    limiter = SpecificOperationRateLimiter(
        RateLimiter(RateLimitRepository(session), settings.rate_limit_key_secret),
        settings,
    )
    user_id = uuid4()
    library_id = uuid4()

    limiter.check_bibliographic_user(user_id)
    with pytest.raises(RateLimitExceededError):
        limiter.check_bibliographic_user(user_id)
    limiter.check_cover_user(user_id)
    with pytest.raises(RateLimitExceededError):
        limiter.check_cover_user(user_id)
    limiter.check_bibliographic_ip("203.0.113.20")
    limiter.check_bibliographic_library(library_id)
    limiter.check_cover_library(library_id)
    limiter.check_rearrangement_user(user_id)
    limiter.check_rearrangement_library(library_id)

    assert stored_buckets(session, "bibliographic_lookup")[0].attempt_count == 2
    assert stored_buckets(session, "cover_upload")[0].attempt_count == 2
    assert stored_buckets(session, "bibliographic_lookup_ip") == []
    assert stored_buckets(session, "bibliographic_lookup_library") == []
    assert stored_buckets(session, "cover_upload_library") == []
    assert stored_buckets(session, "rearrangement_user") == []
    assert stored_buckets(session, "rearrangement_library") == []


def test_unauthorized_lookup_cannot_spend_specific_allowance(
    client, session: Session, monkeypatch
) -> None:
    settings = selected_settings(
        bibliographic_lookup_limit_mode="enforce",
        bibliographic_lookup_attempts_per_ip_per_hour=0,
        bibliographic_lookup_attempts_per_library_per_hour=0,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    library, _user = _authenticate(client, session, role="VIEWER")
    monkeypatch.setattr(
        catalogue_routes,
        "lookup_isbn",
        lambda _isbn: pytest.fail("provider must not be called"),
    )

    response = client.get(
        f"/api/v1/libraries/{library.id}/catalogue/isbn-lookup",
        params={"isbn": "9780306406157"},
    )

    assert response.status_code == 404
    assert stored_buckets(session, "bibliographic_lookup") == []
    assert stored_buckets(session, "bibliographic_lookup_ip") == []
    assert stored_buckets(session, "bibliographic_lookup_library") == []


def test_lookup_limit_blocks_before_external_provider(
    client, session: Session, monkeypatch
) -> None:
    settings = selected_settings(
        bibliographic_lookup_limit_mode="enforce",
        bibliographic_lookup_attempts_per_ip_per_hour=10,
        bibliographic_lookup_attempts_per_library_per_hour=0,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    library, _user = _authenticate(client, session)
    monkeypatch.setattr(
        catalogue_routes,
        "lookup_isbn",
        lambda _isbn: pytest.fail("provider must not be called"),
    )

    response = client.get(
        f"/api/v1/libraries/{library.id}/catalogue/isbn-lookup",
        params={"isbn": "9780306406157"},
    )

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Too many bibliographic lookups. Try again later."
    }
    assert stored_buckets(session, "bibliographic_lookup_library")[0].attempt_count == 1


def test_cover_limit_leaves_no_metadata_or_private_object(
    client, session: Session, monkeypatch, tmp_path
) -> None:
    _owner, library, book = create_book(client, session, "specific_cover_owner")
    settings = selected_settings(
        cover_upload_library_limit_mode="enforce",
        cover_upload_attempts_per_library_per_hour=0,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    path = f"/api/v1/libraries/{library.id}/catalogue/{book['id']}/cover"

    response = client.put(
        path,
        files={"cover": ("cover.jpg", image_bytes(), "image/jpeg")},
        headers=csrf(),
    )

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Too many cover uploads. Please try again later."
    }
    assert session.scalar(
        select(BookCover).where(BookCover.book_id == UUID(book["id"]))
    ) is None
    cover_directory = tmp_path / "private-objects" / "covers"
    assert not cover_directory.exists() or not list(cover_directory.iterdir())
    assert stored_buckets(session, "cover_upload_library")[0].attempt_count == 1


def test_rearrangement_limit_rejects_preview_and_apply_without_audit(
    client, session: Session, monkeypatch
) -> None:
    owner = add_user(session, "specific_rearrangement_owner")
    library = add_library(session, owner)
    authenticate(client, session, owner)
    settings = selected_settings(
        rearrangement_limit_mode="enforce",
        rearrangement_attempts_per_user_per_minute=10,
        rearrangement_attempts_per_library_per_minute=0,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    base = f"/api/v1/libraries/{library.id}/physical-library/rearrangements"
    payload = {"book_id": str(uuid4())}

    preview = client.post(f"{base}/preview", json=payload)
    applied = client.post(
        f"{base}/apply",
        json={**payload, "revision": "0" * 64},
        headers={"X-CSRF-Token": "mutation-limit-csrf"},
    )

    assert preview.status_code == 429
    assert applied.status_code == 429
    assert preview.json() == applied.json() == {
        "detail": "Too many rearrangement requests. Try again later."
    }
    assert session.scalar(
        select(func.count()).select_from(LibraryAuditEvent).where(
            LibraryAuditEvent.library_id == library.id
        )
    ) == 0


def test_specific_limit_database_failure_is_generic_503(
    client, session: Session, monkeypatch
) -> None:
    settings = selected_settings(bibliographic_lookup_limit_mode="enforce")
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    library, _user = _authenticate(client, session)
    monkeypatch.setattr(
        RateLimiter,
        "apply",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RateLimitDecisionUnavailableError()
        ),
    )
    monkeypatch.setattr(
        catalogue_routes,
        "lookup_isbn",
        lambda _isbn: pytest.fail("provider must not be called"),
    )

    response = client.get(
        f"/api/v1/libraries/{library.id}/catalogue/isbn-lookup",
        params={"isbn": "9780306406157"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Request limiting is temporarily unavailable."
    }

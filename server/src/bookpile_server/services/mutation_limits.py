from datetime import timedelta
from uuid import UUID

from ..config import Settings
from .rate_limits import RateLimiter, RateLimitPolicy


# Route names are deliberate rather than inferred from the HTTP method. POST is
# also used for read-only previews and public authentication actions. Keeping an
# explicit registry makes new unsafe routes fail the coverage test until their
# mutation policy is reviewed.
USER_MUTATION_ROUTES = frozenset(
    {
        "logout",
        "update_preferred_locale",
        "rotate_session",
        "revoke_all_sessions",
        "create_library",
        "restore_library",
        "accept_invitation",
        "create_earned_beta_invitation",
        "delete_account",
        "change_password",
        "update_profile",
        "replace_profile_image",
        "remove_profile_image",
    }
)

OWNER_LIBRARY_MUTATION_ROUTES = frozenset(
    {
        "create_book",
        "create_book_with_placement",
        "create_book_with_placement_and_loan",
        "update_book",
        "update_book_with_placement",
        "delete_book",
        "put_book_cover",
        "delete_book_cover",
        "delete_library",
        "create_invitation",
        "revoke_invitation",
        "change_member",
        "update_book_placement",
        "apply_rearrangement",
        "update_visual_layout",
        "create_bookcase",
        "update_bookcase",
        "delete_bookcase",
        "create_shelf",
        "update_shelf",
        "delete_shelf",
        "create_container",
        "update_container",
        "delete_container",
        "start_reading",
        "finish_reading",
        "cancel_reading",
        "add_historical_reading",
        "edit_historical_reading",
        "delete_historical_reading",
        "set_my_goodreads_review",
        "start_loan",
        "return_loan",
        "cancel_loan",
        "add_historical_loan",
        "edit_historical_loan",
        "delete_historical_loan",
        "preflight_local_import",
        "preflight_server_import",
        "cancel_import_job",
        "consolidate_import_job",
        "consolidate_import_job_as_new_library",
    }
)

MEMBER_LIBRARY_MUTATION_ROUTES = frozenset({"select_reading_perspective"})

LIBRARY_MUTATION_ROUTES = (
    OWNER_LIBRARY_MUTATION_ROUTES | MEMBER_LIBRARY_MUTATION_ROUTES
)
MUTATION_ROUTES = USER_MUTATION_ROUTES | LIBRARY_MUTATION_ROUTES


class MutationRateLimiter:
    """Apply independently switchable mutation ceilings."""

    def __init__(self, rate_limiter: RateLimiter, settings: Settings) -> None:
        self._rate_limiter = rate_limiter
        self._settings = settings
        self._window = timedelta(minutes=15)

    def check_user(
        self, user_id: UUID, *, correlation_id: str | None = None
    ) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "mutation_user",
                self._settings.mutation_attempts_per_user_per_15_minutes,
                self._window,
            ),
            key=str(user_id),
            mode=self._settings.mutation_user_limit_mode,
            correlation_id=correlation_id,
        )

    def check_library(
        self, library_id: UUID, *, correlation_id: str | None = None
    ) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "mutation_library",
                self._settings.mutation_attempts_per_library_per_15_minutes,
                self._window,
            ),
            key=str(library_id),
            mode=self._settings.mutation_library_limit_mode,
            correlation_id=correlation_id,
        )

"""Finalize expired shared-library deletions. Run from a scheduled job."""

from bookpile_server.api.dependencies import get_private_object_storage
from bookpile_server.database import SessionFactory
from bookpile_server.services.library_deletion_cleanup import (
    finalize_expired_account_deletions,
    finalize_expired_library_deletions,
)


def main() -> None:
    with SessionFactory() as session:
        storage = get_private_object_storage()
        library_count = finalize_expired_library_deletions(
            session,
            storage,
        )
        account_count = finalize_expired_account_deletions(session, storage)
    print(
        f"Finalized {library_count} expired library deletion(s) and "
        f"{account_count} expired account deletion(s)."
    )


if __name__ == "__main__":
    main()

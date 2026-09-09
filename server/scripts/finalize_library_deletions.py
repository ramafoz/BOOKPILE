"""Finalize expired shared-library deletions. Run from a scheduled job."""

from bookpile_server.config import get_settings
from bookpile_server.cover_storage import FilesystemCoverStorage
from bookpile_server.database import SessionFactory
from bookpile_server.services.library_deletion_cleanup import (
    finalize_expired_account_deletions,
    finalize_expired_library_deletions,
)


def main() -> None:
    settings = get_settings()
    with SessionFactory() as session:
        storage = FilesystemCoverStorage(settings.private_object_root)
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

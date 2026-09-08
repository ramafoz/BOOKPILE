from sqlalchemy.orm import Session

from ..repositories.storage import StorageRepository
from .storage import StorageService


def commit_with_storage(session: Session) -> None:
    """Flush domain changes, reconcile quota under locks, then commit once."""
    try:
        session.flush()
        StorageService(StorageRepository(session)).prepare_owned_library_usage()
        session.commit()
    except Exception:
        session.rollback()
        raise

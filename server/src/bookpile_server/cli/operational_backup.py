"""Operator-only commands for encrypted off-site service recovery."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from ..api.dependencies import get_private_object_storage
from ..backup_repository import S3BackupRepository
from ..config import get_settings
from ..cover_storage import FilesystemCoverStorage, S3PrivateObjectStorage
from ..database import engine
from ..models import Base
from ..operational_backup import OperationalBackupService, PostgresTools
from ..private_object_operations import expected_private_objects


def table_counts(connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in sorted(Base.metadata.tables):
        counts[name] = int(connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one())
    counts["alembic_version"] = int(connection.execute(text("SELECT count(*) FROM alembic_version")).scalar_one())
    return counts


def service_from_settings():
    settings = get_settings()
    required = {
        "endpoint": settings.operational_backup_s3_endpoint_url,
        "region": settings.operational_backup_s3_region,
        "bucket": settings.operational_backup_s3_bucket,
        "access key": settings.operational_backup_s3_access_key_id,
        "secret key": (
            settings.operational_backup_s3_secret_access_key.get_secret_value()
            if settings.operational_backup_s3_secret_access_key
            else None
        ),
    }
    missing = [name for name, value in required.items() if not value or not value.strip()]
    if missing:
        raise RuntimeError(f"Operational backup configuration requires: {', '.join(missing)}")
    endpoint = urlsplit(settings.operational_backup_s3_endpoint_url or "")
    insecure_rehearsal = settings.operational_backup_allow_insecure_endpoint and settings.environment == "development"
    schemes = {"http", "https"} if insecure_rehearsal else {"https"}
    if (
        endpoint.scheme not in schemes
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.path not in {"", "/"}
        or endpoint.query
        or endpoint.fragment
    ):
        raise RuntimeError("Operational backup endpoint must be one HTTPS origin")
    if settings.operational_backup_s3_bucket == settings.private_object_s3_bucket:
        raise RuntimeError("Operational backups require a bucket separate from active private objects")
    backup_secret = settings.operational_backup_encryption_secret.get_secret_value()
    if len(backup_secret) < 32 or (
        settings.operational_backup_encryption_key_id.strip().lower()
        in {"", "development", "unknown"}
    ):
        raise RuntimeError("Operational backup encryption key and explicit key ID are required")
    repository = S3BackupRepository.from_settings(settings)
    repository.check_ready()
    service = OperationalBackupService(
        repository,
        encryption_secret=settings.operational_backup_encryption_secret.get_secret_value(),
        encryption_key_id=settings.operational_backup_encryption_key_id,
        staging_root=settings.operational_backup_staging_root,
        progress=lambda event, details: print(
            json.dumps({"event": event, **details}, sort_keys=True),
            file=sys.stderr,
            flush=True,
        ),
    )
    return settings, service


def create_snapshot() -> dict:
    settings, service = service_from_settings()
    tools = PostgresTools(settings.database_url)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            snapshot = connection.execute(text("SELECT pg_export_snapshot()")).scalar_one()
            with Session(bind=connection) as session:
                expected = expected_private_objects(session)
                counts = table_counts(connection)
                schema_revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                result = service.create(
                    create_database_dump=lambda path: tools.dump(path, snapshot=snapshot),
                    source_objects=get_private_object_storage(),
                    expected_objects=expected,
                    table_counts=counts,
                    schema_revision=schema_revision,
                    deployment_revision=settings.deployment_revision,
                )
        finally:
            transaction.rollback()
    service.verify(result.backup_id)
    removed = service.prune(retention_days=settings.operational_backup_retention_days)
    return {
        "backup_id": str(result.backup_id),
        "created_at": result.created_at.isoformat(),
        "database_bytes": result.database_bytes,
        "object_count": result.object_count,
        "verified": True,
        "expired_snapshots_removed": len(removed),
    }


def target_object_storage(settings):
    backend = os.environ.get("BOOKPILE_RESTORE_PRIVATE_OBJECT_BACKEND", "s3")
    if backend == "filesystem":
        root = os.environ.get("BOOKPILE_RESTORE_PRIVATE_OBJECT_ROOT")
        if not root:
            raise RuntimeError("BOOKPILE_RESTORE_PRIVATE_OBJECT_ROOT is required")
        return FilesystemCoverStorage(Path(root))
    if backend != "s3":
        raise RuntimeError("Restore object backend must be s3 or filesystem")
    required = {
        "private_object_s3_endpoint_url": os.environ.get("BOOKPILE_RESTORE_PRIVATE_OBJECT_S3_ENDPOINT_URL"),
        "private_object_s3_region": os.environ.get("BOOKPILE_RESTORE_PRIVATE_OBJECT_S3_REGION"),
        "private_object_s3_bucket": os.environ.get("BOOKPILE_RESTORE_PRIVATE_OBJECT_S3_BUCKET"),
        "private_object_s3_access_key_id": os.environ.get("BOOKPILE_RESTORE_PRIVATE_OBJECT_S3_ACCESS_KEY_ID"),
        "private_object_s3_secret_access_key": os.environ.get("BOOKPILE_RESTORE_PRIVATE_OBJECT_S3_SECRET_ACCESS_KEY"),
        "private_object_s3_prefix": os.environ.get("BOOKPILE_RESTORE_PRIVATE_OBJECT_S3_PREFIX", "bookpile"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing restore object settings: {', '.join(missing)}")
    endpoint = urlsplit(str(required["private_object_s3_endpoint_url"]))
    insecure_rehearsal = settings.operational_backup_allow_insecure_endpoint and settings.environment == "development"
    schemes = {"http", "https"} if insecure_rehearsal else {"https"}
    if (
        endpoint.scheme not in schemes
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.path not in {"", "/"}
        or endpoint.query
        or endpoint.fragment
    ):
        raise RuntimeError("Restore object endpoint must be one HTTPS origin")
    required["private_object_s3_secret_access_key"] = SecretStr(str(required["private_object_s3_secret_access_key"]))
    return S3PrivateObjectStorage.from_settings(settings.model_copy(update=required))


def restore_snapshot(backup_id: UUID) -> dict:
    settings, service = service_from_settings()
    target_url = os.environ.get("BOOKPILE_RESTORE_DATABASE_URL")
    if not target_url:
        raise RuntimeError("BOOKPILE_RESTORE_DATABASE_URL is required")
    if not target_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("Restore target must be PostgreSQL")
    target_engine = create_engine(target_url, pool_pre_ping=True)
    target_storage = target_object_storage(settings)

    def ensure_empty() -> None:
        tables = inspect(target_engine).get_table_names(schema="public")
        if tables:
            raise RuntimeError("Restore target PostgreSQL database is not empty")

    def read_counts() -> dict[str, int]:
        with target_engine.connect() as connection:
            return table_counts(connection)

    try:
        manifest = service.restore(
            backup_id,
            target_objects=target_storage,
            ensure_database_empty=ensure_empty,
            restore_database=PostgresTools(target_url).restore,
            read_table_counts=read_counts,
        )
    finally:
        target_engine.dispose()
    return {
        "backup_id": str(backup_id),
        "schema_revision": manifest["schema_revision"],
        "object_count": len(manifest["objects"]),
        "table_count": len(manifest["table_counts"]),
        "restored": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("backup_id", type=UUID)
    subparsers.add_parser("prune")
    subparsers.add_parser("status")
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("backup_id", type=UUID)
    restore_parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    exit_code = 0
    if args.command == "create":
        payload = create_snapshot()
    elif args.command == "restore":
        if not args.apply:
            parser.error("restore requires --apply and refuses non-empty targets")
        payload = restore_snapshot(args.backup_id)
    else:
        settings, service = service_from_settings()
        if args.command == "verify":
            manifest = service.verify(args.backup_id)
            payload = {"backup_id": str(args.backup_id), "verified": True, "object_count": len(manifest["objects"])}
            exit_code = 0
        elif args.command == "prune":
            removed = service.prune(retention_days=settings.operational_backup_retention_days)
            payload = {"removed": len(removed)}
            exit_code = 0
        else:
            freshness = service.freshness()
            payload = {
                "healthy": freshness.healthy,
                "latest_backup_id": str(freshness.latest_backup_id) if freshness.latest_backup_id else None,
                "age_seconds": freshness.age_seconds,
            }
            exit_code = 0 if freshness.healthy else 1
    print(json.dumps(payload, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

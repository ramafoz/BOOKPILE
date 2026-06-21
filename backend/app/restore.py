import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from .database import database_path, init_database
from .exports import (
    BACKUP_FORMAT_VERSION,
    SCHEMA_VERSION,
    create_database_snapshot,
    create_full_backup,
    database_summary,
    sha256_file,
)


MAX_BACKUP_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
STAGING_TTL_SECONDS = 30 * 60
RESTORE_LOCK = threading.Lock()


def staging_root() -> Path:
    root = database_path().parent / ".restore-staging"
    root.mkdir(parents=True, exist_ok=True)
    return root


def backups_directory() -> Path:
    directory = database_path().parent.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def cleanup_expired_staging() -> None:
    now = time.time()
    for item in staging_root().iterdir():
        if item.is_dir() and now - item.stat().st_mtime > STAGING_TTL_SECONDS:
            shutil.rmtree(item, ignore_errors=True)


def safe_archive_name(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or name.endswith("/")
    ):
        raise ValueError(f"Unsafe or unsupported ZIP entry: {name}")
    normalized = path.as_posix()
    if normalized not in {"manifest.json", "bookpile.db"} and not (
        normalized.startswith("covers/")
        and len(path.parts) == 2
        and path.suffix.lower() == ".webp"
    ):
        raise ValueError(f"Unexpected file in backup: {normalized}")
    return normalized


def extract_and_validate_archive(archive_path: Path, destination: Path) -> dict:
    try:
        archive = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as exc:
        raise ValueError("The selected file is not a valid ZIP backup") from exc

    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_FILES:
            raise ValueError("The backup contains too many files")
        if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("The uncompressed backup is too large")

        entry_names: set[str] = set()
        for entry in entries:
            name = safe_archive_name(entry.filename)
            if name in entry_names:
                raise ValueError(f"Duplicate ZIP entry: {name}")
            entry_names.add(name)
            unix_mode = (entry.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ValueError("Symbolic links are not allowed in backups")

        if not {"manifest.json", "bookpile.db"} <= entry_names:
            raise ValueError("The backup is missing manifest.json or bookpile.db")

        manifest_bytes = archive.read("manifest.json")
        if len(manifest_bytes) > 1024 * 1024:
            raise ValueError("The backup manifest is unexpectedly large")
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("The backup manifest is invalid") from exc

        if manifest.get("format") != "BOOKPILE_BACKUP":
            raise ValueError("This ZIP is not a BOOKPILE backup")
        if manifest.get("backup_format_version") != BACKUP_FORMAT_VERSION:
            raise ValueError("This BOOKPILE backup format is not supported")
        schema_version = manifest.get("schema_version")
        if not isinstance(schema_version, int) or schema_version > SCHEMA_VERSION:
            raise ValueError(
                "This backup was created by a newer unsupported BOOKPILE version"
            )

        files = manifest.get("files")
        if not isinstance(files, dict):
            raise ValueError("The backup manifest has no valid file list")
        expected_entries = {"manifest.json", *files.keys()}
        if entry_names != expected_entries:
            raise ValueError("The ZIP contents do not match the backup manifest")

        destination.mkdir(parents=True, exist_ok=False)
        for name, metadata in files.items():
            safe_archive_name(name)
            if not isinstance(metadata, dict):
                raise ValueError(f"Invalid manifest metadata for {name}")
            target = destination / Path(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            if target.stat().st_size != metadata.get("size"):
                raise ValueError(f"Size mismatch for {name}")
            if sha256_file(target) != metadata.get("sha256"):
                raise ValueError(f"Checksum mismatch for {name}")

    summary = database_summary(destination / "bookpile.db")
    manifest_counts = manifest.get("counts")
    expected_counts = {
        **summary["counts"],
        "covers": len(summary["cover_filenames"]),
    }
    if manifest_counts != expected_counts:
        raise ValueError("Database counts do not match the backup manifest")

    expected_covers = {f"covers/{name}" for name in summary["cover_filenames"]}
    actual_covers = {
        name for name in files if name.startswith("covers/")
    }
    if actual_covers != expected_covers:
        raise ValueError("Cover files do not match the catalogue references")

    for cover_name in summary["cover_filenames"]:
        cover_path = destination / "covers" / cover_name
        try:
            with Image.open(cover_path) as image:
                image.verify()
                if image.format != "WEBP":
                    raise ValueError(
                        f"Cover is not in BOOKPILE WebP format: {cover_name}"
                    )
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(f"Invalid cover image: {cover_name}") from exc

    validation = {
        "token": destination.name,
        "created_at": manifest.get("created_at"),
        "schema_version": schema_version,
        "counts": expected_counts,
        "files": files,
        "filename": archive_path.name,
        "validated_at": datetime.now().isoformat(),
    }
    (destination / "validation.json").write_text(
        json.dumps(validation, indent=2),
        encoding="utf-8",
    )
    return validation


def stage_restore(archive_path: Path) -> dict:
    cleanup_expired_staging()
    token = uuid4().hex
    destination = staging_root() / token
    try:
        return extract_and_validate_archive(archive_path, destination)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def load_staged_restore(token: str) -> tuple[Path, dict]:
    if len(token) != 32 or any(character not in "0123456789abcdef" for character in token):
        raise ValueError("Invalid restore token")
    directory = staging_root() / token
    validation_path = directory / "validation.json"
    if not validation_path.is_file():
        raise ValueError("This restore session has expired or does not exist")
    if time.time() - validation_path.stat().st_mtime > STAGING_TTL_SECONDS:
        shutil.rmtree(directory, ignore_errors=True)
        raise ValueError("This restore session has expired")
    return directory, json.loads(validation_path.read_text(encoding="utf-8"))


def validate_staged_files(directory: Path, validation: dict) -> None:
    for name, metadata in validation["files"].items():
        path = directory / Path(*PurePosixPath(name).parts)
        if not path.is_file():
            raise ValueError(f"Staged backup file is missing: {name}")
        if path.stat().st_size != metadata["size"]:
            raise ValueError(f"Staged backup file size changed: {name}")
        if sha256_file(path) != metadata["sha256"]:
            raise ValueError(f"Staged backup checksum changed: {name}")

    summary = database_summary(directory / "bookpile.db")
    counts = {**summary["counts"], "covers": len(summary["cover_filenames"])}
    if counts != validation["counts"]:
        raise ValueError("The staged backup changed after validation")
    for filename in summary["cover_filenames"]:
        cover = directory / "covers" / filename
        if not cover.is_file():
            raise ValueError(f"Staged cover is missing: {filename}")
        try:
            with Image.open(cover) as image:
                image.verify()
                if image.format != "WEBP":
                    raise ValueError(
                        f"Staged cover format changed: {filename}"
                    )
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(f"Staged cover is invalid: {filename}") from exc


def perform_restore(token: str) -> dict:
    if not RESTORE_LOCK.acquire(blocking=False):
        raise ValueError("Another restore operation is already running")
    try:
        staged, validation = load_staged_restore(token)
        validate_staged_files(staged, validation)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safety_backup = backups_directory() / f"pre-restore-{timestamp}.zip"
        create_full_backup(safety_backup)

        data_directory = database_path().parent
        live_database = database_path()
        live_covers = data_directory / "covers"

        with tempfile.TemporaryDirectory(
            prefix="bookpile-rollback-",
            dir=data_directory.parent,
        ) as rollback_temp:
            rollback = Path(rollback_temp)
            rollback_database = rollback / "bookpile.db"
            rollback_covers = rollback / "covers"
            create_database_snapshot(rollback_database)
            if live_covers.is_dir():
                shutil.copytree(live_covers, rollback_covers)

            incoming_database = data_directory / "bookpile.restore-new.db"
            incoming_covers = data_directory / "covers.restore-new"
            incoming_database.unlink(missing_ok=True)
            shutil.rmtree(incoming_covers, ignore_errors=True)
            shutil.copy2(staged / "bookpile.db", incoming_database)
            if (staged / "covers").is_dir():
                shutil.copytree(staged / "covers", incoming_covers)
            else:
                incoming_covers.mkdir()

            try:
                os.replace(incoming_database, live_database)
                old_covers = data_directory / "covers.restore-old"
                shutil.rmtree(old_covers, ignore_errors=True)
                if live_covers.exists():
                    os.replace(live_covers, old_covers)
                os.replace(incoming_covers, live_covers)

                # Older valid backups may predate additive feature tables.
                # Bring the restored database up to the current schema before
                # handing it back to the running application.
                init_database()
                final_summary = database_summary(live_database)
                final_counts = {
                    **final_summary["counts"],
                    "covers": len(final_summary["cover_filenames"]),
                }
                if final_counts != validation["counts"]:
                    raise ValueError("Restored catalogue counts failed verification")
                shutil.rmtree(old_covers, ignore_errors=True)
            except Exception:
                shutil.copy2(rollback_database, live_database)
                shutil.rmtree(live_covers, ignore_errors=True)
                if rollback_covers.is_dir():
                    shutil.copytree(rollback_covers, live_covers)
                incoming_database.unlink(missing_ok=True)
                shutil.rmtree(incoming_covers, ignore_errors=True)
                raise

        shutil.rmtree(staged, ignore_errors=True)
        return {
            **validation,
            "safety_backup": safety_backup.name,
            "restored_at": datetime.now().isoformat(),
        }
    finally:
        RESTORE_LOCK.release()

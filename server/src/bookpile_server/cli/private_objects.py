"""Audit private objects or copy verified filesystem objects to configured S3."""

import argparse
import json
from hashlib import sha256

from ..api.dependencies import get_private_object_storage
from ..config import get_settings
from ..cover_storage import FilesystemCoverStorage
from ..database import SessionFactory
from ..private_object_operations import (
    audit_private_objects,
    expected_private_objects,
    migrate_private_objects,
    probe_private_object_storage,
)


def fingerprint(object_key: str) -> str:
    return sha256(object_key.encode("utf-8")).hexdigest()[:12]


def audit_payload(audit) -> dict:
    return {
        "expected_count": audit.expected_count,
        "stored_count": audit.stored_count,
        "exact": audit.is_exact,
        "missing": [fingerprint(key) for key in audit.missing],
        "orphaned": [fingerprint(key) for key in audit.orphaned],
        "mismatched": [fingerprint(key) for key in audit.mismatched],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("probe", "audit", "migrate-from-filesystem")
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy after source validation; omitted means a read-only plan.",
    )
    args = parser.parse_args()
    if args.command != "migrate-from-filesystem" and args.apply:
        parser.error("--apply is valid only for migrate-from-filesystem")

    settings = get_settings()
    selected = get_private_object_storage()
    if args.command == "probe":
        byte_size = probe_private_object_storage(selected)
        print(json.dumps({"ready": True, "verified_bytes": byte_size}, sort_keys=True))
        return 0

    with SessionFactory() as session:
        expected = expected_private_objects(session)
        if args.command == "audit":
            result = audit_private_objects(expected, selected.iter_objects())
            print(json.dumps(audit_payload(result), sort_keys=True))
            return 0 if result.is_exact else 1

        if settings.private_object_backend != "s3":
            parser.error("migrate-from-filesystem requires the configured S3 target")
        result = migrate_private_objects(
            expected,
            FilesystemCoverStorage(settings.private_object_root),
            selected,
            apply=args.apply,
        )
        payload = {
            "mode": "apply" if args.apply else "plan",
            "expected_count": result.expected_count,
            "already_verified": result.already_verified,
            "copied": result.copied,
            "planned": result.planned,
        }
        if result.final_audit is not None:
            payload["final_audit"] = audit_payload(result.final_audit)
        print(json.dumps(payload, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

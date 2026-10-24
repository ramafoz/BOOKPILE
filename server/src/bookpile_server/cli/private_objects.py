"""Audit private objects or copy verified filesystem objects to configured S3."""

import argparse
import json
from datetime import timedelta
from hashlib import sha256
from secrets import token_bytes
from uuid import uuid4

from ..api.dependencies import get_private_object_storage
from ..config import get_settings
from ..cover_storage import FilesystemCoverStorage
from ..database import SessionFactory
from ..models import SecurityEvent
from ..private_object_operations import (
    audit_private_objects,
    expected_private_objects,
    migrate_private_objects,
    probe_private_object_storage,
)
from ..private_object_recovery import (
    fingerprint_private_object_key,
    recover_abandoned_private_objects,
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
        "command",
        choices=(
            "probe",
            "audit",
            "migrate-from-filesystem",
            "recover-orphans",
            "inject-orphan-rehearsal",
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the selected migration or orphan-recovery operation.",
    )
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if (
        args.command not in {"migrate-from-filesystem", "recover-orphans"}
        and args.apply
    ):
        parser.error("--apply is valid only for a mutating command")

    settings = get_settings()
    selected = get_private_object_storage()
    if args.command == "probe":
        byte_size = probe_private_object_storage(selected)
        print(json.dumps({"ready": True, "verified_bytes": byte_size}, sort_keys=True))
        return 0

    with SessionFactory() as session:
        if args.command == "inject-orphan-rehearsal":
            if settings.environment != "staging":
                parser.error("orphan rehearsal injection is restricted to staging")
            if args.confirm != "STAGING-ORPHAN-REHEARSAL":
                parser.error(
                    "orphan rehearsal injection requires "
                    "--confirm STAGING-ORPHAN-REHEARSAL"
                )
            object_key = f"_orphan-rehearsal/{uuid4().hex}.bin"
            content = token_bytes(32)
            selected.put(object_key, content)
            fingerprint = fingerprint_private_object_key(
                settings.rate_limit_key_secret, object_key
            )
            try:
                session.add(
                    SecurityEvent(
                        event_type="private_object_orphan_rehearsal_created",
                        ip_address=None,
                        details={
                            "object_key_hmac": fingerprint,
                            "byte_size": len(content),
                            "deployment_revision": settings.deployment_revision,
                        },
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
                selected.delete(object_key)
                raise
            print(
                json.dumps(
                    {
                        "created": True,
                        "object_key_hmac": fingerprint,
                        "grace_hours": settings.private_object_orphan_grace_hours,
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "recover-orphans":
            if args.apply:
                if settings.private_object_orphan_cleanup_mode != "enforce":
                    parser.error(
                        "orphan deletion requires "
                        "BOOKPILE_SERVER_PRIVATE_OBJECT_ORPHAN_CLEANUP_MODE=enforce"
                    )
                if args.confirm != "DELETE-ABANDONED-PRIVATE-OBJECTS":
                    parser.error(
                        "orphan deletion requires "
                        "--confirm DELETE-ABANDONED-PRIVATE-OBJECTS"
                    )
            result = recover_abandoned_private_objects(
                session,
                selected,
                key_secret=settings.rate_limit_key_secret,
                deployment_revision=settings.deployment_revision,
                grace=timedelta(hours=settings.private_object_orphan_grace_hours),
                max_deletions=settings.private_object_orphan_max_deletions,
                apply=args.apply,
            )
            print(json.dumps(result.payload(), sort_keys=True))
            return 0

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

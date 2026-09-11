from io import BytesIO
from hashlib import sha256

import pytest
from botocore.exceptions import ClientError

from bookpile_server.cover_storage import (
    FilesystemCoverStorage,
    S3PrivateObjectStorage,
)
from bookpile_server.private_object_operations import (
    ExpectedPrivateObject,
    audit_private_objects,
    migrate_private_objects,
    probe_private_object_storage,
)


class FakeBody(BytesIO):
    pass


class FakePaginator:
    def __init__(self, client) -> None:
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str):
        assert Bucket == self.client.bucket
        yield {
            "Contents": [
                {"Key": key, "Size": len(value[0])}
                for key, value in sorted(self.client.objects.items())
                if key.startswith(Prefix)
            ]
        }


class FakeS3Client:
    def __init__(self, *, corrupt_writes: bool = False) -> None:
        self.bucket = "private-bucket"
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.corrupt_writes = corrupt_writes
        self.ready = True

    def put_object(self, *, Bucket, Key, Body, ContentLength, ContentType, Metadata):
        assert Bucket == self.bucket
        assert ContentLength == len(Body)
        assert ContentType == "application/octet-stream"
        content = bytes(Body) + (b"corrupt" if self.corrupt_writes else b"")
        self.objects[Key] = (content, dict(Metadata))

    def head_object(self, *, Bucket, Key):
        assert Bucket == self.bucket
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        content, metadata = self.objects[Key]
        return {"ContentLength": len(content), "Metadata": metadata}

    def get_object(self, *, Bucket, Key):
        assert Bucket == self.bucket
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        content, metadata = self.objects[Key]
        return {
            "Body": FakeBody(content),
            "ContentLength": len(content),
            "Metadata": metadata,
        }

    def delete_object(self, *, Bucket, Key):
        assert Bucket == self.bucket
        self.objects.pop(Key, None)

    def head_bucket(self, *, Bucket):
        assert Bucket == self.bucket
        if not self.ready:
            raise ClientError({"Error": {"Code": "403"}}, "HeadBucket")

    def get_paginator(self, operation: str):
        assert operation == "list_objects_v2"
        return FakePaginator(self)


def storage(client: FakeS3Client) -> S3PrivateObjectStorage:
    return S3PrivateObjectStorage(client, bucket=client.bucket, prefix="production")


def test_s3_round_trip_is_verified_private_and_inventory_safe() -> None:
    client = FakeS3Client()
    objects = storage(client)

    objects.check_ready()
    objects.put("covers/opaque.webp", b"private image")

    assert set(client.objects) == {"production/covers/opaque.webp"}
    assert objects.read("covers/opaque.webp") == b"private image"
    info = objects.stat("covers/opaque.webp")
    assert info is not None
    assert info.byte_size == 13
    assert len(info.sha256 or "") == 64
    assert list(objects.iter_objects()) == [info]

    objects.delete("covers/opaque.webp")
    objects.delete("covers/opaque.webp")
    assert objects.stat("covers/opaque.webp") is None


def test_s3_failed_write_verification_removes_untrusted_object() -> None:
    client = FakeS3Client(corrupt_writes=True)
    objects = storage(client)

    with pytest.raises(OSError, match="verification failed"):
        objects.put("covers/opaque.webp", b"private image")

    assert client.objects == {}


def test_s3_read_rejects_content_that_no_longer_matches_checksum() -> None:
    client = FakeS3Client()
    objects = storage(client)
    objects.put("profiles/opaque.webp", b"profile image")
    _content, metadata = client.objects["production/profiles/opaque.webp"]
    client.objects["production/profiles/opaque.webp"] = (b"tampered", metadata)

    with pytest.raises(OSError, match="integrity verification failed"):
        objects.read("profiles/opaque.webp")


def test_s3_readiness_and_keys_fail_closed() -> None:
    client = FakeS3Client()
    client.ready = False
    objects = storage(client)
    with pytest.raises(OSError, match="bucket is unavailable"):
        objects.check_ready()
    with pytest.raises(ValueError, match="Invalid private object key"):
        objects.read("../secret")


def test_filesystem_inventory_uses_the_same_logical_contract(tmp_path) -> None:
    objects = FilesystemCoverStorage(tmp_path / "private")
    objects.put("covers/opaque.webp", b"image")
    info = objects.stat("covers/opaque.webp")
    assert info is not None
    assert list(objects.iter_objects()) == [info]


def test_provider_probe_verifies_round_trip_and_leaves_no_object(tmp_path) -> None:
    objects = FilesystemCoverStorage(tmp_path / "private")

    assert probe_private_object_storage(objects, byte_size=37) == 37
    assert list(objects.iter_objects()) == []


def test_provider_probe_rejects_invalid_size(tmp_path) -> None:
    objects = FilesystemCoverStorage(tmp_path / "private")

    with pytest.raises(ValueError, match="positive"):
        probe_private_object_storage(objects, byte_size=0)


def test_inventory_identifies_missing_orphaned_and_mismatched_objects(tmp_path) -> None:
    objects = FilesystemCoverStorage(tmp_path / "private")
    objects.put("covers/mismatch.webp", b"wrong")
    objects.put("covers/orphan.webp", b"orphan")
    expected = [
        ExpectedPrivateObject("covers/missing.webp", 7, "0" * 64),
        ExpectedPrivateObject("covers/mismatch.webp", 5, "1" * 64),
    ]

    result = audit_private_objects(expected, objects.iter_objects())

    assert result.is_exact is False
    assert result.missing == ("covers/missing.webp",)
    assert result.orphaned == ("covers/orphan.webp",)
    assert result.mismatched == ("covers/mismatch.webp",)


def test_migration_plans_then_copies_without_removing_source(tmp_path) -> None:
    source = FilesystemCoverStorage(tmp_path / "source")
    target = FilesystemCoverStorage(tmp_path / "target")
    content = b"verified private object"
    source.put("covers/opaque.webp", content)
    expected = [
        ExpectedPrivateObject(
            "covers/opaque.webp",
            len(content),
            sha256(content).hexdigest(),
        )
    ]

    plan = migrate_private_objects(expected, source, target, apply=False)
    assert plan.planned == 1
    assert target.stat("covers/opaque.webp") is None

    applied = migrate_private_objects(expected, source, target, apply=True)
    assert applied.copied == 1
    assert applied.final_audit is not None and applied.final_audit.is_exact
    assert source.read("covers/opaque.webp") == content

    repeated = migrate_private_objects(expected, source, target, apply=True)
    assert repeated.already_verified == 1
    assert repeated.copied == 0


def test_migration_refuses_incomplete_source_and_orphaned_target(tmp_path) -> None:
    source = FilesystemCoverStorage(tmp_path / "source")
    target = FilesystemCoverStorage(tmp_path / "target")
    expected = [ExpectedPrivateObject("covers/missing.webp", 1, "0" * 64)]
    with pytest.raises(RuntimeError, match="Source storage"):
        migrate_private_objects(expected, source, target, apply=True)

    content = b"source"
    source.put("covers/source.webp", content)
    target.put("covers/orphan.webp", b"orphan")
    expected = [
        ExpectedPrivateObject(
            "covers/source.webp",
            len(content),
            sha256(content).hexdigest(),
        )
    ]
    with pytest.raises(RuntimeError, match="Target storage"):
        migrate_private_objects(expected, source, target, apply=True)

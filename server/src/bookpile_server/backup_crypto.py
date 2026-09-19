"""Streaming authenticated encryption for operational backup artefacts."""

from hashlib import sha256
from pathlib import Path
from secrets import token_bytes
from struct import pack, unpack
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b"BPBK1"
CHUNK_SIZE = 1024 * 1024


class BackupIntegrityError(RuntimeError):
    pass


def _cipher(secret: str) -> AESGCM:
    return AESGCM(sha256(secret.encode("utf-8")).digest())


def encrypt_file(source: Path, target: Path, *, secret: str, backup_id: UUID) -> tuple[int, str]:
    nonce_prefix = token_bytes(8)
    header = MAGIC + backup_id.bytes + nonce_prefix
    digest = sha256()
    written = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as incoming, target.open("wb") as outgoing:
        outgoing.write(header)
        digest.update(header)
        written += len(header)
        counter = 0
        while chunk := incoming.read(CHUNK_SIZE):
            if counter >= 2**32 - 1:
                raise ValueError("Backup artefact is too large")
            length = pack(">I", len(chunk))
            nonce = nonce_prefix + pack(">I", counter)
            encrypted = _cipher(secret).encrypt(nonce, chunk, header + length + pack(">I", counter))
            outgoing.write(length)
            outgoing.write(encrypted)
            digest.update(length)
            digest.update(encrypted)
            written += len(length) + len(encrypted)
            counter += 1
        terminator = pack(">I", 0)
        outgoing.write(terminator)
        digest.update(terminator)
        written += len(terminator)
    return written, digest.hexdigest()


def decrypt_file(source: Path, target: Path, *, secret: str, backup_id: UUID) -> tuple[int, str]:
    plaintext_hash = sha256()
    plaintext_size = 0
    temporary = target.with_suffix(target.suffix + ".partial")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as incoming, temporary.open("wb") as outgoing:
            header = incoming.read(len(MAGIC) + 24)
            if len(header) != len(MAGIC) + 24 or not header.startswith(MAGIC):
                raise BackupIntegrityError("Invalid backup artefact header")
            if UUID(bytes=header[len(MAGIC):len(MAGIC) + 16]) != backup_id:
                raise BackupIntegrityError("Backup artefact belongs to another snapshot")
            nonce_prefix = header[-8:]
            counter = 0
            while True:
                encoded_length = incoming.read(4)
                if len(encoded_length) != 4:
                    raise BackupIntegrityError("Truncated backup artefact")
                length = unpack(">I", encoded_length)[0]
                if length == 0:
                    if incoming.read(1):
                        raise BackupIntegrityError("Trailing backup artefact data")
                    break
                if length > CHUNK_SIZE:
                    raise BackupIntegrityError("Invalid backup chunk size")
                encrypted = incoming.read(length + 16)
                if len(encrypted) != length + 16:
                    raise BackupIntegrityError("Truncated backup chunk")
                nonce = nonce_prefix + pack(">I", counter)
                try:
                    chunk = _cipher(secret).decrypt(
                        nonce,
                        encrypted,
                        header + encoded_length + pack(">I", counter),
                    )
                except Exception as exc:
                    raise BackupIntegrityError("Backup authentication failed") from exc
                outgoing.write(chunk)
                plaintext_hash.update(chunk)
                plaintext_size += len(chunk)
                counter += 1
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return plaintext_size, plaintext_hash.hexdigest()

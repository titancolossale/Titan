# =====================================
# Titan Secure Embedding Storage
# =====================================

"""Authenticated embedding storage (Phase 20.11 / 20.12).

Phase 20.12 replaces XOR+HMAC envelopes with AES-GCM using a managed
application secret. Supports:
  • authenticated encryption
  • nonce safety
  • versioned encrypted envelopes
  • key identifier + future rotation
  • corruption / tamper detection
  • graceful migration from legacy XOR envelopes

Never log encryption keys, raw embeddings, decrypted payloads, or recordings.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

EMBEDDING_STORAGE_FORMAT_VERSION = 2
AES_GCM_ENVELOPE_VERSION = 2
LEGACY_XOR_ENVELOPE_VERSION = 1
DEFAULT_KEY_ID = "primary"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


class EmbeddingCodecKind(str, Enum):
    """How embedding vectors are persisted."""

    PLAINTEXT_JSON = "plaintext_json"
    # Legacy Phase 20.11 XOR+HMAC — decode-only for migration.
    ENCRYPTED_ENVELOPE = "encrypted_envelope"
    # Phase 20.12 authenticated AES-GCM.
    AES_GCM_V1 = "aes_gcm_v1"


@dataclass
class StoredEmbeddingBundle:
    """Private on-disk representation of one profile's embeddings."""

    profile_id: str
    user_id: str
    embedding_version: str
    vectors: list[list[float]]
    codec: EmbeddingCodecKind = EmbeddingCodecKind.PLAINTEXT_JSON
    integrity_hash: str = ""
    format_version: int = EMBEDDING_STORAGE_FORMAT_VERSION
    encrypted: bool = False
    created_at: datetime = field(default_factory=_utc_now)
    retain_raw_audio: bool = False
    key_id: str = DEFAULT_KEY_ID
    envelope_version: int = 0

    def compute_integrity_hash(self) -> str:
        payload = json.dumps(
            {
                "profile_id": self.profile_id,
                "user_id": self.user_id,
                "embedding_version": self.embedding_version,
                "vectors": self.vectors,
                "format_version": self.format_version,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def seal(self) -> StoredEmbeddingBundle:
        self.integrity_hash = self.compute_integrity_hash()
        return self

    def verify_integrity(self) -> bool:
        if not self.integrity_hash:
            return False
        return hmac.compare_digest(self.integrity_hash, self.compute_integrity_hash())

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "user_id": self.user_id,
            "embedding_version": self.embedding_version,
            "vectors": self.vectors,
            "codec": self.codec.value,
            "integrity_hash": self.integrity_hash,
            "format_version": self.format_version,
            "encrypted": self.encrypted,
            "created_at": _iso(self.created_at),
            "retain_raw_audio": self.retain_raw_audio,
            "key_id": self.key_id,
            "envelope_version": self.envelope_version,
        }

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> StoredEmbeddingBundle:
        codec_raw = str(data.get("codec", EmbeddingCodecKind.PLAINTEXT_JSON.value))
        try:
            codec = EmbeddingCodecKind(codec_raw)
        except ValueError:
            codec = EmbeddingCodecKind.PLAINTEXT_JSON
        created = data.get("created_at")
        created_at = (
            datetime.fromisoformat(str(created)) if created else _utc_now()
        )
        return cls(
            profile_id=str(data.get("profile_id") or ""),
            user_id=str(data.get("user_id") or ""),
            embedding_version=str(data.get("embedding_version") or ""),
            vectors=[
                [float(v) for v in row]
                for row in data.get("vectors", [])
                if isinstance(row, list)
            ],
            codec=codec,
            integrity_hash=str(data.get("integrity_hash") or ""),
            format_version=int(
                data.get("format_version", EMBEDDING_STORAGE_FORMAT_VERSION)
            ),
            encrypted=bool(data.get("encrypted", False)),
            created_at=created_at,
            retain_raw_audio=bool(data.get("retain_raw_audio", False)),
            key_id=str(data.get("key_id") or DEFAULT_KEY_ID),
            envelope_version=int(data.get("envelope_version") or 0),
        )


class EmbeddingStorageBackend(ABC):
    """Encryption-ready backend interface for private embedding vectors."""

    @abstractmethod
    def encode(self, bundle: StoredEmbeddingBundle) -> dict[str, Any]: ...

    @abstractmethod
    def decode(self, payload: dict[str, Any]) -> StoredEmbeddingBundle: ...

    @property
    @abstractmethod
    def codec(self) -> EmbeddingCodecKind: ...

    @property
    def encryption_enabled(self) -> bool:
        return False

    def health_dict(self) -> dict[str, Any]:
        return {
            "codec": self.codec.value,
            "encryption_enabled": self.encryption_enabled,
            "encryption_ready": True,
            "format_version": EMBEDDING_STORAGE_FORMAT_VERSION,
            "envelope_version": 0,
            "key_id": None,
            "migration_state": "n/a",
        }


class PlaintextEmbeddingStorage(EmbeddingStorageBackend):
    """Plaintext JSON vectors + integrity hash (dev / isolated fixtures)."""

    @property
    def codec(self) -> EmbeddingCodecKind:
        return EmbeddingCodecKind.PLAINTEXT_JSON

    def encode(self, bundle: StoredEmbeddingBundle) -> dict[str, Any]:
        sealed = bundle.seal()
        sealed.codec = EmbeddingCodecKind.PLAINTEXT_JSON
        sealed.encrypted = False
        sealed.envelope_version = 0
        return sealed.to_storage_dict()

    def decode(self, payload: dict[str, Any]) -> StoredEmbeddingBundle:
        bundle = StoredEmbeddingBundle.from_storage_dict(payload)
        if bundle.vectors and bundle.integrity_hash and not bundle.verify_integrity():
            raise EmbeddingCorruptionError(
                f"Integrity check failed for profile {bundle.profile_id}"
            )
        return bundle


def derive_storage_key(material: str | bytes, *, key_id: str = DEFAULT_KEY_ID) -> bytes:
    """Derive a 256-bit AES key from application secret material + key id."""
    if isinstance(material, str):
        raw = material.encode("utf-8")
    else:
        raw = material
    return hashlib.sha256(raw + b"|" + key_id.encode("utf-8")).digest()


class LegacyXorEnvelopeStorage(EmbeddingStorageBackend):
    """Decode-only legacy XOR+HMAC envelope (Phase 20.11 migration path)."""

    def __init__(self, *, key: bytes, key_id: str = DEFAULT_KEY_ID) -> None:
        self._key = key
        self._key_id = key_id

    @property
    def codec(self) -> EmbeddingCodecKind:
        return EmbeddingCodecKind.ENCRYPTED_ENVELOPE

    @property
    def encryption_enabled(self) -> bool:
        return True

    def _xor_bytes(self, data: bytes) -> bytes:
        key = self._key
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

    def encode(self, bundle: StoredEmbeddingBundle) -> dict[str, Any]:
        raise VoiceStorageMigrationError(
            "Legacy XOR envelope encode is disabled; use AES-GCM.",
            code="legacy_xor_encode_disabled",
        )

    def decode(self, payload: dict[str, Any]) -> StoredEmbeddingBundle:
        cipher = base64.b64decode(str(payload.get("ciphertext_b64") or ""))
        mac = str(payload.get("mac") or "")
        expected = hmac.new(self._key, cipher, hashlib.sha256).hexdigest()
        if not mac or not hmac.compare_digest(mac, expected):
            raise EmbeddingCorruptionError(
                f"Envelope MAC failed for profile {payload.get('profile_id')}"
            )
        plain = self._xor_bytes(cipher)
        try:
            vectors_raw = json.loads(plain.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EmbeddingCorruptionError(
                f"Envelope decrypt failed for profile {payload.get('profile_id')}"
            ) from exc
        vectors = [
            [float(v) for v in row]
            for row in vectors_raw
            if isinstance(row, list)
        ]
        bundle = StoredEmbeddingBundle(
            profile_id=str(payload.get("profile_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            embedding_version=str(payload.get("embedding_version") or ""),
            vectors=vectors,
            codec=EmbeddingCodecKind.ENCRYPTED_ENVELOPE,
            integrity_hash=str(payload.get("integrity_hash") or ""),
            format_version=int(
                payload.get("format_version", EMBEDDING_STORAGE_FORMAT_VERSION)
            ),
            encrypted=True,
            retain_raw_audio=bool(payload.get("retain_raw_audio", False)),
            key_id=str(payload.get("key_id") or self._key_id),
            envelope_version=LEGACY_XOR_ENVELOPE_VERSION,
        )
        if bundle.integrity_hash and not bundle.verify_integrity():
            raise EmbeddingCorruptionError(
                f"Integrity check failed for profile {bundle.profile_id}"
            )
        return bundle


class AesGcmEmbeddingStorage(EmbeddingStorageBackend):
    """AES-GCM authenticated encryption for speaker embedding vectors."""

    def __init__(
        self,
        *,
        key: bytes | None = None,
        key_id: str | None = None,
        allow_legacy_xor_decode: bool = True,
    ) -> None:
        env_key = os.getenv("TITAN_VOICE_EMBEDDING_STORAGE_KEY", "").strip()
        self._key_id = (
            key_id
            or os.getenv("TITAN_VOICE_EMBEDDING_KEY_ID", DEFAULT_KEY_ID).strip()
            or DEFAULT_KEY_ID
        )
        if key is not None:
            self._key = key if len(key) == 32 else hashlib.sha256(key).digest()
            self._dev_key = False
        elif env_key:
            self._key = derive_storage_key(env_key, key_id=self._key_id)
            self._dev_key = False
        else:
            # Explicit non-secret default — development fixtures only.
            self._key = derive_storage_key(
                "titan-voice-embedding-dev-key", key_id=self._key_id
            )
            self._dev_key = True
        self._allow_legacy = allow_legacy_xor_decode
        self._migrated_from_legacy = 0

    @property
    def codec(self) -> EmbeddingCodecKind:
        return EmbeddingCodecKind.AES_GCM_V1

    @property
    def encryption_enabled(self) -> bool:
        return True

    @property
    def key_id(self) -> str:
        return self._key_id

    def _aad(self, bundle_or_payload: StoredEmbeddingBundle | dict[str, Any]) -> bytes:
        if isinstance(bundle_or_payload, StoredEmbeddingBundle):
            profile_id = bundle_or_payload.profile_id
            user_id = bundle_or_payload.user_id
            version = bundle_or_payload.embedding_version
        else:
            profile_id = str(bundle_or_payload.get("profile_id") or "")
            user_id = str(bundle_or_payload.get("user_id") or "")
            version = str(bundle_or_payload.get("embedding_version") or "")
        return f"{profile_id}|{user_id}|{version}|{self._key_id}".encode("utf-8")

    def encode(self, bundle: StoredEmbeddingBundle) -> dict[str, Any]:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        sealed = bundle.seal()
        raw = json.dumps(sealed.vectors, separators=(",", ":")).encode("utf-8")
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, raw, self._aad(sealed))
        return {
            "profile_id": sealed.profile_id,
            "user_id": sealed.user_id,
            "embedding_version": sealed.embedding_version,
            "vectors": [],
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "codec": self.codec.value,
            "integrity_hash": sealed.integrity_hash,
            "format_version": EMBEDDING_STORAGE_FORMAT_VERSION,
            "encrypted": True,
            "created_at": _iso(sealed.created_at),
            "retain_raw_audio": sealed.retain_raw_audio,
            "key_id": self._key_id,
            "envelope_version": AES_GCM_ENVELOPE_VERSION,
            "dev_key": self._dev_key,
        }

    def decode(self, payload: dict[str, Any]) -> StoredEmbeddingBundle:
        codec_raw = str(payload.get("codec") or "")
        envelope_version = int(payload.get("envelope_version") or 0)

        # Legacy XOR+HMAC migration path.
        if (
            codec_raw == EmbeddingCodecKind.ENCRYPTED_ENVELOPE.value
            or (payload.get("mac") and not payload.get("nonce_b64"))
        ):
            if not self._allow_legacy:
                raise EmbeddingCorruptionError(
                    "Legacy XOR envelope rejected (migration disabled)"
                )
            # Legacy XOR used sha256(env) without key_id mixing.
            env_key = os.getenv("TITAN_VOICE_EMBEDDING_STORAGE_KEY", "").strip()
            if env_key:
                legacy_key = hashlib.sha256(env_key.encode("utf-8")).digest()
            else:
                legacy_key = hashlib.sha256(b"titan-voice-embedding-dev-key").digest()
            legacy = LegacyXorEnvelopeStorage(key=legacy_key, key_id=self._key_id)
            bundle = legacy.decode(payload)
            self._migrated_from_legacy += 1
            logger.info(
                "EMBEDDING_STORAGE_MIGRATED_LEGACY profile_id=%s envelope=xor→aes_gcm",
                bundle.profile_id,
            )
            return bundle

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            nonce = base64.b64decode(str(payload.get("nonce_b64") or ""))
            cipher = base64.b64decode(str(payload.get("ciphertext_b64") or ""))
        except Exception as exc:
            raise EmbeddingCorruptionError(
                f"Envelope framing corrupt for profile {payload.get('profile_id')}"
            ) from exc
        if len(nonce) != 12 or not cipher:
            raise EmbeddingCorruptionError(
                f"Envelope nonce/ciphertext invalid for profile {payload.get('profile_id')}"
            )
        aesgcm = AESGCM(self._key)
        try:
            plain = aesgcm.decrypt(nonce, cipher, self._aad(payload))
        except Exception as exc:
            raise EmbeddingCorruptionError(
                f"AES-GCM auth failed for profile {payload.get('profile_id')}"
            ) from exc
        try:
            vectors_raw = json.loads(plain.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EmbeddingCorruptionError(
                f"Envelope decrypt failed for profile {payload.get('profile_id')}"
            ) from exc
        vectors = [
            [float(v) for v in row]
            for row in vectors_raw
            if isinstance(row, list)
        ]
        bundle = StoredEmbeddingBundle(
            profile_id=str(payload.get("profile_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            embedding_version=str(payload.get("embedding_version") or ""),
            vectors=vectors,
            codec=EmbeddingCodecKind.AES_GCM_V1,
            integrity_hash=str(payload.get("integrity_hash") or ""),
            format_version=int(
                payload.get("format_version", EMBEDDING_STORAGE_FORMAT_VERSION)
            ),
            encrypted=True,
            retain_raw_audio=bool(payload.get("retain_raw_audio", False)),
            key_id=str(payload.get("key_id") or self._key_id),
            envelope_version=envelope_version or AES_GCM_ENVELOPE_VERSION,
        )
        if bundle.integrity_hash and not bundle.verify_integrity():
            raise EmbeddingCorruptionError(
                f"Integrity check failed for profile {bundle.profile_id}"
            )
        return bundle

    def health_dict(self) -> dict[str, Any]:
        return {
            "codec": self.codec.value,
            "encryption_enabled": True,
            "encryption_ready": True,
            "authenticated_encryption": True,
            "algorithm": "AES-256-GCM",
            "format_version": EMBEDDING_STORAGE_FORMAT_VERSION,
            "envelope_version": AES_GCM_ENVELOPE_VERSION,
            "key_id": self._key_id,
            "using_dev_key": self._dev_key,
            "legacy_xor_decode_enabled": self._allow_legacy,
            "migration_state": (
                "legacy_xor_decodes_observed"
                if self._migrated_from_legacy
                else "aes_gcm_v1"
            ),
            "legacy_migrations_observed": self._migrated_from_legacy,
        }


# Backward-compatible alias — production path is AES-GCM.
EnvelopeEmbeddingStorage = AesGcmEmbeddingStorage


class EmbeddingCorruptionError(Exception):
    """Raised when stored embeddings fail integrity / MAC checks."""

    def __init__(self, message: str, *, code: str = "embedding_corruption") -> None:
        super().__init__(message)
        self.code = code


class VoiceStorageMigrationError(Exception):
    """Raised when a forbidden legacy encode path is attempted."""

    def __init__(self, message: str, *, code: str = "storage_migration") -> None:
        super().__init__(message)
        self.code = code


def build_embedding_storage(
    *,
    prefer_encryption: bool | None = None,
) -> EmbeddingStorageBackend:
    """Select storage backend from settings / env."""
    if prefer_encryption is None:
        prefer_encryption = (
            os.getenv("TITAN_VOICE_EMBEDDING_ENCRYPTION", "false").lower() == "true"
        )
    if prefer_encryption:
        return AesGcmEmbeddingStorage()
    return PlaintextEmbeddingStorage()


def wrap_profile_embeddings(
    *,
    profile_id: str,
    user_id: str,
    embedding_version: str,
    embeddings: list[list[float]],
    backend: EmbeddingStorageBackend | None = None,
    retain_raw_audio: bool = False,
) -> dict[str, Any]:
    """Encode embeddings for private persistence."""
    storage = backend or build_embedding_storage()
    bundle = StoredEmbeddingBundle(
        profile_id=profile_id,
        user_id=user_id,
        embedding_version=embedding_version,
        vectors=[list(row) for row in embeddings],
        retain_raw_audio=retain_raw_audio,
    )
    return storage.encode(bundle)


def unwrap_profile_embeddings(
    payload: dict[str, Any] | list[list[float]] | None,
    *,
    backend: EmbeddingStorageBackend | None = None,
    profile_id: str = "",
    user_id: str = "",
    embedding_version: str = "",
) -> list[list[float]]:
    """Decode embeddings from storage; supports legacy bare list format."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [[float(v) for v in row] for row in payload if isinstance(row, list)]
    if not isinstance(payload, dict):
        return []
    codec = str(payload.get("codec") or "")
    if (
        "ciphertext_b64" in payload
        or codec
        in {
            EmbeddingCodecKind.ENCRYPTED_ENVELOPE.value,
            EmbeddingCodecKind.AES_GCM_V1.value,
        }
    ):
        storage = backend or AesGcmEmbeddingStorage()
        return storage.decode(payload).vectors
    if "vectors" in payload:
        storage = backend or PlaintextEmbeddingStorage()
        try:
            return storage.decode(payload).vectors
        except EmbeddingCorruptionError:
            raise
        except Exception:
            return [
                [float(v) for v in row]
                for row in payload.get("vectors", [])
                if isinstance(row, list)
            ]
    return []


def detect_duplicate_user_embeddings(
    *,
    candidate: list[list[float]],
    existing_by_user: dict[str, list[list[float]]],
    exclude_user_id: str | None = None,
    threshold: float = 0.92,
    similarity_fn: Any | None = None,
) -> str | None:
    """Return conflicting user_id when candidate collides with another user."""
    from voice.embedding_provider import cosine_similarity, mean_embedding

    sim = similarity_fn or cosine_similarity
    cand_mean = mean_embedding(candidate)
    if not cand_mean:
        return None
    for user_id, embeddings in existing_by_user.items():
        if exclude_user_id and user_id == exclude_user_id:
            continue
        other = mean_embedding(embeddings)
        if not other:
            continue
        if sim(cand_mean, other) >= threshold:
            return user_id
    return None

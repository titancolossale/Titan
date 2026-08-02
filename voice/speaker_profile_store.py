# =====================================
# Titan Speaker Profile Store
# =====================================

"""Production-safe persistence for voice identity profiles (Phase 20.2 / 20.11 / 20.13).

Stores derived embeddings only — never raw enrollment audio. Public list/get
APIs return safe metadata without biometric representations.

Phase 20.11 adds schema v4: integrity hashes, encryption-ready codec metadata,
production-trust flags, and corruption detection on load.

Phase 20.13 wires AES-GCM into the save/load path (schema v5): when
``TITAN_VOICE_EMBEDDING_ENCRYPTION=true``, profile and in-flight session
embeddings are persisted as authenticated envelopes with empty plaintext
``embeddings`` / ``embedding`` fields. Durable file lives under ``TITAN_DATA_DIR``
(Railway Volume ``/app/data``).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from voice.embedding_provider import is_dev_fallback_version, is_production_trusted_version
from voice.embedding_storage import (
    EmbeddingCorruptionError,
    StoredEmbeddingBundle,
    build_embedding_storage,
    detect_duplicate_user_embeddings,
    unwrap_profile_embeddings,
    wrap_profile_embeddings,
)
from voice.enrollment_models import (
    EMBEDDING_VERSION,
    EnrollmentSession,
    EnrollmentStatus,
    METADATA_VERSION,
    SpeakerIdentityProfile,
)
from voice.enrollment_audit import EnrollmentAuditEvent
from voice.exceptions import VoiceConfigurationError

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SpeakerProfileStore:
    """Manager for speaker identity profiles + enrollment session persistence."""

    def __init__(self, file_path: Path | str | None = None) -> None:
        self.file_path = Path(file_path) if file_path else None
        self._profiles: dict[str, SpeakerIdentityProfile] = {}
        self._active_by_user: dict[str, str] = {}
        self._sessions: dict[str, EnrollmentSession] = {}
        self._audit_events: list[EnrollmentAuditEvent] = []
        self._loaded = False
        self._corruption_events: list[dict[str, Any]] = []
        self._storage = build_embedding_storage()
        self._retain_raw_audio = False

    def default_schema(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "profiles": {},
            "active_by_user": {},
            "enrollment_sessions": {},
            "audit_history": [],
            "corruption_events": [],
            "storage": self._storage.health_dict(),
        }

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self.file_path is None or not self.file_path.exists():
            return
        try:
            with self.file_path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Corrupt speaker profile store %s: %s", self.file_path, exc)
            raise VoiceConfigurationError(
                f"Failed to load speaker profile store: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            return
        schema = int(raw.get("schema_version", 1))
        if schema <= 1:
            self._load_legacy_v1(raw)
        else:
            self._load_corruption(raw)
            self._load_v2(raw)
            self._load_audit(raw)

    def save(self) -> None:
        if self.file_path is None:
            return
        self.load()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "profiles": {
                pid: self._profile_to_storage(profile)
                for pid, profile in self._profiles.items()
            },
            "active_by_user": dict(self._active_by_user),
            "enrollment_sessions": {
                sid: self._session_to_storage(session)
                for sid, session in self._sessions.items()
            },
            "audit_history": [event.to_dict() for event in self._audit_events[-500:]],
            "corruption_events": list(self._corruption_events[-100:]),
            "storage": self._storage.health_dict(),
        }
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4, ensure_ascii=False)

    def _profile_to_storage(self, profile: SpeakerIdentityProfile) -> dict[str, Any]:
        """Persist profile with integrity-sealed (and optionally AES-GCM) embeddings."""
        base = profile.to_storage_dict()
        # Never retain raw audio in profile storage unless explicitly configured.
        base["retain_raw_audio"] = bool(self._retain_raw_audio)
        base["production_trusted"] = bool(
            getattr(profile, "production_trusted", False)
        )
        if profile.embeddings:
            bundle = StoredEmbeddingBundle(
                profile_id=profile.profile_id,
                user_id=profile.user_id,
                embedding_version=profile.embedding_version,
                vectors=[list(row) for row in profile.embeddings],
                retain_raw_audio=self._retain_raw_audio,
            )
            encoded = self._storage.encode(bundle)
            base["integrity_hash"] = encoded.get("integrity_hash")
            profile.integrity_hash = encoded.get("integrity_hash")
            if self._storage.encryption_enabled:
                # No plaintext vectors on disk when AES-GCM is active.
                base["embeddings"] = []
                base["embedding_bundle"] = encoded
            else:
                base["embeddings"] = [list(row) for row in profile.embeddings]
                base["embedding_bundle"] = {
                    "integrity_hash": encoded.get("integrity_hash"),
                    "codec": encoded.get("codec"),
                    "format_version": encoded.get("format_version"),
                    "encrypted": False,
                }
        return base

    def _session_to_storage(self, session: EnrollmentSession) -> dict[str, Any]:
        """Persist enrollment session; encrypt per-sample embeddings when enabled."""
        raw = session.to_storage_dict()
        if not self._storage.encryption_enabled:
            return raw
        sealed_samples: list[dict[str, Any]] = []
        for sample in raw.get("samples", []):
            if not isinstance(sample, dict):
                continue
            item = dict(sample)
            embedding = item.get("embedding") or []
            if embedding:
                envelope = wrap_profile_embeddings(
                    profile_id=f"{session.session_id}:{item.get('sample_id', 'sample')}",
                    user_id=session.user_id,
                    embedding_version=session.embedding_version,
                    embeddings=[list(embedding)],
                    backend=self._storage,
                    retain_raw_audio=False,
                )
                item["embedding"] = []
                item["embedding_envelope"] = envelope
            sealed_samples.append(item)
        raw["samples"] = sealed_samples
        return raw

    def _load_profile_embeddings(self, payload: dict[str, Any]) -> list[list[float]]:
        """Decode profile embeddings from AES-GCM envelope or legacy plaintext."""
        bundle = payload.get("embedding_bundle")
        if isinstance(bundle, dict) and (
            bundle.get("ciphertext_b64")
            or bundle.get("encrypted")
            or str(bundle.get("codec") or "") in {"aes_gcm_v1", "encrypted_envelope"}
        ):
            try:
                return unwrap_profile_embeddings(
                    bundle,
                    backend=self._storage,
                    profile_id=str(payload.get("profile_id") or ""),
                    user_id=str(payload.get("user_id") or ""),
                    embedding_version=str(payload.get("embedding_version") or ""),
                )
            except EmbeddingCorruptionError:
                raise
        embeddings = payload.get("embeddings") or []
        if isinstance(embeddings, list) and embeddings:
            return [
                [float(v) for v in row]
                for row in embeddings
                if isinstance(row, list)
            ]
        return []

    def _hydrate_session_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Decrypt sample embedding envelopes before EnrollmentSession.from_dict."""
        samples_in = payload.get("samples", [])
        if not isinstance(samples_in, list):
            return payload
        hydrated = dict(payload)
        samples_out: list[dict[str, Any]] = []
        for item in samples_in:
            if not isinstance(item, dict):
                continue
            sample = dict(item)
            envelope = sample.get("embedding_envelope")
            embedding = sample.get("embedding") or []
            if isinstance(envelope, dict) and (
                envelope.get("ciphertext_b64") or envelope.get("encrypted")
            ):
                try:
                    vectors = unwrap_profile_embeddings(
                        envelope,
                        backend=self._storage,
                        profile_id=str(payload.get("session_id") or ""),
                        user_id=str(payload.get("user_id") or ""),
                        embedding_version=str(payload.get("embedding_version") or ""),
                    )
                    sample["embedding"] = list(vectors[0]) if vectors else []
                except EmbeddingCorruptionError as exc:
                    logger.error(
                        "Enrollment sample envelope corrupt session=%s sample=%s: %s",
                        payload.get("session_id"),
                        sample.get("sample_id"),
                        exc,
                    )
                    sample["embedding"] = []
                sample.pop("embedding_envelope", None)
            elif embedding:
                sample["embedding"] = [float(v) for v in embedding]
            samples_out.append(sample)
        hydrated["samples"] = samples_out
        return hydrated

    def _load_corruption(self, raw: dict[str, Any]) -> None:
        events = raw.get("corruption_events", [])
        if isinstance(events, list):
            self._corruption_events = [e for e in events if isinstance(e, dict)][-100:]

    def _load_v2(self, raw: dict[str, Any]) -> None:
        profiles = raw.get("profiles", {})
        if isinstance(profiles, dict):
            for pid, payload in profiles.items():
                if not isinstance(payload, dict):
                    continue
                try:
                    merged = {**payload, "profile_id": payload.get("profile_id", pid)}
                    try:
                        vectors = self._load_profile_embeddings(merged)
                    except EmbeddingCorruptionError as exc:
                        logger.error(
                            "Embedding decrypt/integrity failure for profile %s: %s",
                            pid,
                            exc,
                        )
                        self._corruption_events.append(
                            {
                                "profile_id": str(pid),
                                "user_id": str(payload.get("user_id") or ""),
                                "error": "embedding_corruption_detected",
                                "at": _utc_now().isoformat(),
                            }
                        )
                        merged = {**merged, "embeddings": [], "active": False}
                        profile = SpeakerIdentityProfile.from_dict(merged)
                        profile.active = False
                        profile.failure_reason = "embedding_corruption_detected"
                        if profile.user_id:
                            self._profiles[profile.profile_id] = profile
                        continue
                    merged["embeddings"] = vectors
                    profile = SpeakerIdentityProfile.from_dict(merged)
                except Exception as exc:
                    logger.error("Corrupt profile payload %s: %s", pid, exc)
                    self._corruption_events.append(
                        {
                            "profile_id": str(pid),
                            "error": "profile_parse_failed",
                            "at": _utc_now().isoformat(),
                        }
                    )
                    continue
                # Integrity check when sealed plaintext bundle present.
                integrity = payload.get("integrity_hash") or profile.integrity_hash
                if integrity and profile.embeddings:
                    bundle = StoredEmbeddingBundle(
                        profile_id=profile.profile_id,
                        user_id=profile.user_id,
                        embedding_version=profile.embedding_version,
                        vectors=profile.embeddings,
                        integrity_hash=str(integrity),
                    )
                    if not bundle.verify_integrity():
                        logger.error(
                            "Embedding integrity failure for profile %s",
                            profile.profile_id,
                        )
                        self._corruption_events.append(
                            {
                                "profile_id": profile.profile_id,
                                "user_id": profile.user_id,
                                "error": "embedding_integrity_failed",
                                "at": _utc_now().isoformat(),
                            }
                        )
                        # Do not activate corrupted biometric templates.
                        profile.active = False
                        profile.failure_reason = "embedding_corruption_detected"
                # Histogram / dev fallback never silently production-trusted.
                if is_dev_fallback_version(profile.embedding_version):
                    profile.production_trusted = False
                elif is_production_trusted_version(profile.embedding_version):
                    profile.production_trusted = True
                if profile.user_id:
                    self._profiles[profile.profile_id] = profile
        active = raw.get("active_by_user", {})
        if isinstance(active, dict):
            for user, pid in active.items():
                profile = self._profiles.get(str(pid))
                if profile is None:
                    continue
                if profile.failure_reason == "embedding_corruption_detected":
                    continue
                self._active_by_user[str(user)] = str(pid)
        sessions = raw.get("enrollment_sessions", {})
        if isinstance(sessions, dict):
            for sid, payload in sessions.items():
                if not isinstance(payload, dict):
                    continue
                hydrated = self._hydrate_session_payload(
                    {**payload, "session_id": payload.get("session_id", sid)}
                )
                session = EnrollmentSession.from_dict(hydrated)
                self._sessions[session.session_id] = session

    def _load_audit(self, raw: dict[str, Any]) -> None:
        events = raw.get("audit_history", [])
        if not isinstance(events, list):
            return
        loaded: list[EnrollmentAuditEvent] = []
        for item in events:
            if isinstance(item, dict):
                loaded.append(EnrollmentAuditEvent.from_dict(item))
        self._audit_events = loaded[-500:]

    def append_audit(self, event: EnrollmentAuditEvent) -> EnrollmentAuditEvent:
        """Append one audit event (never stores embeddings/audio)."""
        self.load()
        self._audit_events.append(event)
        if len(self._audit_events) > 500:
            self._audit_events = self._audit_events[-500:]
        self.save()
        return event

    def list_audit_history(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.load()
        items = self._audit_events
        if user_id:
            items = [e for e in items if e.user_id == user_id]
        if session_id:
            items = [e for e in items if e.session_id == session_id]
        return [e.to_dict() for e in items[-max(1, limit) :]]

    def next_profile_version(self, user_id: str) -> int:
        """Return the next profile version for replacement enrollment."""
        self.load()
        versions = [
            p.profile_version
            for p in self._profiles.values()
            if p.user_id == user_id
        ]
        return (max(versions) + 1) if versions else 1

    def _load_legacy_v1(self, raw: dict[str, Any]) -> None:
        """Migrate Phase 20.1 flat user→embeddings schema."""
        profiles = raw.get("profiles", {})
        if not isinstance(profiles, dict):
            return
        for user, payload in profiles.items():
            if not isinstance(payload, dict):
                continue
            user_id = str(payload.get("user") or user)
            embeddings = [
                [float(v) for v in row]
                for row in payload.get("embeddings", [])
                if isinstance(row, list)
            ]
            profile = SpeakerIdentityProfile(
                profile_id=f"legacy-{user_id}",
                user_id=user_id,
                display_name=user_id,
                enrollment_status=EnrollmentStatus.ENROLLED,
                sample_count=int(payload.get("sample_count", len(embeddings))),
                embedding_version=EMBEDDING_VERSION,
                confidence=1.0,
                quality_score=1.0,
                created_at=_utc_now(),
                updated_at=_utc_now(),
                last_verified_at=_utc_now(),
                active=True,
                metadata_version=METADATA_VERSION,
                embeddings=embeddings,
                production_trusted=False,
                trust_level="development_fallback",
            )
            self._profiles[profile.profile_id] = profile
            self._active_by_user[user_id] = profile.profile_id

    # --- profile CRUD -------------------------------------------------

    def create_profile(self, profile: SpeakerIdentityProfile) -> SpeakerIdentityProfile:
        self.load()
        profile.updated_at = _utc_now()
        self._profiles[profile.profile_id] = profile
        self.save()
        return profile

    def get_profile(self, profile_id: str) -> SpeakerIdentityProfile | None:
        self.load()
        return self._profiles.get(profile_id)

    def update_profile(self, profile: SpeakerIdentityProfile) -> SpeakerIdentityProfile:
        self.load()
        if profile.profile_id not in self._profiles:
            raise VoiceConfigurationError(f"Unknown profile {profile.profile_id}")
        profile.updated_at = _utc_now()
        self._profiles[profile.profile_id] = profile
        self.save()
        return profile

    def activate_profile(self, profile_id: str) -> SpeakerIdentityProfile:
        self.load()
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise VoiceConfigurationError(f"Unknown profile {profile_id}")
        if profile.enrollment_status == EnrollmentStatus.REVOKED:
            raise VoiceConfigurationError("Cannot activate a revoked profile")
        # Deactivate other profiles for the same user.
        for other in self._profiles.values():
            if other.user_id == profile.user_id and other.profile_id != profile_id:
                if other.active:
                    other.active = False
                    other.updated_at = _utc_now()
        profile.active = True
        profile.enrollment_status = EnrollmentStatus.ENROLLED
        profile.updated_at = _utc_now()
        self._active_by_user[profile.user_id] = profile_id
        self.save()
        return profile

    def deactivate_profile(self, profile_id: str) -> SpeakerIdentityProfile:
        self.load()
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise VoiceConfigurationError(f"Unknown profile {profile_id}")
        profile.active = False
        profile.updated_at = _utc_now()
        if self._active_by_user.get(profile.user_id) == profile_id:
            del self._active_by_user[profile.user_id]
        self.save()
        return profile

    def revoke_profile(self, profile_id: str) -> SpeakerIdentityProfile:
        self.load()
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise VoiceConfigurationError(f"Unknown profile {profile_id}")
        profile.active = False
        profile.enrollment_status = EnrollmentStatus.REVOKED
        profile.revoked_at = _utc_now()
        profile.updated_at = profile.revoked_at
        if self._active_by_user.get(profile.user_id) == profile_id:
            del self._active_by_user[profile.user_id]
        self.save()
        return profile

    def replace_active_profile(
        self,
        *,
        new_profile_id: str,
        old_profile_id: str | None,
    ) -> SpeakerIdentityProfile:
        """Atomically activate ``new_profile_id`` and revoke/archive the old one."""
        self.load()
        new_profile = self._profiles.get(new_profile_id)
        if new_profile is None:
            raise VoiceConfigurationError(f"Unknown profile {new_profile_id}")
        if old_profile_id and old_profile_id in self._profiles:
            old = self._profiles[old_profile_id]
            old.active = False
            old.enrollment_status = EnrollmentStatus.REVOKED
            old.revoked_at = _utc_now()
            old.updated_at = old.revoked_at
        for other in self._profiles.values():
            if (
                other.user_id == new_profile.user_id
                and other.profile_id != new_profile_id
                and other.active
            ):
                other.active = False
                other.updated_at = _utc_now()
        new_profile.active = True
        new_profile.enrollment_status = EnrollmentStatus.ENROLLED
        new_profile.updated_at = _utc_now()
        self._active_by_user[new_profile.user_id] = new_profile_id
        self.save()
        return new_profile

    def get_active_profile(self, user_id: str) -> SpeakerIdentityProfile | None:
        self.load()
        pid = self._active_by_user.get(user_id)
        if not pid:
            return None
        profile = self._profiles.get(pid)
        if profile is None or not profile.active:
            return None
        if profile.enrollment_status == EnrollmentStatus.REVOKED:
            return None
        return profile

    def list_active_embeddings(self) -> dict[str, list[list[float]]]:
        """Internal recognition feed — embeddings never returned by public APIs."""
        self.load()
        result: dict[str, list[list[float]]] = {}
        for user_id, pid in self._active_by_user.items():
            profile = self._profiles.get(pid)
            if (
                profile is None
                or not profile.active
                or profile.enrollment_status != EnrollmentStatus.ENROLLED
                or not profile.embeddings
                or profile.failure_reason == "embedding_corruption_detected"
            ):
                continue
            result[user_id] = [list(row) for row in profile.embeddings]
        return result

    def find_duplicate_user(
        self,
        *,
        candidate_embeddings: list[list[float]],
        exclude_user_id: str | None = None,
        threshold: float = 0.92,
    ) -> str | None:
        """Return conflicting user_id when candidate collides with another user."""
        active = self.list_active_embeddings()
        return detect_duplicate_user_embeddings(
            candidate=candidate_embeddings,
            existing_by_user=active,
            exclude_user_id=exclude_user_id,
            threshold=threshold,
        )

    def list_corruption_events(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.load()
        return list(self._corruption_events[-max(1, limit) :])

    def storage_health(self) -> dict[str, Any]:
        return {
            **self._storage.health_dict(),
            "retain_raw_audio": self._retain_raw_audio,
            "schema_version": SCHEMA_VERSION,
            "corruption_event_count": len(self._corruption_events),
            "profiles_path": str(self.file_path) if self.file_path else None,
            "plaintext_embeddings_on_disk": not self._storage.encryption_enabled,
        }

    def list_safe_profiles(self, *, user_id: str | None = None) -> list[dict[str, Any]]:
        self.load()
        items = []
        for profile in self._profiles.values():
            if user_id and profile.user_id != user_id:
                continue
            items.append(profile.to_public_dict())
        items.sort(key=lambda item: item.get("updated_at") or "")
        return items

    def iter_profiles(self) -> list[SpeakerIdentityProfile]:
        """Internal iteration over all profiles (includes embeddings)."""
        self.load()
        return list(self._profiles.values())

    def list_sessions_for_user(self, user_id: str) -> list[EnrollmentSession]:
        """All enrollment sessions for a user (history + in-flight)."""
        self.load()
        sessions = [s for s in self._sessions.values() if s.user_id == user_id]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    # --- enrollment sessions ------------------------------------------

    def save_session(self, session: EnrollmentSession) -> EnrollmentSession:
        self.load()
        session.updated_at = _utc_now()
        self._sessions[session.session_id] = session
        self.save()
        return session

    def get_session(self, session_id: str) -> EnrollmentSession | None:
        self.load()
        return self._sessions.get(session_id)

    def get_active_session_for_user(self, user_id: str) -> EnrollmentSession | None:
        self.load()
        active_states = {
            EnrollmentStatus.AWAITING_CONSENT,
            EnrollmentStatus.COLLECTING,
            EnrollmentStatus.VALIDATING,
            EnrollmentStatus.BUILDING_PROFILE,
            EnrollmentStatus.VERIFYING,
        }
        candidates = [
            s
            for s in self._sessions.values()
            if s.user_id == user_id and s.status in active_states
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda s: s.updated_at, reverse=True)
        return candidates[0]

    def delete_session(self, session_id: str) -> None:
        self.load()
        if session_id in self._sessions:
            del self._sessions[session_id]
            self.save()

# =====================================
# Titan Enrollment Audit History
# =====================================

"""Append-only enrollment audit trail (Phase 20.10A).

Never stores embeddings or raw audio — event metadata only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


@dataclass
class EnrollmentAuditEvent:
    """One immutable enrollment audit event (safe for persistence / API)."""

    event_id: str
    event_type: str
    user_id: str
    session_id: str | None = None
    profile_id: str | None = None
    workflow_state: str | None = None
    attempt_number: int = 1
    detail: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "profile_id": self.profile_id,
            "workflow_state": self.workflow_state,
            "attempt_number": self.attempt_number,
            "detail": self.detail,
            "metadata": dict(self.metadata),
            "created_at": _iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnrollmentAuditEvent:
        return cls(
            event_id=str(data.get("event_id") or uuid4()),
            event_type=str(data.get("event_type") or "unknown"),
            user_id=str(data.get("user_id") or ""),
            session_id=(
                str(data["session_id"]) if data.get("session_id") else None
            ),
            profile_id=(
                str(data["profile_id"]) if data.get("profile_id") else None
            ),
            workflow_state=(
                str(data["workflow_state"]) if data.get("workflow_state") else None
            ),
            attempt_number=int(data.get("attempt_number", 1)),
            detail=str(data["detail"]) if data.get("detail") else None,
            metadata=dict(data.get("metadata") or {}),
            created_at=(
                datetime.fromisoformat(str(data["created_at"]))
                if data.get("created_at")
                else _utc_now()
            ),
        )


def make_audit_event(
    *,
    event_type: str,
    user_id: str,
    session_id: str | None = None,
    profile_id: str | None = None,
    workflow_state: str | None = None,
    attempt_number: int = 1,
    detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> EnrollmentAuditEvent:
    """Factory for audit events — strips unsafe keys from metadata."""
    safe_meta = dict(metadata or {})
    for banned in ("embedding", "embeddings", "audio", "audio_bytes", "raw_audio"):
        safe_meta.pop(banned, None)
    return EnrollmentAuditEvent(
        event_id=str(uuid4()),
        event_type=event_type,
        user_id=user_id,
        session_id=session_id,
        profile_id=profile_id,
        workflow_state=workflow_state,
        attempt_number=attempt_number,
        detail=detail,
        metadata=safe_meta,
    )

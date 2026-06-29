# =====================================
# Titan Conversation Models
# =====================================

"""Structured turn model for the conversation engine (Phase 7 — P7-010)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ConversationTurn:
    """Single dialogue turn with speaker attribution and optional metadata."""

    speaker: str
    message: str
    user: str
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    timestamp: str = field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize turn for session persistence."""
        return {
            "id": self.id,
            "user": self.user,
            "speaker": self.speaker,
            "message": self.message,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationTurn:
        """Deserialize turn from session JSON."""
        return cls(
            id=str(data.get("id", uuid4().hex[:12])),
            user=str(data.get("user", "Nolan")),
            speaker=str(data.get("speaker", "Unknown")),
            message=str(data.get("message", "")),
            timestamp=str(data.get("timestamp", _utc_now_iso())),
            metadata=dict(data.get("metadata") or {}),
        )

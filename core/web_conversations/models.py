# =====================================
# Titan Web Conversation Models
# =====================================

"""Dataclass records for durable web conversations (Phase 12.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MessageStatus(str, Enum):
    """Lifecycle status for a persisted chat message."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageRole(str, Enum):
    """Visible chat roles — system/tool never exposed as user-visible history by default."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ConversationRecord:
    """Durable conversation metadata scoped to an authenticated user."""

    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    archived: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "archived": self.archived,
            "metadata": dict(self.metadata),
        }


@dataclass
class MessageRecord:
    """Durable chat message — never stores chain-of-thought or API keys."""

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    request_id: str | None = None
    status: str = MessageStatus.COMPLETED.value
    error_code: str | None = None
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sequence: int = 0

    def to_dict(self, *, include_internal: bool = False) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "request_id": self.request_id,
            "status": self.status,
            "error_code": self.error_code,
            "sequence": self.sequence,
        }
        if include_internal:
            payload["provider"] = self.provider
            payload["model"] = self.model
            payload["metadata"] = dict(self.metadata)
        return payload

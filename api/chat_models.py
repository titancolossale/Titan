# =====================================
# Titan Web Chat Models
# =====================================

"""Structured request/response models for Web Runtime V1 chat."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from config.settings import TITAN_WEB_MAX_MESSAGE_LENGTH


class ChatMessageRequest(BaseModel):
    """Canonical authenticated chat request for Web Runtime V1."""

    message: str = Field(..., min_length=1, max_length=TITAN_WEB_MAX_MESSAGE_LENGTH)
    conversation_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    user: str | None = Field(default=None, max_length=64)
    client_metadata: dict[str, str] | None = None

    @field_validator("client_metadata")
    @classmethod
    def _sanitize_metadata(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        cleaned: dict[str, str] = {}
        for key, raw in value.items():
            safe_key = str(key).strip()[:64]
            if not safe_key:
                continue
            cleaned[safe_key] = str(raw).strip()[:256]
        return cleaned or None


class ChatMessageResponse(BaseModel):
    """Structured chat response — user-safe orchestration summary only."""

    request_id: str
    conversation_id: str
    response: str
    user: str
    detected_intent: str
    confidence: float
    systems_used: dict[str, Any]
    pipeline_summary: dict[str, Any]
    reasoning_summary: str
    brain_state: str
    execution_status: str
    approval_required: bool = False
    approval_id: str | None = None
    approval_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    tool_activity: list[dict[str, Any]] = Field(default_factory=list)
    memory_activity: list[dict[str, Any]] = Field(default_factory=list)
    orchestrator_progress: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


class ChatErrorResponse(BaseModel):
    """Safe structured API error."""

    error: str
    code: str
    request_id: str | None = None
    conversation_id: str | None = None

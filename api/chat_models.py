# =====================================
# Titan Web Chat Models
# =====================================

"""Structured request/response models for Web Runtime + Phase 11.1 chat contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from config.settings import TITAN_WEB_MAX_MESSAGE_LENGTH


class ChatMessageRequest(BaseModel):
    """Canonical authenticated chat request for Web Runtime / Phase 11.1."""

    message: str = Field(..., min_length=1, max_length=TITAN_WEB_MAX_MESSAGE_LENGTH)
    conversation_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    client_request_id: str | None = Field(
        default=None,
        max_length=128,
        description="Phase 11.1 alias for request_id — same idempotency key.",
    )
    user: str | None = Field(default=None, max_length=64)
    client_metadata: dict[str, str] | None = None

    @model_validator(mode="after")
    def _resolve_request_id(self) -> ChatMessageRequest:
        """Prefer explicit request_id; accept client_request_id as alias."""
        if not self.request_id and self.client_request_id:
            self.request_id = self.client_request_id.strip()[:128] or None
        return self

    @field_validator("message")
    @classmethod
    def _message_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message cannot be empty.")
        return cleaned

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


class ChatRuntimeInfo(BaseModel):
    """Honest operational runtime summary — never invents stages or tool use."""

    state: str = "finished"
    stages: list[str] = Field(default_factory=list)
    memory_used: bool = False
    tools_used: list[str] = Field(default_factory=list)
    model: str | None = None
    duration_ms: int = 0


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
    # Phase 11.1 contract fields (additive — keep legacy clients working)
    ok: bool = True
    message_id: str | None = None
    runtime: ChatRuntimeInfo | None = None


class ChatErrorDetail(BaseModel):
    """Structured error detail for Phase 11.1 contract."""

    code: str
    message: str
    retryable: bool = False


class ChatErrorResponse(BaseModel):
    """Safe structured API error (legacy + Phase 11.1)."""

    error: str | ChatErrorDetail
    code: str | None = None
    request_id: str | None = None
    conversation_id: str | None = None
    ok: bool = False
    message_id: str | None = None
    runtime: ChatRuntimeInfo | None = None

    @classmethod
    def from_parts(
        cls,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        request_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> ChatErrorResponse:
        """Build a Phase 11.1 error payload with nested error object."""
        return cls(
            ok=False,
            error=ChatErrorDetail(code=code, message=message, retryable=retryable),
            code=code,
            request_id=request_id,
            conversation_id=conversation_id,
            message_id=message_id,
            runtime=ChatRuntimeInfo(state="error", stages=["error"]),
        )

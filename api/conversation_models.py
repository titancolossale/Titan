# =====================================
# Titan Conversation API Models
# =====================================

"""Pydantic models for durable conversation endpoints (Phase 12.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] | None = None


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class ArchiveConversationRequest(BaseModel):
    archived: bool = True


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    archived: bool = False


class MessageSummary(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    request_id: str | None = None
    status: str
    error_code: str | None = None
    sequence: int = 0


class ConversationListResponse(BaseModel):
    ok: bool = True
    conversations: list[ConversationSummary]
    total: int
    limit: int
    offset: int


class ConversationDetailResponse(BaseModel):
    ok: bool = True
    conversation: ConversationSummary
    messages: list[MessageSummary]
    total_messages: int
    limit: int
    offset: int


class ConversationMutationResponse(BaseModel):
    ok: bool = True
    conversation: ConversationSummary


class SendConversationMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    request_id: str | None = Field(default=None, max_length=128)
    client_request_id: str | None = Field(default=None, max_length=128)
    client_metadata: dict[str, str] | None = None

    def resolved_request_id(self) -> str | None:
        if self.request_id and self.request_id.strip():
            return self.request_id.strip()[:128]
        if self.client_request_id and self.client_request_id.strip():
            return self.client_request_id.strip()[:128]
        return None


class RetryMessageRequest(BaseModel):
    request_id: str | None = Field(default=None, max_length=128)
    message_id: str | None = Field(default=None, max_length=64)


class CancelConversationRequest(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=128)

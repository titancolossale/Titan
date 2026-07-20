# =====================================
# Titan Conversation API Routes
# =====================================

"""Authenticated durable conversation CRUD + message send (Phase 12.1)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.auth import get_session_from_request, require_web_auth
from api.chat_service import cancel_chat_request, process_chat_message, validate_message_size
from api.conversation_models import (
    ArchiveConversationRequest,
    CancelConversationRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMutationResponse,
    ConversationSummary,
    CreateConversationRequest,
    MessageSummary,
    RenameConversationRequest,
    RetryMessageRequest,
    SendConversationMessageRequest,
)
from api.auth_config import is_session_auth_enabled
from config.settings import is_web_dev_mode
from core.web_conversations.db import ConversationStoreUnavailable
from core.web_conversations.service import get_conversation_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_web_auth)],
)


def resolve_authenticated_user(request: Request) -> str:
    """Return ownership key for conversation rows."""
    username = getattr(request.state, "titan_username", None)
    if username:
        return str(username)
    if is_session_auth_enabled():
        session = get_session_from_request(request)
        if session is not None:
            return session.username
    if is_web_dev_mode():
        return "Nolan"
    # Bearer mode — no per-user sessions; single shared owner key.
    return "web"


def _summary(conv: Any) -> ConversationSummary:
    return ConversationSummary(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        archived=conv.archived,
    )


def _message_summary(msg: Any) -> MessageSummary:
    return MessageSummary(
        id=msg.id,
        conversation_id=msg.conversation_id,
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at.isoformat(),
        request_id=msg.request_id,
        status=msg.status,
        error_code=msg.error_code,
        sequence=msg.sequence,
    )


def _store_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ConversationStoreUnavailable):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "conversation_store_unavailable", "message": str(exc)},
        )
    if isinstance(exc, PermissionError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Conversation introuvable."},
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_request", "message": str(exc)},
        )
    logger.exception("Conversation API failure")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "internal_error", "message": "Erreur interne."},
    )


@router.post("", response_model=ConversationMutationResponse)
def create_conversation(
    request: Request,
    body: CreateConversationRequest | None = None,
) -> ConversationMutationResponse:
    user_id = resolve_authenticated_user(request)
    service = get_conversation_service()
    try:
        body = body or CreateConversationRequest()
        conv = service.create_conversation(
            user_id,
            title=body.title or "Nouvelle conversation",
            metadata=body.metadata,
        )
        return ConversationMutationResponse(conversation=_summary(conv))
    except Exception as exc:
        raise _store_error(exc) from exc


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_archived: bool = Query(default=False),
) -> ConversationListResponse:
    user_id = resolve_authenticated_user(request)
    service = get_conversation_service()
    try:
        items, total = service.list_conversations(
            user_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
        )
        return ConversationListResponse(
            conversations=[_summary(c) for c in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise _store_error(exc) from exc


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    request: Request,
    conversation_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ConversationDetailResponse:
    user_id = resolve_authenticated_user(request)
    service = get_conversation_service()
    try:
        conv, messages, total = service.get_conversation_with_messages(
            conversation_id,
            user_id,
            limit=limit,
            offset=offset,
        )
        return ConversationDetailResponse(
            conversation=_summary(conv),
            messages=[_message_summary(m) for m in messages],
            total_messages=total,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise _store_error(exc) from exc


@router.patch("/{conversation_id}", response_model=ConversationMutationResponse)
def rename_conversation(
    request: Request,
    conversation_id: str,
    body: RenameConversationRequest,
) -> ConversationMutationResponse:
    user_id = resolve_authenticated_user(request)
    service = get_conversation_service()
    try:
        conv = service.rename(conversation_id, user_id, body.title)
        return ConversationMutationResponse(conversation=_summary(conv))
    except Exception as exc:
        raise _store_error(exc) from exc


@router.post("/{conversation_id}/archive", response_model=ConversationMutationResponse)
def archive_conversation(
    request: Request,
    conversation_id: str,
    body: ArchiveConversationRequest | None = None,
) -> ConversationMutationResponse:
    user_id = resolve_authenticated_user(request)
    service = get_conversation_service()
    try:
        archived = True if body is None else body.archived
        conv = service.archive(conversation_id, user_id, archived=archived)
        return ConversationMutationResponse(conversation=_summary(conv))
    except Exception as exc:
        raise _store_error(exc) from exc


@router.post("/{conversation_id}/messages")
def send_message(
    request: Request,
    conversation_id: str,
    body: SendConversationMessageRequest,
) -> dict[str, Any]:
    """Compatibility sync send — prefers /chat/stream for progressive UI."""
    user_id = resolve_authenticated_user(request)
    try:
        validate_message_size(body.message)
        payload = process_chat_message(
            body.message,
            user=user_id,
            conversation_id=conversation_id,
            request_id=body.resolved_request_id(),
            client_metadata=body.client_metadata,
        )
        return payload
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_request", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise _store_error(exc) from exc


@router.post("/{conversation_id}/cancel")
def cancel_conversation_request(
    request: Request,
    conversation_id: str,
    body: CancelConversationRequest,
) -> dict[str, Any]:
    del conversation_id  # ownership enforced by subsequent finalize paths
    resolve_authenticated_user(request)
    cancelled = cancel_chat_request(body.request_id)
    return {"ok": True, "cancelled": cancelled, "request_id": body.request_id}


@router.post("/{conversation_id}/retry")
def retry_failed_message(
    request: Request,
    conversation_id: str,
    body: RetryMessageRequest,
) -> dict[str, Any]:
    """Retry a failed assistant turn without duplicating the user message.

    Client should re-send the same user text with a new request_id via stream;
    this endpoint returns the last failed user content for convenience.
    """
    user_id = resolve_authenticated_user(request)
    service = get_conversation_service()
    try:
        _conv, messages, _total = service.get_conversation_with_messages(
            conversation_id,
            user_id,
            limit=50,
            offset=0,
        )
        # Find last failed assistant; pair with preceding user message.
        failed = None
        for msg in reversed(messages):
            if body.message_id and msg.id == body.message_id:
                failed = msg
                break
            if body.request_id and msg.request_id == body.request_id and msg.role == "assistant":
                failed = msg
                break
            if failed is None and msg.role == "assistant" and msg.status == "failed":
                failed = msg
                break
        if failed is None:
            raise ValueError("Aucun message en échec à relancer.")
        prior_user = None
        for msg in reversed(messages):
            if msg.sequence < failed.sequence and msg.role == "user":
                prior_user = msg
                break
        return {
            "ok": True,
            "conversation_id": conversation_id,
            "failed_message_id": failed.id,
            "user_message": prior_user.content if prior_user else None,
            "error_code": failed.error_code,
            "hint": "Renvoyer user_message via POST /chat/stream avec un nouveau request_id.",
        }
    except Exception as exc:
        raise _store_error(exc) from exc

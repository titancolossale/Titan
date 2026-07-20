# =====================================
# Titan Web Conversations
# =====================================

"""Durable web-app conversation history (Phase 12.1) — separate from long-term memory."""

from core.web_conversations.models import ConversationRecord, MessageRecord, MessageStatus
from core.web_conversations.service import ConversationService, get_conversation_service

__all__ = [
    "ConversationRecord",
    "ConversationService",
    "MessageRecord",
    "MessageStatus",
    "get_conversation_service",
]

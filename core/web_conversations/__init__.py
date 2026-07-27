# =====================================
# Titan Web Conversations
# =====================================

"""Durable web-app conversation history (Phase 12.1) + intelligence (Phase 12.2).

Conversation memory is PostgreSQL/SQLite — never Obsidian.
"""

from core.web_conversations.context import (
    ConversationContextBuilder,
    ConversationContextBundle,
    PinnedFacts,
)
from core.web_conversations.models import ConversationRecord, MessageRecord, MessageStatus
from core.web_conversations.service import ConversationService, get_conversation_service

__all__ = [
    "ConversationContextBuilder",
    "ConversationContextBundle",
    "ConversationRecord",
    "ConversationService",
    "MessageRecord",
    "MessageStatus",
    "PinnedFacts",
    "get_conversation_service",
]

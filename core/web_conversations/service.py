# =====================================
# Titan Web Conversation Service
# =====================================

"""High-level durable conversation operations for the Web App (Phase 12.1)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from config.settings import (
    TITAN_CONVERSATION_PERSISTENCE_ENABLED,
    TITAN_CONVERSATION_PERSISTENCE_REQUIRED,
)
from core.web_conversations.context import build_context_summary, format_messages_for_engine
from core.web_conversations.db import (
    ConversationStoreUnavailable,
    apply_migrations,
    check_database_ready,
    get_engine,
    reset_engine,
)
from core.web_conversations.models import (
    ConversationRecord,
    MessageRecord,
    MessageRole,
    MessageStatus,
)
from core.web_conversations.repository import ConversationRepository
from core.web_conversations.title import schedule_title_update

logger = logging.getLogger(__name__)

_service_lock = threading.Lock()
_service: ConversationService | None = None


class ConversationService:
    """Facade used by API and chat_service — ownership enforced in repository."""

    def __init__(self, repository: ConversationRepository | None = None) -> None:
        self._repo = repository or ConversationRepository()
        self._enabled = TITAN_CONVERSATION_PERSISTENCE_ENABLED

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def repository(self) -> ConversationRepository:
        return self._repo

    def ensure_ready(self) -> None:
        if not self._enabled:
            if TITAN_CONVERSATION_PERSISTENCE_REQUIRED:
                raise ConversationStoreUnavailable(
                    "Conversation persistence is required but disabled."
                )
            return
        self._repo.ensure_ready()

    def readiness(self) -> tuple[bool, str, dict[str, Any]]:
        if not self._enabled:
            return True, "Conversation persistence disabled.", {
                "enabled": False,
                "required": TITAN_CONVERSATION_PERSISTENCE_REQUIRED,
            }
        ok, message, details = check_database_ready(self._repo.engine)
        details = dict(details)
        details["enabled"] = True
        details["required"] = TITAN_CONVERSATION_PERSISTENCE_REQUIRED
        if TITAN_CONVERSATION_PERSISTENCE_REQUIRED and not ok:
            return False, message, details
        return ok, message, details

    def create_conversation(
        self,
        user_id: str,
        *,
        title: str = "Nouvelle conversation",
        metadata: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> ConversationRecord:
        self.ensure_ready()
        return self._repo.create_conversation(
            user_id,
            title=title,
            metadata=metadata,
            conversation_id=conversation_id,
        )

    def get_or_create_conversation(
        self,
        user_id: str,
        conversation_id: str | None,
    ) -> ConversationRecord:
        """Resolve client conversation id with ownership; create when missing.

        Compatibility: if the client sends a new non-empty id, adopt it as the
        durable conversation id so existing `/chat/stream` clients keep continuity.
        """
        self.ensure_ready()
        cleaned = (conversation_id or "").strip()[:64]
        if cleaned:
            existing = self._repo.get_conversation(
                cleaned,
                user_id,
                include_archived=True,
            )
            if existing is not None and not existing.archived:
                logger.info(
                    "CONVERSATION_LOADED conversation_id=%s",
                    existing.id[:16],
                )
                return existing
            if existing is not None and existing.archived:
                return self.create_conversation(user_id)
            try:
                return self.create_conversation(user_id, conversation_id=cleaned)
            except Exception:
                # Id collision (another owner / unique conflict) — allocate fresh.
                logger.debug(
                    "Adopt conversation_id failed; allocating new id",
                    exc_info=True,
                )
                return self.create_conversation(user_id)
        return self.create_conversation(user_id)

    def list_conversations(
        self,
        user_id: str,
        *,
        limit: int = 30,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[list[ConversationRecord], int]:
        self.ensure_ready()
        return self._repo.list_conversations(
            user_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
        )

    def get_conversation_with_messages(
        self,
        conversation_id: str,
        user_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[ConversationRecord, list[MessageRecord], int]:
        self.ensure_ready()
        conv = self._repo.get_conversation(conversation_id, user_id, include_archived=True)
        if conv is None:
            raise PermissionError("Conversation not found or access denied")
        messages, total = self._repo.list_messages(
            conversation_id,
            user_id,
            limit=limit,
            offset=offset,
        )
        logger.info(
            "CONVERSATION_LOADED conversation_id=%s messages=%d",
            conversation_id[:16],
            total,
        )
        return conv, messages, total

    def rename(
        self,
        conversation_id: str,
        user_id: str,
        title: str,
    ) -> ConversationRecord:
        self.ensure_ready()
        record = self._repo.rename_conversation(conversation_id, user_id, title)
        if record is None:
            raise PermissionError("Conversation not found or access denied")
        return record

    def archive(
        self,
        conversation_id: str,
        user_id: str,
        *,
        archived: bool = True,
    ) -> ConversationRecord:
        self.ensure_ready()
        record = self._repo.archive_conversation(
            conversation_id,
            user_id,
            archived=archived,
        )
        if record is None:
            raise PermissionError("Conversation not found or access denied")
        return record

    def hydrate_engine_history(
        self,
        conversation_id: str,
        user_id: str,
        conversation_engine: Any,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Replace in-process ConversationEngine turns with durable recent history."""
        self.ensure_ready()
        started = time.perf_counter()
        messages, _total = self._repo.list_messages(
            conversation_id,
            user_id,
            limit=500,
            offset=0,
        )
        summary = build_context_summary(
            messages,
            conversation_id=conversation_id,
            request_id=request_id,
        )
        selected: list[MessageRecord] = summary["messages"]

        # Reset in-process window so follow-ups use this conversation only.
        engine = conversation_engine
        # Accept Conversation facade from titan.conversation (has .engine, no .clear).
        if (
            engine is not None
            and not hasattr(engine, "clear")
            and hasattr(engine, "engine")
        ):
            engine = getattr(engine, "engine", None)
        if (
            engine is not None
            and hasattr(engine, "clear")
            and hasattr(engine, "add_user_turn")
        ):
            engine.clear()
            for speaker, content in format_messages_for_engine(selected):
                if speaker == "Titan":
                    engine.add_titan_turn(
                        content,
                        user=user_id,
                    )
                else:
                    engine.add_user_turn(user_id, content)

        summary["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return summary

    def persist_user_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        content: str,
        request_id: str | None,
        allow_duplicate: bool = True,
    ) -> MessageRecord:
        """Persist a user message; optionally reuse last user turn on retry."""
        if not allow_duplicate:
            messages, _ = self._repo.list_messages(
                conversation_id,
                user_id,
                limit=20,
                offset=0,
            )
            if messages:
                last = messages[-1]
                # Retry after failed/cancelled assistant: reuse prior user row.
                if last.role == "assistant" and last.status in {
                    MessageStatus.FAILED.value,
                    MessageStatus.CANCELLED.value,
                }:
                    for msg in reversed(messages[:-1]):
                        if msg.role == "user" and msg.content.strip() == content.strip():
                            return msg
                if (
                    last.role == "user"
                    and last.content.strip() == content.strip()
                    and last.request_id == request_id
                ):
                    return last
        return self._repo.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=MessageRole.USER.value,
            content=content,
            request_id=request_id,
            status=MessageStatus.COMPLETED.value,
        )

    def begin_assistant_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        request_id: str,
        model: str | None = None,
    ) -> MessageRecord:
        existing = self._repo.find_assistant_by_request(
            conversation_id,
            user_id,
            request_id,
        )
        if existing is not None:
            return existing
        return self._repo.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=MessageRole.ASSISTANT.value,
            content="",
            request_id=request_id,
            status=MessageStatus.PENDING.value,
            provider="openai",
            model=model,
        )

    def finalize_assistant_message(
        self,
        *,
        message_id: str,
        conversation_id: str,
        user_id: str,
        content: str,
        status: str = MessageStatus.COMPLETED.value,
        error_code: str | None = None,
        model: str | None = None,
    ) -> MessageRecord | None:
        return self._repo.update_message_status(
            message_id,
            conversation_id,
            user_id,
            status=status,
            content=content,
            error_code=error_code,
            model=model,
        )

    def maybe_generate_title(
        self,
        *,
        conversation_id: str,
        user_id: str,
        first_message: str,
        llm_ask: Any | None = None,
    ) -> str | None:
        """Generate title after first user message — never blocks response path."""
        count = self._repo.count_user_messages(conversation_id, user_id)
        if count != 1:
            return None

        def _rename(cid: str, uid: str, title: str) -> None:
            self._repo.rename_conversation(cid, uid, title)

        ask = None
        if llm_ask is not None and callable(getattr(llm_ask, "ask", None)):
            # Bound cheap call — wrap to ignore failures.
            def ask(prompt: str) -> str:
                return str(llm_ask.ask(prompt) or "")

        return schedule_title_update(
            conversation_id=conversation_id,
            user_id=user_id,
            first_message=first_message,
            rename=_rename,
            llm_ask=ask,
        )


def get_conversation_service(
    *,
    repository: ConversationRepository | None = None,
    refresh: bool = False,
) -> ConversationService:
    """Process-wide conversation service singleton."""
    global _service
    with _service_lock:
        if _service is None or refresh or repository is not None:
            _service = ConversationService(repository=repository)
        return _service


def reset_conversation_service() -> None:
    """Test helper."""
    global _service
    with _service_lock:
        _service = None
    reset_engine()


def bootstrap_conversation_store() -> None:
    """Apply migrations at web startup when persistence is enabled."""
    if not TITAN_CONVERSATION_PERSISTENCE_ENABLED:
        return
    apply_migrations(get_engine())

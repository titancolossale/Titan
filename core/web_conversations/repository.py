# =====================================
# Titan Web Conversation Repository
# =====================================

"""Ownership-scoped CRUD for durable conversations (Phase 12.1)."""

from __future__ import annotations

import json
import logging
import secrets
import threading
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from core.web_conversations.db import (
    ConversationStoreUnavailable,
    apply_migrations,
    conversations_table,
    get_engine,
    messages_table,
)
from core.web_conversations.models import (
    ConversationRecord,
    MessageRecord,
    MessageRole,
    MessageStatus,
    utc_now,
)

logger = logging.getLogger(__name__)

_MAX_TITLE = 120
_MAX_CONTENT = 100_000


def new_conversation_id() -> str:
    return f"conv_{secrets.token_urlsafe(18)}"


def new_message_id() -> str:
    return f"msg_{secrets.token_urlsafe(18)}"


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            from datetime import timezone

            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return utc_now()


def _loads_meta(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _dumps_meta(data: dict[str, Any] | None) -> str:
    return json.dumps(data or {}, ensure_ascii=False, separators=(",", ":"))


class ConversationRepository:
    """Parameterized SQL access with strict user ownership checks."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine
        self._lock = threading.RLock()
        self._migrated = False

    @property
    def engine(self) -> Engine:
        return self._engine or get_engine()

    def ensure_ready(self) -> None:
        with self._lock:
            if self._migrated:
                return
            try:
                apply_migrations(self.engine)
                self._migrated = True
            except Exception as exc:
                raise ConversationStoreUnavailable(
                    f"Conversation migrations failed: {type(exc).__name__}"
                ) from exc

    def create_conversation(
        self,
        user_id: str,
        *,
        title: str = "Nouvelle conversation",
        metadata: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> ConversationRecord:
        self.ensure_ready()
        user = (user_id or "").strip()
        if not user:
            raise ValueError("user_id is required")
        now = utc_now()
        record = ConversationRecord(
            id=(conversation_id or new_conversation_id())[:64],
            user_id=user[:128],
            title=(title or "Nouvelle conversation").strip()[:_MAX_TITLE] or "Nouvelle conversation",
            created_at=now,
            updated_at=now,
            archived=False,
            metadata=dict(metadata or {}),
        )
        with self._lock, self.engine.begin() as conn:
            conn.execute(
                conversations_table.insert().values(
                    id=record.id,
                    user_id=record.user_id,
                    title=record.title,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    archived=False,
                    metadata_json=_dumps_meta(record.metadata),
                )
            )
        logger.info(
            "CONVERSATION_CREATED conversation_id=%s user_hash=%s",
            record.id[:16],
            _safe_user_hash(user),
        )
        return record

    def get_conversation(
        self,
        conversation_id: str,
        user_id: str,
        *,
        include_archived: bool = True,
    ) -> ConversationRecord | None:
        self.ensure_ready()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(conversations_table).where(
                    and_(
                        conversations_table.c.id == conversation_id,
                        conversations_table.c.user_id == user_id,
                    )
                )
            ).mappings().first()
        if row is None:
            return None
        if not include_archived and bool(row["archived"]):
            return None
        return self._row_to_conversation(row)

    def list_conversations(
        self,
        user_id: str,
        *,
        limit: int = 30,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[list[ConversationRecord], int]:
        self.ensure_ready()
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        filters = [conversations_table.c.user_id == user_id]
        if not include_archived:
            filters.append(conversations_table.c.archived.is_(False))
        with self.engine.connect() as conn:
            total = conn.execute(
                select(func.count()).select_from(conversations_table).where(and_(*filters))
            ).scalar_one()
            rows = conn.execute(
                select(conversations_table)
                .where(and_(*filters))
                .order_by(conversations_table.c.updated_at.desc())
                .limit(limit)
                .offset(offset)
            ).mappings().all()
        return [self._row_to_conversation(r) for r in rows], int(total)

    def rename_conversation(
        self,
        conversation_id: str,
        user_id: str,
        title: str,
    ) -> ConversationRecord | None:
        self.ensure_ready()
        cleaned = (title or "").strip()[:_MAX_TITLE]
        if not cleaned:
            raise ValueError("title cannot be empty")
        now = utc_now()
        with self._lock, self.engine.begin() as conn:
            result = conn.execute(
                update(conversations_table)
                .where(
                    and_(
                        conversations_table.c.id == conversation_id,
                        conversations_table.c.user_id == user_id,
                    )
                )
                .values(title=cleaned, updated_at=now)
            )
            if result.rowcount == 0:
                return None
        return self.get_conversation(conversation_id, user_id)

    def archive_conversation(
        self,
        conversation_id: str,
        user_id: str,
        *,
        archived: bool = True,
    ) -> ConversationRecord | None:
        self.ensure_ready()
        now = utc_now()
        with self._lock, self.engine.begin() as conn:
            result = conn.execute(
                update(conversations_table)
                .where(
                    and_(
                        conversations_table.c.id == conversation_id,
                        conversations_table.c.user_id == user_id,
                    )
                )
                .values(archived=archived, updated_at=now)
            )
            if result.rowcount == 0:
                return None
        return self.get_conversation(conversation_id, user_id, include_archived=True)

    def touch_conversation(self, conversation_id: str, user_id: str) -> None:
        self.ensure_ready()
        now = utc_now()
        with self._lock, self.engine.begin() as conn:
            conn.execute(
                update(conversations_table)
                .where(
                    and_(
                        conversations_table.c.id == conversation_id,
                        conversations_table.c.user_id == user_id,
                    )
                )
                .values(updated_at=now)
            )

    def next_sequence(self, conversation_id: str) -> int:
        self.ensure_ready()
        with self.engine.connect() as conn:
            current = conn.execute(
                select(func.coalesce(func.max(messages_table.c.sequence), 0)).where(
                    messages_table.c.conversation_id == conversation_id
                )
            ).scalar_one()
        return int(current) + 1

    def add_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        request_id: str | None = None,
        status: str = MessageStatus.COMPLETED.value,
        error_code: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> MessageRecord:
        """Insert a message after ownership check. Idempotent for assistant+request_id."""
        self.ensure_ready()
        conv = self.get_conversation(conversation_id, user_id, include_archived=True)
        if conv is None:
            raise PermissionError("Conversation not found or access denied")

        role_norm = (role or "").strip().lower()
        if role_norm not in {r.value for r in MessageRole}:
            raise ValueError(f"Invalid role: {role}")
        text = (content or "")[:_MAX_CONTENT]
        req = (request_id or "").strip()[:128] or None

        # Idempotency: do not duplicate assistant rows for the same request_id.
        if role_norm == MessageRole.ASSISTANT.value and req:
            existing = self.find_assistant_by_request(conversation_id, user_id, req)
            if existing is not None:
                return existing

        seq = self.next_sequence(conversation_id)
        now = utc_now()
        record = MessageRecord(
            id=(message_id or new_message_id())[:64],
            conversation_id=conversation_id,
            role=role_norm,
            content=text,
            created_at=now,
            request_id=req,
            status=status,
            error_code=error_code,
            provider=provider,
            model=model,
            metadata=dict(metadata or {}),
            sequence=seq,
        )
        try:
            with self._lock, self.engine.begin() as conn:
                conn.execute(
                    messages_table.insert().values(
                        id=record.id,
                        conversation_id=record.conversation_id,
                        role=record.role,
                        content=record.content,
                        created_at=record.created_at,
                        request_id=record.request_id,
                        status=record.status,
                        error_code=record.error_code,
                        provider=record.provider,
                        model=record.model,
                        metadata_json=_dumps_meta(record.metadata),
                        sequence=record.sequence,
                    )
                )
                conn.execute(
                    update(conversations_table)
                    .where(
                        and_(
                            conversations_table.c.id == conversation_id,
                            conversations_table.c.user_id == user_id,
                        )
                    )
                    .values(updated_at=now)
                )
        except IntegrityError:
            if role_norm == MessageRole.ASSISTANT.value and req:
                existing = self.find_assistant_by_request(conversation_id, user_id, req)
                if existing is not None:
                    return existing
            raise

        logger.info(
            "MESSAGE_PERSISTED conversation_id=%s request_id=%s role=%s "
            "status=%s chars=%d",
            conversation_id[:16],
            (req or "-")[:32],
            role_norm,
            status,
            len(text),
        )
        return record

    def find_assistant_by_request(
        self,
        conversation_id: str,
        user_id: str,
        request_id: str,
    ) -> MessageRecord | None:
        self.ensure_ready()
        if self.get_conversation(conversation_id, user_id, include_archived=True) is None:
            return None
        with self.engine.connect() as conn:
            row = conn.execute(
                select(messages_table).where(
                    and_(
                        messages_table.c.conversation_id == conversation_id,
                        messages_table.c.request_id == request_id,
                        messages_table.c.role == MessageRole.ASSISTANT.value,
                    )
                )
            ).mappings().first()
        return self._row_to_message(row) if row else None

    def update_message_status(
        self,
        message_id: str,
        conversation_id: str,
        user_id: str,
        *,
        status: str,
        content: str | None = None,
        error_code: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> MessageRecord | None:
        self.ensure_ready()
        if self.get_conversation(conversation_id, user_id, include_archived=True) is None:
            return None
        values: dict[str, Any] = {"status": status}
        if content is not None:
            values["content"] = content[:_MAX_CONTENT]
        if error_code is not None:
            values["error_code"] = error_code
        if provider is not None:
            values["provider"] = provider
        if model is not None:
            values["model"] = model
        with self._lock, self.engine.begin() as conn:
            result = conn.execute(
                update(messages_table)
                .where(
                    and_(
                        messages_table.c.id == message_id,
                        messages_table.c.conversation_id == conversation_id,
                    )
                )
                .values(**values)
            )
            if result.rowcount == 0:
                return None
            conn.execute(
                update(conversations_table)
                .where(
                    and_(
                        conversations_table.c.id == conversation_id,
                        conversations_table.c.user_id == user_id,
                    )
                )
                .values(updated_at=utc_now())
            )
        return self.get_message(message_id, conversation_id, user_id)

    def get_message(
        self,
        message_id: str,
        conversation_id: str,
        user_id: str,
    ) -> MessageRecord | None:
        self.ensure_ready()
        if self.get_conversation(conversation_id, user_id, include_archived=True) is None:
            return None
        with self.engine.connect() as conn:
            row = conn.execute(
                select(messages_table).where(
                    and_(
                        messages_table.c.id == message_id,
                        messages_table.c.conversation_id == conversation_id,
                    )
                )
            ).mappings().first()
        return self._row_to_message(row) if row else None

    def list_messages(
        self,
        conversation_id: str,
        user_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        include_system: bool = False,
    ) -> tuple[list[MessageRecord], int]:
        self.ensure_ready()
        if self.get_conversation(conversation_id, user_id, include_archived=True) is None:
            raise PermissionError("Conversation not found or access denied")
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        filters = [messages_table.c.conversation_id == conversation_id]
        if not include_system:
            filters.append(
                messages_table.c.role.in_(
                    [MessageRole.USER.value, MessageRole.ASSISTANT.value]
                )
            )
        with self.engine.connect() as conn:
            total = conn.execute(
                select(func.count()).select_from(messages_table).where(and_(*filters))
            ).scalar_one()
            rows = conn.execute(
                select(messages_table)
                .where(and_(*filters))
                .order_by(
                    messages_table.c.sequence.asc(),
                    messages_table.c.created_at.asc(),
                )
                .limit(limit)
                .offset(offset)
            ).mappings().all()
        return [self._row_to_message(r) for r in rows], int(total)

    def count_user_messages(self, conversation_id: str, user_id: str) -> int:
        self.ensure_ready()
        if self.get_conversation(conversation_id, user_id, include_archived=True) is None:
            return 0
        with self.engine.connect() as conn:
            return int(
                conn.execute(
                    select(func.count())
                    .select_from(messages_table)
                    .where(
                        and_(
                            messages_table.c.conversation_id == conversation_id,
                            messages_table.c.role == MessageRole.USER.value,
                        )
                    )
                ).scalar_one()
            )

    def _row_to_conversation(self, row: Any) -> ConversationRecord:
        return ConversationRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            title=str(row["title"]),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            archived=bool(row["archived"]),
            metadata=_loads_meta(row["metadata_json"]),
        )

    def _row_to_message(self, row: Any) -> MessageRecord:
        return MessageRecord(
            id=str(row["id"]),
            conversation_id=str(row["conversation_id"]),
            role=str(row["role"]),
            content=str(row["content"] or ""),
            created_at=_parse_dt(row["created_at"]),
            request_id=row["request_id"],
            status=str(row["status"]),
            error_code=row["error_code"],
            provider=row["provider"],
            model=row["model"],
            metadata=_loads_meta(row["metadata_json"]),
            sequence=int(row["sequence"] or 0),
        )


def _safe_user_hash(user_id: str) -> str:
    import hashlib

    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]

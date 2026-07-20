# =====================================
# Titan Conversation Context Builder
# =====================================

"""Bounded recent-history context for follow-up turns (Phase 12.1)."""

from __future__ import annotations

import logging
import time
from typing import Any

from config.settings import (
    CONVERSATION_WINDOW_SIZE,
    MAX_PROMPT_TOKENS,
    TITAN_CONVERSATION_CONTEXT_MAX_TOKENS,
)
from core.web_conversations.models import MessageRecord, MessageStatus

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // _CHARS_PER_TOKEN) if text else 0


def select_recent_messages(
    messages: list[MessageRecord],
    *,
    max_turns: int | None = None,
    max_tokens: int | None = None,
    exclude_pending: bool = True,
) -> list[MessageRecord]:
    """Select useful recent user/assistant turns; trim oldest first when over budget."""
    max_turns = max_turns if max_turns is not None else CONVERSATION_WINDOW_SIZE
    budget = max_tokens if max_tokens is not None else min(
        TITAN_CONVERSATION_CONTEXT_MAX_TOKENS,
        max(512, MAX_PROMPT_TOKENS // 3),
    )

    usable: list[MessageRecord] = []
    for msg in messages:
        if msg.role not in {"user", "assistant"}:
            continue
        if exclude_pending and msg.status == MessageStatus.PENDING.value:
            continue
        if msg.status == MessageStatus.CANCELLED.value and not (msg.content or "").strip():
            continue
        if not (msg.content or "").strip():
            continue
        usable.append(msg)

    # Keep last N turns first, then trim by token budget from the oldest.
    window = usable[-max(1, max_turns) :] if max_turns > 0 else []
    while window and sum(estimate_tokens(m.content) for m in window) > budget:
        window = window[1:]
    return window


def format_messages_for_engine(messages: list[MessageRecord]) -> list[tuple[str, str]]:
    """Return (speaker, content) pairs for ConversationEngine hydration."""
    pairs: list[tuple[str, str]] = []
    for msg in messages:
        if msg.role == "user":
            pairs.append(("user", msg.content))
        elif msg.role == "assistant":
            pairs.append(("Titan", msg.content))
    return pairs


def build_context_summary(
    messages: list[MessageRecord],
    *,
    conversation_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    selected = select_recent_messages(messages)
    tokens = sum(estimate_tokens(m.content) for m in selected)
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "CONVERSATION_CONTEXT_BUILT request_id=%s conversation_id=%s "
        "context_messages=%d estimated_tokens=%d duration_ms=%d",
        (request_id or "-")[:32],
        (conversation_id or "-")[:16],
        len(selected),
        tokens,
        duration_ms,
    )
    return {
        "messages": selected,
        "context_message_count": len(selected),
        "estimated_tokens": tokens,
        "duration_ms": duration_ms,
        "max_prompt_tokens": MAX_PROMPT_TOKENS,
    }

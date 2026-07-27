# =====================================
# Titan Conversation Context Builder
# =====================================

"""Layered conversation intelligence for continuous assistants (Phase 12.2).

Obsidian is never used as conversation memory — history stays in PostgreSQL
(or the configured conversation store). This module only builds prompt-ready
context from durable messages + optional operational hints (project/mission).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from config.settings import (
    CONVERSATION_WINDOW_SIZE,
    MAX_PROMPT_TOKENS,
    TITAN_CONVERSATION_CONTEXT_MAX_TOKENS,
    TITAN_CONVERSATION_SUMMARY_MAX_CHARS,
    TITAN_CONVERSATION_SUMMARY_THRESHOLD,
)
from core.web_conversations.models import MessageRecord, MessageStatus

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4
_INTELLIGENCE_META_KEY = "conversation_intelligence"

# Continuity cues — short follow-ups that require prior conversation context.
_REFERENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(?:continue|continuer|continues|poursuis|poursuite|go on|keep going)"
        r"[.!?\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:same as before|comme avant|pareil|idem|comme d['']habitude)"
        r"[.!?\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:again|encore|recommence|re[- ]?do(?:\s+it)?|relance)"
        r"[.!?\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:do that|do it|fais[- ]?(?:le|ça|ca)|fais[- ]?moi ça|"
        r"go ahead|vas[- ]?y)[.!?\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:this project|ce projet|that project|ce même projet|"
        r"that strategy|cette stratégie|cette strategie|this strategy)"
        r"[.!?\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:and then|et ensuite|next|ensuite|what(?:'s| is) next|"
        r"quoi ensuite|que faire ensuite|what should i do next)"
        r"[.!?\s]*$",
        re.IGNORECASE,
    ),
)

_DECISION_RE = re.compile(
    r"(?:we (?:decided|chose|picked|agreed)|on a (?:décidé|choisi|retenu)|"
    r"decision|décision|we'll use|on va utiliser|using|utiliser)\s+(.+)",
    re.IGNORECASE,
)
_PROJECT_RE = re.compile(
    r"(?:my project is|le projet (?:est|s'appelle)|projet\s*[:=]|project\s*[:=])\s*"
    r"([A-Za-z0-9][\w .-]{1,60})",
    re.IGNORECASE,
)
_GOAL_RE = re.compile(
    r"(?:goal|objectif|je (?:veux|souhaite)|i want to|we need to|"
    r"on doit)\s*[:\s]+(.+)",
    re.IGNORECASE,
)
_TASK_RE = re.compile(
    r"(?:todo|à faire|task|tâche|next step|prochaine étape|"
    r"unfinished|en cours)\s*[:\s]+(.+)",
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // _CHARS_PER_TOKEN) if text else 0


@dataclass
class PinnedFacts:
    """Durable continuity anchors preserved across summarization."""

    active_project: str | None = None
    unfinished_tasks: list[str] = field(default_factory=list)
    user_goals: list[str] = field(default_factory=list)
    important_decisions: list[str] = field(default_factory=list)
    current_topic: str | None = None

    def is_empty(self) -> bool:
        return not any(
            (
                self.active_project,
                self.unfinished_tasks,
                self.user_goals,
                self.important_decisions,
                self.current_topic,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_project": self.active_project,
            "unfinished_tasks": list(self.unfinished_tasks),
            "user_goals": list(self.user_goals),
            "important_decisions": list(self.important_decisions),
            "current_topic": self.current_topic,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PinnedFacts:
        if not data:
            return cls()
        return cls(
            active_project=_clean_str(data.get("active_project")),
            unfinished_tasks=_unique_strings(data.get("unfinished_tasks") or []),
            user_goals=_unique_strings(data.get("user_goals") or []),
            important_decisions=_unique_strings(data.get("important_decisions") or []),
            current_topic=_clean_str(data.get("current_topic")),
        )

    def format_text(self) -> str:
        if self.is_empty():
            return ""
        lines: list[str] = []
        if self.active_project:
            lines.append(f"Projet actif : {self.active_project}")
        if self.current_topic:
            lines.append(f"Sujet en cours : {self.current_topic}")
        if self.important_decisions:
            lines.append("Décisions importantes :")
            lines.extend(f"- {item}" for item in self.important_decisions[:8])
        if self.user_goals:
            lines.append("Objectifs :")
            lines.extend(f"- {item}" for item in self.user_goals[:8])
        if self.unfinished_tasks:
            lines.append("Tâches non terminées :")
            lines.extend(f"- {item}" for item in self.unfinished_tasks[:8])
        return "\n".join(lines)


@dataclass
class ConversationContextBundle:
    """Layered conversation context ready for prompt injection / engine hydrate."""

    recent_messages: list[MessageRecord] = field(default_factory=list)
    recent_lines: list[str] = field(default_factory=list)
    summary: str | None = None
    pinned_facts: PinnedFacts = field(default_factory=PinnedFacts)
    reference_resolution: str | None = None
    estimated_tokens: int = 0
    truncated: bool = False
    summary_created: bool = False
    summary_loaded: bool = False
    pinned_facts_loaded: bool = False
    archived_message_count: int = 0
    duration_ms: int = 0
    layers: dict[str, str] = field(default_factory=dict)

    def to_hydration_dict(self) -> dict[str, Any]:
        return {
            "messages": self.recent_messages,
            "context_message_count": len(self.recent_messages),
            "estimated_tokens": self.estimated_tokens,
            "duration_ms": self.duration_ms,
            "max_prompt_tokens": MAX_PROMPT_TOKENS,
            "summary": self.summary,
            "pinned_facts": self.pinned_facts.to_dict(),
            "reference_resolution": self.reference_resolution,
            "recent_lines": list(self.recent_lines),
            "truncated": self.truncated,
            "summary_created": self.summary_created,
            "summary_loaded": self.summary_loaded,
            "pinned_facts_loaded": self.pinned_facts_loaded,
            "archived_message_count": self.archived_message_count,
            "layers": dict(self.layers),
            "intelligence_metadata": self.to_intelligence_metadata(),
        }

    def to_intelligence_metadata(self) -> dict[str, Any]:
        return {
            "summary": self.summary or "",
            "archived_message_count": self.archived_message_count,
            "pinned_facts": self.pinned_facts.to_dict(),
        }

    def prompt_layers(self) -> list[tuple[str, str]]:
        """Canonical conversation layers (recent → summary → pinned → reference)."""
        ordered: list[tuple[str, str]] = []
        if self.recent_lines:
            ordered.append(("CONVERSATION RÉCENTE", "\n".join(self.recent_lines)))
        if self.summary:
            ordered.append(("RÉSUMÉ CONVERSATION", self.summary))
        pinned = self.pinned_facts.format_text()
        if pinned:
            ordered.append(("FAITS ÉPINGLÉS", pinned))
        if self.reference_resolution:
            ordered.append(("RÉFÉRENCE RÉSOLUE", self.reference_resolution))
        return ordered


class ConversationContextBuilder:
    """Builds layered conversation context with summarization and token budget."""

    def __init__(
        self,
        *,
        max_recent_turns: int | None = None,
        max_tokens: int | None = None,
        summarize_threshold: int | None = None,
        summary_max_chars: int | None = None,
    ) -> None:
        self._max_recent_turns = (
            max_recent_turns if max_recent_turns is not None else CONVERSATION_WINDOW_SIZE
        )
        self._max_tokens = max_tokens if max_tokens is not None else min(
            TITAN_CONVERSATION_CONTEXT_MAX_TOKENS,
            max(512, MAX_PROMPT_TOKENS // 3),
        )
        self._summarize_threshold = (
            summarize_threshold
            if summarize_threshold is not None
            else TITAN_CONVERSATION_SUMMARY_THRESHOLD
        )
        self._summary_max_chars = (
            summary_max_chars
            if summary_max_chars is not None
            else TITAN_CONVERSATION_SUMMARY_MAX_CHARS
        )

    def build(
        self,
        messages: Sequence[MessageRecord],
        *,
        current_message: str | None = None,
        existing_summary: str | None = None,
        existing_pinned: PinnedFacts | None = None,
        archived_message_count: int = 0,
        active_project: str | None = None,
        unfinished_tasks: Sequence[str] | None = None,
        user_goals: Sequence[str] | None = None,
        conversation_id: str | None = None,
        request_id: str | None = None,
    ) -> ConversationContextBundle:
        started = time.perf_counter()
        logger.info(
            "CONTEXT_BUILD_STARTED request_id=%s conversation_id=%s message_count=%d",
            (request_id or "-")[:32],
            (conversation_id or "-")[:16],
            len(messages),
        )

        usable = _usable_messages(list(messages))
        prior_summary = (existing_summary or "").strip() or None
        summary_loaded = bool(prior_summary)
        if summary_loaded:
            logger.info(
                "SUMMARY_LOADED request_id=%s conversation_id=%s summary_chars=%d",
                (request_id or "-")[:32],
                (conversation_id or "-")[:16],
                len(prior_summary or ""),
            )

        pinned = self._merge_pinned_facts(
            messages=usable,
            existing=existing_pinned or PinnedFacts(),
            active_project=active_project,
            unfinished_tasks=unfinished_tasks,
            user_goals=user_goals,
        )
        pinned_loaded = not pinned.is_empty()
        if pinned_loaded:
            logger.info(
                "PINNED_FACTS_LOADED request_id=%s conversation_id=%s "
                "project=%s decisions=%d goals=%d tasks=%d",
                (request_id or "-")[:32],
                (conversation_id or "-")[:16],
                (pinned.active_project or "-")[:40],
                len(pinned.important_decisions),
                len(pinned.user_goals),
                len(pinned.unfinished_tasks),
            )

        summary = prior_summary
        summary_created = False
        archived_count = max(0, int(archived_message_count))
        recent_source = usable

        if len(usable) > self._summarize_threshold:
            keep = max(1, self._max_recent_turns)
            older = usable[:-keep]
            recent_source = usable[-keep:]
            if older:
                created = self._create_summary(older, existing=summary)
                if created and created != summary:
                    summary = created
                    summary_created = True
                    archived_count = max(archived_count, len(older))
                    logger.info(
                        "SUMMARY_CREATED request_id=%s conversation_id=%s "
                        "archived_messages=%d summary_chars=%d",
                        (request_id or "-")[:32],
                        (conversation_id or "-")[:16],
                        len(older),
                        len(summary or ""),
                    )

        recent = select_recent_messages(
            recent_source,
            max_turns=self._max_recent_turns,
            max_tokens=self._max_tokens,
        )
        truncated = len(recent) < len(recent_source) or (
            len(usable) > len(recent) and not summary
        )

        recent_lines = self._format_recent_lines(recent, current_message=current_message)
        recent_lines = self._dedupe_against_summary(recent_lines, summary)

        reference = self.resolve_reference(
            current_message or "",
            pinned_facts=pinned,
            summary=summary,
            recent_lines=recent_lines,
        )

        layers = self._assemble_layers(
            recent_lines=recent_lines,
            summary=summary,
            pinned_facts=pinned,
            reference_resolution=reference,
        )
        token_count, truncated_by_budget = self._enforce_token_budget(layers)
        if truncated_by_budget:
            truncated = True
            recent_lines = [
                line
                for line in (layers.get("recent") or "").splitlines()
                if line.strip()
            ]
            summary = layers.get("summary") or summary

        logger.info(
            "CONTEXT_TOKEN_COUNT request_id=%s conversation_id=%s estimated_tokens=%d",
            (request_id or "-")[:32],
            (conversation_id or "-")[:16],
            token_count,
        )
        if truncated:
            logger.info(
                "CONTEXT_TRUNCATED request_id=%s conversation_id=%s "
                "token_count=%d budget=%d recent=%d",
                (request_id or "-")[:32],
                (conversation_id or "-")[:16],
                token_count,
                self._max_tokens,
                len(recent_lines),
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        bundle = ConversationContextBundle(
            recent_messages=recent,
            recent_lines=recent_lines,
            summary=summary,
            pinned_facts=pinned,
            reference_resolution=reference,
            estimated_tokens=token_count,
            truncated=truncated,
            summary_created=summary_created,
            summary_loaded=summary_loaded and not summary_created,
            pinned_facts_loaded=pinned_loaded,
            archived_message_count=archived_count,
            duration_ms=duration_ms,
            layers=dict(layers),
        )
        logger.info(
            "CONTEXT_BUILD_FINISHED request_id=%s conversation_id=%s "
            "recent=%d summary=%s pinned=%s tokens=%d truncated=%s duration_ms=%d",
            (request_id or "-")[:32],
            (conversation_id or "-")[:16],
            len(recent),
            "yes" if summary else "no",
            "yes" if pinned_loaded else "no",
            token_count,
            truncated,
            duration_ms,
        )
        # Keep Phase 12.1 telemetry name for existing dashboards.
        logger.info(
            "CONVERSATION_CONTEXT_BUILT request_id=%s conversation_id=%s "
            "context_messages=%d estimated_tokens=%d duration_ms=%d",
            (request_id or "-")[:32],
            (conversation_id or "-")[:16],
            len(recent),
            token_count,
            duration_ms,
        )
        return bundle

    def build_from_engine(
        self,
        conversation_engine: Any,
        *,
        current_message: str | None = None,
        active_project: str | None = None,
        unfinished_tasks: Sequence[str] | None = None,
        user_goals: Sequence[str] | None = None,
        request_id: str | None = None,
    ) -> ConversationContextBundle:
        """Build from in-process ConversationEngine turns (CLI + post-hydrate)."""
        turns = list(getattr(conversation_engine, "get_window", lambda: [])() or [])
        messages: list[MessageRecord] = []
        now = datetime.now(timezone.utc)
        for index, turn in enumerate(turns):
            speaker = getattr(turn, "speaker", "") or ""
            role = "assistant" if speaker == "Titan" else "user"
            messages.append(
                MessageRecord(
                    id=f"engine_{index}",
                    conversation_id=str(
                        getattr(conversation_engine, "session_id", "session")
                    ),
                    role=role,
                    content=str(getattr(turn, "message", "") or ""),
                    created_at=now,
                    status=MessageStatus.COMPLETED.value,
                    sequence=index + 1,
                )
            )
        existing_summary = getattr(conversation_engine, "_archived_summary", None)
        archived_count = int(
            getattr(conversation_engine, "_archived_turn_count", 0) or 0
        )
        existing_pinned = None
        getter = getattr(conversation_engine, "get_pinned_facts_payload", None)
        if callable(getter):
            existing_pinned = PinnedFacts.from_dict(getter())
        return self.build(
            messages,
            current_message=current_message,
            existing_summary=existing_summary,
            existing_pinned=existing_pinned,
            archived_message_count=archived_count,
            active_project=active_project,
            unfinished_tasks=unfinished_tasks,
            user_goals=user_goals,
            conversation_id=str(getattr(conversation_engine, "session_id", "") or ""),
            request_id=request_id,
        )

    def resolve_reference(
        self,
        message: str,
        *,
        pinned_facts: PinnedFacts,
        summary: str | None,
        recent_lines: Sequence[str],
    ) -> str | None:
        """Expand continuity phrases using pinned facts / recent topic / summary."""
        text = " ".join((message or "").strip().split())
        if not text:
            return None
        if not any(pattern.match(text) for pattern in _REFERENCE_PATTERNS):
            # Soft match for short deixis containing known cues.
            lowered = text.lower()
            soft_cues = (
                "continue",
                "continuer",
                "same as before",
                "comme avant",
                "again",
                "encore",
                "do that",
                "fais ça",
                "fais ca",
                "this project",
                "ce projet",
                "that strategy",
                "cette stratégie",
                "cette strategie",
            )
            if len(text) > 80 or not any(cue in lowered for cue in soft_cues):
                return None

        parts: list[str] = [
            "Le message utilisateur renvoie au contexte déjà établi — "
            "ne redemande pas les informations déjà connues."
        ]
        if pinned_facts.active_project:
            parts.append(f"Projet concerné : {pinned_facts.active_project}.")
        if pinned_facts.current_topic:
            parts.append(f"Sujet concerné : {pinned_facts.current_topic}.")
        if pinned_facts.important_decisions:
            parts.append(
                "Décisions à respecter : "
                + "; ".join(pinned_facts.important_decisions[:4])
            )
        if pinned_facts.unfinished_tasks:
            parts.append(
                "Tâches en cours : " + "; ".join(pinned_facts.unfinished_tasks[:4])
            )
        if pinned_facts.user_goals:
            parts.append("Objectifs : " + "; ".join(pinned_facts.user_goals[:4]))
        if summary:
            clipped = summary if len(summary) <= 280 else summary[:277] + "..."
            parts.append(f"Résumé utile : {clipped}")
        elif recent_lines:
            parts.append("Dernier échange : " + recent_lines[-1][:200])
        return " ".join(parts)

    def _merge_pinned_facts(
        self,
        *,
        messages: Sequence[MessageRecord],
        existing: PinnedFacts,
        active_project: str | None,
        unfinished_tasks: Sequence[str] | None,
        user_goals: Sequence[str] | None,
    ) -> PinnedFacts:
        extracted = extract_pinned_facts(messages)
        project = (
            _clean_str(active_project)
            or extracted.active_project
            or existing.active_project
        )
        decisions = _unique_strings(
            list(existing.important_decisions) + list(extracted.important_decisions)
        )
        goals = _unique_strings(
            list(existing.user_goals)
            + list(user_goals or [])
            + list(extracted.user_goals)
        )
        tasks = _unique_strings(
            list(existing.unfinished_tasks)
            + list(unfinished_tasks or [])
            + list(extracted.unfinished_tasks)
        )
        topic = extracted.current_topic or existing.current_topic
        if not topic and messages:
            last_user = next(
                (m.content.strip() for m in reversed(messages) if m.role == "user"),
                None,
            )
            if last_user:
                topic = last_user[:120]
        return PinnedFacts(
            active_project=project,
            unfinished_tasks=tasks[:12],
            user_goals=goals[:12],
            important_decisions=decisions[:12],
            current_topic=topic,
        )

    def _create_summary(
        self,
        older_messages: Sequence[MessageRecord],
        *,
        existing: str | None,
    ) -> str:
        parts: list[str] = []
        if existing:
            parts.append(existing.strip())
        facts = extract_pinned_facts(older_messages)
        if facts.active_project:
            parts.append(f"Projet : {facts.active_project}.")
        for decision in facts.important_decisions[:6]:
            parts.append(f"Décision : {decision}.")
        for goal in facts.user_goals[:4]:
            parts.append(f"Objectif : {goal}.")
        for task in facts.unfinished_tasks[:4]:
            parts.append(f"Tâche : {task}.")
        if facts.current_topic:
            parts.append(f"Sujet : {facts.current_topic}.")

        # Compact extractive snippets from older turns (deduped).
        seen: set[str] = set()
        for msg in older_messages:
            text = " ".join((msg.content or "").strip().split())
            if len(text) < 8:
                continue
            key = text.lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            role = "User" if msg.role == "user" else "Titan"
            snippet = text if len(text) <= 90 else text[:87] + "..."
            parts.append(f"{role}: {snippet}")
            if len(parts) >= 24:
                break

        summary = " ".join(_unique_strings(parts, key_fn=lambda s: s.lower()))
        if len(summary) > self._summary_max_chars:
            summary = summary[: self._summary_max_chars - 3] + "..."
        return summary

    def _format_recent_lines(
        self,
        messages: Sequence[MessageRecord],
        *,
        current_message: str | None,
    ) -> list[str]:
        lines: list[str] = []
        for msg in messages:
            speaker = "Titan" if msg.role == "assistant" else "User"
            if msg.role == "user" and current_message:
                if (msg.content or "").strip() == current_message.strip():
                    continue
            content = (msg.content or "").strip()
            if not content:
                continue
            lines.append(f"{speaker} : {content}")
        return lines

    @staticmethod
    def _dedupe_against_summary(
        recent_lines: list[str],
        summary: str | None,
    ) -> list[str]:
        if not summary or not recent_lines:
            return recent_lines
        summary_lower = summary.lower()
        kept: list[str] = []
        for line in recent_lines:
            # Drop lines whose core content is already fully present in summary.
            payload = line.split(" : ", 1)[-1].strip().lower()
            if len(payload) >= 24 and payload in summary_lower:
                continue
            kept.append(line)
        return kept or recent_lines[-2:]

    @staticmethod
    def _assemble_layers(
        *,
        recent_lines: Sequence[str],
        summary: str | None,
        pinned_facts: PinnedFacts,
        reference_resolution: str | None,
    ) -> dict[str, str]:
        return {
            "recent": "\n".join(recent_lines),
            "summary": (summary or "").strip(),
            "pinned": pinned_facts.format_text(),
            "reference": (reference_resolution or "").strip(),
        }

    def _enforce_token_budget(
        self,
        layers: dict[str, str],
    ) -> tuple[int, bool]:
        """Trim lowest-priority conversation layers until within budget.

        Priority (keep first): pinned → reference → summary → recent (oldest drop).
        """
        budget = self._max_tokens
        truncated = False

        def total() -> int:
            return sum(estimate_tokens(v) for v in layers.values() if v)

        tokens = total()
        if tokens <= budget:
            return tokens, False

        # Shrink recent from the oldest line.
        recent = layers.get("recent") or ""
        if recent:
            lines = recent.splitlines()
            while lines and total() > budget:
                lines = lines[1:]
                layers["recent"] = "\n".join(lines)
                truncated = True
            tokens = total()
            if tokens <= budget:
                return tokens, truncated

        # Compress summary.
        summary = layers.get("summary") or ""
        if summary and total() > budget:
            keep_chars = max(120, budget * _CHARS_PER_TOKEN // 3)
            if len(summary) > keep_chars:
                layers["summary"] = summary[: keep_chars - 3] + "..."
                truncated = True
            tokens = total()
            if tokens <= budget:
                return tokens, truncated

        # Last resort: drop reference text (pinned stays).
        if layers.get("reference") and total() > budget:
            layers["reference"] = ""
            truncated = True

        return total(), truncated


def extract_pinned_facts(messages: Sequence[MessageRecord]) -> PinnedFacts:
    """Heuristic extraction of continuity anchors from message text."""
    project: str | None = None
    decisions: list[str] = []
    goals: list[str] = []
    tasks: list[str] = []
    topic: str | None = None

    for msg in messages:
        text = " ".join((msg.content or "").strip().split())
        if not text:
            continue
        if msg.role == "user":
            topic = text[:120]
        project_match = _PROJECT_RE.search(text)
        if project_match:
            project = project_match.group(1).strip(" .")
        decision_match = _DECISION_RE.search(text)
        if decision_match:
            decisions.append(decision_match.group(0).strip(" .")[:160])
        goal_match = _GOAL_RE.search(text)
        if goal_match:
            goals.append(goal_match.group(1).strip(" .")[:160])
        task_match = _TASK_RE.search(text)
        if task_match:
            tasks.append(task_match.group(1).strip(" .")[:160])

    return PinnedFacts(
        active_project=project,
        unfinished_tasks=_unique_strings(tasks),
        user_goals=_unique_strings(goals),
        important_decisions=_unique_strings(decisions),
        current_topic=topic,
    )


def load_intelligence_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Read conversation_intelligence block from conversation.metadata."""
    if not metadata:
        return {}
    block = metadata.get(_INTELLIGENCE_META_KEY)
    return dict(block) if isinstance(block, dict) else {}


def merge_intelligence_metadata(
    metadata: dict[str, Any] | None,
    bundle: ConversationContextBundle,
) -> dict[str, Any]:
    """Write intelligence fields into conversation metadata (Postgres JSON)."""
    merged = dict(metadata or {})
    merged[_INTELLIGENCE_META_KEY] = bundle.to_intelligence_metadata()
    return merged


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

    usable = _usable_messages(messages, exclude_pending=exclude_pending)

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
    existing_summary: str | None = None,
    existing_pinned: PinnedFacts | None = None,
    archived_message_count: int = 0,
    active_project: str | None = None,
    current_message: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible facade — Phase 12.2 uses ConversationContextBuilder."""
    builder = ConversationContextBuilder()
    bundle = builder.build(
        messages,
        current_message=current_message,
        existing_summary=existing_summary,
        existing_pinned=existing_pinned,
        archived_message_count=archived_message_count,
        active_project=active_project,
        conversation_id=conversation_id,
        request_id=request_id,
    )
    return bundle.to_hydration_dict()


def _usable_messages(
    messages: Sequence[MessageRecord],
    *,
    exclude_pending: bool = True,
) -> list[MessageRecord]:
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
    return usable


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unique_strings(
    values: Sequence[Any],
    *,
    key_fn: Any | None = None,
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = key_fn(text) if key_fn else text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out

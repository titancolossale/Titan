# =====================================
# Titan Chat Fast Path
# =====================================

"""Compact conversational path for clearly simple requests (Phase 11.4).

Skips multi-step planning, agent loops, tool selection, and oversized context
while still calling the real configured LLM through the provider abstraction.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from brain.request_deadline import check_deadline, get_request_deadline
from config.settings import (
    LLM_MODEL,
    TITAN_FAST_PATH_MAX_CONTEXT_CHARS,
    TITAN_FAST_PATH_MAX_OUTPUT_TOKENS,
)

# Imported lazily in run_fast_path to avoid circular imports at module load.

if TYPE_CHECKING:
    from brain.brain import Brain

logger = logging.getLogger(__name__)

# Whole-message patterns — greetings, identity, light wellbeing checks.
_SIMPLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(?:bonjour|salut|coucou|hello|hi|hey|yo|bonsoir)"
        r"(?:\s+(?:titan|nolan|ibrahim))?[!?.\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:merci|thanks|thank you|ok|okay|d'accord|dac)[!?.\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:comment\s+(?:vas[- ]tu|ça\s+va|ca\s+va)|how\s+are\s+you)"
        r"[!?.\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:qui\s+es[- ]tu|who\s+are\s+you|c'est\s+quoi\s+titan|"
        r"what\s+are\s+you|présente[- ]toi|presente[- ]toi)[!?.\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:ça\s+va|ca\s+va|tout\s+va\s+bien)[!?.\s]*$",
        re.IGNORECASE,
    ),
)

_COMPLEX_MARKERS = (
    "code",
    "python",
    "patch",
    "mission",
    "planifie",
    "planifier",
    "recherche",
    "search",
    "obsidian",
    "github",
    "terminal",
    "pytest",
    "trading",
    "email",
    "calendar",
    "browser",
    "applique",
    "génère",
    "genere",
    "implement",
    "refactor",
    "analyse le projet",
    "architecture",
)


def is_simple_conversational_request(message: str) -> bool:
    """Return True for clearly simple chat that needs no tools/planner/agents."""
    text = " ".join((message or "").strip().split())
    if not text or len(text) > 120:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _COMPLEX_MARKERS):
        return False
    return any(pattern.match(text) for pattern in _SIMPLE_PATTERNS)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for safe diagnostics."""
    return max(1, (len(text) + 3) // 4) if text else 0


def build_fast_path_prompt(
    message: str,
    *,
    user: str | None = None,
    compact_context: str = "",
) -> str:
    """Compact user prompt — identity lives in system instructions."""
    parts: list[str] = []
    if user:
        parts.append(f"Utilisateur actuel : {user}")
    if compact_context:
        clipped = compact_context.strip()[:TITAN_FAST_PATH_MAX_CONTEXT_CHARS]
        if clipped:
            parts.append(f"Contexte minimal :\n{clipped}")
    parts.append(
        "Réponds brièvement et naturellement (français, tutoiement), "
        "sans outils ni plan multi-étapes."
    )
    parts.append(f"Message : {message.strip()}")
    return "\n\n".join(parts)


def _compact_context(brain: Brain) -> str:
    """Tiny situational snapshot — never full memory/tool schemas."""
    try:
        user = getattr(brain.context_manager, "current_user", None) or ""
        project = getattr(brain.context_manager, "active_project", None) or ""
        bits = [b for b in (f"user={user}" if user else "", f"project={project}" if project else "") if b]
        return "; ".join(bits)
    except Exception:
        logger.debug("Fast-path compact context failed", exc_info=True)
        return ""


def run_fast_path(
    brain: Brain,
    message: str,
    *,
    on_text_delta: Any | None = None,
    conversation_context: str = "",
) -> dict[str, Any]:
    """Call the primary conversational model with a compact prompt.

    Returns a dict with response text and safe telemetry. Does not run
    planner, tools, agents, or the full ThinkPipeline.
    """
    check_deadline("fast_path_start")
    user = getattr(brain.context_manager, "current_user", None)
    compact = _compact_context(brain)
    if conversation_context:
        clipped_history = conversation_context.strip()[:TITAN_FAST_PATH_MAX_CONTEXT_CHARS * 4]
        compact = f"{compact}\nHistorique récent:\n{clipped_history}".strip() if compact else (
            f"Historique récent:\n{clipped_history}"
        )
    prompt = build_fast_path_prompt(message, user=user, compact_context=compact)
    prompt_chars = len(prompt)
    prompt_tokens = estimate_tokens(prompt)

    llm = brain.llm
    model_name = getattr(llm, "model", None) or LLM_MODEL
    deadline = get_request_deadline()
    request_id = deadline.request_id if deadline else getattr(llm, "_active_request_id", None)

    logger.info(
        "CHAT_FAST_PATH_PROVIDER request_id=%s model=%s prompt_chars=%d "
        "prompt_tokens_est=%d max_output_tokens=%d stream=%s",
        request_id or "-",
        model_name,
        prompt_chars,
        prompt_tokens,
        TITAN_FAST_PATH_MAX_OUTPUT_TOKENS,
        bool(on_text_delta),
    )

    check_deadline("provider_start")
    # Prefer budget-aware ask only on the concrete LLM class (not MagicMock).
    from brain.llm import LLM as _LLM

    if type(llm) is _LLM:
        response = llm.ask_with_budget(
            prompt,
            max_output_tokens=TITAN_FAST_PATH_MAX_OUTPUT_TOKENS,
            request_id=request_id,
            on_text_delta=on_text_delta,
        )
    else:
        response = llm.ask(prompt)

    check_deadline("provider_end")
    text = (response or "").strip()
    return {
        "response": text,
        "model": model_name,
        "prompt_chars": prompt_chars,
        "prompt_tokens_est": prompt_tokens,
        "planner_skipped": True,
        "tools_skipped": True,
        "agents_skipped": True,
        "oversized_context_skipped": True,
        "max_output_tokens": TITAN_FAST_PATH_MAX_OUTPUT_TOKENS,
        "ttft_ms": getattr(llm, "last_ttft_ms", None),
        "delta_count": getattr(llm, "last_delta_count", 0),
    }

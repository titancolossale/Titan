# =====================================
# Titan Tool Decision — Modification Param Parser
# =====================================

"""Natural-language modification request parameter extraction (Phase 11 — P11-301)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from context.workspace_map import find_area_in_message
from tools.decision.file_param_parser import _PATH_PATTERN

_MODIFY_VERBS = (
    "ajoute ",
    "ajouter ",
    "ajoutez ",
    "add ",
    "add a ",
    "add an ",
    "add new ",
    "create ",
    "crée ",
    "cree ",
    "créer ",
    "implement ",
    "implémente ",
    "implemente ",
    "corrige ",
    "corriger ",
    "fix ",
    "patch ",
    "modifie ",
    "modifier ",
    "modify ",
)
_EXPLAIN_ONLY = (
    "explique",
    "explain",
    "où dois-je",
    "ou dois-je",
    "where should i",
    "where to modify",
    "où modifier",
    "where modify",
    "comment fonctionne",
    "how does",
)
_CAPABILITY_KEYWORDS = (
    "capacité",
    "capacite",
    "capability",
    "outil",
    "tool",
)
_PROVIDER_KEYWORDS = (
    "provider",
    "providers",
    "fournisseur",
)
_MEMORY_KEYWORDS = (
    "mémoire",
    "memoire",
    "memory",
    "remember",
    "souviens",
)
_BUG_KEYWORDS = (
    "bug",
    "erreur",
    "error",
    "fix",
    "corrige",
    "corriger",
    "patch",
    "regression",
    "régression",
)
_COMMAND_KEYWORDS = (
    "commande",
    "command",
    "repl",
    "cli",
    "exit",
    "quit",
)


@dataclass(frozen=True)
class ModificationParams:
    """Parsed parameters for a workspace modification planning request."""

    modification_type: str
    entity_name: str | None = None
    target_path: str | None = None
    target_area: str | None = None
    topic: str | None = None
    ambiguous: bool = False
    ambiguity_reason: str = ""


def is_modification_request(message: str) -> bool:
    """Return True when the message asks to plan a code change, not explain."""
    lowered = message.lower().strip()
    if not any(verb in lowered for verb in _MODIFY_VERBS):
        return False
    if any(signal in lowered for signal in _EXPLAIN_ONLY):
        if not any(verb in lowered for verb in _MODIFY_VERBS[:8]):
            return False
    return True


def parse_modification_params(message: str) -> ModificationParams:
    """Extract modification planning parameters from a user message."""
    lowered = message.lower().strip()
    if not is_modification_request(message):
        return ModificationParams(
            modification_type="unknown",
            ambiguous=True,
            ambiguity_reason="Demande de modification non reconnue.",
        )

    target_path = _extract_path(message)
    target_area = find_area_in_message(message)
    entity = _extract_entity_name(message, lowered)
    topic = _extract_topic(message, lowered)

    if any(kw in lowered for kw in _BUG_KEYWORDS):
        mod_type = "fix_bug"
    elif any(kw in lowered for kw in _COMMAND_KEYWORDS):
        mod_type = "add_command"
    elif any(kw in lowered for kw in _MEMORY_KEYWORDS):
        mod_type = "add_memory"
    elif any(kw in lowered for kw in _PROVIDER_KEYWORDS):
        mod_type = "add_provider"
    elif any(kw in lowered for kw in _CAPABILITY_KEYWORDS):
        mod_type = "add_capability"
    elif target_path:
        mod_type = "fix_bug"
    elif target_area:
        mod_type = _default_type_for_area(target_area)
    else:
        return ModificationParams(
            modification_type="unknown",
            ambiguous=True,
            ambiguity_reason=(
                "Demande de modification ambiguë — précise ce qu'il faut ajouter "
                "(capacité, provider, mémoire, commande) ou quel bug corriger."
            ),
        )

    return ModificationParams(
        modification_type=mod_type,
        entity_name=entity,
        target_path=target_path,
        target_area=target_area,
        topic=topic,
    )


def _default_type_for_area(area: str) -> str:
    mapping = {
        "tools": "add_capability",
        "providers": "add_provider",
        "memory": "add_memory",
        "brain": "fix_bug",
        "config": "add_command",
    }
    return mapping.get(area, "fix_bug")


def _extract_path(message: str) -> str | None:
    match = _PATH_PATTERN.search(message)
    return match.group(0) if match else None


def _extract_entity_name(message: str, lowered: str) -> str | None:
    quoted = re.search(r"[\"']([^\"']+)[\"']", message)
    if quoted:
        return _normalize_entity(quoted.group(1).strip())

    patterns = (
        r"(?:capacit[ée]|capability|outil|tool)\s+([a-zA-Z_][\w-]*)",
        r"(?:provider|fournisseur)\s+([a-zA-Z_][\w-]*)",
        r"(?:commande|command)\s+([a-zA-Z_][\w-]*)",
        r"(?:mémoire|memoire|memory)\s+([a-zA-Z_][\w-]*)",
        r"(?:add|ajoute|crée|cree|create)\s+(?:a|an|une|un|le|la)?\s*([a-zA-Z_][\w-]*)",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered if "mémoire" in pattern else message, re.IGNORECASE)
        if match:
            candidate = _normalize_entity(match.group(1))
            if candidate and candidate not in {
                "new",
                "nouvelle",
                "nouveau",
                "une",
                "un",
                "a",
                "an",
                "the",
                "le",
                "la",
            }:
                return candidate
    return None


def _normalize_entity(name: str) -> str | None:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or None


def _extract_topic(message: str, lowered: str) -> str | None:
    patterns = (
        r"bug(?: dans| in)?\s+(.+?)(?:\.|$|\?)",
        r"erreur(?: dans| in)?\s+(.+?)(?:\.|$|\?)",
        r"fix(?:ing)?\s+(.+?)(?:\.|$|\?)",
        r"corrige(?:r)?\s+(.+?)(?:\.|$|\?)",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            topic = match.group(1).strip(" ?.")
            if topic and len(topic) > 2:
                return topic
    return None

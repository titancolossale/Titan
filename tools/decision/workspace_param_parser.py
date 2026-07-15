# =====================================
# Titan Tool Decision — Workspace Param Parser
# =====================================

"""Natural-language workspace explanation parameter extraction (Phase 11 — P11-002/P11-102)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from context.workspace_map import find_area_in_message
from tools.decision.file_param_parser import _PATH_PATTERN

_EXPLAIN_FILE_KEYWORDS = (
    "explique-moi ce fichier",
    "explique ce fichier",
    "explique-moi le fichier",
    "explique le fichier",
    "explain this file",
    "explain the file",
    "explique-moi ",
    "explique ",
    "explain ",
)
_SUMMARIZE_KEYWORDS = (
    "résume",
    "resume",
    "summarize",
    "summary",
    "résume-le",
    "summarise",
)
_AREA_KEYWORDS = (
    "comment fonctionne",
    "how does",
    "how do",
    "how works",
    "système de",
    "system of",
    "architecture de",
    "architecture of",
)
_CONTROLLER_KEYWORDS = (
    "quels fichiers contrôlent",
    "quels fichiers controlent",
    "which files control",
    "what files control",
    "fichiers contrôlent",
    "files control",
    "fichiers liés",
    "files related",
)
_SEARCH_KEYWORDS = (
    "trouve le fichier",
    "trouve le ",
    "trouve ",
    "find the file",
    "find ",
    "cherche le fichier",
    "cherche ",
    "search for",
    "locate the file",
    "locate ",
)
_CONTROLLER_REFERENTIAL_KEYWORDS = (
    "fichier qui contrôle",
    "fichier qui control",
    "file that controls",
    "le fichier qui contrôle",
    "the file that controls",
)
_FILE_REFERENTIAL_KEYWORDS = _CONTROLLER_REFERENTIAL_KEYWORDS + (
    "fichier qui parle",
    "fichier qui gère",
    "fichier qui gere",
    "file that talks",
    "file that manages",
    "le fichier qui",
    "the file that",
)
_EXTENSION_KEYWORDS = (
    "où dois-je modifier",
    "ou dois-je modifier",
    "where should i modify",
    "where to modify",
    "où modifier",
    "where modify",
    "ajouter une nouvelle capacité",
    "add a new capability",
    "add new capability",
    "nouvelle capacité",
    "new capability",
    "new tool",
    "nouvel outil",
)


@dataclass(frozen=True)
class WorkspaceParams:
    """Parsed parameters for a workspace intelligence operation."""

    workspace_operation: str
    explanation_mode: str
    target_path: str | None = None
    target_area: str | None = None
    topic: str | None = None
    prefer_controllers: bool = False
    ambiguous: bool = False
    ambiguity_reason: str = ""


def parse_workspace_params(message: str) -> WorkspaceParams:
    """Extract workspace explanation parameters from a user message."""
    lowered = message.lower().strip()
    if ".." in message.replace("\\", "/"):
        return WorkspaceParams(
            workspace_operation="explain_file",
            explanation_mode="single_file",
            ambiguous=True,
            ambiguity_reason="Chemin de fichier refusé ou hors du workspace autorisé.",
        )
    target_path = _extract_path(message)
    target_area = find_area_in_message(message)
    topic = _extract_topic(message, lowered)

    if _matches_any(lowered, _EXTENSION_KEYWORDS):
        area = target_area or "tools"
        return WorkspaceParams(
            workspace_operation="find_extension_point",
            explanation_mode="extension_point",
            target_area=area,
            topic=topic,
        )

    if _is_search_then_read_request(lowered, target_path, target_area):
        filename = target_path or _extract_bare_filename(message)
        mode = (
            "read_and_summarize"
            if _matches_any(lowered, _SUMMARIZE_KEYWORDS)
            else "single_file"
        )
        return WorkspaceParams(
            workspace_operation="search_then_read",
            explanation_mode=mode,
            target_path=filename,
            target_area=target_area,
            topic=topic,
            prefer_controllers=_matches_any(lowered, _CONTROLLER_REFERENTIAL_KEYWORDS),
        )

    if target_path:
        if _is_traversal_attempt(target_path):
            return WorkspaceParams(
                workspace_operation="explain_file",
                explanation_mode="single_file",
                target_path=target_path,
                ambiguous=True,
                ambiguity_reason="Chemin de fichier refusé ou hors du workspace autorisé.",
            )
        mode = "read_and_summarize" if _matches_any(lowered, _SUMMARIZE_KEYWORDS) else "single_file"
        op = "read_and_summarize" if mode == "read_and_summarize" else "explain_file"
        return WorkspaceParams(
            workspace_operation=op,
            explanation_mode=mode,
            target_path=target_path,
            topic=topic,
        )

    if _matches_any(lowered, _CONTROLLER_KEYWORDS):
        area = target_area
        if area is None:
            return WorkspaceParams(
                workspace_operation="identify_controllers",
                explanation_mode="identify_controllers",
                ambiguous=True,
                ambiguity_reason=(
                    "Identification de fichiers contrôleurs ambiguë — "
                    "précise la zone (Brain, mémoire, agents, outils, etc.)."
                ),
            )
        return WorkspaceParams(
            workspace_operation="identify_controllers",
            explanation_mode="identify_controllers",
            target_area=area,
            topic=topic,
        )

    if _matches_any(lowered, _AREA_KEYWORDS) or (
        target_area is not None and _matches_any(lowered, _EXPLAIN_FILE_KEYWORDS + _SUMMARIZE_KEYWORDS)
    ):
        if target_area is None:
            return WorkspaceParams(
                workspace_operation="explain_area",
                explanation_mode="area_overview",
                ambiguous=True,
                ambiguity_reason=(
                    "Explication de zone ambiguë — précise quelle partie du projet "
                    "(mémoire, Brain, agents, outils, etc.)."
                ),
            )
        return WorkspaceParams(
            workspace_operation="explain_area",
            explanation_mode="area_overview",
            target_area=target_area,
            topic=topic,
        )

    if _matches_any(lowered, _EXPLAIN_FILE_KEYWORDS) or _matches_any(lowered, _SUMMARIZE_KEYWORDS):
        filename = _extract_bare_filename(message)
        if filename:
            return WorkspaceParams(
                workspace_operation="search_then_read",
                explanation_mode="single_file",
                target_path=filename,
                topic=topic,
            )
        return WorkspaceParams(
            workspace_operation="explain_file",
            explanation_mode="single_file",
            ambiguous=True,
            ambiguity_reason=(
                "Explication de fichier ambiguë — précise le chemin ou le nom du fichier."
            ),
        )

    if target_area is not None:
        return WorkspaceParams(
            workspace_operation="explain_area",
            explanation_mode="area_overview",
            target_area=target_area,
            topic=topic,
        )

    return WorkspaceParams(
        workspace_operation="explain_area",
        explanation_mode="area_overview",
        ambiguous=True,
        ambiguity_reason="Demande workspace ambiguë — précise un fichier ou une zone du projet.",
    )


def _extract_path(message: str) -> str | None:
    match = _PATH_PATTERN.search(message)
    return match.group(0) if match else None


def _extract_bare_filename(message: str) -> str | None:
    quoted = re.search(r"[\"']([^\"']+)[\"']", message)
    if quoted:
        candidate = quoted.group(1).strip()
        if "." in candidate:
            return candidate
    match = _PATH_PATTERN.search(message)
    return match.group(0) if match else None


def _is_search_then_read_request(
    lowered: str,
    target_path: str | None,
    target_area: str | None,
) -> bool:
    """Return True when the user expects search followed by read/explain."""
    has_search = _matches_any(lowered, _SEARCH_KEYWORDS)
    has_referential = _matches_any(lowered, _FILE_REFERENTIAL_KEYWORDS)
    has_explain = _matches_any(
        lowered,
        _EXPLAIN_FILE_KEYWORDS + _SUMMARIZE_KEYWORDS + _CONTROLLER_KEYWORDS,
    )
    if has_referential and has_explain:
        return True
    if has_search and has_explain:
        return True
    if has_search and (target_path is not None or target_area is not None):
        return True
    return False


def _extract_topic(message: str, lowered: str) -> str | None:
    patterns = (
        r"fichier qui parle de\s+(.+?)(?:\s+et|\?|$)",
        r"file that talks about\s+(.+?)(?:\s+and|\?|$)",
        r"comment fonctionne(?: le| la| l')?\s*(.+?)(?:\?|$)",
        r"how does(?: the)?\s+(.+?)(?:\?|$)",
        r"système de\s+(.+?)(?:\?|$)",
        r"file that controls(?: the)?\s+(.+?)(?:\?|$)",
        r"fichier qui contr(?:ô|o)le(?: le| la| l')?\s*(.+?)(?:\?|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered if pattern.startswith("comment") else message, re.IGNORECASE)
        if match:
            topic = match.group(1).strip(" ?.")
            if topic and len(topic) > 2:
                return topic
    return None


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _is_traversal_attempt(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    if ".." in normalized.split("/"):
        return True
    if normalized.startswith("/") or re.match(r"^[a-zA-Z]:", normalized):
        return True
    return False

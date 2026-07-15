# =====================================
# Titan Tool Decision — File Param Parser
# =====================================

"""Natural-language file operation parameter extraction (Phase 10B — P10B-1503)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from tools.decision.intent import Intent

_PATH_PATTERN = re.compile(
    r"(?:[\w./\\-]+[/\\])?[\w.-]+\.(?:py|txt|md|json|yaml|yml|toml|cfg|ini|pdf|docx?)",
    re.IGNORECASE,
)
_DIR_PATTERN = re.compile(
    r"(?:dans|in|under|sous)\s+([\"']?)([\w./\\-]+)\1",
    re.IGNORECASE,
)
_DIR_STOPWORDS = frozenset({
    "les",
    "le",
    "la",
    "des",
    "du",
    "the",
    "a",
    "fichiers",
    "fichier",
    "files",
    "file",
})
_QUOTED_PATTERN = re.compile(r"[\"']([^\"']+)[\"']")

_EXTENSION_ALIASES: dict[str, str] = {
    "python": "py",
    "py": "py",
    "markdown": "md",
    "md": "md",
    "json": "json",
    "yaml": "yaml",
    "yml": "yml",
    "texte": "txt",
    "text": "txt",
    "txt": "txt",
    "javascript": "js",
    "typescript": "ts",
    "js": "js",
    "ts": "ts",
}

_LIST_KEYWORDS = (
    "liste",
    "list ",
    "listes",
    "montre les fichiers",
    "show files",
    "show the files",
    "affiche les fichiers",
)
_SEARCH_KEYWORDS = (
    "trouve",
    "find",
    "cherche",
    "search",
    "locate",
    "look for",
    "recherche",
)
_READ_KEYWORDS = (
    "lire le fichier",
    "lire fichier",
    "read file",
    "contenu du fichier",
    "affiche le fichier",
    "ouvre le fichier",
    "show file",
    "open file",
)
_METADATA_KEYWORDS = (
    "métadonnées",
    "metadonnees",
    "metadata",
    "info du fichier",
    "file info",
    "informations sur le fichier",
    "taille du fichier",
)

_DEFAULT_MAX_RESULTS = 50


@dataclass(frozen=True)
class FileOperationParams:
    """Parsed parameters for a filesystem tool invocation."""

    operation: str
    directory: str | None = None
    filename: str | None = None
    extension: str | None = None
    keyword: str | None = None
    recursive: bool = True
    max_results: int = _DEFAULT_MAX_RESULTS
    ambiguous: bool = False
    ambiguity_reason: str = ""


def parse_file_params(message: str, intent: Intent) -> FileOperationParams:
    """Extract filesystem parameters from natural-language user message."""
    lowered = message.lower().strip()
    operation = _operation_for_intent(intent, lowered)
    directory = _extract_directory(message, lowered)
    filename = _extract_filename(message)
    extension = _extract_extension(lowered)
    keyword = _extract_keyword(message, lowered, intent)
    recursive = _extract_recursive(lowered, operation)
    max_results = _extract_max_results(lowered)

    ambiguous, reason = _assess_ambiguity(
        intent=intent,
        operation=operation,
        directory=directory,
        filename=filename,
        extension=extension,
        keyword=keyword,
        lowered=lowered,
    )

    return FileOperationParams(
        operation=operation,
        directory=directory,
        filename=filename,
        extension=extension,
        keyword=keyword,
        recursive=recursive,
        max_results=max_results,
        ambiguous=ambiguous,
        ambiguity_reason=reason,
    )


def params_to_tool_dict(params: FileOperationParams) -> dict:
    """Convert parsed params to FileReadTool / provider invocation dict."""
    payload: dict = {"action": params.operation}

    if params.operation == "read_file":
        path = params.filename or params.directory or ""
        payload["path"] = path
    elif params.operation == "get_metadata":
        path = params.filename or params.directory or ""
        payload["path"] = path
    elif params.operation == "list_directory":
        payload["path"] = params.directory or "."
        if params.extension:
            payload["extension"] = params.extension
    elif params.operation == "search_files":
        payload["directory"] = params.directory or "."
        if params.filename:
            payload["pattern"] = f"*{params.filename}" if "*" not in params.filename else params.filename
        elif params.extension:
            payload["pattern"] = f"*.{params.extension.lstrip('.')}"
        else:
            payload["pattern"] = "*"
        if params.keyword:
            payload["keyword"] = params.keyword
        payload["recursive"] = params.recursive
        payload["max_results"] = params.max_results

    return payload


def _operation_for_intent(intent: Intent, lowered: str) -> str:
    if intent == Intent.FILE_LIST:
        return "list_directory"
    if intent == Intent.FILE_SEARCH:
        return "search_files"
    if intent == Intent.FILE_METADATA:
        return "get_metadata"
    if intent == Intent.FILE_READ:
        return "read_file"
    if any(kw in lowered for kw in _METADATA_KEYWORDS):
        return "get_metadata"
    if any(kw in lowered for kw in _LIST_KEYWORDS):
        return "list_directory"
    if any(kw in lowered for kw in _SEARCH_KEYWORDS):
        return "search_files"
    return "read_file"


def _extract_directory(message: str, lowered: str) -> str | None:
    if "du projet" in lowered or "of the project" in lowered or "project root" in lowered:
        return "."
    match = _DIR_PATTERN.search(message)
    if match:
        candidate = match.group(2).strip().rstrip("/\\")
        if candidate.lower() in _DIR_STOPWORDS:
            return None
        return candidate
    return None


def _extract_filename(message: str) -> str | None:
    match = _PATH_PATTERN.search(message)
    if match:
        return match.group(0)
    quoted = _QUOTED_PATTERN.search(message)
    if quoted:
        candidate = quoted.group(1).strip()
        if "." in candidate or "/" in candidate or "\\" in candidate:
            return candidate
    return None


def _extract_extension(lowered: str) -> str | None:
    typed = re.search(
        r"fichiers?\s+(python|markdown|json|yaml|texte|text|javascript|typescript)\b",
        lowered,
    )
    if typed:
        return _EXTENSION_ALIASES.get(typed.group(1).lower(), typed.group(1).lower())
    dotted = re.search(r"\.([\w]{1,5})\b", lowered)
    if dotted:
        token = dotted.group(1).lower()
        if token in _EXTENSION_ALIASES.values() or len(token) <= 4:
            return token
    for alias, ext in _EXTENSION_ALIASES.items():
        if re.search(rf"\bfichiers?\s+{re.escape(alias)}\b|\b{re.escape(alias)}\s+fichiers?\b", lowered):
            return ext
    return None


def _extract_keyword(message: str, lowered: str, intent: Intent) -> str | None:
    if intent not in {Intent.FILE_SEARCH, Intent.FILE}:
        return None

    keyword_patterns = (
        r"(?:qui parlent de|talking about|contenant|containing|with|avec)\s+[\"']?([^\"'.?!]+)[\"']?",
        r"(?:mot[- ]clé|keyword)\s+[\"']?([^\"'.?!]+)[\"']?",
    )
    for pattern in keyword_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    if "todo" in lowered and intent == Intent.FILE_SEARCH:
        return "TODO"

    return None


def _extract_recursive(lowered: str, operation: str) -> bool:
    if "non récursif" in lowered or "non-recursive" in lowered or "not recursive" in lowered:
        return False
    if "récursif" in lowered or "recursive" in lowered:
        return True
    if operation == "list_directory":
        return False
    return True


def _extract_max_results(lowered: str) -> int:
    match = re.search(r"(?:max|limit|limite)\s+(\d+)", lowered)
    if match:
        return min(int(match.group(1)), 200)
    return _DEFAULT_MAX_RESULTS


def _assess_ambiguity(
    *,
    intent: Intent,
    operation: str,
    directory: str | None,
    filename: str | None,
    extension: str | None,
    keyword: str | None,
    lowered: str,
) -> tuple[bool, str]:
    if intent == Intent.FILE_SEARCH:
        has_target = bool(filename or keyword or extension)
        if not has_target and not any(kw in lowered for kw in _SEARCH_KEYWORDS):
            return True, "Recherche de fichiers sans critère (nom, extension ou mot-clé)."
        if not has_target:
            return True, (
                "Recherche de fichiers ambiguë — précise un nom, une extension "
                "ou un mot-clé à chercher."
            )

    if intent == Intent.FILE_READ:
        if not filename and not directory:
            return True, "Lecture de fichier ambiguë — précise le chemin du fichier."

    if intent == Intent.FILE_METADATA:
        if not filename and not directory:
            return True, "Métadonnées ambiguës — précise le fichier cible."

    if intent == Intent.FILE and operation == "read_file":
        if not filename and not any(kw in lowered for kw in _READ_KEYWORDS):
            if not directory:
                return True, "Opération fichier ambiguë — précise le fichier ou l'action souhaitée."

    return False, ""

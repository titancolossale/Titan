# =====================================
# Titan Tool Decision — Search Chain
# =====================================

"""Search-then-read chaining for workspace intelligence (Phase 11 — P11-101–P11-106)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from context.workspace_map import controller_files_for_area, files_for_area
from tools.decision.workspace_param_parser import WorkspaceParams
from tools.path_guard import PathGuardError, resolve_allowed_path
from tools.providers.file_system_provider import LocalFileSystemProvider
from tools.tool_result import ToolRequest, ToolResult

STRONG_MATCH_THRESHOLD = 0.72
_STOPWORDS = frozenset({
    "le", "la", "les", "de", "du", "des", "un", "une", "the", "a", "an", "and", "et",
    "qui", "que", "which", "that", "file", "fichier", "system", "système", "systeme",
})


@dataclass(frozen=True)
class SearchQuery:
    """Normalized search intent for workspace file discovery."""

    display: str
    keyword: str | None = None
    pattern: str | None = None
    target_area: str | None = None
    filename_hint: str | None = None
    use_controllers: bool = False


@dataclass(frozen=True)
class SearchSelection:
    """Result of ranking search candidates."""

    status: str
    selected_file: str | None
    strong_matches: tuple[str, ...]
    all_results: tuple[str, ...]
    confidence: float
    ambiguity_reason: str = ""


def build_search_query(params: WorkspaceParams) -> SearchQuery:
    """Build a search query from parsed workspace parameters."""
    keyword = _keyword_from_params(params)
    pattern = _pattern_from_params(params)
    filename_hint = None
    if params.target_path and _is_bare_filename(params.target_path):
        filename_hint = Path(params.target_path).name
    display_parts = []
    if params.target_path:
        display_parts.append(params.target_path)
    if params.topic:
        display_parts.append(params.topic)
    if params.target_area:
        display_parts.append(f"area:{params.target_area}")
    if keyword:
        display_parts.append(f"keyword:{keyword}")
    display = " | ".join(display_parts) if display_parts else "workspace search"
    return SearchQuery(
        display=display,
        keyword=keyword,
        pattern=pattern,
        target_area=params.target_area,
        filename_hint=filename_hint,
        use_controllers=params.prefer_controllers,
    )


def build_search_tool_request(query: SearchQuery) -> ToolRequest:
    """Build a file_read search_files tool request."""
    params: dict = {
        "action": "search_files",
        "directory": ".",
        "recursive": True,
        "max_results": 20,
    }
    if query.keyword:
        params["keyword"] = query.keyword
        params["pattern"] = query.pattern or "*"
    elif query.pattern:
        params["pattern"] = query.pattern
    else:
        params["pattern"] = "*"
    return ToolRequest("file_read", params)


def run_local_search(project_root: Path, query: SearchQuery) -> tuple[str, ...]:
    """Run a local search without tool dispatch (filename, keyword, pattern, area)."""
    root = project_root.resolve()
    results: list[str] = []

    if query.filename_hint:
        results.extend(_find_by_filename(root, query.filename_hint))

    if query.use_controllers and query.target_area:
        for path in controller_files_for_area(query.target_area, project_root=root):
            if (root / path).is_file():
                results.append(path)
    elif query.keyword and not results:
        provider = LocalFileSystemProvider(root)
        response = provider.execute(
            "search_files",
            directory=".",
            keyword=query.keyword,
            pattern=query.pattern or "*",
            recursive=True,
            max_results=20,
        )
        if response.success and isinstance(response.data, list):
            results.extend(str(item) for item in response.data)

    if query.pattern and query.pattern != "*" and not query.keyword and not results:
        provider = LocalFileSystemProvider(root)
        response = provider.execute(
            "search_files",
            directory=".",
            pattern=query.pattern,
            recursive=True,
            max_results=20,
        )
        if response.success and isinstance(response.data, list):
            results.extend(str(item) for item in response.data)

    if query.target_area and not results:
        for path in controller_files_for_area(query.target_area, project_root=root):
            if (root / path).is_file():
                results.append(path)
        if not results:
            for path in files_for_area(query.target_area, project_root=root):
                if (root / path).is_file():
                    results.append(path)

    unique = sorted({path.replace("\\", "/") for path in results})
    safe: list[str] = []
    for path in unique:
        try:
            resolve_allowed_path(path, root, must_exist=True)
            safe.append(path)
        except PathGuardError:
            continue
    return tuple(safe)


def select_strong_matches(
    results: tuple[str, ...],
    query: SearchQuery,
    params: WorkspaceParams,
    project_root: Path,
) -> SearchSelection:
    """Rank search results and decide single match, ambiguity, or no match."""
    if not results:
        return SearchSelection(
            status="no_match",
            selected_file=None,
            strong_matches=(),
            all_results=(),
            confidence=0.0,
            ambiguity_reason="Aucun fichier correspondant trouvé.",
        )

    scored = sorted(
        ((path, _score_candidate(path, query, params, project_root)) for path in results),
        key=lambda item: item[1],
        reverse=True,
    )
    strong = tuple(path for path, score in scored if score >= STRONG_MATCH_THRESHOLD)

    if len(strong) == 1:
        score = scored[0][1]
        return SearchSelection(
            status="single_match",
            selected_file=strong[0],
            strong_matches=strong,
            all_results=results,
            confidence=min(max(score, 0.55), 0.98),
        )

    if len(strong) > 1:
        top_path, top_score = scored[0]
        second_score = scored[1][1]
        if top_score - second_score >= 0.07:
            return SearchSelection(
                status="single_match",
                selected_file=top_path,
                strong_matches=(top_path,),
                all_results=results,
                confidence=min(max(top_score, 0.55), 0.98),
            )
        listed = ", ".join(strong[:5])
        return SearchSelection(
            status="multiple_matches",
            selected_file=None,
            strong_matches=strong,
            all_results=results,
            confidence=0.45,
            ambiguity_reason=(
                f"Plusieurs fichiers correspondent fortement : {listed}. "
                "Précise le chemin complet."
            ),
        )

    if len(results) == 1:
        return SearchSelection(
            status="single_match",
            selected_file=results[0],
            strong_matches=results,
            all_results=results,
            confidence=0.62,
        )

    if query.filename_hint and len(results) > 1:
        listed = ", ".join(results[:5])
        return SearchSelection(
            status="multiple_matches",
            selected_file=None,
            strong_matches=(),
            all_results=results,
            confidence=0.4,
            ambiguity_reason=(
                f"Plusieurs fichiers correspondent à {query.filename_hint!r} : {listed}. "
                "Précise le chemin complet."
            ),
        )

    listed = ", ".join(results[:5])
    return SearchSelection(
        status="multiple_matches",
        selected_file=None,
        strong_matches=(),
        all_results=results,
        confidence=0.4,
        ambiguity_reason=(
            f"Plusieurs fichiers possibles : {listed}. Précise le fichier à expliquer."
        ),
    )


def extract_search_results(tool_result: ToolResult) -> tuple[str, ...]:
    """Extract normalized search paths from a search_files tool result."""
    metadata = getattr(tool_result, "metadata", None) or {}
    raw = metadata.get("search_results")
    if isinstance(raw, list):
        return tuple(str(item).replace("\\", "/") for item in raw)

    if not getattr(tool_result, "success", False):
        return ()

    data = getattr(tool_result, "data", "") or ""
    paths: list[str] = []
    for line in str(data).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            paths.append(stripped[2:].strip().replace("\\", "/"))
    return tuple(paths)


def read_tool_request(path: str) -> ToolRequest:
    """Build a read_file request for a resolved project path."""
    return ToolRequest("file_read", {"action": "read_file", "path": path})


def no_match_tool_result(search_query: str) -> ToolResult:
    """Surface a no-match outcome after search chaining."""
    message = f"Aucun fichier correspondant trouvé pour : {search_query}."
    return ToolResult(
        tool_name="file_read",
        success=False,
        error=message,
        source="search_chain",
        metadata={
            "file_operation": "search_chain",
            "ambiguity_status": "no_match",
            "search_query": search_query,
        },
    )


def ambiguity_tool_result(reason: str, candidates: tuple[str, ...]) -> ToolResult:
    """Surface ambiguity after search chaining."""
    listed = ", ".join(candidates[:8]) if candidates else "(aucun candidat)"
    return ToolResult(
        tool_name="file_read",
        success=False,
        error=f"{reason} Candidats : {listed}.",
        source="search_chain",
        metadata={
            "file_operation": "search_chain",
            "ambiguity_status": "ambiguous",
            "search_results": list(candidates),
        },
    )


def _score_candidate(
    path: str,
    query: SearchQuery,
    params: WorkspaceParams,
    project_root: Path,
) -> float:
    score = 0.0
    normalized = path.replace("\\", "/").lower()
    name = Path(path).name.lower()

    if query.filename_hint and name == query.filename_hint.lower():
        score += 0.95

    if params.target_path and name == Path(params.target_path).name.lower():
        score += 0.9

    if query.target_area:
        controllers = controller_files_for_area(query.target_area, project_root=project_root)
        if path in controllers:
            score += 0.88 - controllers.index(path) * 0.06

    topic_tokens = _tokenize(params.topic or "")
    if topic_tokens:
        path_hits = sum(1 for token in topic_tokens if token in normalized)
        score += min(0.35, path_hits * 0.12)

    if query.keyword:
        keyword = query.keyword.lower()
        if keyword in normalized:
            score += 0.25
        if keyword in name:
            score += 0.2

    return min(score, 1.0)


def _keyword_from_params(params: WorkspaceParams) -> str | None:
    topic_lower = (params.topic or "").lower()
    if params.target_area:
        area_keywords = {
            "memory": "memory",
            "brain": "Brain",
            "agents": "Agent",
            "tools": "Tool",
        }
        area_hint = area_keywords.get(params.target_area)
        if area_hint and (
            not params.topic
            or params.target_area in topic_lower
            or any(token in topic_lower for token in ("mémoire", "memoire", "memory", "brain", "agent", "outil"))
        ):
            return area_hint
    if params.topic:
        tokens = [token for token in _tokenize(params.topic) if len(token) > 3]
        if tokens:
            return tokens[-1]
    return None


def _pattern_from_params(params: WorkspaceParams) -> str | None:
    if params.target_path and _is_bare_filename(params.target_path):
        return f"*{Path(params.target_path).name}*"
    return None


def _find_by_filename(project_root: Path, filename: str) -> list[str]:
    name = Path(filename).name
    matches: list[str] = []
    for path in project_root.rglob(name):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(project_root.resolve()).as_posix()
            resolve_allowed_path(rel, project_root, must_exist=True)
        except (ValueError, PathGuardError):
            continue
        matches.append(rel)
    return matches


def _tokenize(text: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", text.lower())
    return tuple(token for token in tokens if token not in _STOPWORDS and len(token) > 2)


def _is_bare_filename(path: str) -> bool:
    return "/" not in path and "\\" not in path

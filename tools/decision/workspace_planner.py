# =====================================
# Titan Tool Decision — Workspace Planner
# =====================================

"""Plan filesystem tool requests for workspace intelligence (Phase 11 — P11-001/002/P11-101)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from context.workspace_map import (
    controller_files_for_area,
    extension_point_files,
    files_for_area,
    summarize_area,
)
from tools.decision.search_chain import (
    build_search_query,
    build_search_tool_request,
    read_tool_request,
    run_local_search,
    select_strong_matches,
)
from tools.decision.workspace_param_parser import WorkspaceParams, parse_workspace_params
from tools.path_guard import PathGuardError, resolve_allowed_path
from tools.tool_result import ToolRequest

_MAX_READS = 3


@dataclass(frozen=True)
class WorkspacePlan:
    """Planned workspace operation with tool requests and metadata."""

    tool_requests: tuple[ToolRequest, ...]
    workspace_operation: str
    explanation_mode: str
    files_considered: tuple[str, ...]
    confidence: float
    ambiguous: bool = False
    ambiguity_reason: str = ""
    area_summary: str = ""
    search_query: str = ""
    chain_after_search: bool = False
    search_results: tuple[str, ...] = ()
    selected_file: str | None = None
    ambiguity_status: str = ""


def plan_workspace_operation(
    message: str,
    *,
    project_root: Path,
    confidence: float = 0.85,
) -> WorkspacePlan:
    """Build tool requests and metadata for a workspace intelligence request."""
    params = parse_workspace_params(message)
    if params.ambiguous:
        return WorkspacePlan(
            tool_requests=(),
            workspace_operation=params.workspace_operation,
            explanation_mode=params.explanation_mode,
            files_considered=(),
            confidence=min(confidence, 0.45),
            ambiguous=True,
            ambiguity_reason=params.ambiguity_reason,
        )

    if params.workspace_operation == "find_extension_point":
        return _plan_extension_point(params, confidence=confidence)

    if params.workspace_operation == "identify_controllers":
        return _plan_identify_controllers(params, project_root, confidence=confidence)

    if params.workspace_operation == "explain_area":
        return _plan_explain_area(params, project_root, confidence=confidence)

    if params.workspace_operation == "search_then_read":
        return _plan_search_then_read(params, project_root, confidence=confidence)

    if params.workspace_operation in {"explain_file", "read_and_summarize"}:
        return _plan_file_explain(params, project_root, confidence=confidence)

    return WorkspacePlan(
        tool_requests=(),
        workspace_operation=params.workspace_operation,
        explanation_mode=params.explanation_mode,
        files_considered=(),
        confidence=0.35,
        ambiguous=True,
        ambiguity_reason="Opération workspace non reconnue.",
    )


def resolve_filename(project_root: Path, filename: str) -> tuple[str | None, tuple[str, ...]]:
    """Resolve a filename to a unique project-relative path via lightweight scan."""
    name = Path(filename).name
    if not name:
        return None, ()
    matches: list[str] = []
    for path in project_root.rglob(name):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(project_root.resolve()).as_posix()
        except ValueError:
            continue
        try:
            resolve_allowed_path(rel, project_root, must_exist=True)
        except PathGuardError:
            continue
        matches.append(rel)
    unique = tuple(sorted(set(matches)))
    if len(unique) == 1:
        return unique[0], unique
    return None, unique


def _plan_extension_point(params: WorkspaceParams, *, confidence: float) -> WorkspacePlan:
    area = params.target_area or "tools"
    considered = extension_point_files(area)
    key_files = files_for_area(area)[:_MAX_READS]
    requests = tuple(
        ToolRequest("file_read", {"action": "read_file", "path": path})
        for path in key_files
    )
    return WorkspacePlan(
        tool_requests=requests,
        workspace_operation="find_extension_point",
        explanation_mode="extension_point",
        files_considered=considered + key_files,
        confidence=confidence,
        area_summary=summarize_area(area),
    )


def _plan_identify_controllers(
    params: WorkspaceParams,
    project_root: Path,
    *,
    confidence: float,
) -> WorkspacePlan:
    area = params.target_area or "brain"
    considered = controller_files_for_area(area, project_root=project_root)
    requests: list[ToolRequest] = []
    for path in considered[:_MAX_READS]:
        requests.append(
            ToolRequest("file_read", {"action": "get_metadata", "path": path}),
        )
        if len(requests) >= _MAX_READS:
            break
    if not requests and considered:
        requests.append(
            ToolRequest("file_read", {"action": "read_file", "path": considered[0]}),
        )
    return WorkspacePlan(
        tool_requests=tuple(requests),
        workspace_operation="identify_controllers",
        explanation_mode="identify_controllers",
        files_considered=considered,
        confidence=confidence,
        area_summary=summarize_area(area),
    )


def _plan_explain_area(
    params: WorkspaceParams,
    project_root: Path,
    *,
    confidence: float,
) -> WorkspacePlan:
    area = params.target_area or "brain"
    considered = files_for_area(area, project_root=project_root)[:_MAX_READS]
    requests = tuple(
        ToolRequest("file_read", {"action": "read_file", "path": path})
        for path in considered
    )
    return WorkspacePlan(
        tool_requests=requests,
        workspace_operation="explain_area",
        explanation_mode="area_overview",
        files_considered=considered,
        confidence=confidence,
        area_summary=summarize_area(area),
    )


def _plan_search_then_read(
    params: WorkspaceParams,
    project_root: Path,
    *,
    confidence: float,
) -> WorkspacePlan:
    """Plan search-then-read with local resolution or deferred tool search (P11-101)."""
    query = build_search_query(params)
    local_results = run_local_search(project_root, query)
    selection = select_strong_matches(local_results, query, params, project_root)

    if selection.status == "single_match" and selection.selected_file:
        return WorkspacePlan(
            tool_requests=(read_tool_request(selection.selected_file),),
            workspace_operation="search_then_read",
            explanation_mode=params.explanation_mode,
            files_considered=selection.all_results or (selection.selected_file,),
            confidence=selection.confidence,
            search_query=query.display,
            search_results=selection.all_results,
            selected_file=selection.selected_file,
            ambiguity_status="clear",
        )

    if selection.status == "multiple_matches":
        candidates = selection.strong_matches or selection.all_results
        return WorkspacePlan(
            tool_requests=(),
            workspace_operation="search_then_read",
            explanation_mode=params.explanation_mode,
            files_considered=candidates,
            confidence=selection.confidence,
            ambiguous=True,
            ambiguity_reason=selection.ambiguity_reason,
            search_query=query.display,
            search_results=selection.all_results,
            ambiguity_status="ambiguous",
        )

    if selection.status == "no_match" and not local_results:
        return WorkspacePlan(
            tool_requests=(build_search_tool_request(query),),
            workspace_operation="search_then_read",
            explanation_mode=params.explanation_mode,
            files_considered=(),
            confidence=min(confidence, 0.55),
            search_query=query.display,
            chain_after_search=True,
            ambiguity_status="pending",
        )

    return WorkspacePlan(
        tool_requests=(),
        workspace_operation="search_then_read",
        explanation_mode=params.explanation_mode,
        files_considered=(),
        confidence=0.35,
        ambiguous=True,
        ambiguity_reason=selection.ambiguity_reason or "Aucun fichier correspondant trouvé.",
        search_query=query.display,
        search_results=selection.all_results,
        ambiguity_status="no_match",
    )


def _plan_file_explain(
    params: WorkspaceParams,
    project_root: Path,
    *,
    confidence: float,
) -> WorkspacePlan:
    target = params.target_path
    if target is None:
        return WorkspacePlan(
            tool_requests=(),
            workspace_operation=params.workspace_operation,
            explanation_mode=params.explanation_mode,
            files_considered=(),
            confidence=0.4,
            ambiguous=True,
            ambiguity_reason="Aucun fichier cible identifié.",
        )

    if _is_bare_filename(target):
        unique, candidates = resolve_filename(project_root, target)
        if len(candidates) > 1:
            return WorkspacePlan(
                tool_requests=(),
                workspace_operation="search_then_read",
                explanation_mode=params.explanation_mode,
                files_considered=candidates,
                confidence=0.45,
                ambiguous=True,
                ambiguity_reason=(
                    f"Plusieurs fichiers correspondent à {target!r} : "
                    f"{', '.join(candidates[:5])}. Précise le chemin complet."
                ),
            )
        if unique:
            return WorkspacePlan(
                tool_requests=(
                    ToolRequest("file_read", {"action": "read_file", "path": unique}),
                ),
                workspace_operation="read_resolved_search",
                explanation_mode=params.explanation_mode,
                files_considered=candidates or (unique,),
                confidence=confidence,
            )

    try:
        resolved = resolve_allowed_path(target, project_root, must_exist=True)
        normalized = resolved.relative_to(project_root.resolve()).as_posix()
        return WorkspacePlan(
            tool_requests=(
                ToolRequest("file_read", {"action": "read_file", "path": normalized}),
            ),
            workspace_operation=params.workspace_operation,
            explanation_mode=params.explanation_mode,
            files_considered=(normalized,),
            confidence=confidence,
        )
    except PathGuardError as exc:
        message = str(exc).lower()
        if ".." in target or "sort du répertoire" in message or "refusé" in message:
            return WorkspacePlan(
                tool_requests=(),
                workspace_operation=params.workspace_operation,
                explanation_mode=params.explanation_mode,
                files_considered=(target,),
                confidence=0.2,
                ambiguous=True,
                ambiguity_reason="Chemin de fichier refusé ou hors du workspace autorisé.",
            )

    search_name = Path(target).name
    return WorkspacePlan(
        tool_requests=(
            ToolRequest(
                "file_read",
                {
                    "action": "search_files",
                    "directory": ".",
                    "pattern": f"*{search_name}*",
                    "recursive": True,
                    "max_results": 10,
                },
            ),
        ),
        workspace_operation="search_then_read",
        explanation_mode=params.explanation_mode,
        files_considered=(target,),
        confidence=min(confidence, 0.55),
    )


def _is_bare_filename(path: str) -> bool:
    return "/" not in path and "\\" not in path

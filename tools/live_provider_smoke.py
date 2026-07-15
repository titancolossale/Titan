# =====================================
# Titan Live Provider Smoke Examples
# =====================================

"""Manual smoke helpers for Phase 10B Batch 14 — live provider integration closure (P10B-1401).

Run from project root::

    python -c "from tools.live_provider_smoke import smoke_web_search; smoke_web_search()"

REPL examples (``python main.py``) — natural-language prompts that exercise the full loop:

Web search (BraveSearchProvider)::

    Recherche web : dernières actualités sur l'IA agentique

GitHub read-only (GitHubProvider)::

    Liste les commits du dépôt github titan-org/Titan

Local file read (FileSystemProvider)::

    Lire le fichier config/settings.py

Programmatic smoke (decision → runtime → telemetry → performance)::

    from pathlib import Path
    from tools.live_provider_smoke import smoke_file_read, smoke_github, smoke_web_search

    smoke_web_search("Titan AI agent")
    smoke_github("get_authenticated_user")
    smoke_file_read(Path("."), "config/settings.py")
"""

from __future__ import annotations

from pathlib import Path

from brain.decision_execution_bridge import (
    availability_resolver_from_manager,
    decision_engine_from_manager,
)
from tools.decision.execution_context import attach_decision_report, enrich_decision_report_from_result
from tools.decision.models import FallbackAction
from tools.tool_enums import ExecutionMode
from tools.tool_manager import ToolManager
from tools.tool_run_models import ToolExecutionContext


def _manager(project_root: Path | None = None) -> ToolManager:
    root = (project_root or Path(".")).resolve()
    return ToolManager(project_root=root, use_runtime_v2=True)


def smoke_web_search(query: str = "Titan AI", *, project_root: Path | None = None) -> dict:
    """Run web search through decision engine + runtime + performance loop."""
    manager = _manager(project_root)
    engine = decision_engine_from_manager(manager)
    resolver = availability_resolver_from_manager(manager)
    report = engine.decide(f"Recherche web : {query}", availability_resolver=resolver)
    assert report.fallback_action == FallbackAction.EXECUTE_TOOL
    assert report.selected_provider in {"brave_search", "web_search"}

    ctx = attach_decision_report(
        ToolExecutionContext(
            caller="smoke",
            user="Nolan",
            session_id="smoke",
            turn_id="web",
            execution_mode=ExecutionMode.MOCK,
            metadata={"execution_mode_override": True},
        ),
        report,
    )
    outcome = manager.runtime.invoke("web_search", {"query": query}, ctx)
    result = manager.runtime.outcome_to_result(outcome)
    enriched = enrich_decision_report_from_result(report, result.metadata or {})
    perf = manager.performance_model.get_metrics(report.selected_provider or "brave_search")
    return {
        "success": result.success,
        "provider": enriched.selected_provider if enriched else report.selected_provider,
        "performance_score": perf.performance_score,
        "latency_ms": enriched.provider_latency_ms if enriched else None,
        "fallback_used": enriched.fallback_used if enriched else False,
    }


def smoke_github(
    action: str = "get_authenticated_user",
    *,
    project_root: Path | None = None,
    **params: object,
) -> dict:
    """Run a read-only GitHub query through the full decision/runtime loop."""
    manager = _manager(project_root)
    engine = decision_engine_from_manager(manager)
    resolver = availability_resolver_from_manager(manager)
    report = engine.decide(
        f"GitHub {action.replace('_', ' ')}",
        availability_resolver=resolver,
    )
    assert report.selected_provider == "github"

    invoke_params = {"action": action, **params}
    ctx = attach_decision_report(
        ToolExecutionContext(
            caller="smoke",
            user="Nolan",
            session_id="smoke",
            turn_id="github",
            execution_mode=ExecutionMode.MOCK,
            metadata={"execution_mode_override": True},
        ),
        report,
    )
    outcome = manager.runtime.invoke("github", invoke_params, ctx)
    result = manager.runtime.outcome_to_result(outcome)
    enriched = enrich_decision_report_from_result(report, result.metadata or {})
    perf = manager.performance_model.get_metrics("github")
    return {
        "success": result.success,
        "provider": "github",
        "github_operation": enriched.github_operation if enriched else action,
        "performance_score": perf.performance_score,
        "latency_ms": enriched.provider_latency_ms if enriched else None,
    }


def smoke_file_read(
    project_root: Path,
    relative_path: str,
) -> dict:
    """Read a project file via FileSystemProvider through decision + runtime."""
    manager = _manager(project_root)
    engine = decision_engine_from_manager(manager)
    resolver = availability_resolver_from_manager(manager)
    report = engine.decide(
        f"Lire le fichier {relative_path}",
        availability_resolver=resolver,
    )
    assert report.selected_provider == "file_system"

    ctx = attach_decision_report(
        ToolExecutionContext(
            caller="smoke",
            user="Nolan",
            session_id="smoke",
            turn_id="file",
            execution_mode=ExecutionMode.LIVE,
        ),
        report,
    )
    outcome = manager.runtime.invoke("file_read", {"path": relative_path}, ctx)
    result = manager.runtime.outcome_to_result(outcome)
    enriched = enrich_decision_report_from_result(report, result.metadata or {})
    perf = manager.performance_model.get_metrics("file_system")
    return {
        "success": result.success,
        "provider": "file_system",
        "target_path": enriched.target_path if enriched else relative_path,
        "performance_score": perf.performance_score,
        "latency_ms": enriched.provider_latency_ms if enriched else None,
    }


def smoke_file_list(project_root: Path, relative_path: str = ".") -> dict:
    """List a directory via FileSystemProvider (provider executor direct path)."""
    manager = _manager(project_root)
    from tools.providers.provider_executor import ProviderExecutionContext

    ctx = ProviderExecutionContext(
        action="list_directory",
        params={"path": relative_path},
        execution_mode=ExecutionMode.LIVE,
        tool_name="file_system",
    )
    outcome = manager.provider_executor.execute(
        "list_directory",
        {"path": relative_path},
        capability="file_system",
        context=ctx,
    )
    return {
        "success": outcome.success,
        "provider": outcome.provider_id,
        "entries": outcome.data,
    }


def smoke_file_search(
    project_root: Path,
    pattern: str = "*.py",
    *,
    root: str = ".",
) -> dict:
    """Search files under project root via FileSystemProvider."""
    manager = _manager(project_root)
    from tools.providers.provider_executor import ProviderExecutionContext

    ctx = ProviderExecutionContext(
        action="search_files",
        params={"pattern": pattern, "root": root},
        execution_mode=ExecutionMode.LIVE,
        tool_name="file_system",
    )
    outcome = manager.provider_executor.execute(
        "search_files",
        {"pattern": pattern, "root": root},
        capability="file_system",
        context=ctx,
    )
    return {
        "success": outcome.success,
        "provider": outcome.provider_id,
        "matches": outcome.data,
    }

# =====================================
# Titan Tool Decision — Execution Context
# =====================================

"""DecisionReport propagation through ToolRuntime execution context (P10B-105)."""

from __future__ import annotations

from tools.decision.models import ToolDecisionReport
from tools.tool_run_models import ToolExecutionContext

DECISION_REPORT_METADATA_KEY = "decision_report"


def attach_decision_report(
    context: ToolExecutionContext,
    report: ToolDecisionReport | None,
) -> ToolExecutionContext:
    """Inject DecisionReport into execution context metadata."""
    if report is None:
        return context
    metadata = dict(context.metadata)
    metadata[DECISION_REPORT_METADATA_KEY] = report.to_dict()
    return ToolExecutionContext(
        caller=context.caller,
        user=context.user,
        session_id=context.session_id,
        turn_id=context.turn_id,
        confirmed=context.confirmed,
        confirmation_token=context.confirmation_token,
        dry_run=context.dry_run,
        execution_mode=context.execution_mode,
        metadata=metadata,
    )


def enrich_decision_report_from_result(
    report: ToolDecisionReport | None,
    result_metadata: dict,
    *,
    telemetry_record_index: int | None = None,
    telemetry_snapshot_at: str = "",
) -> ToolDecisionReport | None:
    """Enrich DecisionReport with provider execution metadata (P10B-205, P10B-805, P10B-1004)."""
    if report is None:
        return None
    provider_id = result_metadata.get("provider_id")
    if not provider_id:
        return report
    execution_path = result_metadata.get("execution_path", [])
    path_tuple = tuple(execution_path) if isinstance(execution_path, list) else ()
    execution_provider = result_metadata.get("execution_provider") or str(provider_id)
    planned_provider = (
        result_metadata.get("planned_provider")
        or report.planned_provider
        or report.selected_provider
    )
    provider_changed = bool(result_metadata.get("provider_changed", False))
    if not provider_changed and planned_provider and execution_provider:
        provider_changed = execution_provider != planned_provider
    provider_change_reason = str(result_metadata.get("provider_change_reason", ""))
    if provider_changed and not provider_change_reason:
        provider_change_reason = (
            f"Exécution sur {execution_provider!r} "
            f"au lieu du provider planifié {planned_provider!r}."
        )
    record_index = telemetry_record_index
    if record_index is None and result_metadata.get("telemetry_record_index") is not None:
        record_index = int(result_metadata["telemetry_record_index"])
    snapshot_at = telemetry_snapshot_at or str(
        result_metadata.get("telemetry_snapshot_at", ""),
    )
    return report.with_provider_execution(
        selected_provider=str(provider_id),
        provider_score=(
            float(result_metadata["provider_score"])
            if result_metadata.get("provider_score") is not None
            else None
        ),
        provider_health=str(result_metadata.get("provider_health", "")),
        provider_version=str(result_metadata.get("provider_version", "")),
        execution_path=path_tuple,
        provider_latency_ms=(
            float(result_metadata["duration_ms"])
            if result_metadata.get("duration_ms") is not None
            else (
                float(result_metadata["provider_latency_ms"])
                if result_metadata.get("provider_latency_ms") is not None
                else None
            )
        ),
        fallback_used=bool(result_metadata.get("fallback_used", False)),
        execution_provider=str(execution_provider),
        planned_provider=str(planned_provider) if planned_provider else None,
        provider_changed=provider_changed,
        provider_change_reason=provider_change_reason,
        fallback_reason=str(result_metadata.get("fallback_reason", "")),
        original_provider=(
            str(result_metadata["original_provider"])
            if result_metadata.get("original_provider")
            else None
        ),
        replacement_provider=(
            str(result_metadata["replacement_provider"])
            if result_metadata.get("replacement_provider")
            else None
        ),
        retry_count=int(result_metadata.get("retry_count", report.retry_count)),
        telemetry_record_index=record_index,
        telemetry_snapshot_at=snapshot_at,
    ).with_file_context(
        file_operation=(
            str(result_metadata["file_operation"])
            if result_metadata.get("file_operation")
            else report.file_operation
        ),
        target_path=(
            str(result_metadata["target_path"])
            if result_metadata.get("target_path")
            else report.target_path
        ),
        execution_mode=(
            str(result_metadata["execution_mode"])
            if result_metadata.get("execution_mode")
            else report.execution_mode
        ),
        selected_provider=str(provider_id),
        directory=(
            str(result_metadata["directory"])
            if result_metadata.get("directory")
            else report.directory
        ),
        filename=(
            str(result_metadata["filename"])
            if result_metadata.get("filename")
            else report.filename
        ),
        extension=(
            str(result_metadata["extension"])
            if result_metadata.get("extension")
            else report.extension
        ),
        keyword=(
            str(result_metadata["keyword"])
            if result_metadata.get("keyword")
            else report.keyword
        ),
        recursive=(
            bool(result_metadata["recursive"])
            if result_metadata.get("recursive") is not None
            else report.recursive
        ),
    ).with_github_context(
        github_operation=(
            str(result_metadata["github_operation"])
            if result_metadata.get("github_operation")
            else report.github_operation
        ),
        repository=(
            str(result_metadata["repository"])
            if result_metadata.get("repository")
            else report.repository
        ),
        branch=(
            str(result_metadata["branch"])
            if result_metadata.get("branch")
            else report.branch
        ),
        target_path=(
            str(result_metadata["target_path"])
            if result_metadata.get("target_path")
            else report.target_path
        ),
        execution_mode=(
            str(result_metadata["execution_mode"])
            if result_metadata.get("execution_mode")
            else report.execution_mode
        ),
        selected_provider=str(provider_id),
    )


def extract_decision_report(context: ToolExecutionContext) -> ToolDecisionReport | None:
    """Rehydrate DecisionReport from execution context metadata."""
    raw = context.metadata.get(DECISION_REPORT_METADATA_KEY)
    if not isinstance(raw, dict):
        return None
    return ToolDecisionReport.from_dict(raw)

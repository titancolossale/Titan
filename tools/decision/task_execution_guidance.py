# =====================================
# Titan Tool Decision — Task Execution Guidance
# =====================================

"""User-facing summaries for multi-step task execution (Phase 12 Batch 3)."""

from __future__ import annotations

from tools.decision.task_execution_models import (
    STEP_STATUS_COMPLETED,
    STEP_STATUS_FAILED,
    STEP_STATUS_SKIPPED,
    TaskExecutionReport,
)


def build_execution_summary(report: TaskExecutionReport) -> str:
    """Build a French execution summary for prompts and DecisionReport (P12B3-006)."""
    lines = [
        f"Objectif : {report.objective}",
        (
            f"Étapes : {report.steps_completed} terminée(s), "
            f"{report.steps_failed} en échec, "
            f"durée totale {report.total_duration_ms:.1f} ms."
        ),
    ]

    for step in report.steps:
        status_label = {
            STEP_STATUS_COMPLETED: "OK",
            STEP_STATUS_FAILED: "ÉCHEC",
            STEP_STATUS_SKIPPED: "IGNORÉE",
        }.get(step.status, step.status.upper())
        line = f"- [{step.step_id}] {step.tool} — {status_label}"
        if step.failure_reason:
            line = f"{line} ({step.failure_reason})"
        lines.append(line)

    if report.partial and report.unfinished_steps:
        remaining = ", ".join(report.unfinished_steps)
        lines.append(f"Travail restant : {remaining}.")

    if report.steps_completed == len(report.steps) and report.steps_failed == 0:
        lines.append("Exécution multi-étapes terminée avec succès.")
    elif report.steps_failed > 0:
        lines.append("Exécution interrompue — voir les étapes en échec ou ignorées.")

    return "\n".join(lines)


def format_task_execution_results(
    tool_results_text: str,
    report: TaskExecutionReport,
) -> str:
    """Attach multi-step summary to coordinator tool output."""
    summary = report.execution_summary or build_execution_summary(report)
    if tool_results_text.strip():
        return f"{summary}\n\n{tool_results_text}"
    return summary

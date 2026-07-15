# =====================================
# Titan Tool Decision — Task Execution Engine
# =====================================

"""Sequential multi-step tool execution with output chaining (Phase 12 Batch 3 — P12B3-002)."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brain.tool_dispatcher import ToolDispatcher

from core.execution_context import ExecutionDispatchContext
from tools.decision.task_execution_guidance import build_execution_summary
from tools.decision.task_execution_models import (
    STEP_STATUS_COMPLETED,
    STEP_STATUS_FAILED,
    STEP_STATUS_RUNNING,
    STEP_STATUS_SKIPPED,
    TaskExecutionPlan,
    TaskExecutionReport,
    TaskExecutionStep,
    TaskStepDefinition,
)
from tools.tool_result import ToolRequest, ToolResult

InvokeFn = Callable[[ToolRequest], ToolResult]
_PLACEHOLDER_PATTERN = re.compile(r"^\$([a-zA-Z0-9_]+)(?:\.(.+))?$")
_INDEX_PATTERN = re.compile(r"^(.+)\[(\d+)\]$")


class TaskExecutionEngine:
    """Execute TaskExecutionPlan steps sequentially with output reuse (P12B3-002)."""

    def execute(
        self,
        plan: TaskExecutionPlan,
        dispatcher: ToolDispatcher | None = None,
        *,
        invoke: InvokeFn | None = None,
        dispatch_context: ExecutionDispatchContext | None = None,
    ) -> TaskExecutionReport:
        """Run plan steps in order; stop on unrecoverable failure (P12B3-004/P12B3-005)."""
        invoke_fn = self._resolve_invoke(dispatcher, invoke, dispatch_context)
        output_context: dict[str, dict[str, Any]] = {}
        executed_steps: list[TaskExecutionStep] = []
        tool_results: list[ToolResult] = []
        steps_completed = 0
        steps_failed = 0
        total_duration_ms = 0.0
        stop_execution = False
        stop_reason = ""

        for step_def in plan.steps:
            if stop_execution:
                skipped = TaskExecutionStep(
                    step_id=step_def.step_id,
                    tool=step_def.tool,
                    status=STEP_STATUS_SKIPPED,
                    failure_reason=stop_reason or "Étape précédente en échec.",
                )
                executed_steps.append(skipped)
                continue

            if not self._dependencies_satisfied(step_def, output_context):
                stop_execution = True
                stop_reason = (
                    f"Dépendances non satisfaites pour l'étape {step_def.step_id}."
                )
                failed = TaskExecutionStep(
                    step_id=step_def.step_id,
                    tool=step_def.tool,
                    status=STEP_STATUS_FAILED,
                    failure_reason=stop_reason,
                )
                executed_steps.append(failed)
                steps_failed += 1
                continue

            record, result = self._run_step(step_def, invoke_fn, output_context)
            executed_steps.append(record)
            if result is not None:
                tool_results.append(result)

            if record.duration_ms is not None:
                total_duration_ms += record.duration_ms

            if record.status == STEP_STATUS_COMPLETED:
                steps_completed += 1
                output_context[step_def.step_id] = dict(record.outputs)
                continue

            steps_failed += 1
            stop_execution = True
            stop_reason = record.failure_reason or f"Échec étape {step_def.step_id}."

        unfinished = tuple(
            step.step_id
            for step in executed_steps
            if step.status in {STEP_STATUS_SKIPPED, STEP_STATUS_FAILED}
        )
        partial = stop_execution and steps_completed > 0
        report = TaskExecutionReport(
            objective=plan.objective,
            steps=tuple(executed_steps),
            steps_completed=steps_completed,
            steps_failed=steps_failed,
            total_duration_ms=round(total_duration_ms, 3),
            execution_summary="",
            partial=partial,
            tool_results=tuple(tool_results),
            unfinished_steps=unfinished,
        )
        summary = build_execution_summary(report)
        return TaskExecutionReport(
            objective=report.objective,
            steps=report.steps,
            steps_completed=report.steps_completed,
            steps_failed=report.steps_failed,
            total_duration_ms=report.total_duration_ms,
            execution_summary=summary,
            partial=report.partial,
            tool_results=report.tool_results,
            unfinished_steps=report.unfinished_steps,
        )

    @staticmethod
    def _resolve_invoke(
        dispatcher: ToolDispatcher | None,
        invoke: InvokeFn | None,
        dispatch_context: ExecutionDispatchContext | None,
    ) -> InvokeFn:
        if invoke is not None:
            return invoke
        if dispatcher is None:
            raise ValueError(
                "TaskExecutionEngine requires invoke callback or ToolDispatcher.",
            )

        def _dispatch(request: ToolRequest) -> ToolResult:
            results = dispatcher.dispatch(
                [request],
                dispatch_context=dispatch_context,
            )
            if not results:
                return ToolResult(
                    tool_name=request.tool_name,
                    success=False,
                    error="Aucun résultat retourné par le dispatcher.",
                    source="task_execution_engine",
                )
            return results[0]

        return _dispatch

    @staticmethod
    def _dependencies_satisfied(
        step_def: TaskStepDefinition,
        output_context: dict[str, dict[str, Any]],
    ) -> bool:
        for dep_id in step_def.depends_on:
            dep_outputs = output_context.get(dep_id)
            if dep_outputs is None or not dep_outputs.get("success", False):
                return False
        return True

    def _run_step(
        self,
        step_def: TaskStepDefinition,
        invoke_fn: InvokeFn,
        output_context: dict[str, dict[str, Any]],
    ) -> tuple[TaskExecutionStep, ToolResult | None]:
        started_at = _utc_now()
        resolved_inputs = resolve_step_inputs(step_def.inputs, output_context)
        record = TaskExecutionStep(
            step_id=step_def.step_id,
            tool=step_def.tool,
            status=STEP_STATUS_RUNNING,
            started_at=started_at,
            inputs=resolved_inputs,
        )

        result = invoke_fn(ToolRequest(step_def.tool, dict(resolved_inputs)))
        if result.success:
            finished_at = _utc_now()
            duration_ms = _duration_ms(started_at, finished_at)
            outputs = extract_step_outputs(result)
            record.status = STEP_STATUS_COMPLETED
            record.finished_at = finished_at
            record.duration_ms = duration_ms
            record.outputs = outputs
            return record, result

        fallback_result = self._attempt_fallback(
            step_def,
            invoke_fn,
            output_context,
            primary_error=result.error or "échec outil",
        )
        if fallback_result is not None:
            fb_record, fb_tool_result = fallback_result
            fb_record.started_at = started_at
            return fb_record, fb_tool_result

        finished_at = _utc_now()
        record.status = STEP_STATUS_FAILED
        record.finished_at = finished_at
        record.duration_ms = _duration_ms(started_at, finished_at)
        record.outputs = extract_step_outputs(result)
        record.failure_reason = result.error or "Échec outil sans message."
        return record, result

    def _attempt_fallback(
        self,
        step_def: TaskStepDefinition,
        invoke_fn: InvokeFn,
        output_context: dict[str, dict[str, Any]],
        *,
        primary_error: str,
    ) -> tuple[TaskExecutionStep, ToolResult] | None:
        if not step_def.fallback_tool:
            return None

        fallback_inputs = step_def.fallback_inputs or step_def.inputs
        resolved = resolve_step_inputs(fallback_inputs, output_context)
        result = invoke_fn(
            ToolRequest(step_def.fallback_tool, dict(resolved)),
        )
        if not result.success:
            return None

        outputs = extract_step_outputs(result)
        outputs["fallback_used"] = True
        outputs["primary_error"] = primary_error
        record = TaskExecutionStep(
            step_id=step_def.step_id,
            tool=step_def.fallback_tool,
            status=STEP_STATUS_COMPLETED,
            finished_at=_utc_now(),
            inputs=resolved,
            outputs=outputs,
            failure_reason=None,
        )
        record.duration_ms = 0.0
        return record, result


def extract_step_outputs(result: ToolResult) -> dict[str, Any]:
    """Normalize tool result into step output context."""
    metadata = dict(getattr(result, "metadata", None) or {})
    return {
        "success": bool(result.success),
        "data": getattr(result, "data", "") or "",
        "error": getattr(result, "error", "") or "",
        "metadata": metadata,
        **metadata,
    }


def resolve_step_inputs(
    inputs: dict[str, Any],
    output_context: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve $step.field placeholders using prior step outputs (P12B3-004)."""
    resolved: dict[str, Any] = {}
    for key, value in inputs.items():
        resolved[key] = _resolve_value(value, output_context)
    return resolved


def _resolve_value(value: Any, output_context: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, str):
        return _resolve_placeholder(value, output_context)
    if isinstance(value, list):
        return [_resolve_value(item, output_context) for item in value]
    if isinstance(value, dict):
        return {
            key: _resolve_value(item, output_context)
            for key, item in value.items()
        }
    return value


def _resolve_placeholder(value: str, output_context: dict[str, dict[str, Any]]) -> Any:
    if not value.startswith("$"):
        return value

    match = _PLACEHOLDER_PATTERN.match(value)
    if match is None:
        return value

    step_id, path = match.group(1), match.group(2)
    step_outputs = output_context.get(step_id)
    if step_outputs is None:
        return value

    if not path:
        return step_outputs

    return _resolve_path(step_outputs, path)


def _resolve_path(data: Any, path: str) -> Any:
    current = data
    for segment in path.split("."):
        index_match = _INDEX_PATTERN.match(segment)
        if index_match:
            segment = index_match.group(1)
            index = int(index_match.group(2))

        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return None

        if index_match is not None:
            if not isinstance(current, (list, tuple)):
                return None
            if index >= len(current):
                return None
            current = current[index]

    return current


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(started_at: str, finished_at: str) -> float:
    start = datetime.fromisoformat(started_at)
    end = datetime.fromisoformat(finished_at)
    return round((end - start).total_seconds() * 1000.0, 3)

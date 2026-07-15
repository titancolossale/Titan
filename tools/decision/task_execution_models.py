# =====================================
# Titan Tool Decision — Task Execution Models
# =====================================

"""Multi-step task execution plan and report types (Phase 12 Batch 3 — P12B3-001)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tools.tool_result import ToolResult

STEP_STATUS_PENDING = "pending"
STEP_STATUS_RUNNING = "running"
STEP_STATUS_COMPLETED = "completed"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_SKIPPED = "skipped"


@dataclass(frozen=True)
class TaskStepDefinition:
    """Single planned step in a multi-step objective."""

    step_id: str
    tool: str
    inputs: dict[str, Any]
    depends_on: tuple[str, ...] = ()
    fallback_tool: str | None = None
    fallback_inputs: dict[str, Any] | None = None
    expected_output: str = ""


@dataclass
class TaskExecutionStep:
    """Runtime record for one executed step (P12B3-003)."""

    step_id: str
    tool: str
    status: str = STEP_STATUS_PENDING
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: float | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for DecisionReport and logging."""
        return {
            "step_id": self.step_id,
            "tool": self.tool,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskExecutionStep:
        """Deserialize a stored step record."""
        return cls(
            step_id=str(data["step_id"]),
            tool=str(data["tool"]),
            status=str(data.get("status", STEP_STATUS_PENDING)),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            duration_ms=(
                float(data["duration_ms"])
                if data.get("duration_ms") is not None
                else None
            ),
            inputs=dict(data.get("inputs", {})),
            outputs=dict(data.get("outputs", {})),
            failure_reason=data.get("failure_reason"),
        )


@dataclass(frozen=True)
class TaskExecutionPlan:
    """Ordered multi-step plan for a user objective (P12B3-001)."""

    objective: str
    steps: tuple[TaskStepDefinition, ...]
    dependencies: dict[str, tuple[str, ...]]
    required_tools: tuple[str, ...]
    expected_outputs: tuple[str, ...]

    @classmethod
    def from_definitions(
        cls,
        objective: str,
        step_definitions: tuple[TaskStepDefinition, ...],
        *,
        expected_outputs: tuple[str, ...] = (),
    ) -> TaskExecutionPlan:
        """Build a plan with derived dependencies and required tools."""
        dependencies = {
            step.step_id: step.depends_on
            for step in step_definitions
            if step.depends_on
        }
        required_tools = tuple(
            dict.fromkeys(step.tool for step in step_definitions).keys(),
        )
        return cls(
            objective=objective,
            steps=step_definitions,
            dependencies=dependencies,
            required_tools=required_tools,
            expected_outputs=expected_outputs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize plan metadata."""
        return {
            "objective": self.objective,
            "steps": [
                {
                    "step_id": step.step_id,
                    "tool": step.tool,
                    "inputs": dict(step.inputs),
                    "depends_on": list(step.depends_on),
                    "fallback_tool": step.fallback_tool,
                    "fallback_inputs": (
                        dict(step.fallback_inputs)
                        if step.fallback_inputs is not None
                        else None
                    ),
                    "expected_output": step.expected_output,
                }
                for step in self.steps
            ],
            "dependencies": {
                key: list(value) for key, value in self.dependencies.items()
            },
            "required_tools": list(self.required_tools),
            "expected_outputs": list(self.expected_outputs),
        }


@dataclass(frozen=True)
class TaskExecutionReport:
    """Final outcome of a multi-step execution (P12B3-002)."""

    objective: str
    steps: tuple[TaskExecutionStep, ...]
    steps_completed: int
    steps_failed: int
    total_duration_ms: float
    execution_summary: str
    partial: bool
    tool_results: tuple[ToolResult, ...] = ()
    unfinished_steps: tuple[str, ...] = ()

    @property
    def multi_step_execution(self) -> bool:
        """Whether any step was attempted."""
        return bool(self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for DecisionReport enrichment."""
        return {
            "objective": self.objective,
            "steps": [step.to_dict() for step in self.steps],
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "total_duration_ms": self.total_duration_ms,
            "execution_summary": self.execution_summary,
            "partial": self.partial,
            "multi_step_execution": self.multi_step_execution,
            "unfinished_steps": list(self.unfinished_steps),
        }

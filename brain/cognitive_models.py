# =====================================
# Titan Cognitive Orchestrator Models
# =====================================

"""Task graph and plan runtime models for Phase 24.0 — Cognitive Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from tools.orchestration_models import ToolOrchestrationResult
from tools.planner_models import ExecutionPlan, PlannerResult, PlanStepKind
from tools.tool_result import ToolResult


class CognitivePhase(str, Enum):
    """High-level cognitive activity — safe for UI and neural visualization."""

    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    MEMORY = "memory"
    RESEARCH = "research"
    WRITING = "writing"
    VERIFICATION = "verification"
    IDLE = "idle"


class TaskNodeStatus(str, Enum):
    """Runtime status of a task graph node."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class PlanStatus(str, Enum):
    """Lifecycle status of a cognitive plan."""

    CREATED = "created"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"


@dataclass(frozen=True)
class TaskGraphNode:
    """Single node in the cognitive task graph."""

    node_id: str
    objective: str
    tool: str | None
    dependencies: tuple[str, ...]
    cognitive_phase: CognitivePhase
    step_kind: PlanStepKind = PlanStepKind.STANDARD
    selected_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API — no internal reasoning."""
        return {
            "node_id": self.node_id,
            "objective": self.objective,
            "tool": self.tool,
            "dependencies": list(self.dependencies),
            "cognitive_phase": self.cognitive_phase.value,
            "status": TaskNodeStatus.PENDING.value,
        }


@dataclass(frozen=True)
class TaskGraph:
    """Ordered task graph derived from a structured execution plan."""

    nodes: tuple[TaskGraphNode, ...]
    execution_order: tuple[str, ...]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def get_node(self, node_id: str) -> TaskGraphNode | None:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def independent_node_ids(self) -> tuple[str, ...]:
        """Nodes with no dependencies — future parallel execution entry points."""
        return tuple(node.node_id for node in self.nodes if not node.dependencies)

    def estimated_tools(self) -> tuple[str, ...]:
        tools: list[str] = []
        seen: set[str] = set()
        for node in self.nodes:
            if node.tool and node.tool not in seen:
                seen.add(node.tool)
                tools.append(node.tool)
        return tuple(tools)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "execution_order": list(self.execution_order),
            "node_count": self.node_count,
            "estimated_tools": list(self.estimated_tools()),
            "parallel_ready": list(self.independent_node_ids()),
        }


@dataclass(frozen=True)
class ProgressEvent:
    """Sanitized high-level progress event for UI — never exposes reasoning."""

    phase: CognitivePhase
    label: str
    node_id: str | None = None
    tool: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "label": self.label,
            "node_id": self.node_id,
            "tool": self.tool,
        }


@dataclass
class PlanRuntimeState:
    """Mutable runtime tracking for plan execution, resume, and cancel."""

    plan_id: str
    status: PlanStatus = PlanStatus.CREATED
    node_status: dict[str, TaskNodeStatus] = field(default_factory=dict)
    current_node_id: str | None = None
    progress_events: list[ProgressEvent] = field(default_factory=list)
    completed_nodes: set[str] = field(default_factory=set)
    failed_nodes: set[str] = field(default_factory=set)
    skipped_nodes: set[str] = field(default_factory=set)
    orchestration_results: list[ToolOrchestrationResult] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    verification_passed: bool | None = None
    verification_summary: str = ""

    def record_progress(self, event: ProgressEvent) -> None:
        self.progress_events.append(event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "status": self.status.value,
            "current_node_id": self.current_node_id,
            "node_status": {k: v.value for k, v in self.node_status.items()},
            "progress": [event.to_dict() for event in self.progress_events],
            "verification_passed": self.verification_passed,
            "verification_summary": self.verification_summary,
        }


@dataclass(frozen=True)
class CognitivePlan:
    """Intelligence-layer plan: intent, task graph, and underlying execution plan."""

    plan_id: str
    message: str
    task_graph: TaskGraph
    planner_result: PlannerResult
    execution_plan: ExecutionPlan
    analysis: dict[str, Any]
    requires_confirmation: bool = False
    clarification_required: bool = False
    clarification_message: str = ""

    @property
    def total_steps(self) -> int:
        return self.planner_result.total_steps

    @property
    def estimated_tools(self) -> tuple[str, ...]:
        return self.task_graph.estimated_tools()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "message": self.message,
            "task_graph": self.task_graph.to_dict(),
            "total_steps": self.total_steps,
            "estimated_tools": list(self.estimated_tools),
            "requires_confirmation": self.requires_confirmation,
            "clarification_required": self.clarification_required,
        }


@dataclass(frozen=True)
class PlanVerificationResult:
    """Outcome of post-execution verification."""

    passed: bool
    summary: str
    failed_node_ids: tuple[str, ...] = ()
    pending_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "summary": self.summary,
            "failed_node_ids": list(self.failed_node_ids),
            "pending_confirmation": self.pending_confirmation,
        }


@dataclass(frozen=True)
class CognitiveExecutionResult:
    """Combined outcome of plan creation, execution, and verification."""

    plan: CognitivePlan
    runtime: PlanRuntimeState
    verification: PlanVerificationResult
    tool_results: tuple[ToolResult, ...]
    orchestration_results: tuple[ToolOrchestrationResult, ...]

    @property
    def cognitive_phase(self) -> CognitivePhase:
        if self.runtime.status == PlanStatus.COMPLETED:
            return CognitivePhase.IDLE
        if self.runtime.status == PlanStatus.VERIFYING:
            return CognitivePhase.VERIFICATION
        if self.runtime.current_node_id:
            node = self.plan.task_graph.get_node(self.runtime.current_node_id)
            if node is not None:
                return node.cognitive_phase
        return CognitivePhase.IDLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "runtime": self.runtime.to_dict(),
            "verification": self.verification.to_dict(),
            "cognitive_phase": self.cognitive_phase.value,
        }


def new_plan_id() -> str:
    """Generate a unique plan identifier."""
    return f"plan_{uuid4().hex[:12]}"

# =====================================
# Titan Natural Language Planner Models
# =====================================

"""Structured planning artifacts for Phase 12.6 Batch 2 (P126-010)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tools.permission_manager import PermissionLevel


class PlanStepKind(str, Enum):
    """Classification of a planned execution step."""

    STANDARD = "standard"
    CONDITIONAL = "conditional"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class PlanStep:
    """Single step in a structured execution plan."""

    step_id: str
    objective: str
    reasoning: str
    required_tool: str
    required_permission: PermissionLevel
    expected_output: str
    dependencies: tuple[str, ...] = ()
    tool_params: dict[str, Any] = field(default_factory=dict)
    step_kind: PlanStepKind = PlanStepKind.STANDARD
    condition: str = ""
    fallback_step_id: str | None = None
    fallback_tool: str | None = None
    fallback_params: dict[str, Any] | None = None
    selected_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging, tests, and persistence."""
        return {
            "step_id": self.step_id,
            "objective": self.objective,
            "reasoning": self.reasoning,
            "required_tool": self.required_tool,
            "required_permission": self.required_permission.value,
            "expected_output": self.expected_output,
            "dependencies": list(self.dependencies),
            "tool_params": dict(self.tool_params),
            "step_kind": self.step_kind.value,
            "condition": self.condition,
            "fallback_step_id": self.fallback_step_id,
            "fallback_tool": self.fallback_tool,
            "fallback_params": (
                dict(self.fallback_params)
                if self.fallback_params is not None
                else None
            ),
            "selected_action": self.selected_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        """Deserialize a stored plan step."""
        return cls(
            step_id=str(data["step_id"]),
            objective=str(data.get("objective", "")),
            reasoning=str(data.get("reasoning", "")),
            required_tool=str(data["required_tool"]),
            required_permission=PermissionLevel(
                str(data.get("required_permission", PermissionLevel.AUTO_ALLOWED.value)),
            ),
            expected_output=str(data.get("expected_output", "")),
            dependencies=tuple(data.get("dependencies", ())),
            tool_params=dict(data.get("tool_params", {})),
            step_kind=PlanStepKind(str(data.get("step_kind", PlanStepKind.STANDARD.value))),
            condition=str(data.get("condition", "")),
            fallback_step_id=data.get("fallback_step_id"),
            fallback_tool=data.get("fallback_tool"),
            fallback_params=(
                dict(data["fallback_params"])
                if data.get("fallback_params") is not None
                else None
            ),
            selected_action=data.get("selected_action"),
        )


@dataclass(frozen=True)
class ExecutionPlan:
    """Reusable structured execution plan independent of runtime context."""

    overall_goal: str
    plan_summary: str
    steps: tuple[PlanStep, ...]
    execution_order: tuple[str, ...]

    @property
    def total_steps(self) -> int:
        """Number of planned steps."""
        return len(self.steps)

    @property
    def estimated_tools(self) -> tuple[str, ...]:
        """Unique tools referenced by the plan."""
        tools: list[str] = []
        seen: set[str] = set()
        for step in self.steps:
            if step.required_tool not in seen:
                seen.add(step.required_tool)
                tools.append(step.required_tool)
            if step.fallback_tool and step.fallback_tool not in seen:
                seen.add(step.fallback_tool)
                tools.append(step.fallback_tool)
        return tuple(tools)

    def get_step(self, step_id: str) -> PlanStep | None:
        """Return a step by identifier."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the reusable plan object."""
        return {
            "overall_goal": self.overall_goal,
            "plan_summary": self.plan_summary,
            "steps": [step.to_dict() for step in self.steps],
            "execution_order": list(self.execution_order),
            "total_steps": self.total_steps,
            "estimated_tools": list(self.estimated_tools),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionPlan:
        """Deserialize a stored execution plan."""
        steps = tuple(PlanStep.from_dict(item) for item in data.get("steps", []))
        execution_order = tuple(str(item) for item in data.get("execution_order", ()))
        if not execution_order:
            execution_order = tuple(step.step_id for step in steps)
        return cls(
            overall_goal=str(data.get("overall_goal", "")),
            plan_summary=str(data.get("plan_summary", "")),
            steps=steps,
            execution_order=execution_order,
        )


@dataclass(frozen=True)
class PlannerResult:
    """Outcome of NaturalLanguagePlanner for Brain and orchestration layers."""

    overall_goal: str
    plan_summary: str
    total_steps: int
    estimated_tools: tuple[str, ...]
    requires_confirmation: bool
    execution_order: tuple[str, ...]
    steps: tuple[PlanStep, ...]
    plan: ExecutionPlan

    def get_step(self, step_id: str) -> PlanStep | None:
        """Return a step by identifier."""
        return self.plan.get_step(step_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for DecisionReport enrichment and tests."""
        return {
            "overall_goal": self.overall_goal,
            "plan_summary": self.plan_summary,
            "total_steps": self.total_steps,
            "estimated_tools": list(self.estimated_tools),
            "requires_confirmation": self.requires_confirmation,
            "execution_order": list(self.execution_order),
            "steps": [step.to_dict() for step in self.steps],
            "plan": self.plan.to_dict(),
        }

    @classmethod
    def from_execution_plan(
        cls,
        plan: ExecutionPlan,
        *,
        requires_confirmation: bool = False,
    ) -> PlannerResult:
        """Build a PlannerResult wrapper around a reusable ExecutionPlan."""
        return cls(
            overall_goal=plan.overall_goal,
            plan_summary=plan.plan_summary,
            total_steps=plan.total_steps,
            estimated_tools=plan.estimated_tools,
            requires_confirmation=requires_confirmation,
            execution_order=plan.execution_order,
            steps=plan.steps,
            plan=plan,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlannerResult:
        """Deserialize a stored planner result."""
        plan_data = data.get("plan")
        if isinstance(plan_data, dict):
            plan = ExecutionPlan.from_dict(plan_data)
        else:
            steps = tuple(PlanStep.from_dict(item) for item in data.get("steps", []))
            execution_order = tuple(str(item) for item in data.get("execution_order", ()))
            if not execution_order:
                execution_order = tuple(step.step_id for step in steps)
            plan = ExecutionPlan(
                overall_goal=str(data.get("overall_goal", "")),
                plan_summary=str(data.get("plan_summary", "")),
                steps=steps,
                execution_order=execution_order,
            )
        return cls(
            overall_goal=str(data.get("overall_goal", plan.overall_goal)),
            plan_summary=str(data.get("plan_summary", plan.plan_summary)),
            total_steps=int(data.get("total_steps", plan.total_steps)),
            estimated_tools=tuple(data.get("estimated_tools", plan.estimated_tools)),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            execution_order=tuple(
                data.get("execution_order", plan.execution_order),
            ),
            steps=plan.steps,
            plan=plan,
        )


@dataclass(frozen=True)
class ReviewedPlannerResult:
    """Outcome of ReasoningLoop critical review before tool orchestration (P126-020)."""

    planner_result: PlannerResult
    confidence_score: float
    reasoning_summary: str
    clarification_required: bool
    optimization_count: int
    clarification_message: str = ""
    review_issues: tuple[str, ...] = ()

    @property
    def overall_goal(self) -> str:
        """Delegate to the underlying planner result."""
        return self.planner_result.overall_goal

    @property
    def plan_summary(self) -> str:
        """Delegate to the underlying planner result."""
        return self.planner_result.plan_summary

    @property
    def total_steps(self) -> int:
        """Delegate to the underlying planner result."""
        return self.planner_result.total_steps

    @property
    def requires_confirmation(self) -> bool:
        """Delegate to the underlying planner result."""
        return self.planner_result.requires_confirmation

    @property
    def execution_order(self) -> tuple[str, ...]:
        """Delegate to the underlying planner result."""
        return self.planner_result.execution_order

    @property
    def steps(self) -> tuple[PlanStep, ...]:
        """Delegate to the underlying planner result."""
        return self.planner_result.steps

    def get_step(self, step_id: str) -> PlanStep | None:
        """Return a step from the reviewed plan."""
        return self.planner_result.get_step(step_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for DecisionReport enrichment and tests."""
        return {
            "planner_result": self.planner_result.to_dict(),
            "confidence_score": self.confidence_score,
            "reasoning_summary": self.reasoning_summary,
            "clarification_required": self.clarification_required,
            "optimization_count": self.optimization_count,
            "clarification_message": self.clarification_message,
            "review_issues": list(self.review_issues),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewedPlannerResult:
        """Deserialize a stored reviewed planner result."""
        planner_data = data.get("planner_result", {})
        return cls(
            planner_result=PlannerResult.from_dict(planner_data),
            confidence_score=float(data.get("confidence_score", 0.0)),
            reasoning_summary=str(data.get("reasoning_summary", "")),
            clarification_required=bool(data.get("clarification_required", False)),
            optimization_count=int(data.get("optimization_count", 0)),
            clarification_message=str(data.get("clarification_message", "")),
            review_issues=tuple(data.get("review_issues", ())),
        )

    @classmethod
    def from_planner_result(
        cls,
        planner_result: PlannerResult,
        *,
        confidence_score: float = 1.0,
        reasoning_summary: str = "",
        clarification_required: bool = False,
        optimization_count: int = 0,
        clarification_message: str = "",
        review_issues: tuple[str, ...] = (),
    ) -> ReviewedPlannerResult:
        """Wrap a planner result without modifications."""
        summary = reasoning_summary or "Plan validé sans modification."
        return cls(
            planner_result=planner_result,
            confidence_score=confidence_score,
            reasoning_summary=summary,
            clarification_required=clarification_required,
            optimization_count=optimization_count,
            clarification_message=clarification_message,
            review_issues=review_issues,
        )

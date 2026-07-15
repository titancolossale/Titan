# =====================================
# Titan Autonomous Workflow Engine
# =====================================

"""Autonomous Workflow Engine V1 — generic multi-step workflow orchestration.

Coordinates existing cognitive systems (Cognitive Context Builder, Reasoning
Engine, Executive Function, Meta-Cognition, Cognitive Orchestrator, Knowledge
Learning Engine) to execute high-level objectives. Does not replace reasoning,
executive function, or tool execution — it orchestrates them.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from brain.cognitive_models import (
    CognitiveExecutionResult,
    CognitivePlan,
    PlanStatus,
)

if TYPE_CHECKING:
    from brain.cognitive_context_builder import (
        CognitiveContext,
        CognitiveContextBuilder,
    )
    from brain.cognitive_orchestrator import CognitiveOrchestrator
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.knowledge_learning_engine import KnowledgeLearningEngine, LearningResult
    from brain.meta_cognition import MetaCognitionEngine, MetaCognitionReport
    from brain.reasoning_engine import ReasoningEngine
    from brain.reasoning_models import ReasoningResult
    from context.context_manager import ContextManager
    from tools.confirmation_gate import ConfirmationGate

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
META_CONFIDENCE_MIN = 0.45


class WorkflowStatus(str, Enum):
    """Lifecycle states for an autonomous workflow."""

    CREATED = "created"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


_TERMINAL_STATUSES = frozenset(
    {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }
)

_PAUSABLE_STATUSES = frozenset(
    {
        WorkflowStatus.CREATED,
        WorkflowStatus.ANALYZING,
        WorkflowStatus.PLANNING,
        WorkflowStatus.AWAITING_CONFIRMATION,
        WorkflowStatus.EXECUTING,
        WorkflowStatus.VALIDATING,
    }
)


def new_workflow_id() -> str:
    """Generate a stable unique workflow identifier."""
    return f"wf_{uuid.uuid4().hex[:12]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkflowRecord:
    """Mutable in-memory workflow state tracked by the engine."""

    workflow_id: str
    objective: str
    status: WorkflowStatus = WorkflowStatus.CREATED
    user: str | None = None
    project_id: str | None = None
    mission_id: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    paused_from: WorkflowStatus | None = None
    confirmation_reason: str = ""
    confirmation_required: bool = False
    # Cognitive artifacts (populated as the workflow advances)
    cognitive_context_id: str | None = None
    reasoning_id: str | None = None
    executive_summary: str = ""
    meta_confidence: float = 0.0
    plan_id: str | None = None
    execution_summary: str = ""
    error_message: str = ""
    learning_recorded: bool = False

    def touch(self) -> None:
        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "workflow_id": self.workflow_id,
            "objective": self.objective,
            "status": self.status.value,
            "user": self.user,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "paused_from": self.paused_from.value if self.paused_from else None,
            "confirmation_reason": self.confirmation_reason,
            "confirmation_required": self.confirmation_required,
            "cognitive_context_id": self.cognitive_context_id,
            "reasoning_id": self.reasoning_id,
            "executive_summary": self.executive_summary,
            "meta_confidence": round(self.meta_confidence, 3),
            "plan_id": self.plan_id,
            "execution_summary": self.execution_summary,
            "error_message": self.error_message,
            "learning_recorded": self.learning_recorded,
        }


@dataclass(frozen=True)
class WorkflowRunResult:
    """Outcome of a workflow lifecycle operation."""

    workflow: WorkflowRecord
    success: bool
    message: str
    reasoning: ReasoningResult | None = None
    executive_evaluation: ExecutiveEvaluation | None = None
    meta_report: MetaCognitionReport | None = None
    cognitive_context: CognitiveContext | None = None
    plan: CognitivePlan | None = None
    execution: CognitiveExecutionResult | None = None
    learning_result: LearningResult | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "workflow": self.workflow.to_dict(),
            "success": self.success,
            "message": self.message,
        }
        if self.reasoning is not None:
            payload["reasoning"] = self.reasoning.to_dict()
        if self.executive_evaluation is not None:
            payload["executive_evaluation"] = self.executive_evaluation.to_dict()
        if self.meta_report is not None:
            payload["meta_report"] = self.meta_report.to_dict()
        if self.cognitive_context is not None:
            payload["cognitive_context"] = self.cognitive_context.to_dict()
        if self.plan is not None:
            payload["plan"] = self.plan.to_dict()
        if self.execution is not None:
            payload["execution"] = self.execution.to_dict()
        if self.learning_result is not None:
            payload["learning_result"] = self.learning_result.to_dict()
        return payload


class AutonomousWorkflowEngine:
    """Orchestrates existing cognitive systems for multi-step workflows."""

    def __init__(
        self,
        *,
        reasoning_engine: ReasoningEngine,
        cognitive_context_builder: CognitiveContextBuilder,
        executive_function: ExecutiveFunction,
        meta_cognition: MetaCognitionEngine,
        knowledge_learning_engine: KnowledgeLearningEngine,
        cognitive_orchestrator: CognitiveOrchestrator,
        context_manager: ContextManager | None = None,
        confirmation_gate: ConfirmationGate | None = None,
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._context_builder = cognitive_context_builder
        self._executive_function = executive_function
        self._meta_cognition = meta_cognition
        self._knowledge_learning_engine = knowledge_learning_engine
        self._cognitive_orchestrator = cognitive_orchestrator
        self._context_manager = context_manager
        self._confirmation_gate = confirmation_gate
        self._workflows: dict[str, WorkflowRecord] = {}
        self._artifacts: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public workflow API
    # ------------------------------------------------------------------

    def create_workflow(
        self,
        objective: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        mission_id: str | None = None,
    ) -> WorkflowRecord:
        """Register a new workflow in ``created`` state."""
        objective = (objective or "").strip()
        if not objective:
            raise ValueError("workflow objective must not be empty")

        workflow_id = new_workflow_id()
        record = WorkflowRecord(
            workflow_id=workflow_id,
            objective=objective,
            user=user or self._resolve_user(),
            project_id=project_id or self._resolve_project_id(),
            mission_id=mission_id,
        )
        self._workflows[workflow_id] = record
        self._artifacts[workflow_id] = {}
        logger.info("Workflow created: %s", workflow_id)
        return record

    def start_workflow(
        self,
        workflow_id: str,
        *,
        confirmed: bool = False,
    ) -> WorkflowRunResult:
        """Run analysis → planning → execution → validation for a workflow."""
        record = self._require_workflow(workflow_id)

        if record.status == WorkflowStatus.PAUSED:
            record.status = record.paused_from or WorkflowStatus.CREATED
            record.paused_from = None
            record.touch()

        if record.status in _TERMINAL_STATUSES:
            return WorkflowRunResult(
                workflow=record,
                success=False,
                message=f"workflow already terminal: {record.status.value}",
            )

        if record.status == WorkflowStatus.AWAITING_CONFIRMATION and not confirmed:
            return WorkflowRunResult(
                workflow=record,
                success=False,
                message=record.confirmation_reason or "user confirmation required",
            )

        try:
            return self._run_workflow(record, confirmed=confirmed)
        except Exception as exc:
            logger.exception("Workflow %s failed", workflow_id)
            record.status = WorkflowStatus.FAILED
            record.error_message = str(exc)
            record.touch()
            return WorkflowRunResult(
                workflow=record,
                success=False,
                message=str(exc),
            )

    def pause_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Pause a non-terminal workflow."""
        record = self._workflows.get(workflow_id)
        if record is None or record.status in _TERMINAL_STATUSES:
            return None
        if record.status == WorkflowStatus.PAUSED:
            return record
        if record.status not in _PAUSABLE_STATUSES:
            return None

        if record.status == WorkflowStatus.EXECUTING and record.plan_id:
            self._cognitive_orchestrator.cancel_plan(record.plan_id)

        record.paused_from = record.status
        record.status = WorkflowStatus.PAUSED
        record.touch()
        logger.info("Workflow paused: %s", workflow_id)
        return record

    def resume_workflow(self, workflow_id: str) -> WorkflowRunResult:
        """Resume a paused workflow from its saved phase."""
        record = self._workflows.get(workflow_id)
        if record is None:
            raise KeyError(f"workflow not found: {workflow_id}")
        if record.status != WorkflowStatus.PAUSED:
            return WorkflowRunResult(
                workflow=record,
                success=False,
                message=f"workflow is not paused: {record.status.value}",
            )
        return self.start_workflow(workflow_id)

    def cancel_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Cancel a workflow and any active cognitive plan."""
        record = self._workflows.get(workflow_id)
        if record is None or record.status in _TERMINAL_STATUSES:
            return None

        if record.plan_id:
            self._cognitive_orchestrator.cancel_plan(record.plan_id)

        record.status = WorkflowStatus.CANCELLED
        record.touch()
        logger.info("Workflow cancelled: %s", workflow_id)
        return record

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Return a workflow by id."""
        return self._workflows.get(workflow_id)

    def list_workflows(
        self,
        *,
        status: WorkflowStatus | None = None,
        limit: int = 50,
    ) -> tuple[WorkflowRecord, ...]:
        """List workflows, optionally filtered by status."""
        records = list(self._workflows.values())
        if status is not None:
            records = [record for record in records if record.status == status]
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return tuple(records[: max(limit, 0)])

    def export_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Export workflow state and cached artifacts as JSON-serializable data."""
        record = self._workflows.get(workflow_id)
        if record is None:
            return {}

        payload = record.to_dict()
        artifacts = self._artifacts.get(workflow_id, {})
        if artifacts:
            payload["artifacts"] = artifacts
        return payload

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------

    def _run_workflow(
        self,
        record: WorkflowRecord,
        *,
        confirmed: bool,
    ) -> WorkflowRunResult:
        user = record.user
        project_id = record.project_id
        objective = record.objective

        # --- Analyzing ---
        record.status = WorkflowStatus.ANALYZING
        record.touch()

        context = self._context_builder.build_for_request(
            objective,
            user=user,
            project_id=project_id,
        )
        self._store_artifact(record.workflow_id, "cognitive_context", context.to_dict())

        reasoning = self._reasoning_engine.reason(
            objective,
            user=user,
            project_id=project_id,
        )
        record.reasoning_id = reasoning.summary.headline[:80] if reasoning.summary else None
        self._store_artifact(record.workflow_id, "reasoning", reasoning.to_dict())

        executive = self._executive_function.evaluate_missions(
            objective,
            user=user,
            project_id=project_id,
            reasoning_result=reasoning,
        )
        record.executive_summary = (
            executive.recommendation.reasoning if executive.recommendation else ""
        )
        self._store_artifact(record.workflow_id, "executive_evaluation", executive.to_dict())

        meta_report = self._meta_cognition.evaluate_reasoning(
            reasoning,
            context=context,
            executive_evaluation=executive,
        )
        record.meta_confidence = self._meta_cognition.confidence(meta_report)
        self._store_artifact(record.workflow_id, "meta_report", meta_report.to_dict())

        needs_confirmation, reason = self._requires_user_confirmation(
            reasoning=reasoning,
            meta_report=meta_report,
            confirmed=confirmed,
        )
        if needs_confirmation:
            record.status = WorkflowStatus.AWAITING_CONFIRMATION
            record.confirmation_required = True
            record.confirmation_reason = reason
            record.touch()
            return WorkflowRunResult(
                workflow=record,
                success=False,
                message=reason,
                reasoning=reasoning,
                executive_evaluation=executive,
                meta_report=meta_report,
                cognitive_context=context,
            )

        # --- Planning ---
        record.status = WorkflowStatus.PLANNING
        record.confirmation_required = False
        record.confirmation_reason = ""
        record.touch()

        plan = self._cognitive_orchestrator.create_plan(objective)
        record.plan_id = plan.plan_id
        self._store_artifact(record.workflow_id, "plan", plan.to_dict())

        plan_needs_confirmation, plan_reason = self._requires_user_confirmation(
            reasoning=reasoning,
            meta_report=meta_report,
            plan=plan,
            confirmed=confirmed,
        )
        if plan_needs_confirmation:
            record.status = WorkflowStatus.AWAITING_CONFIRMATION
            record.confirmation_required = True
            record.confirmation_reason = plan_reason
            record.touch()
            return WorkflowRunResult(
                workflow=record,
                success=False,
                message=plan_reason,
                reasoning=reasoning,
                executive_evaluation=executive,
                meta_report=meta_report,
                cognitive_context=context,
                plan=plan,
            )

        # --- Executing ---
        record.status = WorkflowStatus.EXECUTING
        record.touch()

        runtime = self._cognitive_orchestrator.execute_plan(plan, message=objective)
        if runtime.status == PlanStatus.SUSPENDED:
            record.status = WorkflowStatus.AWAITING_CONFIRMATION
            record.confirmation_required = True
            record.confirmation_reason = "tool execution suspended pending confirmation"
            record.touch()
            return WorkflowRunResult(
                workflow=record,
                success=False,
                message=record.confirmation_reason,
                reasoning=reasoning,
                executive_evaluation=executive,
                meta_report=meta_report,
                cognitive_context=context,
                plan=plan,
            )

        # --- Validating ---
        record.status = WorkflowStatus.VALIDATING
        record.touch()

        verification = self._cognitive_orchestrator.verify_plan(plan, runtime)
        execution = CognitiveExecutionResult(
            plan=plan,
            runtime=runtime,
            verification=verification,
            tool_results=runtime.tool_results,
            orchestration_results=runtime.orchestration_results,
        )
        self._store_artifact(record.workflow_id, "execution", execution.to_dict())

        passed = verification.passed and runtime.status != PlanStatus.FAILED
        record.execution_summary = verification.summary
        record.status = WorkflowStatus.COMPLETED if passed else WorkflowStatus.FAILED
        if not passed:
            record.error_message = verification.summary

        learning = self._record_learning(record, reasoning, execution, passed)
        record.learning_recorded = learning is not None
        record.touch()

        return WorkflowRunResult(
            workflow=record,
            success=passed,
            message=verification.summary,
            reasoning=reasoning,
            executive_evaluation=executive,
            meta_report=meta_report,
            cognitive_context=context,
            plan=plan,
            execution=execution,
            learning_result=learning,
        )

    def _requires_user_confirmation(
        self,
        *,
        reasoning: ReasoningResult,
        meta_report: MetaCognitionReport,
        plan: CognitivePlan | None = None,
        confirmed: bool = False,
    ) -> tuple[bool, str]:
        if confirmed:
            return False, ""

        if self._meta_cognition.requires_clarification(meta_report):
            return True, "meta-cognition requires clarification before proceeding"

        if meta_report.confidence_score < META_CONFIDENCE_MIN:
            return (
                True,
                f"meta-cognition confidence below threshold "
                f"({meta_report.confidence_score:.2f} < {META_CONFIDENCE_MIN})",
            )

        if reasoning.open_questions:
            questions = "; ".join(question.question for question in reasoning.open_questions[:3])
            return True, f"reasoning has open questions: {questions}"

        if plan is not None:
            if plan.clarification_required:
                return True, "cognitive plan requires clarification"
            if plan.requires_confirmation:
                return True, "cognitive plan requires user confirmation"

        if self._confirmation_gate is not None and self._has_pending_confirmations():
            return True, "pending tool confirmations require user approval"

        return False, ""

    def _has_pending_confirmations(self) -> bool:
        gate = self._confirmation_gate
        if gate is None:
            return False
        pending = getattr(gate, "_pending", None)
        if isinstance(pending, dict):
            return bool(pending)
        purge = getattr(gate, "purge_expired", None)
        if callable(purge):
            purge()
        lookup = getattr(gate, "lookup_pending", None)
        if callable(lookup):
            return False
        return False

    def _record_learning(
        self,
        record: WorkflowRecord,
        reasoning: ReasoningResult,
        execution: CognitiveExecutionResult,
        passed: bool,
    ) -> LearningResult | None:
        try:
            tool_name = self._primary_tool_name(execution)
            execution_learning = self._knowledge_learning_engine.learn_from_execution(
                mission_id=record.mission_id,
                tool_name=tool_name,
                success=passed,
                summary_message=record.execution_summary,
                user=record.user,
                project_id=record.project_id,
            )
            self._knowledge_learning_engine.learn_from_reasoning(
                reasoning,
                user=record.user,
                project_id=record.project_id,
            )
            return execution_learning
        except Exception:
            logger.exception("Knowledge learning failed for workflow %s", record.workflow_id)
            return None

    @staticmethod
    def _primary_tool_name(execution: CognitiveExecutionResult) -> str:
        for node in execution.plan.task_graph.nodes:
            if node.tool:
                return node.tool
        if execution.orchestration_results:
            first = execution.orchestration_results[0]
            tool = getattr(first, "tool_name", "") or ""
            if tool:
                return tool
        return "workflow"

    def _store_artifact(self, workflow_id: str, key: str, value: Any) -> None:
        bucket = self._artifacts.setdefault(workflow_id, {})
        bucket[key] = value

    def _require_workflow(self, workflow_id: str) -> WorkflowRecord:
        record = self._workflows.get(workflow_id)
        if record is None:
            raise KeyError(f"workflow not found: {workflow_id}")
        return record

    def _resolve_user(self) -> str | None:
        if self._context_manager is None:
            return None
        return self._context_manager.current_user

    def _resolve_project_id(self) -> str | None:
        if self._context_manager is None:
            return None
        project = self._context_manager.active_project
        return project or None

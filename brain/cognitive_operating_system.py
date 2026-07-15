# =====================================
# Titan Cognitive Operating System
# =====================================

"""Cognitive Operating System V1 — central coordination layer for Titan cognition.

Routes work between existing cognitive subsystems without replacing their logic.
Produces execution plans, tracks lifecycle stages, collects metrics, and
generates execution traces. Orchestration only — no duplicated reasoning,
planning, or memory.
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
from brain.reasoning_models import ReasoningDomain

if TYPE_CHECKING:
    from brain.autonomous_workflow_engine import (
        AutonomousWorkflowEngine,
        WorkflowRecord,
        WorkflowRunResult,
    )
    from brain.cognitive_context_builder import (
        CognitiveContext,
        CognitiveContextBuilder,
    )
    from brain.cognitive_orchestrator import CognitiveOrchestrator
    from brain.developer_workflow import DeveloperWorkflow, DeveloperWorkflowPlan
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.knowledge_learning_engine import KnowledgeLearningEngine, LearningResult
    from brain.meta_cognition import MetaCognitionEngine, MetaCognitionReport
    from brain.project_intelligence import ArchitectureSummary, ProjectIntelligence
    from brain.reasoning_engine import ReasoningEngine
    from brain.reasoning_models import ReasoningResult
    from brain.world_model import WorldModel, WorldModelSnapshot
    from brain.workspace_awareness import WorkspaceAwareness
    from context.context_manager import ContextManager
    from memory.memory_service import MemoryService
    from tools.confirmation_gate import ConfirmationGate

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
META_CONFIDENCE_MIN = 0.45

_CODE_DOMAINS = frozenset(
    {
        ReasoningDomain.SOFTWARE,
        ReasoningDomain.CODE,
        ReasoningDomain.ARCHITECTURE,
        ReasoningDomain.WORKSPACE,
    }
)


class CognitiveStage(str, Enum):
    """Canonical execution stages for the cognitive lifecycle."""

    RECEIVE = "receive"
    CONTEXT = "context"
    REASON = "reason"
    EVALUATE = "evaluate"
    PLAN = "plan"
    CONFIRM = "confirm"
    EXECUTE = "execute"
    LEARN = "learn"
    COMPLETE = "complete"


class ExecutionStatus(str, Enum):
    """Lifecycle status for a cognitive execution."""

    RECEIVED = "received"
    BUILDING_PLAN = "building_plan"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = frozenset(
    {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }
)

_PLAN_STAGES = (
    CognitiveStage.RECEIVE,
    CognitiveStage.CONTEXT,
    CognitiveStage.REASON,
    CognitiveStage.EVALUATE,
    CognitiveStage.PLAN,
)

_EXECUTE_STAGES = (
    CognitiveStage.CONFIRM,
    CognitiveStage.EXECUTE,
    CognitiveStage.LEARN,
    CognitiveStage.COMPLETE,
)


def new_execution_id() -> str:
    """Generate a stable unique cognitive execution identifier."""
    return f"cos_{uuid.uuid4().hex[:12]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class StageTraceEntry:
    """Single stage entry in an execution trace."""

    stage: CognitiveStage
    started_at: datetime
    duration_ms: float
    success: bool
    summary: str
    subsystem: str = ""
    artifact_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "started_at": self.started_at.isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "summary": self.summary,
            "subsystem": self.subsystem,
            "artifact_keys": list(self.artifact_keys),
        }


@dataclass
class ExecutionTrace:
    """Ordered trace of stage transitions for one execution."""

    execution_id: str
    entries: list[StageTraceEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass
class ExecutionMetrics:
    """Aggregated metrics for a cognitive execution."""

    execution_id: str
    total_duration_ms: float = 0.0
    stage_durations_ms: dict[str, float] = field(default_factory=dict)
    subsystem_calls: dict[str, int] = field(default_factory=dict)
    confirmation_gates: int = 0
    learning_items: int = 0
    stages_completed: int = 0
    stages_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "stage_durations_ms": {
                key: round(value, 2) for key, value in self.stage_durations_ms.items()
            },
            "subsystem_calls": dict(self.subsystem_calls),
            "confirmation_gates": self.confirmation_gates,
            "learning_items": self.learning_items,
            "stages_completed": self.stages_completed,
            "stages_failed": self.stages_failed,
        }


@dataclass
class ExecutionPlan:
    """Complete cognitive execution plan produced before execution."""

    plan_id: str
    execution_id: str
    request: str
    user: str | None
    project_id: str | None
    pipeline_stages: tuple[CognitiveStage, ...]
    requires_confirmation: bool
    confirmation_reason: str
    use_workflow_engine: bool
    reasoning: ReasoningResult | None = None
    cognitive_context: CognitiveContext | None = None
    world_snapshot: WorldModelSnapshot | None = None
    executive_evaluation: ExecutiveEvaluation | None = None
    meta_report: MetaCognitionReport | None = None
    architecture_summary: ArchitectureSummary | None = None
    developer_plan: DeveloperWorkflowPlan | None = None
    cognitive_plan: CognitivePlan | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "execution_id": self.execution_id,
            "request": self.request,
            "user": self.user,
            "project_id": self.project_id,
            "pipeline_stages": [stage.value for stage in self.pipeline_stages],
            "requires_confirmation": self.requires_confirmation,
            "confirmation_reason": self.confirmation_reason,
            "use_workflow_engine": self.use_workflow_engine,
            "created_at": self.created_at.isoformat(),
        }
        if self.reasoning is not None:
            payload["reasoning"] = self.reasoning.to_dict()
        if self.cognitive_context is not None:
            payload["cognitive_context"] = self.cognitive_context.to_dict()
        if self.world_snapshot is not None:
            payload["world_snapshot"] = self.world_snapshot.to_dict()
        if self.executive_evaluation is not None:
            payload["executive_evaluation"] = self.executive_evaluation.to_dict()
        if self.meta_report is not None:
            payload["meta_report"] = self.meta_report.to_dict()
        if self.architecture_summary is not None:
            payload["architecture_summary"] = self.architecture_summary.to_dict()
        if self.developer_plan is not None:
            payload["developer_plan"] = self.developer_plan.to_dict()
        if self.cognitive_plan is not None:
            payload["cognitive_plan"] = self.cognitive_plan.to_dict()
        return payload


@dataclass
class CognitiveExecutionRecord:
    """Mutable in-memory execution state tracked by the operating system."""

    execution_id: str
    request: str
    status: ExecutionStatus = ExecutionStatus.RECEIVED
    current_stage: CognitiveStage = CognitiveStage.RECEIVE
    user: str | None = None
    project_id: str | None = None
    plan_id: str | None = None
    workflow_id: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    confirmation_required: bool = False
    confirmation_reason: str = ""
    error_message: str = ""
    learning_recorded: bool = False

    def touch(self) -> None:
        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "request": self.request,
            "status": self.status.value,
            "current_stage": self.current_stage.value,
            "user": self.user,
            "project_id": self.project_id,
            "plan_id": self.plan_id,
            "workflow_id": self.workflow_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "confirmation_required": self.confirmation_required,
            "confirmation_reason": self.confirmation_reason,
            "error_message": self.error_message,
            "learning_recorded": self.learning_recorded,
        }


@dataclass(frozen=True)
class CognitiveProcessResult:
    """Outcome of a full or partial cognitive lifecycle operation."""

    execution: CognitiveExecutionRecord
    success: bool
    message: str
    plan: ExecutionPlan | None = None
    execution_result: CognitiveExecutionResult | None = None
    workflow_result: WorkflowRunResult | None = None
    learning_result: LearningResult | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "execution": self.execution.to_dict(),
            "success": self.success,
            "message": self.message,
        }
        if self.plan is not None:
            payload["plan"] = self.plan.to_dict()
        if self.execution_result is not None:
            payload["execution_result"] = self.execution_result.to_dict()
        if self.workflow_result is not None:
            payload["workflow_result"] = self.workflow_result.to_dict()
        if self.learning_result is not None:
            payload["learning_result"] = self.learning_result.to_dict()
        return payload


class CognitiveOperatingSystem:
    """Central coordination layer above Titan's cognitive subsystems."""

    def __init__(
        self,
        *,
        cognitive_context_builder: CognitiveContextBuilder,
        reasoning_engine: ReasoningEngine,
        executive_function: ExecutiveFunction,
        meta_cognition: MetaCognitionEngine,
        knowledge_learning_engine: KnowledgeLearningEngine,
        world_model: WorldModel,
        memory_service: MemoryService,
        project_intelligence: ProjectIntelligence,
        developer_workflow: DeveloperWorkflow,
        cognitive_orchestrator: CognitiveOrchestrator,
        autonomous_workflow_engine: AutonomousWorkflowEngine | None = None,
        context_manager: ContextManager | None = None,
        confirmation_gate: ConfirmationGate | None = None,
        workspace_awareness: WorkspaceAwareness | None = None,
    ) -> None:
        self._context_builder = cognitive_context_builder
        self._reasoning_engine = reasoning_engine
        self._executive_function = executive_function
        self._meta_cognition = meta_cognition
        self._knowledge_learning_engine = knowledge_learning_engine
        self._world_model = world_model
        self._memory_service = memory_service
        self._project_intelligence = project_intelligence
        self._developer_workflow = developer_workflow
        self._cognitive_orchestrator = cognitive_orchestrator
        self._autonomous_workflow_engine = autonomous_workflow_engine
        self._context_manager = context_manager
        self._confirmation_gate = confirmation_gate
        self._workspace_awareness = workspace_awareness
        self._executions: dict[str, CognitiveExecutionRecord] = {}
        self._plans: dict[str, ExecutionPlan] = {}
        self._traces: dict[str, ExecutionTrace] = {}
        self._metrics: dict[str, ExecutionMetrics] = {}
        self._artifacts: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_request(
        self,
        message: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        confirmed: bool = False,
        use_workflow_engine: bool | None = None,
    ) -> CognitiveProcessResult:
        """Run the full cognitive lifecycle for a high-level request."""
        record = self._register_execution(message, user=user, project_id=project_id)
        try:
            plan = self.build_execution_plan(
                message,
                execution_id=record.execution_id,
                user=user,
                project_id=project_id,
                use_workflow_engine=use_workflow_engine,
            )
            return self.execute_plan(
                plan.plan_id,
                confirmed=confirmed,
            )
        except Exception as exc:
            logger.exception("Cognitive execution %s failed", record.execution_id)
            record.status = ExecutionStatus.FAILED
            record.error_message = str(exc)
            record.touch()
            self._record_stage(
                record.execution_id,
                CognitiveStage.COMPLETE,
                success=False,
                summary=str(exc),
                subsystem="cognitive_operating_system",
            )
            return CognitiveProcessResult(
                execution=record,
                success=False,
                message=str(exc),
            )

    def build_execution_plan(
        self,
        message: str,
        *,
        execution_id: str | None = None,
        user: str | None = None,
        project_id: str | None = None,
        use_workflow_engine: bool | None = None,
    ) -> ExecutionPlan:
        """Analyze a request and produce a complete execution plan."""
        request = (message or "").strip()
        if not request:
            raise ValueError("request must not be empty")

        record = self._require_execution(execution_id) if execution_id else None
        if record is None:
            record = self._register_execution(request, user=user, project_id=project_id)
        else:
            record.request = request
            record.touch()

        resolved_user = user or record.user or self._resolve_user()
        resolved_project = project_id or record.project_id or self._resolve_project_id()

        record.status = ExecutionStatus.BUILDING_PLAN
        self._run_receive_stage(record, request)

        context, world_snapshot = self._run_context_stage(
            record,
            request,
            user=resolved_user,
            project_id=resolved_project,
        )
        reasoning = self._run_reason_stage(
            record,
            request,
            user=resolved_user,
            project_id=resolved_project,
        )
        executive, meta_report, architecture_summary = self._run_evaluate_stage(
            record,
            request,
            reasoning=reasoning,
            context=context,
            user=resolved_user,
            project_id=resolved_project,
        )
        developer_plan, cognitive_plan, workflow_mode = self._run_plan_stage(
            record,
            request,
            reasoning=reasoning,
            executive=executive,
            user=resolved_user,
            project_id=resolved_project,
            use_workflow_engine=use_workflow_engine,
        )

        needs_confirmation, reason = self._requires_confirmation(
            reasoning=reasoning,
            meta_report=meta_report,
            plan=cognitive_plan,
            confirmed=False,
        )

        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        plan = ExecutionPlan(
            plan_id=plan_id,
            execution_id=record.execution_id,
            request=request,
            user=resolved_user,
            project_id=resolved_project,
            pipeline_stages=_PLAN_STAGES + _EXECUTE_STAGES,
            requires_confirmation=needs_confirmation,
            confirmation_reason=reason,
            use_workflow_engine=workflow_mode,
            reasoning=reasoning,
            cognitive_context=context,
            world_snapshot=world_snapshot,
            executive_evaluation=executive,
            meta_report=meta_report,
            architecture_summary=architecture_summary,
            developer_plan=developer_plan,
            cognitive_plan=cognitive_plan,
        )
        self._plans[plan_id] = plan
        record.plan_id = plan_id
        record.confirmation_required = needs_confirmation
        record.confirmation_reason = reason
        record.status = (
            ExecutionStatus.AWAITING_CONFIRMATION
            if needs_confirmation
            else ExecutionStatus.RECEIVED
        )
        record.touch()
        self._store_artifact(record.execution_id, "execution_plan", plan.to_dict())
        return plan

    def execute_plan(
        self,
        plan_id: str,
        *,
        confirmed: bool = False,
    ) -> CognitiveProcessResult:
        """Execute a previously built plan through confirm → execute → learn → complete."""
        plan = self._require_plan(plan_id)
        record = self._require_execution(plan.execution_id)

        if record.status in _TERMINAL_STATUSES:
            return CognitiveProcessResult(
                execution=record,
                success=False,
                message=f"execution already terminal: {record.status.value}",
                plan=plan,
            )

        if record.status == ExecutionStatus.AWAITING_CONFIRMATION and not confirmed:
            return CognitiveProcessResult(
                execution=record,
                success=False,
                message=plan.confirmation_reason or "user confirmation required",
                plan=plan,
            )

        try:
            return self._run_execute_pipeline(record, plan, confirmed=confirmed)
        except Exception as exc:
            logger.exception("Plan execution %s failed", plan_id)
            record.status = ExecutionStatus.FAILED
            record.error_message = str(exc)
            record.touch()
            self._record_stage(
                record.execution_id,
                CognitiveStage.COMPLETE,
                success=False,
                summary=str(exc),
                subsystem="cognitive_operating_system",
            )
            return CognitiveProcessResult(
                execution=record,
                success=False,
                message=str(exc),
                plan=plan,
            )

    def cancel_execution(self, execution_id: str) -> CognitiveExecutionRecord | None:
        """Cancel an execution and any active cognitive plan or workflow."""
        record = self._executions.get(execution_id)
        if record is None or record.status in _TERMINAL_STATUSES:
            return None

        if record.plan_id:
            stored_plan = self._plans.get(record.plan_id)
            if stored_plan is not None and stored_plan.cognitive_plan is not None:
                self._cognitive_orchestrator.cancel_plan(stored_plan.cognitive_plan.plan_id)

        if record.workflow_id and self._autonomous_workflow_engine is not None:
            self._autonomous_workflow_engine.cancel_workflow(record.workflow_id)

        record.status = ExecutionStatus.CANCELLED
        record.current_stage = CognitiveStage.COMPLETE
        record.touch()
        self._record_stage(
            execution_id,
            CognitiveStage.COMPLETE,
            success=True,
            summary="execution cancelled",
            subsystem="cognitive_operating_system",
        )
        logger.info("Cognitive execution cancelled: %s", execution_id)
        return record

    def get_execution_trace(self, execution_id: str) -> ExecutionTrace:
        """Return the ordered stage trace for an execution."""
        return self._traces.get(execution_id) or ExecutionTrace(execution_id=execution_id)

    def get_execution_metrics(self, execution_id: str) -> ExecutionMetrics:
        """Return aggregated metrics for an execution."""
        return self._metrics.get(execution_id) or ExecutionMetrics(execution_id=execution_id)

    def export_execution(self, execution_id: str) -> dict[str, Any]:
        """Export execution state, plan, trace, metrics, and artifacts."""
        record = self._executions.get(execution_id)
        if record is None:
            return {}

        payload = record.to_dict()
        if record.plan_id and record.plan_id in self._plans:
            payload["plan"] = self._plans[record.plan_id].to_dict()
        trace = self._traces.get(execution_id)
        if trace is not None:
            payload["trace"] = trace.to_dict()
        metrics = self._metrics.get(execution_id)
        if metrics is not None:
            payload["metrics"] = metrics.to_dict()
        artifacts = self._artifacts.get(execution_id)
        if artifacts:
            payload["artifacts"] = artifacts
        return payload

    def get_execution(self, execution_id: str) -> CognitiveExecutionRecord | None:
        """Return execution record by id."""
        return self._executions.get(execution_id)

    def list_executions(self, *, limit: int = 50) -> tuple[CognitiveExecutionRecord, ...]:
        """List recent executions."""
        records = sorted(
            self._executions.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        return tuple(records[: max(limit, 0)])

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _run_receive_stage(
        self,
        record: CognitiveExecutionRecord,
        request: str,
    ) -> None:
        record.current_stage = CognitiveStage.RECEIVE
        record.touch()
        self._record_stage(
            record.execution_id,
            CognitiveStage.RECEIVE,
            success=True,
            summary=f"received request ({len(request)} chars)",
            subsystem="cognitive_operating_system",
        )
        self._increment_subsystem_call(record.execution_id, "cognitive_operating_system")

    def _run_context_stage(
        self,
        record: CognitiveExecutionRecord,
        request: str,
        *,
        user: str | None,
        project_id: str | None,
    ) -> tuple[CognitiveContext, WorldModelSnapshot | None]:
        record.current_stage = CognitiveStage.CONTEXT
        record.touch()

        if self._workspace_awareness is not None:
            self._workspace_awareness.refresh(user=user, project_id=project_id)
            self._increment_subsystem_call(record.execution_id, "workspace_awareness")

        context = self._context_builder.build_for_request(
            request,
            user=user,
            project_id=project_id,
        )
        self._store_artifact(record.execution_id, "cognitive_context", context.to_dict())
        self._increment_subsystem_call(record.execution_id, "cognitive_context_builder")

        world_snapshot = self._world_model.refresh(
            request,
            user=user,
            project_id=project_id,
        )
        self._store_artifact(record.execution_id, "world_snapshot", world_snapshot.to_dict())
        self._increment_subsystem_call(record.execution_id, "world_model")

        retrieval = self._memory_service.retrieve(user or "", request, project_id=project_id)
        if retrieval.has_matches:
            self._store_artifact(
                record.execution_id,
                "memory_retrieval",
                {"item_count": len(retrieval.items), "user": retrieval.user},
            )
        self._increment_subsystem_call(record.execution_id, "memory_service")

        self._record_stage(
            record.execution_id,
            CognitiveStage.CONTEXT,
            success=True,
            summary="context and world model assembled",
            subsystem="cognitive_context_builder",
            artifact_keys=("cognitive_context", "world_snapshot", "memory_retrieval"),
        )
        return context, world_snapshot

    def _run_reason_stage(
        self,
        record: CognitiveExecutionRecord,
        request: str,
        *,
        user: str | None,
        project_id: str | None,
    ) -> ReasoningResult:
        record.current_stage = CognitiveStage.REASON
        record.touch()

        reasoning = self._reasoning_engine.reason(
            request,
            user=user,
            project_id=project_id,
        )
        self._store_artifact(record.execution_id, "reasoning", reasoning.to_dict())
        self._increment_subsystem_call(record.execution_id, "reasoning_engine")

        self._record_stage(
            record.execution_id,
            CognitiveStage.REASON,
            success=True,
            summary=reasoning.summary.headline if reasoning.summary else "reasoning complete",
            subsystem="reasoning_engine",
            artifact_keys=("reasoning",),
        )
        return reasoning

    def _run_evaluate_stage(
        self,
        record: CognitiveExecutionRecord,
        request: str,
        *,
        reasoning: ReasoningResult,
        context: CognitiveContext,
        user: str | None,
        project_id: str | None,
    ) -> tuple[ExecutiveEvaluation, MetaCognitionReport, ArchitectureSummary | None]:
        record.current_stage = CognitiveStage.EVALUATE
        record.touch()

        executive = self._executive_function.evaluate_missions(
            request,
            user=user,
            project_id=project_id,
            reasoning_result=reasoning,
        )
        self._store_artifact(record.execution_id, "executive_evaluation", executive.to_dict())
        self._increment_subsystem_call(record.execution_id, "executive_function")

        meta_report = self._meta_cognition.evaluate_reasoning(
            reasoning,
            context=context,
            executive_evaluation=executive,
        )
        self._store_artifact(record.execution_id, "meta_report", meta_report.to_dict())
        self._increment_subsystem_call(record.execution_id, "meta_cognition")

        architecture_summary = None
        domain = reasoning.understanding.domain if reasoning.understanding else None
        if domain in _CODE_DOMAINS:
            architecture_summary = self._project_intelligence.analyze_project(
                user=user,
                project_id=project_id,
                executive_evaluation=executive,
            )
            self._store_artifact(
                record.execution_id,
                "architecture_summary",
                architecture_summary.to_dict(),
            )
            self._increment_subsystem_call(record.execution_id, "project_intelligence")

        self._record_stage(
            record.execution_id,
            CognitiveStage.EVALUATE,
            success=True,
            summary=(
                executive.recommendation.reasoning
                if executive.recommendation
                else "evaluation complete"
            ),
            subsystem="executive_function",
            artifact_keys=("executive_evaluation", "meta_report", "architecture_summary"),
        )
        return executive, meta_report, architecture_summary

    def _run_plan_stage(
        self,
        record: CognitiveExecutionRecord,
        request: str,
        *,
        reasoning: ReasoningResult,
        executive: ExecutiveEvaluation,
        user: str | None,
        project_id: str | None,
        use_workflow_engine: bool | None,
    ) -> tuple[DeveloperWorkflowPlan | None, CognitivePlan | None, bool]:
        record.current_stage = CognitiveStage.PLAN
        record.touch()

        developer_plan = None
        domain = reasoning.understanding.domain if reasoning.understanding else None
        if domain in _CODE_DOMAINS:
            developer_plan = self._developer_workflow.plan(
                request,
                user=user,
                project_id=project_id,
                executive_evaluation=executive,
            )
            self._store_artifact(record.execution_id, "developer_plan", developer_plan.to_dict())
            self._increment_subsystem_call(record.execution_id, "developer_workflow")

        cognitive_plan = self._cognitive_orchestrator.create_plan(request)
        self._store_artifact(record.execution_id, "cognitive_plan", cognitive_plan.to_dict())
        self._increment_subsystem_call(record.execution_id, "cognitive_orchestrator")

        workflow_mode = use_workflow_engine
        if workflow_mode is None:
            workflow_mode = (
                self._autonomous_workflow_engine is not None
                and len(cognitive_plan.task_graph.nodes) > 2
            )

        self._record_stage(
            record.execution_id,
            CognitiveStage.PLAN,
            success=True,
            summary=f"plan created ({len(cognitive_plan.task_graph.nodes)} steps)",
            subsystem="cognitive_orchestrator",
            artifact_keys=("developer_plan", "cognitive_plan"),
        )
        return developer_plan, cognitive_plan, bool(workflow_mode)

    def _run_execute_pipeline(
        self,
        record: CognitiveExecutionRecord,
        plan: ExecutionPlan,
        *,
        confirmed: bool,
    ) -> CognitiveProcessResult:
        reasoning = plan.reasoning
        meta_report = plan.meta_report
        cognitive_plan = plan.cognitive_plan

        if reasoning is None or meta_report is None or cognitive_plan is None:
            raise RuntimeError("execution plan is missing required cognitive artifacts")

        # --- Confirm ---
        record.current_stage = CognitiveStage.CONFIRM
        record.touch()
        needs_confirmation, reason = self._requires_confirmation(
            reasoning=reasoning,
            meta_report=meta_report,
            plan=cognitive_plan,
            confirmed=confirmed,
        )
        if needs_confirmation:
            record.status = ExecutionStatus.AWAITING_CONFIRMATION
            record.confirmation_required = True
            record.confirmation_reason = reason
            plan = ExecutionPlan(
                plan_id=plan.plan_id,
                execution_id=plan.execution_id,
                request=plan.request,
                user=plan.user,
                project_id=plan.project_id,
                pipeline_stages=plan.pipeline_stages,
                requires_confirmation=True,
                confirmation_reason=reason,
                use_workflow_engine=plan.use_workflow_engine,
                reasoning=plan.reasoning,
                cognitive_context=plan.cognitive_context,
                world_snapshot=plan.world_snapshot,
                executive_evaluation=plan.executive_evaluation,
                meta_report=plan.meta_report,
                architecture_summary=plan.architecture_summary,
                developer_plan=plan.developer_plan,
                cognitive_plan=plan.cognitive_plan,
                created_at=plan.created_at,
            )
            self._plans[plan.plan_id] = plan
            metrics = self._metrics_for(record.execution_id)
            metrics.confirmation_gates += 1
            self._record_stage(
                record.execution_id,
                CognitiveStage.CONFIRM,
                success=False,
                summary=reason,
                subsystem="meta_cognition",
            )
            return CognitiveProcessResult(
                execution=record,
                success=False,
                message=reason,
                plan=plan,
            )

        self._record_stage(
            record.execution_id,
            CognitiveStage.CONFIRM,
            success=True,
            summary="confirmation gate passed",
            subsystem="meta_cognition",
        )

        # --- Execute ---
        record.status = ExecutionStatus.EXECUTING
        record.current_stage = CognitiveStage.EXECUTE
        record.touch()

        workflow_result = None
        execution_result = None

        if plan.use_workflow_engine and self._autonomous_workflow_engine is not None:
            workflow_record = self._autonomous_workflow_engine.create_workflow(
                plan.request,
                user=plan.user,
                project_id=plan.project_id,
            )
            record.workflow_id = workflow_record.workflow_id
            workflow_result = self._autonomous_workflow_engine.start_workflow(
                workflow_record.workflow_id,
                confirmed=True,
            )
            self._increment_subsystem_call(record.execution_id, "autonomous_workflow_engine")
            if workflow_result.execution is not None:
                execution_result = workflow_result.execution
            passed = workflow_result.success
            summary = workflow_result.message
        else:
            runtime = self._cognitive_orchestrator.execute_plan(
                cognitive_plan,
                message=plan.request,
            )
            self._increment_subsystem_call(record.execution_id, "cognitive_orchestrator")

            if runtime.status == PlanStatus.SUSPENDED:
                record.status = ExecutionStatus.AWAITING_CONFIRMATION
                record.confirmation_required = True
                record.confirmation_reason = "tool execution suspended pending confirmation"
                record.touch()
                metrics = self._metrics_for(record.execution_id)
                metrics.confirmation_gates += 1
                self._record_stage(
                    record.execution_id,
                    CognitiveStage.EXECUTE,
                    success=False,
                    summary=record.confirmation_reason,
                    subsystem="cognitive_orchestrator",
                )
                return CognitiveProcessResult(
                    execution=record,
                    success=False,
                    message=record.confirmation_reason,
                    plan=plan,
                )

            verification = self._cognitive_orchestrator.verify_plan(cognitive_plan, runtime)
            execution_result = CognitiveExecutionResult(
                plan=cognitive_plan,
                runtime=runtime,
                verification=verification,
                tool_results=runtime.tool_results,
                orchestration_results=runtime.orchestration_results,
            )
            self._store_artifact(record.execution_id, "execution", execution_result.to_dict())
            passed = verification.passed and runtime.status != PlanStatus.FAILED
            summary = verification.summary

        self._record_stage(
            record.execution_id,
            CognitiveStage.EXECUTE,
            success=passed,
            summary=summary,
            subsystem=(
                "autonomous_workflow_engine"
                if plan.use_workflow_engine
                else "cognitive_orchestrator"
            ),
            artifact_keys=("execution",),
        )

        # --- Learn ---
        record.current_stage = CognitiveStage.LEARN
        record.touch()
        learning = self._run_learn_stage(record, plan, reasoning, execution_result, passed)

        # --- Complete ---
        record.current_stage = CognitiveStage.COMPLETE
        record.status = ExecutionStatus.COMPLETED if passed else ExecutionStatus.FAILED
        if not passed:
            record.error_message = summary
        record.touch()
        self._record_stage(
            record.execution_id,
            CognitiveStage.COMPLETE,
            success=passed,
            summary=summary,
            subsystem="cognitive_operating_system",
        )

        return CognitiveProcessResult(
            execution=record,
            success=passed,
            message=summary,
            plan=plan,
            execution_result=execution_result,
            workflow_result=workflow_result,
            learning_result=learning,
        )

    def _run_learn_stage(
        self,
        record: CognitiveExecutionRecord,
        plan: ExecutionPlan,
        reasoning: ReasoningResult,
        execution: CognitiveExecutionResult | None,
        passed: bool,
    ) -> LearningResult | None:
        try:
            tool_name = self._primary_tool_name(execution, plan)
            execution_learning = self._knowledge_learning_engine.learn_from_execution(
                tool_name=tool_name,
                success=passed,
                summary_message=record.error_message or "execution completed",
                user=record.user,
                project_id=record.project_id,
            )
            self._knowledge_learning_engine.learn_from_reasoning(
                reasoning,
                user=record.user,
                project_id=record.project_id,
            )
            if plan.developer_plan is not None:
                self._knowledge_learning_engine.learn_from_workflow(
                    plan.developer_plan,
                    user=record.user,
                    project_id=record.project_id,
                )
            self._increment_subsystem_call(record.execution_id, "knowledge_learning_engine")
            metrics = self._metrics_for(record.execution_id)
            metrics.learning_items += 1
            record.learning_recorded = True
            self._record_stage(
                record.execution_id,
                CognitiveStage.LEARN,
                success=True,
                summary=execution_learning.message,
                subsystem="knowledge_learning_engine",
            )
            return execution_learning
        except Exception:
            logger.exception("Learning failed for execution %s", record.execution_id)
            self._record_stage(
                record.execution_id,
                CognitiveStage.LEARN,
                success=False,
                summary="learning stage failed",
                subsystem="knowledge_learning_engine",
            )
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _requires_confirmation(
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
            questions = "; ".join(
                question.question for question in reasoning.open_questions[:3]
            )
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
        return False

    @staticmethod
    def _primary_tool_name(
        execution: CognitiveExecutionResult | None,
        plan: ExecutionPlan,
    ) -> str:
        if execution is not None:
            for node in execution.plan.task_graph.nodes:
                if node.tool:
                    return node.tool
        if plan.cognitive_plan is not None:
            for node in plan.cognitive_plan.task_graph.nodes:
                if node.tool:
                    return node.tool
        return "cognitive_execution"

    def _register_execution(
        self,
        request: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
    ) -> CognitiveExecutionRecord:
        execution_id = new_execution_id()
        record = CognitiveExecutionRecord(
            execution_id=execution_id,
            request=request,
            user=user or self._resolve_user(),
            project_id=project_id or self._resolve_project_id(),
        )
        self._executions[execution_id] = record
        self._traces[execution_id] = ExecutionTrace(execution_id=execution_id)
        self._metrics[execution_id] = ExecutionMetrics(execution_id=execution_id)
        self._artifacts[execution_id] = {}
        logger.info("Cognitive execution registered: %s", execution_id)
        return record

    def _record_stage(
        self,
        execution_id: str,
        stage: CognitiveStage,
        *,
        success: bool,
        summary: str,
        subsystem: str = "",
        artifact_keys: tuple[str, ...] = (),
    ) -> None:
        trace = self._traces.setdefault(execution_id, ExecutionTrace(execution_id=execution_id))
        metrics = self._metrics_for(execution_id)
        started_at = _utc_now()
        duration_ms = 0.0
        if trace.entries:
            last = trace.entries[-1]
            elapsed = (started_at - last.started_at).total_seconds() * 1000
            duration_ms = max(elapsed, 0.0)
            metrics.stage_durations_ms[last.stage.value] = (
                metrics.stage_durations_ms.get(last.stage.value, 0.0) + duration_ms
            )

        entry = StageTraceEntry(
            stage=stage,
            started_at=started_at,
            duration_ms=duration_ms,
            success=success,
            summary=summary,
            subsystem=subsystem,
            artifact_keys=artifact_keys,
        )
        trace.entries.append(entry)
        metrics.total_duration_ms += duration_ms
        if success:
            metrics.stages_completed += 1
        else:
            metrics.stages_failed += 1

    def _metrics_for(self, execution_id: str) -> ExecutionMetrics:
        return self._metrics.setdefault(
            execution_id,
            ExecutionMetrics(execution_id=execution_id),
        )

    def _increment_subsystem_call(self, execution_id: str, subsystem: str) -> None:
        metrics = self._metrics_for(execution_id)
        metrics.subsystem_calls[subsystem] = metrics.subsystem_calls.get(subsystem, 0) + 1

    def _store_artifact(self, execution_id: str, key: str, value: Any) -> None:
        bucket = self._artifacts.setdefault(execution_id, {})
        bucket[key] = value

    def _require_execution(self, execution_id: str) -> CognitiveExecutionRecord:
        record = self._executions.get(execution_id)
        if record is None:
            raise KeyError(f"execution not found: {execution_id}")
        return record

    def _require_plan(self, plan_id: str) -> ExecutionPlan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise KeyError(f"plan not found: {plan_id}")
        return plan

    def _resolve_user(self) -> str | None:
        if self._context_manager is None:
            return None
        return self._context_manager.current_user

    def _resolve_project_id(self) -> str | None:
        if self._context_manager is None:
            return None
        project = self._context_manager.active_project
        return project or None

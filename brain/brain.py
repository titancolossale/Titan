# =====================================
# Titan Brain
# =====================================

from datetime import datetime

from brain.decision import Decision
from brain.decision_execution_bridge import decision_engine_from_manager
from brain.reasoning import Reasoning
from brain.planning import Planning
from brain.knowledge import Knowledge
from brain.executor import Executor
from brain.llm import LLM
from brain.prompt_builder import PromptBuilder
from brain.pipeline.stages import ThinkPipeline
from brain.pipeline.context_bundle import ThinkContext
from context.context_manager import ContextManager
from brain.internal_monologue import InternalMonologue
from memory.memory_service import MemoryService
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from core.execution_coordinator import ExecutionCoordinator
from core.execution_policy import ExecutionPolicy
from config.settings import EXECUTION_MAX_AGENTS, EXECUTION_MAX_TOOLS
from brain.autonomy_policy import AutonomyPolicy
from memory.learning_memory import LearningMemory
from agents.agent_manager import AgentManager
from core.state_manager import StateManager
from brain.executive_brain import ExecutiveBrain
from brain.executive_function import (
    ExecutiveEvaluation,
    ExecutiveFunction,
    FocusRecommendation,
)
from brain.initiative_engine import InitiativeEngine
from brain.llm_router import LLMRouter, LLMCallType
from brain.task_evaluator import TaskEvaluator
from brain.tool_dispatcher import ToolDispatcher
from brain.cognitive_loop import CognitiveLoop, CognitiveLoopResult
from brain.proactive_intelligence import (
    AttentionItem,
    ProactiveDigest,
    ProactiveEvaluation,
    ProactiveIntelligence,
)
from brain.knowledge_learning_engine import (
    KnowledgeCategory,
    KnowledgeItem,
    KnowledgeLearningEngine,
    KnowledgeSource,
    LearningResult,
)
from brain.world_model import (
    ActiveFocus,
    ProjectState,
    WorldBlocker,
    WorldModel,
    WorldModelSnapshot,
    WorldOpportunity,
    WorkspaceState,
)
from brain.cognitive_context_builder import (
    CognitiveContext,
    CognitiveContextBuilder,
)
from brain.meta_cognition import MetaCognitionEngine, MetaCognitionReport
from brain.autonomous_workflow_engine import (
    AutonomousWorkflowEngine,
    WorkflowRecord,
    WorkflowRunResult,
    WorkflowStatus,
)
from brain.cognitive_operating_system import (
    CognitiveExecutionRecord,
    CognitiveOperatingSystem,
    CognitiveProcessResult,
    ExecutionMetrics,
    ExecutionPlan,
    ExecutionTrace,
)
from brain.tool_intelligence import (
    ToolExecutionPlan,
    ToolIntelligence,
    build_default_tool_intelligence,
)
from brain.tool_execution_engine import (
    CoreToolRuntime,
    RequestExecutionResult,
    ToolExecutionEngine,
    build_core_tool_runtime,
)
from core.tools.capability_models import CapabilityRecord
from core.tools.capability_registry import CapabilityRegistrySummary, CapabilitySearchResult
from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
from brain.developer_workflow import DeveloperWorkflow, DeveloperWorkflowPlan
from brain.long_term_planner import GoalPlan, LongTermPlanner
from brain.project_intelligence import (
    ArchitectureSummary,
    FeatureLocation,
    ImpactAnalysis,
    ModuleDescription,
    ProjectIntelligence,
)
from brain.code_intelligence import (
    CallGraph,
    ClassSummary,
    CodeIntelligence,
    FunctionSummary,
    ModuleSummary,
    SymbolLocation,
    UnusedCandidate,
)
from brain.code_modification_planner import (
    CodeModificationPlan,
    CodeModificationPlanner,
)
from brain.code_generation_engine import CodeGenerationEngine, GeneratedPatch
from brain.development_session import (
    DevelopmentSession,
    DevelopmentSessionRuntime,
    SessionSummary,
)
from brain.natural_language_orchestrator import (
    NaturalLanguageOrchestrator,
    OrchestrationResult,
)
from brain.reasoning_engine import ReasoningEngine
from brain.reasoning_models import (
    ReasoningQuestion,
    ReasoningRecommendation,
    ReasoningResult,
)
from core.tools.code_editor import (
    CodeEditorTool,
    PatchApplicationResult,
    PatchPreview,
    PatchRollbackResult,
    PatchValidationResult,
)
from core.tools.code_editor.exceptions import (
    CodeEditorApprovalError,
    CodeEditorConfirmationError,
    CodeEditorError,
    CodeEditorPermissionDeniedError,
)
from core.tools.code_editor.models import TransactionStatus
from tools.tool_manager import ToolManager
from core.conversation_engine import ConversationEngine
from core.mission_manager import MissionManager
from core.mission_models import Mission, MissionPriority, MissionProgress, MissionState


class Brain:
    """Central cognitive orchestrator for Titan.

    ``process_request()`` is the primary high-level entry point: natural-language
    routing via ``NaturalLanguageOrchestrator`` to existing Brain systems.

    ``think()`` remains the cognitive pipeline entry for conversational synthesis
    (delegates to ``ThinkPipeline`` — Phase 2 — P2-021).

    Constructor contract (Track E, P1-050 — target after P1-069)
    -------------------------------------------------------------

    Shared managers are **injected from** ``core.titan.Titan`` (composition root).
    Brain must not instantiate these classes once DI is complete (P1-059).

    Required injected dependencies (keyword-only)::

        def __init__(
            self,
            *,
            agent_manager: AgentManager,
            context_manager: ContextManager,
            state_manager: StateManager,
            mission_manager: MissionManager,
            memory_service: MemoryService,
            tool_manager: ToolManager,
            llm: LLM | None = None,
        ) -> None:

    ``Titan.__init__`` owns construction and passes one shared instance of each
    manager to both itself and ``Brain``.

    High-level NL requests should prefer ``brain.process_request()``; the REPL
    may still call ``think()`` directly for pure conversation (P2-030).
    """

    def __init__(
        self,
        *,
        agent_manager: AgentManager,
        context_manager: ContextManager,
        state_manager: StateManager,
        mission_manager: MissionManager,
        memory_service: MemoryService,
        tool_manager: ToolManager,
        conversation_engine: ConversationEngine | None = None,
        llm: LLM | None = None,
        autonomy_policy: AutonomyPolicy | None = None,
        learning_memory: LearningMemory | None = None,
        initiative_engine: InitiativeEngine | None = None,
        llm_router: LLMRouter | None = None,
        tool_intelligence: ToolIntelligence | None = None,
        tool_execution_engine: ToolExecutionEngine | None = None,
        core_tool_runtime: CoreToolRuntime | None = None,
    ) -> None:
        self.decision = Decision()
        self.reasoning = Reasoning(
            decision_engine=decision_engine_from_manager(tool_manager),
            project_root=tool_manager.project_root,
        )
        self.planning = Planning()
        self.knowledge = Knowledge()
        self.executor = Executor()
        self.tool_manager = tool_manager
        self.tool_dispatcher = ToolDispatcher(tool_manager)
        runtime = core_tool_runtime
        if runtime is None and (
            tool_intelligence is None or tool_execution_engine is None
        ):
            runtime = build_core_tool_runtime()
        self.tool_intelligence = (
            tool_intelligence
            if tool_intelligence is not None
            else runtime.intelligence if runtime is not None
            else build_default_tool_intelligence()
        )
        self.tool_execution_engine = (
            tool_execution_engine
            if tool_execution_engine is not None
            else runtime.engine if runtime is not None
            else build_core_tool_runtime().engine
        )
        self._capability_registry = (
            runtime.capability_registry
            if runtime is not None
            else self.tool_intelligence.capability_registry
        )
        self._core_permission_manager = (
            runtime.permission_manager if runtime is not None else None
        )
        self.llm = llm if llm is not None else LLM()
        self.llm_router = llm_router if llm_router is not None else LLMRouter(self.llm)
        self.autonomy_policy = autonomy_policy or AutonomyPolicy.from_settings()
        self.learning_memory = learning_memory or LearningMemory()
        self.initiative_engine = initiative_engine or InitiativeEngine(
            policy=self.autonomy_policy,
            learning_memory=self.learning_memory,
        )
        self.monologue = InternalMonologue()
        self.context_manager = context_manager
        self.memory_service = memory_service
        self.state_manager = state_manager
        self.mission_manager = mission_manager
        self.workspace_awareness = WorkspaceAwareness(
            workspace_root=getattr(tool_manager, "project_root", None),
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
        )
        self.executive_function = ExecutiveFunction(
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
            workspace_awareness=self.workspace_awareness,
        )
        self.project_intelligence = ProjectIntelligence(
            workspace_awareness=self.workspace_awareness,
            executive_function=self.executive_function,
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
        )
        self.code_intelligence = CodeIntelligence(
            workspace_awareness=self.workspace_awareness,
            project_intelligence=self.project_intelligence,
            executive_function=self.executive_function,
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
        )
        self.developer_workflow = DeveloperWorkflow(
            workspace_awareness=self.workspace_awareness,
            executive_function=self.executive_function,
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
            tool_intelligence=self.tool_intelligence,
            code_intelligence=self.code_intelligence,
        )
        self.long_term_planner = LongTermPlanner(
            workspace_awareness=self.workspace_awareness,
            executive_function=self.executive_function,
            project_intelligence=self.project_intelligence,
            developer_workflow=self.developer_workflow,
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
        )
        self.code_modification_planner = CodeModificationPlanner(
            workspace_awareness=self.workspace_awareness,
            project_intelligence=self.project_intelligence,
            code_intelligence=self.code_intelligence,
            developer_workflow=self.developer_workflow,
            executive_function=self.executive_function,
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
        )
        self.code_generation_engine = CodeGenerationEngine(
            workspace_awareness=self.workspace_awareness,
            project_intelligence=self.project_intelligence,
            code_intelligence=self.code_intelligence,
            developer_workflow=self.developer_workflow,
            executive_function=self.executive_function,
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
            code_modification_planner=self.code_modification_planner,
            project_root=getattr(tool_manager, "project_root", None),
        )
        self.development_session = DevelopmentSessionRuntime(
            workspace_awareness=self.workspace_awareness,
            executive_function=self.executive_function,
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
        )
        self.reasoning_engine = ReasoningEngine()
        project_root = getattr(tool_manager, "project_root", None)
        self.code_editor = CodeEditorTool(
            workspace_root=project_root,
            permission_manager=self._core_permission_manager,
        )
        self.cognitive_loop = CognitiveLoop(
            memory_service=self.memory_service,
            tool_intelligence=self.tool_intelligence,
            context_manager=self.context_manager,
            mission_manager=self.mission_manager,
            executive_function=self.executive_function,
            workspace_awareness=self.workspace_awareness,
        )
        confirmation_gate = getattr(self.tool_manager, "confirmation_gate", None)
        self.proactive_intelligence = ProactiveIntelligence(
            executive_function=self.executive_function,
            workspace_awareness=self.workspace_awareness,
            mission_manager=self.mission_manager,
            development_session=self.development_session,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
            reasoning_engine=self.reasoning_engine,
            confirmation_gate=confirmation_gate,
        )
        self.knowledge_learning_engine = KnowledgeLearningEngine(
            memory_service=self.memory_service,
            learning_memory=self.learning_memory,
            project_intelligence=self.project_intelligence,
            code_intelligence=self.code_intelligence,
            mission_manager=self.mission_manager,
            developer_workflow=self.developer_workflow,
            reasoning_engine=self.reasoning_engine,
            executive_function=self.executive_function,
            context_manager=self.context_manager,
        )
        self.world_model = WorldModel(
            workspace_awareness=self.workspace_awareness,
            executive_function=self.executive_function,
            mission_manager=self.mission_manager,
            memory_service=self.memory_service,
            context_manager=self.context_manager,
            state_manager=self.state_manager,
            project_intelligence=self.project_intelligence,
            code_intelligence=self.code_intelligence,
            developer_workflow=self.developer_workflow,
            knowledge_learning_engine=self.knowledge_learning_engine,
            proactive_intelligence=self.proactive_intelligence,
            tool_intelligence=self.tool_intelligence,
        )
        self.cognitive_context_builder = CognitiveContextBuilder(
            workspace_awareness=self.workspace_awareness,
            memory_service=self.memory_service,
            mission_manager=self.mission_manager,
            context_manager=self.context_manager,
            state_manager=self.state_manager,
            project_intelligence=self.project_intelligence,
            code_intelligence=self.code_intelligence,
            developer_workflow=self.developer_workflow,
            development_session=self.development_session,
            executive_function=self.executive_function,
            knowledge_learning_engine=self.knowledge_learning_engine,
            proactive_intelligence=self.proactive_intelligence,
            world_model=self.world_model,
            tool_intelligence=self.tool_intelligence,
            conversation_engine=conversation_engine,
        )
        self.reasoning_engine.attach_context_builder(self.cognitive_context_builder)
        self.meta_cognition = MetaCognitionEngine(
            reasoning_engine=self.reasoning_engine,
            cognitive_context_builder=self.cognitive_context_builder,
            knowledge_learning_engine=self.knowledge_learning_engine,
            world_model=self.world_model,
            executive_function=self.executive_function,
            memory_service=self.memory_service,
        )
        self.agent_manager = agent_manager
        self.task_manager = TaskManager(self.agent_manager)
        self.task_orchestrator = TaskOrchestrator(
            self.task_manager,
            self.agent_manager,
        )
        self.execution_coordinator = ExecutionCoordinator(
            self.task_orchestrator,
            self.tool_dispatcher,
            reasoning=self.reasoning,
            executor=self.executor,
            policy=ExecutionPolicy(
                max_agents=EXECUTION_MAX_AGENTS,
                max_tools=EXECUTION_MAX_TOOLS,
            ),
        )
        self.autonomous_workflow_engine = AutonomousWorkflowEngine(
            reasoning_engine=self.reasoning_engine,
            cognitive_context_builder=self.cognitive_context_builder,
            executive_function=self.executive_function,
            meta_cognition=self.meta_cognition,
            knowledge_learning_engine=self.knowledge_learning_engine,
            cognitive_orchestrator=self.execution_coordinator.cognitive_orchestrator,
            context_manager=self.context_manager,
            confirmation_gate=confirmation_gate,
        )
        self.cognitive_operating_system = CognitiveOperatingSystem(
            cognitive_context_builder=self.cognitive_context_builder,
            reasoning_engine=self.reasoning_engine,
            executive_function=self.executive_function,
            meta_cognition=self.meta_cognition,
            knowledge_learning_engine=self.knowledge_learning_engine,
            world_model=self.world_model,
            memory_service=self.memory_service,
            project_intelligence=self.project_intelligence,
            developer_workflow=self.developer_workflow,
            cognitive_orchestrator=self.execution_coordinator.cognitive_orchestrator,
            autonomous_workflow_engine=self.autonomous_workflow_engine,
            context_manager=self.context_manager,
            confirmation_gate=confirmation_gate,
            workspace_awareness=self.workspace_awareness,
        )
        self.executive_brain = ExecutiveBrain(llm=self.llm)
        self.task_evaluator = TaskEvaluator(llm=self.llm)
        self.prompt_builder = PromptBuilder()
        self.conversation_engine = conversation_engine
        self.pipeline = ThinkPipeline(
            knowledge=self.knowledge,
            context_manager=self.context_manager,
            memory_service=self.memory_service,
            state_manager=self.state_manager,
            mission_manager=self.mission_manager,
            executive_brain=self.executive_brain,
            execution_coordinator=self.execution_coordinator,
            task_evaluator=self.task_evaluator,
            llm=self.llm,
            prompt_builder=self.prompt_builder,
            initiative_engine=self.initiative_engine,
            learning_memory=self.learning_memory,
            reasoning=self.reasoning,
            planning=self.planning,
            decision=self.decision,
            executor=self.executor,
            monologue=self.monologue,
            tool_dispatcher=self.tool_dispatcher,
            conversation_engine=conversation_engine,
        )
        self.natural_language_orchestrator = NaturalLanguageOrchestrator(self)

    @property
    def long_memory(self):
        """Backward-compatible access to long-term store (P3-040)."""
        return self.memory_service.long_term

    def process_request(self, message: str, *, stream=None) -> OrchestrationResult:
        """Primary high-level Brain entry — NL routing to existing systems.

        Delegates to ``NaturalLanguageOrchestrator``. Does not replace
        ``think()``; conversation intents still call ``think()`` internally.
        Optional *stream* is forwarded to ``think()`` for conversation intents.
        """
        result = self.natural_language_orchestrator.process(message, stream=stream)
        self._last_orchestration_result = result
        return result

    @property
    def last_orchestration_result(self) -> OrchestrationResult | None:
        """Most recent ``process_request`` result (routing / systems used)."""
        return getattr(self, "_last_orchestration_result", None)

    def think(self, message: str, *, stream=None) -> str:
        """Cognitive pipeline entry — delegates to the think pipeline."""
        ctx = ThinkContext(user_message=message)
        result = self.pipeline.run(ctx, stream=stream)
        self._last_think_context = result
        return result.response

    @property
    def last_think_context(self) -> ThinkContext | None:
        """Most recent pipeline context — used by web layer for memory activity (Phase 17.9)."""
        return getattr(self, "_last_think_context", None)

    def ask_routed(self, prompt: str, call_type: LLMCallType = LLMCallType.SYNTHESIS) -> str:
        """LLM call with multi-model routing (P9-070)."""
        return self.llm_router.ask(prompt, call_type=call_type)

    def generate_thoughts(self, message: str) -> CognitiveLoopResult:
        """Run the cognitive loop — observations, thoughts, recommendations only.

        Workspace Awareness refreshes once, then Executive Function ranks
        missions before cognition so the loop can observe focus and workspace
        context without mutating mission state or executing tools.
        """
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        evaluation = self.executive_function.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        return self.cognitive_loop.run(
            message,
            user=user,
            project_id=project_id,
            executive_evaluation=evaluation,
            workspace=workspace,
        )

    # --- Proactive Intelligence V1 Brain API ---

    def evaluate_proactive_context(self, message: str = "") -> ProactiveEvaluation:
        """Analyze existing context and produce ranked proactive recommendations."""
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        evaluation = self.executive_function.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        cognitive = self.cognitive_loop.run(
            message,
            user=user,
            project_id=project_id,
            executive_evaluation=evaluation,
            workspace=workspace,
        )
        return self.proactive_intelligence.evaluate(
            message,
            user=user,
            project_id=project_id,
            executive_evaluation=evaluation,
            workspace=workspace,
            cognitive_result=cognitive,
        )

    def get_proactive_digest(self) -> ProactiveDigest:
        """Return the latest proactive digest (empty if not yet evaluated)."""
        return self.proactive_intelligence.get_digest()

    def get_attention_items(self) -> tuple[AttentionItem, ...]:
        """Return compact attention items from the latest proactive digest."""
        return self.proactive_intelligence.get_attention_items()

    def acknowledge_recommendation(self, recommendation_id: str) -> bool:
        """Acknowledge a proactive recommendation."""
        return self.proactive_intelligence.acknowledge_recommendation(recommendation_id)

    def dismiss_recommendation(self, recommendation_id: str) -> bool:
        """Dismiss a proactive recommendation fingerprint."""
        return self.proactive_intelligence.dismiss_recommendation(recommendation_id)

    def snooze_recommendation(
        self,
        recommendation_id: str,
        until: datetime | None = None,
    ) -> bool:
        """Snooze a proactive recommendation until *until*."""
        return self.proactive_intelligence.snooze_recommendation(recommendation_id, until)

    def complete_recommendation(self, recommendation_id: str) -> bool:
        """Mark a proactive recommendation as completed."""
        return self.proactive_intelligence.complete_recommendation(recommendation_id)

    # --- Knowledge Learning Engine V1 Brain API ---

    def learn_from_interaction(
        self,
        user_message: str,
        assistant_response: str = "",
        *,
        tools_used: list[str] | None = None,
        outcome: str | None = None,
    ) -> LearningResult:
        """Extract knowledge candidates from a completed interaction."""
        return self.knowledge_learning_engine.learn_from_interaction(
            user_message,
            assistant_response,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
            tools_used=tools_used,
            outcome=outcome,
        )

    def learn_from_project(self, message: str = "") -> LearningResult:
        """Extract knowledge from project and architecture context."""
        return self.knowledge_learning_engine.learn_from_project(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def learn_from_execution(
        self,
        *,
        mission_id: str | None = None,
        tool_name: str = "",
        success: bool = True,
        summary_message: str = "",
    ) -> LearningResult:
        """Learn from a completed tool or mission execution."""
        return self.knowledge_learning_engine.learn_from_execution(
            mission_id=mission_id,
            tool_name=tool_name,
            success=success,
            summary_message=summary_message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def learn_from_code_change(
        self,
        *,
        files_changed: list[str],
        change_summary: str = "",
        patch_approved: bool = False,
    ) -> LearningResult:
        """Learn conventions and patterns from code changes."""
        return self.knowledge_learning_engine.learn_from_code_change(
            files_changed=files_changed,
            change_summary=change_summary,
            patch_approved=patch_approved,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def learn_from_feedback(self, feedback: str, *, context: str = "") -> LearningResult:
        """Detect user corrections and preference signals."""
        return self.knowledge_learning_engine.learn_from_feedback(
            feedback,
            context=context,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def generate_candidate_knowledge(
        self,
        *,
        title: str,
        description: str,
        category: KnowledgeCategory = KnowledgeCategory.LESSON,
        source: KnowledgeSource = KnowledgeSource.MANUAL,
        tags: list[str] | None = None,
        related_files: list[str] | None = None,
        related_tools: list[str] | None = None,
    ) -> KnowledgeItem:
        """Create a manual knowledge candidate."""
        return self.knowledge_learning_engine.generate_candidate_knowledge(
            title=title,
            description=description,
            category=category,
            source=source,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
            tags=tags,
            related_files=related_files,
            related_tools=related_tools,
        )

    def approve_knowledge(self, knowledge_id: str, *, note: str = "") -> KnowledgeItem | None:
        """Promote a knowledge candidate to verified."""
        return self.knowledge_learning_engine.approve_candidate(
            knowledge_id,
            actor=self.context_manager.current_user,
            note=note,
        )

    def reject_knowledge(self, knowledge_id: str, *, note: str = "") -> KnowledgeItem | None:
        """Reject a knowledge candidate."""
        return self.knowledge_learning_engine.reject_candidate(
            knowledge_id,
            actor=self.context_manager.current_user,
            note=note,
        )

    def list_knowledge_candidates(
        self,
        *,
        category: KnowledgeCategory | None = None,
    ) -> tuple[KnowledgeItem, ...]:
        """Return knowledge items awaiting verification."""
        return self.knowledge_learning_engine.list_candidates(category=category)

    def list_verified_knowledge(
        self,
        *,
        category: KnowledgeCategory | None = None,
    ) -> tuple[KnowledgeItem, ...]:
        """Return verified knowledge entries."""
        return self.knowledge_learning_engine.list_verified_knowledge(category=category)

    def search_knowledge(
        self,
        query: str,
        *,
        verified_only: bool = False,
        limit: int = 20,
    ) -> tuple[KnowledgeItem, ...]:
        """Search knowledge by title, description, and tags."""
        return self.knowledge_learning_engine.search_knowledge(
            query,
            verified_only=verified_only,
            limit=limit,
        )

    def update_knowledge_confidence(
        self,
        knowledge_id: str,
        *,
        delta: float = 0.0,
        absolute: float | None = None,
        evidence_increment: int = 0,
    ) -> KnowledgeItem | None:
        """Adjust confidence and evidence for a knowledge entry."""
        return self.knowledge_learning_engine.update_confidence(
            knowledge_id,
            delta=delta,
            absolute=absolute,
            evidence_increment=evidence_increment,
        )

    def merge_duplicate_knowledge(
        self,
        primary_id: str,
        duplicate_id: str,
    ) -> KnowledgeItem | None:
        """Merge duplicate knowledge into the primary entry."""
        return self.knowledge_learning_engine.merge_duplicate_knowledge(
            primary_id,
            duplicate_id,
        )

    # --- World Model V1 Brain API ---

    def build_world_model(self, message: str = "") -> WorldModelSnapshot:
        """Aggregate subsystem signals into Titan's current world model."""
        return self.world_model.build_world_model(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def refresh_world_model(self, message: str = "") -> WorldModelSnapshot:
        """Rebuild the world model from current subsystem state."""
        return self.world_model.refresh(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def get_world_model_snapshot(self) -> WorldModelSnapshot:
        """Return the cached world model snapshot (build if empty)."""
        return self.world_model.get_snapshot()

    def get_project_state(self) -> ProjectState:
        """Return the project-centric slice of the world model."""
        return self.world_model.get_project_state()

    def get_workspace_state(self) -> WorkspaceState:
        """Return the workspace-centric slice of the world model."""
        return self.world_model.get_workspace_state()

    def get_world_blockers(self) -> tuple[WorldBlocker, ...]:
        """Return known blockers from the world model."""
        return self.world_model.get_blockers()

    def get_world_opportunities(self) -> tuple[WorldOpportunity, ...]:
        """Return known opportunities from the world model."""
        return self.world_model.get_opportunities()

    def get_world_dependencies(self) -> dict[str, tuple[str, ...]]:
        """Return project dependency map from the world model."""
        return self.world_model.get_dependencies()

    def get_world_active_focus(self) -> ActiveFocus:
        """Return what Titan believes deserves attention (world model view)."""
        return self.world_model.get_active_focus()

    def export_world_model(self) -> dict:
        """Export the full world model as JSON-serializable data."""
        return self.world_model.export_world_model()

    # --- Cognitive Context Builder V1 Brain API ---

    def build_cognitive_context(self, message: str = "") -> CognitiveContext:
        """Assemble unified cognitive context for reasoning and planning."""
        return self.cognitive_context_builder.build_context(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def build_cognitive_context_for_request(self, message: str) -> CognitiveContext:
        """Build request-aware cognitive context."""
        return self.cognitive_context_builder.build_for_request(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def build_cognitive_context_for_project(self, project_id: str) -> CognitiveContext:
        """Build project-centric cognitive context."""
        return self.cognitive_context_builder.build_for_project(
            project_id,
            user=self.context_manager.current_user,
        )

    def build_cognitive_context_for_code_task(self, message: str) -> CognitiveContext:
        """Build context optimized for code tasks."""
        return self.cognitive_context_builder.build_for_code_task(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def build_cognitive_context_for_mission(self, mission_id: str) -> CognitiveContext:
        """Build mission-focused cognitive context."""
        return self.cognitive_context_builder.build_for_mission(
            mission_id,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def get_last_cognitive_context(self) -> CognitiveContext | None:
        """Return the most recently assembled cognitive context."""
        return self.cognitive_context_builder.get_last_context()

    def export_cognitive_context(self) -> dict:
        """Export the last cognitive context as JSON-serializable data."""
        return self.cognitive_context_builder.export_context()

    # --- Meta-Cognition Engine V1 Brain API ---

    def evaluate_reasoning_quality(
        self,
        message: str,
        *,
        reasoning_result: ReasoningResult | None = None,
    ) -> MetaCognitionReport:
        """Evaluate reasoning quality — meta-cognition only, never changes answers."""
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        reasoning = reasoning_result or self.reasoning_engine.reason(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        context = self.cognitive_context_builder.build_for_request(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        executive = self.executive_function.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
            reasoning_result=reasoning,
        )
        return self.meta_cognition.evaluate_reasoning(
            reasoning,
            context=context,
            executive_evaluation=executive,
        )

    def evaluate_cognitive_context_quality(
        self,
        message: str = "",
    ) -> MetaCognitionReport:
        """Evaluate assembled cognitive context sufficiency."""
        return self.meta_cognition.evaluate_context(
            self.build_cognitive_context_for_request(message or " "),
        )

    def evaluate_response_quality(
        self,
        response: str,
        message: str = "",
        *,
        reasoning_result: ReasoningResult | None = None,
    ) -> MetaCognitionReport:
        """Evaluate a candidate response before it is sent to the user."""
        context = None
        if message.strip():
            context = self.build_cognitive_context_for_request(message)
        return self.meta_cognition.evaluate_response(
            response,
            reasoning=reasoning_result,
            context=context,
            message=message,
        )

    def meta_cognition_requires_clarification(
        self,
        report: MetaCognitionReport | None = None,
    ) -> bool:
        """Return whether meta-cognition recommends user clarification."""
        return self.meta_cognition.requires_clarification(report)

    def meta_cognition_confidence(
        self,
        report: MetaCognitionReport | None = None,
    ) -> float:
        """Return confidence score from meta-cognition."""
        return self.meta_cognition.confidence(report)

    def export_meta_cognition_report(
        self,
        report: MetaCognitionReport | None = None,
    ) -> dict:
        """Export meta-cognition report as JSON-serializable data."""
        return self.meta_cognition.export_report(report)

    def get_last_meta_cognition_report(self) -> MetaCognitionReport | None:
        """Return the most recently produced meta-cognition report."""
        return self.meta_cognition.get_last_report()

    # --- Autonomous Workflow Engine V1 Brain API ---

    def create_workflow(
        self,
        objective: str,
        *,
        mission_id: str | None = None,
    ) -> WorkflowRecord:
        """Create a new autonomous workflow for a high-level objective."""
        return self.autonomous_workflow_engine.create_workflow(
            objective,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
            mission_id=mission_id,
        )

    def start_workflow(
        self,
        workflow_id: str,
        *,
        confirmed: bool = False,
    ) -> WorkflowRunResult:
        """Start or continue a workflow through analysis, planning, and execution."""
        return self.autonomous_workflow_engine.start_workflow(
            workflow_id,
            confirmed=confirmed,
        )

    def pause_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Pause a non-terminal workflow."""
        return self.autonomous_workflow_engine.pause_workflow(workflow_id)

    def resume_workflow(self, workflow_id: str) -> WorkflowRunResult:
        """Resume a paused workflow."""
        return self.autonomous_workflow_engine.resume_workflow(workflow_id)

    def cancel_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Cancel a workflow and any active cognitive plan."""
        return self.autonomous_workflow_engine.cancel_workflow(workflow_id)

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Return workflow state by id."""
        return self.autonomous_workflow_engine.get_workflow(workflow_id)

    def list_workflows(
        self,
        *,
        status: WorkflowStatus | None = None,
        limit: int = 50,
    ) -> tuple[WorkflowRecord, ...]:
        """List workflows, optionally filtered by status."""
        return self.autonomous_workflow_engine.list_workflows(status=status, limit=limit)

    def export_workflow(self, workflow_id: str) -> dict:
        """Export workflow state and artifacts as JSON-serializable data."""
        return self.autonomous_workflow_engine.export_workflow(workflow_id)

    # --- Cognitive Operating System V1 Brain API ---

    def run_cognitive_cycle(
        self,
        message: str,
        *,
        confirmed: bool = False,
        use_workflow_engine: bool | None = None,
    ) -> CognitiveProcessResult:
        """Run the full cognitive lifecycle via the Cognitive Operating System.

        Delegates to ``CognitiveOperatingSystem.process_request``. Does not
        replace ``process_request()`` (Natural Language Orchestrator front door).
        """
        return self.cognitive_operating_system.process_request(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
            confirmed=confirmed,
            use_workflow_engine=use_workflow_engine,
        )

    def build_cognitive_execution_plan(self, message: str) -> ExecutionPlan:
        """Build a cognitive execution plan without executing it."""
        return self.cognitive_operating_system.build_execution_plan(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def execute_cognitive_plan(
        self,
        plan_id: str,
        *,
        confirmed: bool = False,
    ) -> CognitiveProcessResult:
        """Execute a plan produced by ``build_cognitive_execution_plan``."""
        return self.cognitive_operating_system.execute_plan(
            plan_id,
            confirmed=confirmed,
        )

    def cancel_cognitive_execution(
        self,
        execution_id: str,
    ) -> CognitiveExecutionRecord | None:
        """Cancel an in-flight cognitive execution."""
        return self.cognitive_operating_system.cancel_execution(execution_id)

    def get_cognitive_execution_trace(self, execution_id: str) -> ExecutionTrace:
        """Return stage trace for a cognitive execution."""
        return self.cognitive_operating_system.get_execution_trace(execution_id)

    def get_cognitive_execution_metrics(self, execution_id: str) -> ExecutionMetrics:
        """Return aggregated metrics for a cognitive execution."""
        return self.cognitive_operating_system.get_execution_metrics(execution_id)

    def export_cognitive_execution(self, execution_id: str) -> dict:
        """Export cognitive execution state, trace, metrics, and artifacts."""
        return self.cognitive_operating_system.export_execution(execution_id)

    def get_cognitive_execution(
        self,
        execution_id: str,
    ) -> CognitiveExecutionRecord | None:
        """Return cognitive execution record by id."""
        return self.cognitive_operating_system.get_execution(execution_id)

    def list_cognitive_executions(
        self,
        *,
        limit: int = 50,
    ) -> tuple[CognitiveExecutionRecord, ...]:
        """List recent cognitive executions."""
        return self.cognitive_operating_system.list_executions(limit=limit)

    # --- Workspace Awareness V1 Brain API ---

    def get_workspace(self) -> WorkspaceSnapshot:
        """Return the cached workspace snapshot (refresh once if empty)."""
        return self.workspace_awareness.get_workspace()

    def refresh_workspace(
        self,
        *,
        open_files: list[str] | tuple[str, ...] | None = None,
        record_to_session: bool = False,
    ) -> WorkspaceSnapshot:
        """Explicitly rebuild workspace context — no background monitoring."""
        workspace = self.workspace_awareness.refresh(
            open_files=open_files,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )
        if record_to_session and self.development_session.get_active() is not None:
            self.development_session.update(workspace=workspace)
        return workspace

    # --- Executive Function V1 Brain API ---

    def get_current_focus(self) -> Mission | None:
        """Return the mission currently marked as active focus (read-only)."""
        return self.executive_function.get_current_focus()

    def evaluate_missions(
        self,
        message: str = "",
        *,
        reasoning_result: ReasoningResult | None = None,
    ) -> ExecutiveEvaluation:
        """Rank active missions and recommend focus — never mutates missions."""
        project_id = self.context_manager.active_project or None
        return self.executive_function.evaluate_missions(
            message,
            user=self.context_manager.current_user,
            project_id=project_id,
            reasoning_result=reasoning_result,
        )

    def recommend_focus(self, message: str = "") -> FocusRecommendation:
        """Recommend which mission should receive attention next."""
        project_id = self.context_manager.active_project or None
        return self.executive_function.recommend_focus(
            message,
            user=self.context_manager.current_user,
            project_id=project_id,
        )

    def plan_tool_execution(self, message: str) -> ToolExecutionPlan:
        """Produce a metadata-driven tool execution plan without running tools."""
        return self.tool_intelligence.plan(message)

    # --- Capability Registry Brain API ---

    def list_capabilities(self) -> list[CapabilityRecord]:
        """Return metadata for every installed tool from the shared capability registry."""
        return self.tool_intelligence.list_capabilities()

    def search_capabilities(
        self,
        query: str,
        *,
        exact: bool = False,
    ) -> list[CapabilitySearchResult]:
        """Search installed tools by id, name, tags, capabilities, actions, or permissions."""
        return self.tool_intelligence.search_capabilities(query, exact=exact)

    def find_tools_for_task(self, task: str) -> list[CapabilitySearchResult]:
        """Rank tools likely useful for a natural-language task description."""
        return self.tool_intelligence.find_tools_for_task(task)

    def describe_tool(self, name: str) -> CapabilityRecord | None:
        """Return full metadata for a tool by id or display name."""
        return self.tool_intelligence.describe_tool(name)

    def summarize_installed_tools(self) -> CapabilityRegistrySummary:
        """Return an aggregate summary of installed tools for NL and future UI."""
        return self.tool_intelligence.summarize_installed_tools()

    def plan_development_workflow(
        self,
        message: str,
        *,
        record_to_session: bool = False,
    ) -> DeveloperWorkflowPlan:
        """Produce a workspace-aware development plan without executing anything.

        Refreshes workspace context and ranks missions, then returns an advisory
        DeveloperWorkflowPlan. Commands and tools are recommendations only —
        Tool Execution Engine handles execution after approval.
        """
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        evaluation = self.executive_function.evaluate_missions(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        plan = self.developer_workflow.plan(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=evaluation,
        )
        if record_to_session and self.development_session.get_active() is not None:
            self.development_session.update(plan=plan)
        return plan

    # --- Long-Term Planning Engine V1 Brain API ---

    def plan_goal(self, goal: str) -> GoalPlan:
        """Transform a high-level objective into a structured GoalPlan.

        Planning only — never executes tools, never edits code, never starts
        missions. Mission Runtime may adopt ``mission_proposals`` later.
        """
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        reasoning = self.reasoning_engine.reason(
            goal,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        evaluation = self.executive_function.evaluate_missions(
            goal,
            user=user,
            project_id=project_id,
            workspace=workspace,
            reasoning_result=reasoning,
        )
        return self.long_term_planner.plan_goal(
            goal,
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=evaluation,
            reasoning_result=reasoning,
        )

    # --- Reasoning Engine V1 Brain API ---

    def reason(self, message: str) -> ReasoningResult:
        """Run the multi-step reasoning pipeline — analysis only, no tool execution."""
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        return self.reasoning_engine.reason(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )

    def compare_options(
        self,
        message: str,
        options: tuple[str, ...] | None = None,
    ) -> ReasoningResult:
        """Compare explicit or generated strategy options."""
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        return self.reasoning_engine.compare_options(
            message,
            options,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )

    def evaluate_request(self, message: str) -> ReasoningResult:
        """Holistically evaluate a request before planning or execution."""
        return self.reason(message)

    def detect_missing_information(self, message: str) -> tuple[ReasoningQuestion, ...]:
        """Return open questions and missing information for *message*."""
        return self.reasoning_engine.detect_missing_information(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def recommend_strategy(self, message: str) -> ReasoningRecommendation:
        """Return the recommended strategy without full reasoning artifacts."""
        return self.reasoning_engine.recommend_strategy(
            message,
            user=self.context_manager.current_user,
            project_id=self.context_manager.active_project or None,
        )

    def reason_about_project(self, message: str) -> ReasoningResult:
        """Reason with project and architecture context emphasized."""
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        return self.reasoning_engine.reason_about_project(
            message,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )

    def expand_goal(self, goal: str) -> GoalPlan:
        """Produce a deeper GoalPlan with nested subtasks (still plan-only)."""
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        evaluation = self.executive_function.evaluate_missions(
            goal,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        return self.long_term_planner.expand_goal(
            goal,
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=evaluation,
        )

    def review_plan(self, plan: GoalPlan) -> GoalPlan:
        """Critically review a GoalPlan — adjust risks/confidence, never execute."""
        return self.long_term_planner.review_plan(plan)

    def recalculate_plan(self, plan: GoalPlan) -> GoalPlan:
        """Rebuild a GoalPlan from its goal using fresh workspace context."""
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        evaluation = self.executive_function.evaluate_missions(
            plan.request or plan.goal,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        return self.long_term_planner.recalculate_plan(
            plan,
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=evaluation,
        )

    # --- Project Intelligence V1 Brain API ---

    def analyze_project(self) -> ArchitectureSummary:
        """Analyze project architecture — structure, dependencies, boundaries.

        Read-only. Never modifies code or executes tools. Refreshes workspace
        context and may consult Executive Function / Memory for signals.
        """
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        evaluation = self.executive_function.evaluate_missions(
            "project architecture",
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        return self.project_intelligence.analyze_project(
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=evaluation,
            refresh=False,
        )

    def find_feature(self, feature_name: str) -> FeatureLocation:
        """Locate which modules/files own a named feature (analysis only)."""
        return self.project_intelligence.find_feature(feature_name)

    def explain_module(self, module_name: str) -> ModuleDescription:
        """Explain a module's responsibility, dependencies, and reason for existing."""
        return self.project_intelligence.explain_module(module_name)

    def analyze_change_impact(self, file_or_module: str) -> ImpactAnalysis:
        """Estimate likely blast radius of modifying a file or module (advisory)."""
        return self.project_intelligence.analyze_change_impact(file_or_module)

    # --- Code Intelligence V1 Brain API ---

    def explain_function(
        self,
        name: str,
        *,
        record_to_session: bool = False,
    ) -> FunctionSummary:
        """Explain what a function or method does (static analysis only)."""
        summary = self.code_intelligence.explain_function(name)
        self._record_reviewed_paths(summary, record_to_session=record_to_session)
        return summary

    def explain_class(
        self,
        name: str,
        *,
        record_to_session: bool = False,
    ) -> ClassSummary:
        """Explain what a class does (static analysis only)."""
        summary = self.code_intelligence.explain_class(name)
        self._record_reviewed_paths(summary, record_to_session=record_to_session)
        return summary

    def find_symbol(self, name: str) -> tuple[SymbolLocation, ...]:
        """Locate definitions for a symbol name across the codebase."""
        return self.code_intelligence.find_symbol(name)

    def find_callers(self, name: str) -> CallGraph:
        """Find static callers and callees for a symbol."""
        return self.code_intelligence.find_callers(name)

    def find_unused_candidates(self) -> tuple[UnusedCandidate, ...]:
        """Return heuristic unused-code candidates (advisory only)."""
        return self.code_intelligence.find_unused_candidates()

    def summarize_module(
        self,
        module: str,
        *,
        record_to_session: bool = False,
    ) -> ModuleSummary:
        """Summarize a Python module at the symbol level (analysis only)."""
        summary = self.code_intelligence.summarize_module(module)
        if record_to_session and self.development_session.get_active() is not None:
            path = getattr(summary, "path", None) or getattr(summary, "module", None)
            reviewed = [str(path)] if path else [module]
            self.development_session.update(reviewed_files=reviewed)
        return summary

    # --- Code Modification Planner / Code Generation Engine V1 ---

    def plan_code_change(
        self,
        request: str,
        *,
        record_to_session: bool = False,
    ) -> CodeModificationPlan:
        """Prepare an implementation plan for a code change — no patches, no writes.

        Refreshes workspace context and ranks missions, then returns an advisory
        CodeModificationPlan. Generation requires an approved plan via
        ``generate_code``.
        """
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        evaluation = self.executive_function.evaluate_missions(
            request,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        plan = self.code_modification_planner.plan(
            request,
            user=user,
            project_id=project_id,
            workspace=workspace,
            executive_evaluation=evaluation,
        )
        if record_to_session and self.development_session.get_active() is not None:
            self.development_session.update(plan=plan)
        return plan

    def generate_code(
        self,
        plan: CodeModificationPlan,
        *,
        record_to_session: bool = False,
    ) -> GeneratedPatch:
        """Generate implementation patches from an approved CodeModificationPlan.

        Never writes files, never executes code, never commits. Returns
        GeneratedPatch proposals only. Plans must be approved
        (``plan.with_approval()``) unless the engine is configured otherwise.
        """
        project_id = self.context_manager.active_project or None
        user = self.context_manager.current_user
        workspace = self.workspace_awareness.refresh(
            user=user,
            project_id=project_id,
        )
        evaluation = self.executive_function.evaluate_missions(
            plan.request,
            user=user,
            project_id=project_id,
            workspace=workspace,
        )
        patch = self.code_generation_engine.generate(
            plan,
            workspace=workspace,
            executive_evaluation=evaluation,
        )
        if record_to_session and self.development_session.get_active() is not None:
            self.development_session.update(patch=patch)
        return patch

    # --- Controlled Patch Application V1 Brain API ---

    def validate_generated_patch(
        self,
        patch: GeneratedPatch,
        *,
        record_to_session: bool = False,
    ) -> PatchValidationResult:
        """Validate a GeneratedPatch without mutating the repository."""
        result = self.code_editor.validate_patch(patch)
        if record_to_session and self.development_session.get_active() is not None:
            self.development_session.update(
                application_record={
                    "kind": "validation",
                    "valid": result.valid,
                    "errors": list(result.errors),
                    "conflicts": list(result.conflicts),
                    "files_to_create": list(result.files_to_create),
                    "files_to_modify": list(result.files_to_modify),
                },
                add_pending=(
                    ["Review validation errors before apply"]
                    if not result.valid
                    else None
                ),
                complete_task="Validate generated patch" if result.valid else None,
            )
        return result

    def preview_generated_patch(
        self,
        patch: GeneratedPatch,
        *,
        record_to_session: bool = False,
    ) -> PatchPreview:
        """Preview a GeneratedPatch without mutating the repository."""
        preview = self.code_editor.preview_patch(patch)
        if record_to_session and self.development_session.get_active() is not None:
            self.development_session.update(
                application_record={
                    "kind": "preview",
                    "additions": preview.additions,
                    "deletions": preview.deletions,
                    "new_files": list(preview.new_files),
                    "affected_files": list(preview.affected_files),
                    "risk_level": preview.risk_level.value,
                    "change_summary": preview.change_summary,
                },
                reviewed_files=list(preview.affected_files),
            )
        return preview

    def apply_generated_patch(
        self,
        patch: GeneratedPatch,
        *,
        confirmed: bool = False,
        record_to_session: bool = False,
    ) -> PatchApplicationResult:
        """Apply an approved GeneratedPatch after explicit confirmation.

        Never silently mutates the repository. Does not commit or push.
        """
        try:
            result = self.code_editor.apply_patch(patch, confirmed=confirmed)
        except (
            CodeEditorConfirmationError,
            CodeEditorApprovalError,
            CodeEditorPermissionDeniedError,
            CodeEditorError,
        ) as exc:
            result = PatchApplicationResult(
                success=False,
                status=TransactionStatus.FAILED,
                errors=(str(exc),),
                message=str(exc),
            )

        if record_to_session and self.development_session.get_active() is not None:
            affected = list(
                dict.fromkeys([*result.files_created, *result.files_modified])
            )
            self.development_session.update(
                application_record={
                    "kind": "application",
                    "success": result.success,
                    "transaction_id": result.transaction_id,
                    "status": result.status.value,
                    "files_created": list(result.files_created),
                    "files_modified": list(result.files_modified),
                    "rollback_performed": result.rollback_performed,
                    "approved": bool(getattr(patch, "approved", False)),
                },
                decision=(
                    f"Applied patch transaction {result.transaction_id}"
                    if result.success and result.transaction_id
                    else "Patch application rejected or failed"
                ),
                decision_rationale=result.message,
                decision_source="user",
                reviewed_files=affected or None,
                complete_task="Apply generated patch" if result.success else None,
                add_pending=(
                    ["Review applied changes", "Run tests for affected modules"]
                    if result.success
                    else ["Fix patch validation / approval issues"]
                ),
                mark_patch_applied=bool(result.success),
            )
        return result

    def rollback_patch(
        self,
        transaction_id: str,
        *,
        confirmed: bool = False,
        record_to_session: bool = False,
    ) -> PatchRollbackResult:
        """Rollback a prior patch transaction after explicit confirmation."""
        try:
            result = self.code_editor.rollback_patch(
                transaction_id,
                confirmed=confirmed,
            )
        except (
            CodeEditorConfirmationError,
            CodeEditorPermissionDeniedError,
            CodeEditorError,
        ) as exc:
            result = PatchRollbackResult(
                success=False,
                transaction_id=str(transaction_id),
                status=TransactionStatus.FAILED,
                errors=(str(exc),),
                message=str(exc),
            )

        if record_to_session and self.development_session.get_active() is not None:
            self.development_session.update(
                application_record={
                    "kind": "rollback",
                    "success": result.success,
                    "transaction_id": result.transaction_id,
                    "status": result.status.value,
                    "files_restored": list(result.files_restored),
                    "files_removed": list(result.files_removed),
                },
                decision=(
                    f"Rolled back patch transaction {result.transaction_id}"
                    if result.success
                    else f"Rollback failed for {result.transaction_id}"
                ),
                decision_rationale=result.message,
                decision_source="user",
                complete_task="Rollback patch transaction" if result.success else None,
                add_pending=(
                    None
                    if result.success
                    else ["Investigate rollback failure"]
                ),
            )
        return result

    # --- Development Session Runtime V1 Brain API ---

    def start_development_session(
        self,
        feature: str,
        **kwargs,
    ) -> DevelopmentSession:
        """Start a persistent development session for a feature (track only)."""
        return self.development_session.start(feature, **kwargs)

    def update_development_session(self, **kwargs) -> DevelopmentSession:
        """Update the active development session with progress artifacts."""
        return self.development_session.update(**kwargs)

    def pause_development_session(
        self,
        session_id: str | None = None,
    ) -> DevelopmentSession:
        """Pause the active (or specified) development session."""
        return self.development_session.pause(session_id)

    def resume_development_session(
        self,
        session_id: str | None = None,
    ) -> DevelopmentSession:
        """Resume a paused development session (latest if id omitted)."""
        return self.development_session.resume(session_id)

    def end_development_session(
        self,
        session_id: str | None = None,
    ) -> DevelopmentSession:
        """End the active or paused development session."""
        return self.development_session.end(session_id)

    def summarize_development_session(
        self,
        session_id: str | None = None,
    ) -> SessionSummary:
        """Summarize development-session progress for prompt or user display."""
        return self.development_session.summarize(session_id)

    def get_development_session(self) -> DevelopmentSession | None:
        """Return the currently active development session, if any."""
        return self.development_session.get_active()

    def _record_reviewed_paths(
        self,
        summary: object,
        *,
        record_to_session: bool,
    ) -> None:
        if not record_to_session or self.development_session.get_active() is None:
            return
        path = getattr(summary, "path", None) or getattr(summary, "file_path", None)
        if path:
            self.development_session.update(reviewed_files=[str(path)])

    def execute_request(self, message: str) -> RequestExecutionResult:
        """Plan and execute tools for *message*; return the aggregated result."""
        plan = self.tool_intelligence.plan(message)
        execution = self.tool_execution_engine.execute(plan)
        self.mission_manager.on_tool_execution_complete(
            success=execution.success,
            summary_message=execution.summary_message,
            completed_tool_steps=len(execution.completed_steps),
            failed_tool_steps=len(execution.failed_steps),
        )
        return RequestExecutionResult(
            request=message,
            plan=plan,
            execution=execution,
        )

    # --- Mission Runtime V1 Brain API ---

    def create_mission(
        self,
        title: str,
        objective: str,
        steps: list[str],
        *,
        priority: MissionPriority | str = MissionPriority.NORMAL,
    ) -> Mission:
        """Create a long-running mission with explicit steps."""
        mission = self.mission_manager.runtime.create_mission(
            title,
            objective,
            steps,
            priority=priority,
        )
        self.mission_manager.mission = self.mission_manager.runtime.get_legacy_mission_view()
        return mission

    def resume_mission(self, mission_id: str) -> Mission:
        """Resume a paused or waiting mission."""
        return self.mission_manager.resume_mission(mission_id)

    def update_mission(self, mission_id: str, **kwargs) -> Mission:
        """Update mission fields (title, objective, state, priority, steps)."""
        return self.mission_manager.update_mission(mission_id, **kwargs)

    def complete_mission(self, mission_id: str) -> Mission:
        """Mark a mission as completed."""
        return self.mission_manager.complete_mission(mission_id)

    def list_active_missions(self) -> list[Mission]:
        """Return all missions not in a terminal state."""
        return self.mission_manager.list_active_missions()

    def get_mission_progress(self, mission_id: str) -> MissionProgress:
        """Return computed progress for a mission."""
        return self.mission_manager.runtime.get_progress(mission_id)

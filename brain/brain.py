# =====================================
# Titan Brain
# =====================================

from brain.decision import Decision
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
from brain.initiative_engine import InitiativeEngine
from brain.llm_router import LLMRouter, LLMCallType
from brain.task_evaluator import TaskEvaluator
from brain.tool_dispatcher import ToolDispatcher
from tools.tool_manager import ToolManager
from core.conversation_engine import ConversationEngine


class Brain:
    """Central cognitive orchestrator for Titan.

    ``think()`` is the single entry point for generating a user-facing response.
    All cognitive work is delegated to ``ThinkPipeline`` (Phase 2 — P2-021).

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

    Titan shell only calls ``brain.think()`` — Brain is the sole cognitive entry
    point (P2-030).
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
    ) -> None:
        self.decision = Decision()
        self.reasoning = Reasoning()
        self.planning = Planning()
        self.knowledge = Knowledge()
        self.executor = Executor()
        self.tool_manager = tool_manager
        self.tool_dispatcher = ToolDispatcher(tool_manager)
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
        self.state_manager = state_manager
        self.mission_manager = mission_manager
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

    @property
    def long_memory(self):
        """Backward-compatible access to long-term store (P3-040)."""
        return self.memory_service.long_term

    def think(self, message: str) -> str:
        """Single cognitive entry point — delegates to the think pipeline."""
        ctx = ThinkContext(user_message=message)
        result = self.pipeline.run(ctx)
        return result.response

    def ask_routed(self, prompt: str, call_type: LLMCallType = LLMCallType.SYNTHESIS) -> str:
        """LLM call with multi-model routing (P9-070)."""
        return self.llm_router.ask(prompt, call_type=call_type)

# =====================================
# Titan Think Pipeline Stages
# =====================================

"""Ordered cognitive pipeline stages for Brain.think() (Phase 2 — P2-020)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agents.agent_context import AgentContext
from brain.chat_fast_path import is_simple_conversational_request
from brain.pipeline.context_bundle import ThinkContext
from brain.prompt_builder import PromptBuilder
from brain.request_deadline import check_deadline, get_request_deadline
from config.settings import DEBUG_BRAIN, TITAN_MAX_AGENT_HANDOFFS
from memory.learning_memory import LearningOutcome

if TYPE_CHECKING:
    from brain.cognitive_stream import CognitiveStreamEmitter
    from agents.agent_manager import AgentManager
    from brain.executive_brain import ExecutiveBrain
    from brain.initiative_engine import InitiativeEngine
    from brain.knowledge import Knowledge
    from brain.llm import LLM
    from brain.task_evaluator import TaskEvaluator
    from context.context_manager import ContextManager
    from core.execution_coordinator import ExecutionCoordinator
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager
    from memory.learning_memory import LearningMemory
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Canonical stage order — rulebook Section 14.2 (P2-020).
STAGE_ORDER: tuple[str, ...] = (
    "knowledge_search",
    "session_commands",
    "conversation_commands",
    "mission_commands",
    "load_context",
    "load_conversation",
    "memory_commands",
    "load_and_retrieve_memory",
    "load_state",
    "load_or_create_mission",
    "executive_analysis",
    "initiative_analysis",
    "create_plan",
    "internal_analysis_debug",
    "memory_write_decision",
    "tool_confirmation_commands",
    "load_tool_status",
    "execution_coordinate",
    "assemble_prompt",
    "llm_call",
    "evaluate_mission_step",
    "record_learning",
    "update_state",
    "update_context",
)


class ThinkPipeline:
    """Runs the canonical think() pipeline; mutates and returns ``ThinkContext``."""

    def __init__(
        self,
        *,
        knowledge: Knowledge,
        context_manager: ContextManager,
        memory_service: MemoryService,
        state_manager: StateManager,
        mission_manager: MissionManager,
        executive_brain: ExecutiveBrain,
        execution_coordinator: ExecutionCoordinator,
        task_evaluator: TaskEvaluator,
        llm: LLM,
        prompt_builder: PromptBuilder | None = None,
        initiative_engine: InitiativeEngine | None = None,
        learning_memory: LearningMemory | None = None,
        # Collapsed placeholder stages — debug-only (P2-023)
        reasoning=None,
        planning=None,
        decision=None,
        executor=None,
        monologue=None,
        tool_dispatcher=None,
        conversation_engine=None,
    ) -> None:
        self.knowledge = knowledge
        self.context_manager = context_manager
        self.memory_service = memory_service
        self.state_manager = state_manager
        self.mission_manager = mission_manager
        self.executive_brain = executive_brain
        self.execution_coordinator = execution_coordinator
        self.task_evaluator = task_evaluator
        self.llm = llm
        self.prompt_builder = prompt_builder or PromptBuilder()
        self._initiative_engine = initiative_engine
        self._learning_memory = learning_memory
        self._reasoning = reasoning
        self._planning = planning
        self._decision = decision
        self._executor = executor
        self._monologue = monologue
        self._tool_dispatcher = tool_dispatcher
        self._conversation_engine = conversation_engine
        self._stage_log: list[str] = []
        self._stream: CognitiveStreamEmitter | None = None

    @property
    def stage_log(self) -> list[str]:
        """Record of stages executed in the last ``run()`` call."""
        return list(self._stage_log)

    def run(
        self,
        ctx: ThinkContext,
        *,
        stream: CognitiveStreamEmitter | None = None,
    ) -> ThinkContext:
        """Execute all pipeline stages in canonical order."""
        self._stage_log = []
        self._stream = stream
        # Safety net: conversational greetings never need agent/tool orchestration.
        if is_simple_conversational_request(ctx.user_message):
            ctx.skip_agents = True
        for stage_name in STAGE_ORDER:
            check_deadline(stage_name)
            if ctx.skip_llm and stage_name in (
                "execution_coordinate",
                "assemble_prompt",
                "llm_call",
            ):
                continue
            stage_fn = getattr(self, f"_stage_{stage_name}")
            self._stage_log.append(stage_name)
            stage_fn(ctx)
            deadline = get_request_deadline()
            if deadline is not None:
                deadline.mark_stage(stage_name)
        self._stream = None
        return ctx

    def _emit_stream(self, event_type: str, data: dict | None = None) -> None:
        """Emit a live cognitive event when a stream emitter is attached."""
        if self._stream is not None:
            self._stream.emit(event_type, data or {})

    def _debug(self, message: str, *args: object) -> None:
        if DEBUG_BRAIN:
            logger.debug(message, *args)

    def _stage_knowledge_search(self, ctx: ThinkContext) -> None:
        ctx.knowledge_hits = self.knowledge.search(ctx.user_message)
        if ctx.knowledge_hits:
            self._debug("Connaissances : %s", ctx.knowledge_hits)
        else:
            self._debug("Connaissances : aucune connaissance trouvée.")

    def _stage_session_commands(self, ctx: ThinkContext) -> None:
        """Handle /user session commands before memory retrieval (P4-031)."""
        response = self.context_manager.handle_session_command(ctx.user_message)
        if response is None:
            return
        if self.context_manager.is_pure_session_command(ctx.user_message):
            ctx.response = response
            ctx.skip_llm = True
            self._debug("Commande session : réponse directe.")

    def _stage_conversation_commands(self, ctx: ThinkContext) -> None:
        """Handle conversation REPL commands before LLM (P7-031)."""
        if self._conversation_engine is None:
            return
        response = self._conversation_engine.handle_command(ctx.user_message)
        if response is None:
            return
        ctx.response = response
        ctx.skip_llm = True
        self._debug("Commande conversation : réponse directe.")

    def _stage_mission_commands(self, ctx: ThinkContext) -> None:
        """Handle mission REPL commands before LLM (P8-011)."""
        response = self.mission_manager.handle_command(ctx.user_message)
        if response is None:
            return
        ctx.response = response
        ctx.mission = self.mission_manager.get_mission()
        if self.mission_manager.is_pure_mission_command(ctx.user_message):
            ctx.skip_llm = True
        self._debug("Commande mission : réponse directe.")

    def _stage_load_context(self, ctx: ThinkContext) -> None:
        snapshot = self.context_manager.refresh()
        ctx.context_snapshot = snapshot
        ctx.situational_context = self.context_manager.format_snapshot(snapshot)
        ctx.current_user = snapshot.current_user
        ctx.session_id = self.context_manager.session.session_id
        self._debug("Contexte actuel :\n%s", ctx.situational_context)

    def _stage_load_conversation(self, ctx: ThinkContext) -> None:
        """Load recent conversation window for prompt injection (P7-030)."""
        if self._conversation_engine is None:
            return
        ctx.session_id = ctx.session_id or self._conversation_engine.session_id
        ctx.turn_id = str(self._conversation_engine.total_turn_count + 1)
        ctx.conversation_window = self._conversation_engine.get_prompt_window(
            current_message=ctx.user_message,
        )
        ctx.conversation_loaded = bool(ctx.conversation_window)
        if ctx.conversation_window:
            self._debug(
                "Conversation récente (%d lignes)",
                len(ctx.conversation_window),
            )

    def _stage_memory_commands(self, ctx: ThinkContext) -> None:
        """Handle explicit memory commands before LLM (P3-030)."""
        command_response = self.memory_service.handle_command(
            ctx.current_user,
            ctx.user_message,
        )
        if command_response is None:
            return
        ctx.response = command_response
        ctx.skip_llm = True
        self._debug("Commande mémoire : réponse directe.")

    def _stage_load_and_retrieve_memory(self, ctx: ThinkContext) -> None:
        project_id = ""
        if ctx.context_snapshot is not None:
            project_id = ctx.context_snapshot.active_project or ""
        ctx.active_project = project_id
        self._emit_stream(
            "memory_lookup",
            {
                "label": "Recherche en mémoire…",
                "neural_state": "memory_retrieval",
                "source": "long_term",
            },
        )
        result = self.memory_service.retrieve(
            ctx.current_user,
            ctx.user_message,
            project_id=project_id or None,
        )
        ctx.retrieval_result = result
        ctx.retrieved_memory = result.text
        if result.has_matches:
            self._emit_stream(
                "memory_hit",
                {
                    "label": "Souvenirs retrouvés…",
                    "neural_state": "memory_retrieval",
                    "match_count": len(result.items),
                    "has_matches": True,
                },
            )
        else:
            self._emit_stream(
                "memory_miss",
                {
                    "label": "Aucun souvenir précis pour l'instant…",
                    "neural_state": "memory_retrieval",
                    "match_count": 0,
                    "has_matches": False,
                },
            )
        self._debug("Mémoire permanente (retrieved) :\n%s", ctx.retrieved_memory)

    def _stage_load_state(self, ctx: ThinkContext) -> None:
        ctx.state = self.state_manager.get_state()
        self._debug("ÉTAT ACTUEL :\n%s", ctx.state)

    def _stage_load_or_create_mission(self, ctx: ThinkContext) -> None:
        ctx.mission = self.mission_manager.get_mission()
        if (
            not ctx.mission.get("active")
            and self.mission_manager.should_create_mission_from_message(ctx.user_message)
        ):
            self.mission_manager.create_mission_from_message(ctx.user_message)
            ctx.mission = self.mission_manager.get_mission()
        self._debug("MISSION ACTIVE :\n%s", self.mission_manager.show_mission())

    def _stage_executive_analysis(self, ctx: ThinkContext) -> None:
        ctx.executive_analysis = self.executive_brain.analyze_mission(
            ctx.user_message,
            ctx.situational_context,
            ctx.retrieved_memory,
            ctx.state,
            ctx.mission,
        )
        self._debug("EXECUTIVE ANALYSIS :\n%s", ctx.executive_analysis)

    def _stage_initiative_analysis(self, ctx: ThinkContext) -> None:
        """Detect proactive signals when autonomy policy allows (P9-050)."""
        if ctx.skip_llm or self._initiative_engine is None:
            return
        project_id = ctx.active_project
        if ctx.context_snapshot is not None and not project_id:
            project_id = ctx.context_snapshot.active_project or ""
        result = self._initiative_engine.analyze(
            ctx.user_message,
            mission=ctx.mission,
            state=ctx.state,
            user=ctx.current_user,
            project_id=project_id,
        )
        ctx.initiative_text = result.format_for_prompt()
        if ctx.initiative_text:
            self._debug("INITIATIVE :\n%s", ctx.initiative_text)

    def _stage_create_plan(self, ctx: ThinkContext) -> None:
        """Build structured plan linked to mission step (P8-033)."""
        if ctx.skip_llm or self._planning is None:
            return
        engine = getattr(self._planning, "engine", None)
        if engine is None:
            return
        plan = engine.create_plan(
            ctx.user_message,
            mission=ctx.mission,
            state=ctx.state,
        )
        ctx.structured_plan_text = plan.format_for_prompt()
        self._debug("Plan structuré :\n%s", ctx.structured_plan_text)

    def _stage_internal_analysis_debug(self, ctx: ThinkContext) -> None:
        """Collapsed placeholder stages — debug output only, not injected into prompt."""
        if not DEBUG_BRAIN:
            return
        if self._monologue is not None:
            thoughts = self._monologue.think(ctx.user_message, ctx.situational_context)
            self._debug("Monologue interne :\n%s", thoughts)
        if self._reasoning is not None:
            analysis = self._reasoning.analyze(ctx.user_message)
            self._debug("Analyse :\n%s", analysis)
            if self._executor is not None:
                action = self._executor.execute(analysis)
                self._debug("Action choisie : %s", action)
        if self._planning is not None:
            plan = self._planning.create_plan(ctx.user_message)
            plan_lines = "\n".join(f"- {step}" for step in plan)
            self._debug("Plan :\n%s", plan_lines)
        if self._decision is not None:
            decision = self._decision.decide(ctx.user_message)
            self._debug("Décision : %s", decision)

    def _stage_memory_write_decision(self, ctx: ThinkContext) -> None:
        if ctx.skip_llm:
            return
        saved = self.memory_service.maybe_remember(ctx.current_user, ctx.user_message)
        if saved:
            self._debug("Mémoire sauvegardée avec succès.")

    def _stage_tool_confirmation_commands(self, ctx: ThinkContext) -> None:
        """Resolve /confirm commands into pending tool re-invocations (P10A-027)."""
        if ctx.skip_llm or self._tool_dispatcher is None:
            return
        gate = self._tool_dispatcher.tool_manager.confirmation_gate
        if gate is None:
            return

        from brain.tool_confirmation_handler import resolve_confirmed_tool_requests

        session_id = ctx.session_id or self.context_manager.session.session_id
        turn_id = ctx.turn_id or "default"
        requests, dispatch = resolve_confirmed_tool_requests(
            ctx.user_message,
            gate,
            session_id=session_id,
            user=ctx.current_user,
            turn_id=turn_id,
        )
        if dispatch is None:
            return
        ctx.confirmed_tool_requests = requests
        ctx.tool_confirmed = dispatch.confirmed
        ctx.confirmation_token = dispatch.confirmation_token
        self._debug(
            "Confirmation outil : confirmed=%s requests=%d",
            ctx.tool_confirmed,
            len(requests),
        )

    def _stage_load_tool_status(self, ctx: ThinkContext) -> None:
        """Probe provider health for prompt injection (P10A-026)."""
        if ctx.skip_llm or self._tool_dispatcher is None:
            return
        ctx.tool_status_text = self._tool_dispatcher.probe_provider_health()
        if ctx.tool_status_text:
            self._debug("Santé outils :\n%s", ctx.tool_status_text)

    def _stage_execution_coordinate(self, ctx: ThinkContext) -> None:
        """Run agents and tools via ExecutionCoordinator (P8-063)."""
        if ctx.skip_llm:
            return
        # Phase 11.4 — skip agent/tool orchestration for light conversation.
        if getattr(ctx, "skip_agents", False):
            self._debug("Execution coordinate skipped (conversational fast safety).")
            return
        from brain.tool_execution_bridge import dispatch_context_from_think

        agent_context = AgentContext.from_think_context(ctx, task=ctx.user_message)
        dispatch_context = dispatch_context_from_think(ctx)
        tool_override = ctx.confirmed_tool_requests if ctx.confirmed_tool_requests else None
        # Cap agent handoffs by global complex-path limit.
        prior_max = getattr(self.execution_coordinator.policy, "max_agents", None)
        result = None
        try:
            if prior_max is not None:
                self.execution_coordinator.policy.max_agents = min(
                    int(prior_max),
                    int(TITAN_MAX_AGENT_HANDOFFS),
                )
            result = self.execution_coordinator.execute(
                ctx.user_message,
                agent_context=agent_context,
                dispatch_context=dispatch_context,
                tool_requests_override=tool_override,
                stream=self._stream,
            )
        finally:
            if prior_max is not None:
                self.execution_coordinator.policy.max_agents = prior_max
        if result is None:
            return
        ctx.agent_results = result.agent_results
        ctx.agent_results_text = result.agent_results_text
        ctx.tool_results = result.tool_results
        ctx.tool_results_text = result.tool_results_text
        ctx.decision_report = result.decision_report
        ctx.cognitive_execution = result.cognitive_execution
        if result.cognitive_execution is not None:
            from brain.cognitive_progress import resolve_neural_state

            ctx.cognitive_neural_state = resolve_neural_state(
                result.cognitive_execution.cognitive_phase,
            )
        self._track_obsidian_consultation(ctx)
        self._track_browser_exploration(ctx)
        if ctx.obsidian_consulted:
            titles = ctx.obsidian_note_titles or []
            self._emit_stream(
                "obsidian_lookup",
                {
                    "label": "Consultation des notes Obsidian…",
                    "neural_state": "memory_retrieval",
                    "source": "obsidian",
                    "match_count": len(titles),
                    "has_matches": bool(titles),
                },
            )
        if result.tool_results_text:
            self._debug("Résultats outils :\n%s", result.tool_results_text)

    def _stage_assemble_prompt(self, ctx: ThinkContext) -> None:
        self._emit_stream(
            "response_building",
            {
                "label": "Construction de la réponse…",
                "neural_state": "thinking",
                "phase": "writing",
            },
        )
        ctx.prompt = self.prompt_builder.build(ctx)
        self._debug("LLM prompt (%d chars):\n%s", len(ctx.prompt), ctx.prompt)

    def _stage_llm_call(self, ctx: ThinkContext) -> None:
        if ctx.skip_llm:
            return
        logger.info("Calling LLM")
        on_delta = None
        stream = self._stream
        if stream is not None and hasattr(stream, "emit_text_delta"):
            started_flag = {"done": False}

            def on_delta(text: str) -> None:
                if not started_flag["done"]:
                    started_flag["done"] = True
                    if hasattr(stream, "emit_response_started"):
                        stream.emit_response_started()
                stream.emit_text_delta(text)

        ask_scoped = getattr(self.llm, "ask_scoped", None)
        if callable(ask_scoped) and on_delta is not None:
            # Prefer streaming when a cognitive stream is attached (Phase 12.1).
            instructions = getattr(self.llm, "system_instructions", "")
            ctx.response = ask_scoped(
                ctx.prompt,
                instructions,
                on_text_delta=on_delta,
            )
        else:
            ctx.response = self.llm.ask(ctx.prompt)
        self._emit_stream(
            "response_ready",
            {
                "label": "Réponse prête",
                "neural_state": "idle",
                "length": len(ctx.response or ""),
            },
        )

    def _stage_evaluate_mission_step(self, ctx: ThinkContext) -> None:
        if ctx.skip_llm:
            return
        if self.task_evaluator.is_step_completed(
            ctx.user_message,
            ctx.response,
            ctx.mission,
        ):
            self._debug("Étape terminée.")
            self.mission_manager.complete_current_step()
            ctx.mission = self.mission_manager.get_mission()
            self._debug("Nouvelle mission :\n%s", self.mission_manager.show_mission())

    def _stage_record_learning(self, ctx: ThinkContext) -> None:
        """Attach learning context and record explicit failure/success signals (P9-020)."""
        if ctx.skip_llm or self._learning_memory is None:
            return
        domain = ctx.active_project or "general"
        ctx.learning_text = self._learning_memory.format_for_prompt(
            domain,
            user=ctx.current_user,
        )
        message_lower = ctx.user_message.lower()
        if "n'a pas marché" in message_lower or "échec" in message_lower:
            self._learning_memory.record_outcome(
                domain,
                ctx.user_message[:120],
                LearningOutcome.FAILURE,
                user=ctx.current_user,
                project_id=ctx.active_project,
            )
        elif "ça marche" in message_lower or "succès" in message_lower:
            self._learning_memory.record_outcome(
                domain,
                ctx.user_message[:120],
                LearningOutcome.SUCCESS,
                user=ctx.current_user,
                project_id=ctx.active_project,
            )

    def _stage_update_state(self, ctx: ThinkContext) -> None:
        self.state_manager.update_after_response(ctx.user_message, ctx.response)

    def _stage_update_context(self, ctx: ThinkContext) -> None:
        """Post-response context session update (P4-040)."""
        self.context_manager.update_after_turn(ctx.user_message, ctx.response)

    @staticmethod
    def _track_obsidian_consultation(ctx: ThinkContext) -> None:
        """Record Obsidian vault consultation for memory visualization (Phase 22.0)."""
        from tools.connectors.vault_link_index import note_display_name

        titles: list[str] = []
        consulted = False
        for result in ctx.tool_results:
            if result.tool_name != "obsidian" or not result.success:
                continue
            consulted = True
            target = str((result.metadata or {}).get("target_path", "")).strip()
            if target and target not in {".", ""}:
                label = note_display_name(target)
                if label and label not in titles:
                    titles.append(label)
        ctx.obsidian_consulted = consulted
        ctx.obsidian_note_titles = titles[:4]

    @staticmethod
    def _track_browser_exploration(ctx: ThinkContext) -> None:
        """Record Browser exploration for Exploration UI and source cards (Phase 23.0)."""
        labels: list[str] = []
        exploring = False
        for result in ctx.tool_results:
            if result.tool_name != "browser" or not result.success:
                continue
            metadata = result.metadata or {}
            if metadata.get("exploration") or metadata.get("sources"):
                exploring = True
            for citation in metadata.get("citations") or []:
                label = str(citation).strip()
                if label and label not in labels:
                    labels.append(label)
            for source in metadata.get("sources") or []:
                if isinstance(source, dict):
                    title = str(source.get("title", "")).strip()
                    if title and title not in labels:
                        labels.append(title)
            if not labels:
                target_url = str(metadata.get("target_url", "")).strip()
                if target_url:
                    host_label = target_url.split("//")[-1].split("/")[0]
                    if host_label and host_label not in labels:
                        labels.append(host_label)
                exploring = True
        ctx.browser_exploring = exploring
        ctx.browser_source_labels = labels[:4]

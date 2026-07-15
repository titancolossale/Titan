# =====================================
# Titan Cognitive Context Builder
# =====================================

"""Cognitive Context Builder V1 — unified read-only context assembly.

Assembles every signal Reasoning and downstream cognition need into one
``CognitiveContext`` object. Subsystems are queried only through this
builder — Reasoning Engine must not call Memory, Knowledge, World Model,
Project Intelligence, or Proactive Intelligence directly.

Never mutates memory, knowledge, missions, or files. Never executes tools.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from brain.reasoning_models import ReasoningDomain
from brain.world_model import ActiveFocus, RuntimeStatus, WorldModelSnapshot
from core.mission_models import Mission

if TYPE_CHECKING:
    from brain.code_intelligence import CodeIntelligence
    from brain.developer_workflow import DeveloperWorkflow, DeveloperWorkflowPlan
    from brain.development_session import DevelopmentSessionRuntime
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.knowledge_learning_engine import KnowledgeItem, KnowledgeLearningEngine
    from brain.proactive_intelligence import ProactiveEvaluation, ProactiveIntelligence
    from brain.project_intelligence import ArchitectureSummary, ProjectIntelligence
    from brain.reasoning_models import RequestUnderstanding
    from brain.tool_intelligence import ToolIntelligence
    from brain.world_model import WorldModel
    from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
    from context.context_manager import ContextManager
    from core.conversation_engine import ConversationEngine
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager
    from memory.memory_service import MemoryService
    from memory.models import RetrievalResult

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_MODULE_RE = re.compile(
    r"\b(?:module|package)\s+([A-Za-z_][A-Za-z0-9_./]*)\b",
    re.IGNORECASE,
)
_CLASS_RE = re.compile(r"\b(?:class|classe)\s+([A-Z][A-Za-z0-9_]*)\b", re.IGNORECASE)
_SYMBOL_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\b")

_ARCHITECTURE_DOMAINS = frozenset(
    {
        ReasoningDomain.SOFTWARE,
        ReasoningDomain.ARCHITECTURE,
        ReasoningDomain.CODE,
        ReasoningDomain.PLANNING,
    }
)
_CODE_DOMAINS = frozenset(
    {
        ReasoningDomain.CODE,
        ReasoningDomain.SOFTWARE,
        ReasoningDomain.ARCHITECTURE,
    }
)


class ContextBuildMode(str, Enum):
    """How the cognitive context was assembled."""

    GENERAL = "general"
    REQUEST = "request"
    PROJECT = "project"
    CODE_TASK = "code_task"
    MISSION = "mission"


@dataclass(frozen=True)
class CognitiveContext:
    """Unified read-only cognitive context for one reasoning operation."""

    schema_version: int
    timestamp: datetime
    build_mode: ContextBuildMode
    message: str
    user: str
    project_id: str | None
    memories: RetrievalResult | None
    verified_knowledge: tuple[Any, ...]
    world_model: WorldModelSnapshot | None
    active_missions: tuple[Mission, ...]
    current_project: str
    active_workspace: WorkspaceSnapshot | None
    current_focus: ActiveFocus | None
    executive_priorities: ExecutiveEvaluation | None
    proactive_recommendations: ProactiveEvaluation | None
    user_goals: tuple[str, ...]
    available_tools: tuple[Any, ...]
    tool_candidates: tuple[Any, ...]
    runtime_state: RuntimeStatus | None
    conversation_context: str
    situational_context: str
    architecture: ArchitectureSummary | None
    code_context: dict[str, Any]
    development_session: Any | None
    developer_workflow_plan: DeveloperWorkflowPlan | None
    focus_mission_id: str | None
    sources: dict[str, bool]
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe structure."""
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp.isoformat(),
            "build_mode": self.build_mode.value,
            "message": self.message,
            "user": self.user,
            "project_id": self.project_id,
            "memories": (
                {
                    "text": self.memories.text,
                    "items": list(self.memories.items),
                    "user": self.memories.user,
                }
                if self.memories is not None
                else None
            ),
            "verified_knowledge": [
                item.to_dict() if hasattr(item, "to_dict") else str(item)
                for item in self.verified_knowledge
            ],
            "world_model": (
                self.world_model.to_dict() if self.world_model is not None else None
            ),
            "active_missions": [
                mission.to_dict() if hasattr(mission, "to_dict") else str(mission)
                for mission in self.active_missions
            ],
            "current_project": self.current_project,
            "active_workspace": (
                self.active_workspace.to_dict()
                if self.active_workspace is not None
                and hasattr(self.active_workspace, "to_dict")
                else None
            ),
            "current_focus": (
                self.current_focus.to_dict()
                if self.current_focus is not None
                else None
            ),
            "executive_priorities": (
                self.executive_priorities.to_dict()
                if self.executive_priorities is not None
                and hasattr(self.executive_priorities, "to_dict")
                else None
            ),
            "proactive_recommendations": (
                self.proactive_recommendations.to_dict()
                if self.proactive_recommendations is not None
                and hasattr(self.proactive_recommendations, "to_dict")
                else None
            ),
            "user_goals": list(self.user_goals),
            "available_tools": [
                tool.to_dict() if hasattr(tool, "to_dict") else str(tool)
                for tool in self.available_tools
            ],
            "tool_candidates": [
                item.to_dict() if hasattr(item, "to_dict") else str(item)
                for item in self.tool_candidates
            ],
            "runtime_state": (
                self.runtime_state.to_dict()
                if self.runtime_state is not None
                else None
            ),
            "conversation_context": self.conversation_context,
            "situational_context": self.situational_context,
            "architecture": (
                self.architecture.to_dict()
                if self.architecture is not None
                and hasattr(self.architecture, "to_dict")
                else None
            ),
            "code_context": self.code_context,
            "development_session": (
                self.development_session.to_dict()
                if self.development_session is not None
                and hasattr(self.development_session, "to_dict")
                else None
            ),
            "developer_workflow_plan": (
                self.developer_workflow_plan.to_dict()
                if self.developer_workflow_plan is not None
                else None
            ),
            "focus_mission_id": self.focus_mission_id,
            "sources": dict(self.sources),
            "summary": self.summary,
        }

    def format_for_prompt(self) -> str:
        """Format context for LLM prompt injection."""
        lines = [
            "CONTEXTE COGNITIF",
            f"Mode: {self.build_mode.value}",
            f"Utilisateur: {self.user}",
            f"Projet: {self.current_project or '(aucun)'}",
            "",
            self.summary or "(contexte assemblé)",
        ]
        if self.situational_context:
            lines.extend(["", "SITUATION", self.situational_context])
        if self.memories and self.memories.text:
            lines.extend(["", "MÉMOIRE PERTINENTE", self.memories.text])
        if self.verified_knowledge:
            lines.append("")
            lines.append("CONNAISSANCE VÉRIFIÉE")
            for item in self.verified_knowledge[:5]:
                title = getattr(item, "title", str(item))
                lines.append(f"- {title}")
        if self.world_model is not None:
            lines.extend(["", self.world_model.format_for_prompt()])
        if self.executive_priorities is not None and hasattr(
            self.executive_priorities,
            "recommendation",
        ):
            rec = self.executive_priorities.recommendation
            if rec is not None and getattr(rec, "reasoning", ""):
                lines.extend(["", "PRIORITÉS EXÉCUTIVES", rec.reasoning])
        if self.proactive_recommendations is not None:
            digest = getattr(self.proactive_recommendations, "digest", None)
            if digest is not None and getattr(digest, "recommendations", ()):
                lines.append("")
                lines.append("RECOMMANDATIONS PROACTIVES")
                for rec in digest.recommendations[:5]:
                    lines.append(f"- {getattr(rec, 'title', rec)}")
        if self.conversation_context:
            lines.extend(["", "CONVERSATION RÉCENTE", self.conversation_context])
        if self.architecture is not None and hasattr(self.architecture, "format_for_prompt"):
            lines.extend(["", self.architecture.format_for_prompt()])
        if self.code_context:
            lines.extend(["", "CONTEXTE CODE", str(self.code_context)[:800]])
        if self.developer_workflow_plan is not None:
            lines.extend(["", self.developer_workflow_plan.format_for_prompt()])
        return "\n".join(lines)


class CognitiveContextBuilder:
    """Assemble unified cognitive context from existing Titan subsystems.

    Read-only aggregation only. Never mutates memory, knowledge, or missions.
    """

    def __init__(
        self,
        *,
        workspace_awareness: WorkspaceAwareness | None = None,
        memory_service: MemoryService | None = None,
        mission_manager: MissionManager | None = None,
        context_manager: ContextManager | None = None,
        state_manager: StateManager | None = None,
        project_intelligence: ProjectIntelligence | None = None,
        code_intelligence: CodeIntelligence | None = None,
        developer_workflow: DeveloperWorkflow | None = None,
        development_session: DevelopmentSessionRuntime | None = None,
        executive_function: ExecutiveFunction | None = None,
        knowledge_learning_engine: KnowledgeLearningEngine | None = None,
        proactive_intelligence: ProactiveIntelligence | None = None,
        world_model: WorldModel | None = None,
        tool_intelligence: ToolIntelligence | None = None,
        conversation_engine: ConversationEngine | None = None,
    ) -> None:
        self._workspace_awareness = workspace_awareness
        self._memory_service = memory_service
        self._mission_manager = mission_manager
        self._context_manager = context_manager
        self._state_manager = state_manager
        self._project_intelligence = project_intelligence
        self._code_intelligence = code_intelligence
        self._developer_workflow = developer_workflow
        self._development_session = development_session
        self._executive_function = executive_function
        self._knowledge_learning_engine = knowledge_learning_engine
        self._proactive_intelligence = proactive_intelligence
        self._world_model = world_model
        self._tool_intelligence = tool_intelligence
        self._conversation_engine = conversation_engine
        self._last_context: CognitiveContext | None = None

    # --- Public API ---

    def build_context(
        self,
        message: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        refresh_workspace: bool = True,
    ) -> CognitiveContext:
        """Build a full general-purpose cognitive context."""
        return self._assemble(
            message,
            build_mode=ContextBuildMode.GENERAL,
            user=user,
            project_id=project_id,
            workspace=workspace,
            refresh_workspace=refresh_workspace,
            include_request_extras=False,
        )

    def build_for_request(
        self,
        message: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
        understanding: RequestUnderstanding | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
        proactive_evaluation: ProactiveEvaluation | None = None,
    ) -> CognitiveContext:
        """Build request-aware context for Reasoning Engine and NLO awareness."""
        domain = understanding.domain if understanding is not None else None
        return self._assemble(
            message,
            build_mode=ContextBuildMode.REQUEST,
            user=user,
            project_id=project_id,
            workspace=workspace,
            refresh_workspace=workspace is None,
            include_request_extras=True,
            reasoning_domain=domain,
            executive_evaluation=executive_evaluation,
            proactive_evaluation=proactive_evaluation,
        )

    def build_for_project(
        self,
        project_id: str,
        message: str = "",
        *,
        user: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
    ) -> CognitiveContext:
        """Build project-centric cognitive context."""
        return self._assemble(
            message,
            build_mode=ContextBuildMode.PROJECT,
            user=user,
            project_id=project_id,
            workspace=workspace,
            refresh_workspace=True,
            include_request_extras=True,
            reasoning_domain=ReasoningDomain.SOFTWARE,
            force_architecture=True,
        )

    def build_for_code_task(
        self,
        message: str,
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
    ) -> CognitiveContext:
        """Build context optimized for code analysis and modification tasks."""
        return self._assemble(
            message,
            build_mode=ContextBuildMode.CODE_TASK,
            user=user,
            project_id=project_id,
            workspace=workspace,
            refresh_workspace=True,
            include_request_extras=True,
            reasoning_domain=ReasoningDomain.CODE,
            force_architecture=True,
            force_code=True,
            include_developer_workflow=True,
        )

    def build_for_mission(
        self,
        mission_id: str,
        message: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
        workspace: WorkspaceSnapshot | None = None,
    ) -> CognitiveContext:
        """Build context focused on a specific active mission."""
        return self._assemble(
            message,
            build_mode=ContextBuildMode.MISSION,
            user=user,
            project_id=project_id,
            workspace=workspace,
            refresh_workspace=True,
            include_request_extras=False,
            reasoning_domain=ReasoningDomain.MISSION,
            focus_mission_id=mission_id,
        )

    def get_last_context(self) -> CognitiveContext | None:
        """Return the most recently built cognitive context."""
        return self._last_context

    def export_context(self) -> dict[str, Any]:
        """Export the last built context as JSON-serializable data."""
        if self._last_context is None:
            context = self.build_context()
        else:
            context = self._last_context
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": _utc_now().isoformat(),
            "cognitive_context": context.to_dict(),
        }

    # ------------------------------------------------------------------
    # Private assembly
    # ------------------------------------------------------------------

    def _assemble(
        self,
        message: str,
        *,
        build_mode: ContextBuildMode,
        user: str | None,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
        refresh_workspace: bool,
        include_request_extras: bool,
        reasoning_domain: ReasoningDomain | None = None,
        executive_evaluation: ExecutiveEvaluation | None = None,
        proactive_evaluation: ProactiveEvaluation | None = None,
        force_architecture: bool = False,
        force_code: bool = False,
        include_developer_workflow: bool = False,
        focus_mission_id: str | None = None,
    ) -> CognitiveContext:
        timestamp = _utc_now()
        resolved_user, resolved_project = self._resolve_context(user, project_id)
        sources: dict[str, bool] = {}
        request = (message or "").strip()

        workspace_snapshot = self._load_workspace(
            workspace,
            user=resolved_user,
            project_id=resolved_project,
            refresh=refresh_workspace,
            sources=sources,
        )

        world_snapshot = self._load_world_model(
            request,
            user=resolved_user,
            project_id=resolved_project,
            refresh_workspace=False,
            sources=sources,
            workspace=workspace_snapshot,
        )

        executive = executive_evaluation
        if executive is None:
            executive = self._load_executive(
                request,
                user=resolved_user,
                project_id=resolved_project,
                workspace=workspace_snapshot,
                sources=sources,
            )

        memories = self._load_memories(
            request,
            user=resolved_user,
            project_id=resolved_project,
            sources=sources,
        )

        verified_knowledge = self._load_verified_knowledge(
            request,
            sources=sources,
        )

        missions = self._load_missions(sources=sources, focus_mission_id=focus_mission_id)

        proactive = proactive_evaluation
        if proactive is None and self._proactive_intelligence is not None:
            proactive = self._load_proactive(
                request,
                user=resolved_user,
                project_id=resolved_project,
                workspace=workspace_snapshot,
                executive=executive,
                sources=sources,
            )

        situational = self._load_situational_context(sources=sources)
        conversation = self._load_conversation_context(request, sources=sources)

        architecture = None
        if (
            force_architecture
            or (
                include_request_extras
                and reasoning_domain in _ARCHITECTURE_DOMAINS
            )
        ):
            architecture = self._load_architecture(
                user=resolved_user,
                project_id=resolved_project,
                workspace=workspace_snapshot,
                executive=executive,
                sources=sources,
            )

        code_context: dict[str, Any] = {}
        if force_code or (
            include_request_extras and reasoning_domain in _CODE_DOMAINS and request
        ):
            code_context = self._load_code_context(request, sources=sources)

        development_session = self._load_development_session(sources=sources)

        developer_plan = None
        if include_developer_workflow and self._developer_workflow is not None:
            developer_plan = self._load_developer_workflow(
                request,
                user=resolved_user,
                project_id=resolved_project,
                workspace=workspace_snapshot,
                executive=executive,
                sources=sources,
            )

        tool_candidates: tuple[Any, ...] = ()
        if include_request_extras and request:
            tool_candidates = self._load_tool_candidates(request, sources=sources)

        available_tools = self._resolve_available_tools(world_snapshot, sources=sources)

        user_goals = world_snapshot.user_goals if world_snapshot is not None else ()
        current_focus = world_snapshot.current_focus if world_snapshot is not None else None
        runtime_state = world_snapshot.runtime_status if world_snapshot is not None else None
        current_project = resolved_project or (
            world_snapshot.runtime_status.active_project
            if world_snapshot is not None
            else ""
        )

        summary = self._build_summary(
            build_mode=build_mode,
            user=resolved_user,
            project=current_project,
            mission_count=len(missions),
            memory_available=memories is not None and memories.has_matches,
            knowledge_count=len(verified_knowledge),
            tool_count=len(available_tools),
            source_count=sum(1 for value in sources.values() if value),
        )

        context = CognitiveContext(
            schema_version=SCHEMA_VERSION,
            timestamp=timestamp,
            build_mode=build_mode,
            message=request,
            user=resolved_user,
            project_id=resolved_project,
            memories=memories,
            verified_knowledge=verified_knowledge,
            world_model=world_snapshot,
            active_missions=missions,
            current_project=current_project or "",
            active_workspace=workspace_snapshot,
            current_focus=current_focus,
            executive_priorities=executive,
            proactive_recommendations=proactive,
            user_goals=user_goals,
            available_tools=available_tools,
            tool_candidates=tool_candidates,
            runtime_state=runtime_state,
            conversation_context=conversation,
            situational_context=situational,
            architecture=architecture,
            code_context=code_context,
            development_session=development_session,
            developer_workflow_plan=developer_plan,
            focus_mission_id=focus_mission_id,
            sources=sources,
            summary=summary,
        )
        self._last_context = context
        logger.debug("Cognitive context built mode=%s sources=%d", build_mode.value, len(sources))
        return context

    def _resolve_context(
        self,
        user: str | None,
        project_id: str | None,
    ) -> tuple[str, str | None]:
        resolved_user = user
        resolved_project = project_id
        if self._context_manager is not None:
            if resolved_user is None:
                resolved_user = getattr(self._context_manager, "current_user", None) or "Nolan"
            if resolved_project is None:
                resolved_project = (
                    getattr(self._context_manager, "active_project", None) or None
                )
        return resolved_user or "Nolan", resolved_project

    def _load_workspace(
        self,
        workspace: WorkspaceSnapshot | None,
        *,
        user: str,
        project_id: str | None,
        refresh: bool,
        sources: dict[str, bool],
    ) -> WorkspaceSnapshot | None:
        if workspace is not None:
            sources["workspace_awareness"] = True
            return workspace
        if self._workspace_awareness is None:
            sources["workspace_awareness"] = False
            return None
        try:
            if refresh:
                snapshot = self._workspace_awareness.refresh(
                    user=user,
                    project_id=project_id,
                )
            else:
                snapshot = self._workspace_awareness.get_workspace()
            sources["workspace_awareness"] = True
            return snapshot
        except Exception:
            logger.debug("CognitiveContextBuilder workspace load failed", exc_info=True)
            sources["workspace_awareness"] = False
            return None

    def _load_world_model(
        self,
        message: str,
        *,
        user: str,
        project_id: str | None,
        refresh_workspace: bool,
        sources: dict[str, bool],
        workspace: WorkspaceSnapshot | None,
    ) -> WorldModelSnapshot | None:
        if self._world_model is None:
            sources["world_model"] = False
            return None
        try:
            if workspace is not None and not refresh_workspace:
                snapshot = self._world_model.build_world_model(
                    message,
                    user=user,
                    project_id=project_id,
                    refresh_workspace=False,
                )
            else:
                snapshot = self._world_model.build_world_model(
                    message,
                    user=user,
                    project_id=project_id,
                    refresh_workspace=refresh_workspace,
                )
            sources["world_model"] = True
            return snapshot
        except Exception:
            logger.debug("CognitiveContextBuilder world model load failed", exc_info=True)
            sources["world_model"] = False
            return None

    def _load_executive(
        self,
        message: str,
        *,
        user: str,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
        sources: dict[str, bool],
    ) -> ExecutiveEvaluation | None:
        if self._executive_function is None:
            sources["executive_function"] = False
            return None
        try:
            evaluation = self._executive_function.evaluate_missions(
                message,
                user=user,
                project_id=project_id,
                workspace=workspace,
            )
            sources["executive_function"] = True
            return evaluation
        except Exception:
            logger.debug("CognitiveContextBuilder executive load failed", exc_info=True)
            sources["executive_function"] = False
            return None

    def _load_memories(
        self,
        message: str,
        *,
        user: str,
        project_id: str | None,
        sources: dict[str, bool],
    ) -> RetrievalResult | None:
        if self._memory_service is None or not message:
            sources["memory"] = False
            return None
        try:
            retrieval = self._memory_service.retrieve(user, message, project_id=project_id)
            sources["memory"] = True
            return retrieval
        except Exception:
            logger.debug("CognitiveContextBuilder memory retrieve failed", exc_info=True)
            sources["memory"] = False
            return None

    def _load_verified_knowledge(
        self,
        message: str,
        *,
        sources: dict[str, bool],
    ) -> tuple[Any, ...]:
        if self._knowledge_learning_engine is None:
            sources["knowledge_learning_engine"] = False
            return ()
        try:
            if message:
                items = self._knowledge_learning_engine.search_knowledge(
                    message,
                    verified_only=True,
                    limit=8,
                )
            else:
                items = self._knowledge_learning_engine.list_verified_knowledge()[:8]
            sources["knowledge_learning_engine"] = True
            return tuple(items)
        except Exception:
            logger.debug("CognitiveContextBuilder knowledge load failed", exc_info=True)
            sources["knowledge_learning_engine"] = False
            return ()

    def _load_missions(
        self,
        *,
        sources: dict[str, bool],
        focus_mission_id: str | None,
    ) -> tuple[Mission, ...]:
        if self._mission_manager is None:
            sources["mission_runtime"] = False
            return ()
        try:
            if focus_mission_id:
                mission = self._mission_manager.runtime.get_mission(focus_mission_id)
                if mission is not None:
                    sources["mission_runtime"] = True
                    return (mission,)
                sources["mission_runtime"] = False
                return ()
            missions = self._mission_manager.runtime.list_active_missions()
            sources["mission_runtime"] = True
            return tuple(missions)
        except Exception:
            logger.debug("CognitiveContextBuilder mission load failed", exc_info=True)
            sources["mission_runtime"] = False
            return ()

    def _load_proactive(
        self,
        message: str,
        *,
        user: str,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
        executive: ExecutiveEvaluation | None,
        sources: dict[str, bool],
    ) -> ProactiveEvaluation | None:
        assert self._proactive_intelligence is not None
        try:
            evaluation = self._proactive_intelligence.evaluate(
                message,
                user=user,
                project_id=project_id,
                workspace=workspace,
                executive_evaluation=executive,
            )
            sources["proactive_intelligence"] = True
            return evaluation
        except Exception:
            logger.debug("CognitiveContextBuilder proactive load failed", exc_info=True)
            sources["proactive_intelligence"] = False
            return None

    def _load_situational_context(self, *, sources: dict[str, bool]) -> str:
        if self._context_manager is None:
            sources["context_manager"] = False
            return ""
        try:
            text = self._context_manager.get_context()
            sources["context_manager"] = bool(text)
            return text or ""
        except Exception:
            logger.debug("CognitiveContextBuilder context manager failed", exc_info=True)
            sources["context_manager"] = False
            return ""

    def _load_conversation_context(
        self,
        message: str,
        *,
        sources: dict[str, bool],
    ) -> str:
        if self._conversation_engine is None:
            sources["conversation_engine"] = False
            return ""
        try:
            window = self._conversation_engine.get_prompt_window(
                current_message=message or None,
            )
            text = "\n".join(window) if window else ""
            sources["conversation_engine"] = bool(text)
            return text
        except Exception:
            logger.debug("CognitiveContextBuilder conversation load failed", exc_info=True)
            sources["conversation_engine"] = False
            return ""

    def _load_architecture(
        self,
        *,
        user: str,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
        executive: ExecutiveEvaluation | None,
        sources: dict[str, bool],
    ) -> ArchitectureSummary | None:
        if self._project_intelligence is None:
            sources["project_intelligence"] = False
            return None
        try:
            summary = self._project_intelligence.analyze_project(
                user=user,
                project_id=project_id,
                workspace=workspace,
                executive_evaluation=executive,
                refresh=False,
            )
            sources["project_intelligence"] = True
            return summary
        except Exception:
            logger.debug("CognitiveContextBuilder architecture load failed", exc_info=True)
            sources["project_intelligence"] = False
            return None

    def _load_code_context(
        self,
        request: str,
        *,
        sources: dict[str, bool],
    ) -> dict[str, Any]:
        if self._code_intelligence is None:
            sources["code_intelligence"] = False
            return {}
        result: dict[str, Any] = {}
        module_match = _MODULE_RE.search(request)
        class_match = _CLASS_RE.search(request)
        try:
            if module_match:
                module_name = module_match.group(1)
                result["module_summary"] = self._code_intelligence.summarize_module(
                    module_name,
                )
            if class_match:
                class_name = class_match.group(1)
                result["class_summary"] = self._code_intelligence.explain_class(class_name)
            for symbol in _SYMBOL_RE.findall(request)[:3]:
                if symbol in ("Brain", "Titan", "Mission", "Tool"):
                    impact = self._code_intelligence.estimate_modification_impact(symbol)
                    result.setdefault("impacts", []).append(impact)
            sources["code_intelligence"] = bool(result)
        except Exception:
            logger.debug("CognitiveContextBuilder code context failed", exc_info=True)
            sources["code_intelligence"] = False
        return result

    def _load_development_session(self, *, sources: dict[str, bool]) -> Any | None:
        if self._development_session is None:
            sources["development_session"] = False
            return None
        try:
            session = self._development_session.get_active()
            sources["development_session"] = session is not None
            return session
        except Exception:
            sources["development_session"] = False
            return None

    def _load_developer_workflow(
        self,
        message: str,
        *,
        user: str,
        project_id: str | None,
        workspace: WorkspaceSnapshot | None,
        executive: ExecutiveEvaluation | None,
        sources: dict[str, bool],
    ) -> DeveloperWorkflowPlan | None:
        assert self._developer_workflow is not None
        try:
            plan = self._developer_workflow.plan(
                message,
                user=user,
                project_id=project_id,
                workspace=workspace,
                executive_evaluation=executive,
            )
            sources["developer_workflow"] = True
            return plan
        except Exception:
            logger.debug("CognitiveContextBuilder developer workflow failed", exc_info=True)
            sources["developer_workflow"] = False
            return None

    def _load_tool_candidates(
        self,
        request: str,
        *,
        sources: dict[str, bool],
    ) -> tuple[Any, ...]:
        if self._tool_intelligence is None:
            sources["capability_registry"] = False
            return ()
        try:
            candidates = self._tool_intelligence.find_tools_for_task(request)
            sources["capability_registry"] = bool(candidates)
            return tuple(candidates)
        except Exception:
            logger.debug("CognitiveContextBuilder tool search failed", exc_info=True)
            sources["capability_registry"] = False
            return ()

    def _resolve_available_tools(
        self,
        world_snapshot: WorldModelSnapshot | None,
        *,
        sources: dict[str, bool],
    ) -> tuple[Any, ...]:
        if world_snapshot is not None and world_snapshot.available_tools:
            sources["available_tools"] = True
            return world_snapshot.available_tools
        if self._tool_intelligence is None:
            sources["available_tools"] = False
            return ()
        try:
            records = self._tool_intelligence.list_capabilities()
            sources["available_tools"] = bool(records)
            return tuple(records)
        except Exception:
            sources["available_tools"] = False
            return ()

    def _build_summary(
        self,
        *,
        build_mode: ContextBuildMode,
        user: str,
        project: str,
        mission_count: int,
        memory_available: bool,
        knowledge_count: int,
        tool_count: int,
        source_count: int,
    ) -> str:
        parts = [
            f"Contexte cognitif ({build_mode.value}) pour {user}",
            f"projet={project or 'aucun'}",
            f"missions actives={mission_count}",
            f"mémoire={'oui' if memory_available else 'non'}",
            f"connaissances vérifiées={knowledge_count}",
            f"outils={tool_count}",
            f"sources={source_count}",
        ]
        return " | ".join(parts)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

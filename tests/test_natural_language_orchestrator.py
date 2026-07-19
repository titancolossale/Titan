# =====================================
# Titan Natural Language Orchestrator Tests
# =====================================

"""Comprehensive tests for Natural Language Orchestrator V1 — routing only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.llm import LLM
from brain.natural_language_orchestrator import (
    DetectedIntent,
    NaturalLanguageOrchestrator,
    OrchestrationResult,
    PipelineDecision,
    RequestAnalysis,
    SystemName,
    SystemsUsed,
)
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


def _write(path: Path, content: str = "# note\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_python_project(root: Path, *, name: str = "TitanNLO") -> Path:
    project = root / name
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")
    _write(project / "README.md", f"# {name}\n")
    _write(project / "CHANGELOG.md", "# Changelog\n")
    for pkg in ("core", "brain", "memory", "tools", "tests", "docs"):
        (project / pkg).mkdir(exist_ok=True)
        if pkg not in ("docs", "tests"):
            _write(project / pkg / "__init__.py", "")
    _write(
        project / "brain" / "engine.py",
        "class Engine:\n    def run(self):\n        return True\n\n"
        "def helper():\n    return 1\n",
    )
    _write(project / "core" / "util.py", "VALUE = 1\n")
    _write(project / "tests" / "test_engine.py", "def test_engine():\n    assert True\n")
    _write(project / "docs" / "ARCHITECTURE.md", "# Architecture\n")
    return project


def _build_brain(tmp_path: Path, workspace_root: Path | None = None) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    root = workspace_root or tmp_path
    return Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=root),
        llm=mock_llm,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return _make_python_project(tmp_path)


@pytest.fixture
def brain(tmp_path: Path, project: Path) -> Brain:
    return _build_brain(tmp_path, project)


@pytest.fixture
def orchestrator(brain: Brain) -> NaturalLanguageOrchestrator:
    return brain.natural_language_orchestrator


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Bonjour Titan", DetectedIntent.CONVERSATION),
        ("What is the capital of France?", DetectedIntent.QUESTION),
        ("Search FastAPI docs", DetectedIntent.RESEARCH),
        ("Plan the ORR automation", DetectedIntent.PLANNING),
        ("Show me the architecture", DetectedIntent.ARCHITECTURE),
        ("Analyze the project", DetectedIntent.PROJECT_ANALYSIS),
        ("Explain class Engine", DetectedIntent.CODE_EXPLANATION),
        ("Plan a code change for Engine", DetectedIntent.CODE_PLANNING),
        ("Generate code for a helper", DetectedIntent.CODE_GENERATION),
        ("Preview the patch", DetectedIntent.PATCH_PREVIEW),
        ("Apply the approved patch", DetectedIntent.PATCH_APPLICATION),
        ("What is the current workspace?", DetectedIntent.WORKSPACE_QUERY),
        ("List active missions", DetectedIntent.MISSION_MANAGEMENT),
        ("Read my ORR notes", DetectedIntent.MEMORY),
        ("Run pytest", DetectedIntent.TOOL_REQUEST),
        ("Continue Titan", DetectedIntent.DEVELOPMENT_CONTINUATION),
    ],
)
def test_intent_detection(
    orchestrator: NaturalLanguageOrchestrator,
    message: str,
    expected: DetectedIntent,
) -> None:
    analysis = orchestrator._analyze_request(message)
    intent, confidence, _reason = orchestrator._detect_intent(analysis)
    assert intent == expected
    assert 0.0 < confidence <= 1.0


def test_confidence_present(orchestrator: NaturalLanguageOrchestrator) -> None:
    result = orchestrator.process("Plan the ORR automation")
    assert isinstance(result, OrchestrationResult)
    assert result.confidence >= 0.7
    assert result.detected_intent == DetectedIntent.PLANNING


# ---------------------------------------------------------------------------
# Pipeline ordering
# ---------------------------------------------------------------------------


def test_pipeline_awareness_first(orchestrator: NaturalLanguageOrchestrator) -> None:
    analysis = orchestrator._analyze_request("Continue Titan")
    intent, _c, reason = orchestrator._detect_intent(analysis)
    decision = orchestrator._build_pipeline(intent, analysis, reason)
    assert isinstance(decision, PipelineDecision)
    assert decision.systems[0] == SystemName.REASONING_ENGINE
    assert SystemName.CONTEXT_MANAGER in decision.systems
    assert SystemName.WORKSPACE_AWARENESS in decision.systems
    assert SystemName.MISSION_RUNTIME in decision.systems
    assert SystemName.EXECUTIVE_FUNCTION in decision.systems
    assert SystemName.DEVELOPER_WORKFLOW in decision.systems
    idx_ws = decision.systems.index(SystemName.WORKSPACE_AWARENESS)
    idx_wf = decision.systems.index(SystemName.DEVELOPER_WORKFLOW)
    assert idx_ws < idx_wf


def test_code_generation_pipeline_order(
    orchestrator: NaturalLanguageOrchestrator,
) -> None:
    analysis = orchestrator._analyze_request("Generate code for Engine")
    intent, _c, reason = orchestrator._detect_intent(analysis)
    decision = orchestrator._build_pipeline(intent, analysis, reason)
    assert SystemName.CODE_MODIFICATION_PLANNER in decision.systems
    assert SystemName.CODE_GENERATION_ENGINE in decision.systems
    idx_plan = decision.systems.index(SystemName.CODE_MODIFICATION_PLANNER)
    idx_gen = decision.systems.index(SystemName.CODE_GENERATION_ENGINE)
    assert idx_plan < idx_gen


def test_developer_mode_enrichment(
    orchestrator: NaturalLanguageOrchestrator,
) -> None:
    analysis = orchestrator._analyze_request("Explain class Engine")
    intent, _c, reason = orchestrator._detect_intent(analysis)
    decision = orchestrator._build_pipeline(intent, analysis, reason)
    assert decision.developer_mode is True
    for system in (
        SystemName.WORKSPACE_AWARENESS,
        SystemName.PROJECT_INTELLIGENCE,
        SystemName.CODE_INTELLIGENCE,
        SystemName.EXECUTIVE_FUNCTION,
        SystemName.DEVELOPER_WORKFLOW,
    ):
        assert system in decision.systems


# ---------------------------------------------------------------------------
# Routing handlers
# ---------------------------------------------------------------------------


def test_conversation_routes_to_fast_path(brain: Brain) -> None:
    result = brain.process_request("Bonjour")
    assert result.detected_intent == DetectedIntent.CONVERSATION
    assert SystemName.BRAIN_THINK.value in result.systems_used.invoked
    assert "Réponse de test" in result.final_response
    assert (result.artifacts or {}).get("fast_path", {}).get("selected") is True
    assert brain.last_orchestration_result is result


def test_question_routes_to_think(brain: Brain) -> None:
    result = brain.process_request("What is Titan?")
    assert result.detected_intent == DetectedIntent.QUESTION
    assert SystemName.BRAIN_THINK.value in result.systems_used.invoked


def test_planning_routes_to_long_term_planner(brain: Brain) -> None:
    result = brain.process_request("Plan the ORR automation")
    assert result.detected_intent == DetectedIntent.PLANNING
    assert SystemName.LONG_TERM_PLANNER.value in result.systems_used.invoked
    assert "goal_plan" in result.artifacts or "Plan" in result.final_response


def test_research_routes_to_tool_systems(brain: Brain) -> None:
    with patch.object(
        brain,
        "execute_request",
        return_value=MagicMock(
            summary_message="Browser search completed",
            to_dict=lambda: {"ok": True},
        ),
    ) as mock_exec:
        with patch.object(
            brain,
            "plan_tool_execution",
            return_value=MagicMock(
                requires_tools=True,
                selected_tools=(),
                to_dict=lambda: {},
            ),
        ):
            result = brain.process_request("Search FastAPI docs")
    assert result.detected_intent == DetectedIntent.RESEARCH
    assert SystemName.TOOL_INTELLIGENCE.value in result.systems_used.invoked
    assert SystemName.TOOL_EXECUTION_ENGINE.value in result.systems_used.invoked
    mock_exec.assert_called_once()
    assert "Browser search" in result.final_response


def test_memory_routing(brain: Brain) -> None:
    brain.memory_service.store_categorized("Nolan", "notes", "ORR notes about risk")
    with patch.object(
        brain,
        "execute_request",
        return_value=MagicMock(
            summary_message="Obsidian notes loaded",
            to_dict=lambda: {},
        ),
    ):
        result = brain.process_request("Read my ORR notes")
    assert result.detected_intent == DetectedIntent.MEMORY
    assert SystemName.MEMORY.value in result.systems_used.invoked
    assert SystemName.TOOL_INTELLIGENCE.value in result.systems_used.invoked


def test_workspace_query(brain: Brain) -> None:
    result = brain.process_request("What is the current workspace?")
    assert result.detected_intent == DetectedIntent.WORKSPACE_QUERY
    assert SystemName.WORKSPACE_AWARENESS.value in result.systems_used.invoked
    assert result.final_response


def test_mission_routing(brain: Brain) -> None:
    brain.create_mission(
        "ORR Sprint",
        "Ship ORR automation",
        ["Research", "Implement", "Test"],
        priority=MissionPriority.HIGH,
    )
    result = brain.process_request("List active missions")
    assert result.detected_intent == DetectedIntent.MISSION_MANAGEMENT
    assert SystemName.MISSION_RUNTIME.value in result.systems_used.invoked
    assert SystemName.EXECUTIVE_FUNCTION.value in result.systems_used.invoked
    assert "ORR Sprint" in result.final_response


def test_code_explanation_routing(brain: Brain) -> None:
    result = brain.process_request("Explain class Engine")
    assert result.detected_intent == DetectedIntent.CODE_EXPLANATION
    assert SystemName.CODE_INTELLIGENCE.value in result.systems_used.invoked
    assert "class_summary" in result.artifacts or "Engine" in result.final_response


def test_code_planning_routing(brain: Brain) -> None:
    result = brain.process_request("Plan a code change to add logging to Engine")
    assert result.detected_intent == DetectedIntent.CODE_PLANNING
    assert SystemName.CODE_MODIFICATION_PLANNER.value in result.systems_used.invoked
    assert "code_plan" in result.artifacts


def test_generation_routing_no_application(brain: Brain) -> None:
    result = brain.process_request("Generate code for a Discord notifier helper")
    assert result.detected_intent == DetectedIntent.CODE_GENERATION
    assert SystemName.CODE_MODIFICATION_PLANNER.value in result.systems_used.invoked
    assert SystemName.CODE_GENERATION_ENGINE.value in result.systems_used.invoked
    assert SystemName.CONTROLLED_PATCH.value not in result.systems_used.invoked
    assert any("generation only" in s for s in result.systems_used.skipped) or (
        "non appliqué" in result.final_response.lower()
        or "appliqué" in result.final_response
    )


def test_patch_preview_without_session_patch(brain: Brain) -> None:
    result = brain.process_request("Preview the patch")
    assert result.detected_intent == DetectedIntent.PATCH_PREVIEW
    assert SystemName.CONTROLLED_PATCH.value in result.systems_used.invoked or any(
        "controlled_patch" in s for s in result.systems_used.skipped
    )
    assert "patch" in result.final_response.lower() or "Patch" in result.final_response


def test_patch_application_without_session_patch(brain: Brain) -> None:
    result = brain.process_request("Apply the approved patch")
    assert result.detected_intent == DetectedIntent.PATCH_APPLICATION
    assert "patch" in result.final_response.lower() or "Patch" in result.final_response


def test_developer_continuation(brain: Brain) -> None:
    if brain.get_development_session() is not None:
        brain.end_development_session()
    brain.create_mission(
        "Continue Titan",
        "Keep building Titan",
        ["Orchestrator", "Tests", "Docs"],
    )
    brain.start_development_session("Natural Language Orchestrator")
    result = brain.process_request("Continue Titan")
    assert result.detected_intent == DetectedIntent.DEVELOPMENT_CONTINUATION
    invoked = result.systems_used.invoked
    assert SystemName.WORKSPACE_AWARENESS.value in invoked
    assert SystemName.MISSION_RUNTIME.value in invoked
    assert SystemName.EXECUTIVE_FUNCTION.value in invoked
    assert SystemName.DEVELOPER_WORKFLOW.value in invoked


def test_mixed_request_prefers_strongest_intent(brain: Brain) -> None:
    result = brain.process_request("Plan a code change for the mission module")
    assert result.detected_intent == DetectedIntent.CODE_PLANNING


# ---------------------------------------------------------------------------
# Response model & logging contract
# ---------------------------------------------------------------------------


def test_response_model_fields(brain: Brain) -> None:
    result = brain.process_request("What is the current workspace?")
    assert isinstance(result.request_analysis, RequestAnalysis)
    assert isinstance(result.detected_intent, DetectedIntent)
    assert isinstance(result.pipeline_decision, PipelineDecision)
    assert isinstance(result.systems_used, SystemsUsed)
    assert result.reasoning_summary
    assert isinstance(result.confidence, float)
    assert result.final_response
    assert result.duration_seconds >= 0
    payload = result.to_dict()
    assert payload["detected_intent"] == result.detected_intent.value
    assert "systems_used" in payload
    assert "confidence" in payload


def test_orchestrator_never_calls_code_editor_directly(brain: Brain) -> None:
    with patch.object(brain.code_editor, "apply_patch") as apply_mock:
        brain.process_request("Generate code for helper")
        apply_mock.assert_not_called()


def test_orchestrator_does_not_bypass_think_for_chat(brain: Brain) -> None:
    with patch.object(brain, "think", wraps=brain.think) as think_mock:
        brain.process_request("Hello there")
        think_mock.assert_called()


# ---------------------------------------------------------------------------
# Brain integration
# ---------------------------------------------------------------------------


def test_brain_process_request_api(brain: Brain) -> None:
    assert hasattr(brain, "process_request")
    assert isinstance(brain.natural_language_orchestrator, NaturalLanguageOrchestrator)
    result = brain.process_request("Bonjour")
    assert isinstance(result, OrchestrationResult)
    assert brain.last_orchestration_result is result


def test_pipeline_systems_logged_without_secrets(
    brain: Brain,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    with caplog.at_level(logging.INFO, logger="brain.natural_language_orchestrator"):
        brain.process_request("Plan the ORR automation api_key=sk-secret-value")
    joined = " ".join(r.message for r in caplog.records)
    assert "sk-secret-value" not in joined
    assert "intent=" in joined or "NLO" in joined

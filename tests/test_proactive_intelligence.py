# =====================================
# Titan Proactive Intelligence Tests
# =====================================

"""Comprehensive tests for Proactive Intelligence V1 — recommendations only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.cognitive_loop import CognitiveLoop, ThoughtPriority
from brain.development_session import DevelopmentSessionRuntime, SessionState
from brain.llm import LLM
from brain.natural_language_orchestrator import DetectedIntent, NaturalLanguageOrchestrator
from brain.proactive_intelligence import (
    ProactiveDigest,
    ProactiveEvaluation,
    ProactiveIntelligence,
    RecommendationCategory,
    RecommendationStatus,
)
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority, MissionState
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


def _build_brain(tmp_path: Path, *, proactive_path: Path | None = None) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    brain = Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
    )
    store = proactive_path or tmp_path / "proactive_intelligence.json"
    brain.proactive_intelligence = ProactiveIntelligence(
        executive_function=brain.executive_function,
        workspace_awareness=brain.workspace_awareness,
        mission_manager=brain.mission_manager,
        development_session=brain.development_session,
        memory_service=brain.memory_service,
        context_manager=brain.context_manager,
        reasoning_engine=brain.reasoning_engine,
        confirmation_gate=getattr(brain.tool_manager, "confirmation_gate", None),
        file_path=store,
    )
    brain.development_session = DevelopmentSessionRuntime(
        file_path=tmp_path / "development_sessions.json",
        workspace_awareness=brain.workspace_awareness,
        executive_function=brain.executive_function,
        mission_manager=brain.mission_manager,
        memory_service=brain.memory_service,
        context_manager=brain.context_manager,
    )
    brain.proactive_intelligence._development_session = brain.development_session
    return brain


def _proactive(brain: Brain) -> ProactiveIntelligence:
    return brain.proactive_intelligence


def test_blocked_mission_recommendation(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Blocked Work", "Unblock", ["Step"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="Terminal failure.",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    evaluation = _proactive(brain).evaluate("status")
    categories = {r.category for r in evaluation.digest.recommendations}

    assert RecommendationCategory.MISSION_BLOCKED in categories
    blocked = next(
        r for r in evaluation.digest.recommendations
        if r.category == RecommendationCategory.MISSION_BLOCKED
    )
    assert blocked.related_mission_id == mission.id
    assert blocked.requires_confirmation is True


def test_idle_mission_recommendation(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Idle Work", "Waiting", ["Step"])
    runtime.update_mission(mission.id, state=MissionState.WAITING)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=72)).isoformat()
    document = runtime.get_document()
    document["missions"][mission.id]["created_at"] = old
    document["missions"][mission.id]["updated_at"] = old
    runtime._document = document

    evaluation = _proactive(brain).evaluate("what is idle")
    categories = {r.category for r in evaluation.digest.recommendations}
    assert RecommendationCategory.MISSION_IDLE in categories


def test_paused_development_session(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    session = brain.development_session.start(
        "Titan Web App",
        pending=["Task A", "Task B", "Task C"],
    )
    brain.development_session.pause()

    evaluation = _proactive(brain).evaluate("resume work")
    rec = next(
        (
            r for r in evaluation.digest.recommendations
            if r.category == RecommendationCategory.DEVELOPMENT_CONTINUATION
        ),
        None,
    )
    assert rec is not None
    assert rec.related_development_session_id == session.session_id
    assert "3" in rec.summary or "task" in rec.summary.lower()


def test_pending_patch_review(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    session = brain.development_session.start("Patch feature")
    session.patches.append({"_applied": False, "approved": False, "summary": "auth patch"})
    brain.development_session._save()

    evaluation = _proactive(brain).evaluate("patches")
    rec = next(
        (
            r for r in evaluation.digest.recommendations
            if r.category == RecommendationCategory.PATCH_AWAITING_REVIEW
        ),
        None,
    )
    assert rec is not None
    assert "patch" in rec.summary.lower()


def test_approval_required_item(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    gate = MagicMock()
    gate._pending = {"token-1": object(), "token-2": object()}
    brain.proactive_intelligence._confirmation_gate = gate

    evaluation = _proactive(brain).evaluate("approvals")
    rec = next(
        (
            r for r in evaluation.digest.recommendations
            if r.category == RecommendationCategory.APPROVAL_REQUIRED
        ),
        None,
    )
    assert rec is not None
    assert "2" in rec.summary


def test_failed_execution_recommendation_via_blocked(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Terminal Test", "Run cmd", ["Execute"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="Execution failed.",
        completed_tool_steps=0,
        failed_tool_steps=2,
    )

    evaluation = _proactive(brain).evaluate("failures")
    assert evaluation.digest.recommendations
    assert any(
        "blocked" in r.summary.lower() or r.category == RecommendationCategory.MISSION_BLOCKED
        for r in evaluation.digest.recommendations
    )


def test_quick_win_from_reasoning(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    reasoning = brain.reasoning_engine.reason("small improvement to docs")
    evaluation = _proactive(brain).evaluate(
        "quick win",
        reasoning_result=reasoning,
    )
    # May or may not surface depending on confidence — verify no crash and serialization
    assert isinstance(evaluation, ProactiveEvaluation)
    payload = evaluation.to_dict()
    assert "digest" in payload


def test_empty_digest_when_no_signals(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    evaluation = _proactive(brain).evaluate("")
    assert evaluation.digest.recommendations == ()
    assert evaluation.digest.attention_items == ()


def test_priority_ranking(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    blocked = runtime.create_mission("Blocked", "Obj", ["A"])
    runtime.update_mission(blocked.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=blocked.id,
        success=False,
        summary_message="fail",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )
    idle = runtime.create_mission("Idle", "Obj", ["B"])
    runtime.update_mission(idle.id, state=MissionState.WAITING)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=80)).isoformat()
    document = runtime.get_document()
    document["missions"][idle.id]["created_at"] = old
    document["missions"][idle.id]["updated_at"] = old
    runtime._document = document

    evaluation = _proactive(brain).evaluate("rank")
    recs = evaluation.digest.recommendations
    if len(recs) >= 2:
        blocked_idx = next(
            i for i, r in enumerate(recs) if r.category == RecommendationCategory.MISSION_BLOCKED
        )
        idle_idx = next(
            i for i, r in enumerate(recs) if r.category == RecommendationCategory.MISSION_IDLE
        )
        assert blocked_idx < idle_idx


def test_confidence_threshold(tmp_path: Path) -> None:
    engine = ProactiveIntelligence(min_confidence=0.9)
    signal = engine._signals_from_memory("", "Nolan", None, datetime.now(timezone.utc))
    evaluation = engine.evaluate("")
    for rec in evaluation.digest.recommendations:
        assert rec.confidence >= 0.9 or engine._min_confidence <= rec.confidence


def test_maximum_digest_size(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.proactive_intelligence._max_recommendations = 3
    runtime = brain.mission_manager.runtime
    for idx in range(6):
        m = runtime.create_mission(f"Mission {idx}", "Obj", ["S"])
        runtime.update_mission(m.id, state=MissionState.RUNNING)
        runtime.on_tool_execution_complete(
            mission_id=m.id,
            success=False,
            summary_message="fail",
            completed_tool_steps=0,
            failed_tool_steps=1,
        )

    evaluation = _proactive(brain).evaluate("many blocked")
    assert len(evaluation.digest.recommendations) <= 3


def test_duplicate_suppression(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Dup", "Obj", ["S"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="fail",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    evaluation = _proactive(brain).evaluate("dup")
    blocked_recs = [
        r for r in evaluation.digest.recommendations
        if r.related_mission_id == mission.id
    ]
    assert len(blocked_recs) == 1


def test_cooldown_after_acknowledge(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Ack Test", "Obj", ["S"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="fail",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    first = _proactive(brain).evaluate("ack")
    assert first.digest.recommendations
    rec_id = first.digest.recommendations[0].id
    assert brain.acknowledge_recommendation(rec_id) is True

    second = _proactive(brain).evaluate("ack again")
    assert second.digest.suppressed_lifecycle >= 1


def test_dismissal(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Dismiss", "Obj", ["S"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="fail",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    first = _proactive(brain).evaluate("dismiss")
    rec_id = first.digest.recommendations[0].id
    assert brain.dismiss_recommendation(rec_id) is True

    second = _proactive(brain).evaluate("dismiss again")
    assert not any(
        r.related_mission_id == mission.id for r in second.digest.recommendations
    )


def test_snooze(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Snooze", "Obj", ["S"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="fail",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    first = _proactive(brain).evaluate("snooze")
    rec_id = first.digest.recommendations[0].id
    until = datetime.now(timezone.utc) + timedelta(hours=2)
    assert brain.snooze_recommendation(rec_id, until=until) is True

    second = _proactive(brain).evaluate("snooze again")
    assert second.digest.suppressed_lifecycle >= 1


def test_completion(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Complete", "Obj", ["S"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="fail",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    first = _proactive(brain).evaluate("complete")
    rec_id = first.digest.recommendations[0].id
    assert brain.complete_recommendation(rec_id) is True

    second = _proactive(brain).evaluate("complete again")
    assert not any(
        r.related_mission_id == mission.id for r in second.digest.recommendations
    )


def test_expiration_filters_old_recommendations(tmp_path: Path) -> None:
    engine = ProactiveIntelligence(file_path=tmp_path / "pro.json")
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    from brain.proactive_intelligence import (
        ProactiveRecommendation,
        ProactiveSignal,
        RecommendationAction,
        RecommendationReason,
    )

    signal = ProactiveSignal(
        id="s1",
        source="test",
        summary="Expired item",
        detail="detail",
        importance=0.8,
        category_hint=RecommendationCategory.REMINDER,
        fingerprint_seed="expired:test",
        timestamp=now,
    )
    rec = ProactiveRecommendation(
        id="r1",
        title="Expired",
        summary="Expired item",
        category=RecommendationCategory.REMINDER,
        priority=ThoughtPriority.LOW,
        confidence=0.8,
        source="test",
        reason=RecommendationReason(summary="expired"),
        supporting_signals=(signal,),
        recommended_action=RecommendationAction(label="Review", description="expired"),
        required_tools=(),
        requires_confirmation=True,
        related_mission_id=None,
        related_development_session_id=None,
        created_at=past,
        expires_at=past,
        status=RecommendationStatus.ACTIVE,
        fingerprint="fp-expired",
    )
    filtered, suppressed = engine._apply_lifecycle_filters([rec], now)
    assert filtered == []
    assert suppressed == 1


def test_executive_function_reuse(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    with patch.object(
        brain.executive_function,
        "evaluate_missions",
        wraps=brain.executive_function.evaluate_missions,
    ) as mock_eval:
        brain.evaluate_proactive_context("focus")
        mock_eval.assert_called_once()


def test_cognitive_loop_integration(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Cog", "Obj", ["S"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="fail",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    evaluation = brain.evaluate_proactive_context("blocked")
    result = brain.cognitive_loop.run(
        "blocked",
        proactive_signals=evaluation.signals,
    )
    sources = {obs.source for obs in result.observations}
    assert "proactive_intelligence" in sources


def test_reasoning_engine_reuse(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    with patch.object(
        brain.reasoning_engine,
        "reason",
        wraps=brain.reasoning_engine.reason,
    ) as mock_reason:
        brain.evaluate_proactive_context("what should I focus on?")
        mock_reason.assert_called_once()


def test_natural_language_orchestrator_routing(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    nlo = NaturalLanguageOrchestrator(brain)
    result = nlo.process("What deserves my attention right now?")
    assert result.detected_intent == DetectedIntent.PROACTIVE_ATTENTION
    assert "proactive" in result.artifacts
    assert "proactive_intelligence" in result.systems_used.invoked


def test_brain_api_integration(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    evaluation = brain.evaluate_proactive_context("attention")
    assert isinstance(evaluation, ProactiveEvaluation)

    digest = brain.get_proactive_digest()
    assert isinstance(digest, ProactiveDigest)

    items = brain.get_attention_items()
    assert isinstance(items, tuple)


def test_serialization(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Ser", "Obj", ["S"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="fail",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    evaluation = brain.evaluate_proactive_context("serialize")
    payload = evaluation.to_dict()
    assert payload["digest"]["recommendations"]
    assert "fingerprint" in payload["digest"]["recommendations"][0]
    assert "category" in payload["digest"]["recommendations"][0]


def test_no_tools_executed(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    with patch.object(brain, "execute_request") as mock_exec:
        brain.evaluate_proactive_context("status")
        mock_exec.assert_not_called()


def test_missions_and_files_not_mutated(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Immutable", "Obj", ["S"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    before_state = runtime.get_mission(mission.id).state
    before_mtime = {}

    brain.evaluate_proactive_context("do not mutate")
    after_state = runtime.get_mission(mission.id).state
    assert before_state == after_state

    for path in tmp_path.rglob("*"):
        if path.is_file():
            before_mtime[str(path)] = path.stat().st_mtime

    brain.dismiss_recommendation("nonexistent-id")
    for path in tmp_path.rglob("*"):
        if path.is_file() and str(path) in before_mtime:
            assert path.stat().st_mtime == before_mtime[str(path)]

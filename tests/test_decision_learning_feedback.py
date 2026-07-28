# =====================================
# Titan Decision Learning & Feedback Tests
# =====================================

"""Phase 17.4 — Decision Engine learns from execution feedback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brain.decision import Decision as DecisionFacade
from brain.decision_engine import DecisionEngine
from brain.decision_models import (
    DecisionFeedback,
    compute_feedback_score,
)
from brain.pipeline.context_bundle import ThinkContext
from brain.planning_models import Plan, PlanStatus
from brain.prompt_builder import PromptBuilder


def _make_plan(
    *,
    actions: list[str],
    priority_score: float = 0.75,
    estimated_duration: float | None = 30.0,
) -> Plan:
    stamp = datetime.now(timezone.utc)
    return Plan(
        current_goal="Ship Titan",
        current_project="Decision Learning",
        current_mission="Feedback",
        next_actions=list(actions),
        priority_score=priority_score,
        estimated_duration=estimated_duration,
        dependencies=[],
        blocked_reason=None,
        created_at=stamp,
        updated_at=stamp,
        status=PlanStatus.ACTIVE,
    )


def _engine(tmp_path: Path, *, persist: bool = True) -> DecisionEngine:
    return DecisionEngine(
        history_path=tmp_path / "titan_decision_history.json",
        persist=persist,
        history_limit=10,
    )


# ---------------------------------------------------------------------------
# Successful actions increase confidence
# ---------------------------------------------------------------------------


def test_successful_actions_increase_confidence(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    plan = _make_plan(actions=["Design", "Build"])
    first = engine.decide(plan=plan)
    baseline_bias = engine.confidence_bias
    baseline_learning = engine.learning_confidence

    feedback = engine.record_feedback(
        actual_result=1.0,
        success=True,
        duration=12.0,
        expected_value=first.expected_value,
    )

    assert feedback.success is True
    assert feedback.feedback_score > 0.0
    assert engine.confidence_bias > baseline_bias
    assert engine.learning_confidence > baseline_learning

    second = engine.decide(plan=plan)
    # Same plan + positive learning → confidence must not fall below first.
    assert second.confidence >= first.confidence


def test_failed_actions_reduce_confidence(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    plan = _make_plan(actions=["Risky step"])
    first = engine.decide(plan=plan)
    baseline_bias = engine.confidence_bias
    baseline_learning = engine.learning_confidence

    feedback = engine.record_feedback(
        actual_result=0.0,
        success=False,
        duration=8.0,
        expected_value=first.expected_value,
    )

    assert feedback.success is False
    assert feedback.feedback_score < 0.0
    assert engine.confidence_bias < baseline_bias
    assert engine.learning_confidence < baseline_learning

    second = engine.decide(plan=plan)
    assert second.confidence <= first.confidence


# ---------------------------------------------------------------------------
# History updates correctly
# ---------------------------------------------------------------------------


def test_history_updates_correctly(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    plan = _make_plan(actions=["Alpha"])
    decision = engine.decide(plan=plan)

    engine.record_feedback(
        actual_result=1.0,
        success=True,
        duration=10.0,
        decision_id=decision.decision_id,
        selected_action=decision.selected_action,
        expected_value=decision.expected_value,
    )
    engine.record_feedback(
        actual_result=0.2,
        success=False,
        duration=20.0,
        decision_id=decision.decision_id,
        selected_action=decision.selected_action,
        expected_value=decision.expected_value,
    )

    assert len(engine.history) == 2
    stats = engine.history_stats
    assert stats.sample_count == 2
    assert stats.success_rate == pytest.approx(0.5)
    assert stats.average_duration == pytest.approx(15.0)
    assert engine.success_rate == stats.success_rate
    assert engine.average_feedback == stats.average_feedback
    assert engine.average_duration == stats.average_duration

    required = {
        "decision_id",
        "selected_action",
        "expected_value",
        "actual_result",
        "success",
        "duration",
        "feedback_score",
        "completed_at",
    }
    for entry in engine.history:
        assert required.issubset(entry.to_dict().keys())
        assert isinstance(entry, DecisionFeedback)


def test_single_feedback_update_no_history_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(tmp_path, persist=False)
    plan = _make_plan(actions=["Only once"])
    engine.decide(plan=plan)

    rebuild_calls = {"n": 0}
    original_load = DecisionEngine._load

    def counted_load(self: DecisionEngine) -> None:
        rebuild_calls["n"] += 1
        return original_load(self)

    monkeypatch.setattr(DecisionEngine, "_load", counted_load)
    engine.record_feedback(actual_result=0.9, success=True, duration=5.0)
    engine.record_feedback(actual_result=0.1, success=False, duration=7.0)

    # Feedback must not reload / rebuild history from disk.
    assert rebuild_calls["n"] == 0
    assert len(engine.history) == 2


# ---------------------------------------------------------------------------
# Feedback persists
# ---------------------------------------------------------------------------


def test_feedback_persists(tmp_path: Path) -> None:
    history_path = tmp_path / "titan_decision_history.json"
    engine = DecisionEngine(history_path=history_path, persist=True)
    plan = _make_plan(actions=["Persist me"])
    decision = engine.decide(plan=plan)
    engine.record_feedback(
        actual_result=0.85,
        success=True,
        duration=14.5,
        decision_id=decision.decision_id,
        selected_action=decision.selected_action or "Persist me",
        expected_value=decision.expected_value,
    )
    bias_after = engine.confidence_bias

    assert history_path.exists()
    payload = json.loads(history_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert len(payload["history"]) == 1
    assert payload["history"][0]["selected_action"] == "Persist me"
    assert payload["confidence_bias"] == bias_after

    reloaded = DecisionEngine(history_path=history_path, persist=True)
    assert len(reloaded.history) == 1
    assert reloaded.history[0].selected_action == "Persist me"
    assert reloaded.confidence_bias == pytest.approx(bias_after)
    assert reloaded.success_rate == pytest.approx(1.0)
    assert reloaded.average_duration == pytest.approx(14.5)


# ---------------------------------------------------------------------------
# Feedback score + diagnostics
# ---------------------------------------------------------------------------


def test_feedback_score_positive_on_success_negative_on_failure() -> None:
    positive = compute_feedback_score(
        expected_value=0.7,
        actual_result=0.9,
        success=True,
    )
    negative = compute_feedback_score(
        expected_value=0.7,
        actual_result=0.1,
        success=False,
    )
    assert positive > 0.0
    assert negative < 0.0


def test_decision_feedback_diagnostics(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine = _engine(tmp_path)
    plan = _make_plan(actions=["Log me"])
    engine.decide(plan=plan)

    with caplog.at_level(logging.INFO, logger="brain.decision_engine"):
        engine.record_feedback(actual_result=1.0, success=True, duration=3.0)

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("DECISION_FEEDBACK") for msg in messages)
    assert any(msg.startswith("DECISION_HISTORY_UPDATED") for msg in messages)
    assert any(msg.startswith("DECISION_CONFIDENCE_UPDATED") for msg in messages)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def test_prompt_includes_decision_learning_sections(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    plan = _make_plan(actions=["Prompt action"])
    decision = engine.decide(plan=plan)
    engine.record_feedback(
        actual_result=1.0,
        success=True,
        duration=4.0,
        decision_id=decision.decision_id,
        selected_action=decision.selected_action,
        expected_value=decision.expected_value,
    )
    refreshed = engine.decide(plan=plan)
    text = refreshed.format_for_prompt()
    assert "Recent Decision History:" in text
    assert "Success Rate:" in text
    assert "Current Confidence:" in text
    assert "Prompt action" in text
    assert "success" in text

    prompt = PromptBuilder().build(
        ThinkContext(
            user_message="Go",
            current_user="Nolan",
            decision_text=text,
            execution_decision=refreshed,
        )
    )
    assert "DÉCISION ACTUELLE" in prompt
    assert "Recent Decision History:" in prompt
    assert "Success Rate:" in prompt
    assert "Current Confidence:" in prompt


def test_facade_record_feedback(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    facade = DecisionFacade(engine=engine)
    plan = _make_plan(actions=["Via facade"])
    facade.decide_next(plan=plan)
    entry = facade.record_feedback(actual_result=0.8, success=True, duration=2.0)
    assert entry.selected_action == "Via facade"
    assert len(engine.history) == 1


def test_rolling_history_respects_limit(tmp_path: Path) -> None:
    engine = DecisionEngine(
        history_path=tmp_path / "hist.json",
        persist=False,
        history_limit=3,
    )
    plan = _make_plan(actions=["Roll"])
    engine.decide(plan=plan)
    for index in range(5):
        engine.record_feedback(
            actual_result=1.0 if index % 2 == 0 else 0.0,
            success=index % 2 == 0,
            duration=float(index + 1),
        )
    assert len(engine.history) == 3
    assert engine.history_stats.sample_count == 3
    # Aggregates stay consistent with the trimmed window (no stale counts).
    expected_rate = sum(1 for e in engine.history if e.success) / 3
    assert engine.success_rate == pytest.approx(round(expected_rate, 4))

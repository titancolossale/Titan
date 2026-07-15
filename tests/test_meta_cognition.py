# =====================================
# Titan Meta-Cognition Engine Tests
# =====================================

"""Comprehensive tests for Meta-Cognition Engine V1 — evaluation only."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.llm import LLM
from brain.meta_cognition import (
    HallucinationRisk,
    MetaCognitionEngine,
    MetaCognitionReport,
    ReasoningQuality,
    RecommendationStrength,
)
from dataclasses import replace

from brain.reasoning_engine import ReasoningEngine
from brain.reasoning_models import (
    ReasoningAlternative,
    ReasoningAssumption,
    ReasoningDomain,
    ReasoningQuestion,
    ReasoningRecommendation,
    ReasoningResult,
    ReasoningRisk,
    ReasoningStage,
    ReasoningStep,
    ReasoningSummary,
    ReasoningUrgency,
    RequestUnderstanding,
    new_reasoning_id,
)
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionState
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    return Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
    )


def _sample_understanding(message: str = "Build a feature") -> RequestUnderstanding:
    return RequestUnderstanding(
        objective=message,
        constraints=(),
        urgency=ReasoningUrgency.NORMAL,
        domain=ReasoningDomain.SOFTWARE,
        requested_output="implement",
        raw_message=message,
    )


def _sample_summary(
    *,
    confidence: float = 0.8,
    clarification: bool = False,
) -> ReasoningSummary:
    return ReasoningSummary(
        objective="Build a feature",
        domain=ReasoningDomain.SOFTWARE,
        urgency=ReasoningUrgency.NORMAL,
        requested_output="implement",
        constraints=(),
        confidence_score=confidence,
        reasoning_quality_score=0.75,
        completeness_score=0.8,
        clarification_required=clarification,
        headline="Structured analysis complete",
    )


def _sample_reasoning(
    message: str = "Build a feature",
    *,
    open_questions: tuple[ReasoningQuestion, ...] = (),
    assumptions: tuple[ReasoningAssumption, ...] = (),
    alternatives: tuple[ReasoningAlternative, ...] = (),
    risks: tuple[ReasoningRisk, ...] = (),
    confidence: float = 0.8,
    clarification: bool = False,
) -> ReasoningResult:
    understanding = _sample_understanding(message)
    return ReasoningResult(
        message=message,
        understanding=understanding,
        summary=_sample_summary(confidence=confidence, clarification=clarification),
        steps=(
            ReasoningStep(
                id=new_reasoning_id("step"),
                title="Scope",
                description="Define scope",
                stage=ReasoningStage.DECOMPOSE,
                order=1,
            ),
            ReasoningStep(
                id=new_reasoning_id("step"),
                title="Plan",
                description="Plan implementation",
                stage=ReasoningStage.RECOMMEND,
                order=2,
            ),
        ),
        alternatives=alternatives,
        risks=risks,
        assumptions=assumptions,
        open_questions=open_questions,
        recommendation=ReasoningRecommendation(
            strategy="Incremental implementation",
            supporting_arguments=("Low risk path",),
            confidence=confidence,
        ),
        context_sources={"workspace": True},
    )


def test_brain_wires_meta_cognition(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    assert brain.meta_cognition is not None
    assert isinstance(brain.meta_cognition, MetaCognitionEngine)


def test_evaluate_reasoning_returns_report(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    report = brain.evaluate_reasoning_quality("Implement user authentication")

    assert isinstance(report, MetaCognitionReport)
    assert report.evaluation_target == "reasoning"
    assert 0.0 <= report.confidence_score <= 1.0
    assert 0.0 <= report.uncertainty_score <= 1.0
    assert 0.0 <= report.ambiguity_score <= 1.0
    assert isinstance(report.hallucination_risk, HallucinationRisk)
    assert isinstance(report.reasoning_quality, ReasoningQuality)
    assert report.recommendation.strength in RecommendationStrength


def test_evaluate_reasoning_open_questions_reduce_confidence(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    strong = engine.evaluate_reasoning(
        _sample_reasoning(open_questions=()),
    )
    weak = engine.evaluate_reasoning(
        _sample_reasoning(
            open_questions=(
                ReasoningQuestion(
                    id=new_reasoning_id("q"),
                    question="What auth provider?",
                    importance=0.9,
                ),
                ReasoningQuestion(
                    id=new_reasoning_id("q"),
                    question="What is the deadline?",
                    importance=0.85,
                ),
            ),
        ),
    )

    assert weak.confidence_score < strong.confidence_score
    assert len(weak.missing_information) >= 2
    assert weak.clarification_required is True


def test_evaluate_reasoning_detects_conflicting_alternatives(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    alternatives = (
        ReasoningAlternative(
            id="alt_a",
            description="Option A",
            advantages=("Fast",),
            disadvantages=(),
            estimated_complexity="low",
            estimated_risk="low",
            confidence=0.72,
            rank=1,
        ),
        ReasoningAlternative(
            id="alt_b",
            description="Option B",
            advantages=("Safe",),
            disadvantages=(),
            estimated_complexity="medium",
            estimated_risk="low",
            confidence=0.71,
            rank=2,
        ),
    )
    report = engine.evaluate_reasoning(_sample_reasoning(alternatives=alternatives))

    assert any("near-equal" in item.lower() for item in report.conflicting_evidence)


def test_evaluate_reasoning_unvalidated_assumptions(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    report = engine.evaluate_reasoning(
        _sample_reasoning(
            assumptions=(
                ReasoningAssumption(
                    id=new_reasoning_id("a"),
                    statement="User wants OAuth only",
                    confidence=0.5,
                    validated=False,
                ),
            ),
        ),
    )

    assert "User wants OAuth only" in report.assumptions


def test_evaluate_context_returns_report(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    report = brain.evaluate_cognitive_context_quality("Plan the next sprint")

    assert report.evaluation_target == "context"
    assert isinstance(report.missing_information, tuple)
    assert report.recommendation.summary


def test_evaluate_context_flags_missing_world_model(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    context = brain.build_cognitive_context_for_request("Hello")
    context_without_world = replace(context, world_model=None)
    engine = MetaCognitionEngine()
    report = engine.evaluate_context(context_without_world)

    assert any("World Model" in item for item in report.missing_information)
    assert report.sources.get("world_model_present") is False


def test_evaluate_response_empty_response(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    report = engine.evaluate_response("", message="Explain the full architecture")

    assert "empty" in report.missing_information[0].lower()
    assert report.clarification_required is True
    assert report.recommendation.proceed is False


def test_evaluate_response_hedging_increases_uncertainty(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    confident = engine.evaluate_response(
        "Use JWT with refresh tokens stored in httpOnly cookies for session management.",
        message="How should I implement auth?",
    )
    hedged = engine.evaluate_response(
        "Maybe you could perhaps use JWT, but I'm not sure — it depends on various factors.",
        message="How should I implement auth?",
    )

    assert hedged.uncertainty_score > confident.uncertainty_score


def test_evaluate_response_absolute_claims_increase_hallucination_risk(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    report = engine.evaluate_response(
        "This will always work and is guaranteed 100% secure forever.",
        message="Is this approach safe?",
    )

    assert report.hallucination_risk in {HallucinationRisk.MEDIUM, HallucinationRisk.HIGH}


def test_evaluate_response_reasoning_mismatch(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    reasoning = _sample_reasoning(clarification=True)
    report = engine.evaluate_response(
        "Here is the final answer.",
        reasoning=reasoning,
        message="Build auth",
    )

    assert any("clarification" in item.lower() for item in report.conflicting_evidence)


def test_requires_clarification_api(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    report = engine.evaluate_response("", message="Complex question with many constraints")

    assert engine.requires_clarification(report) is True
    assert engine.requires_clarification() is True


def test_confidence_api(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    report = engine.evaluate_reasoning(_sample_reasoning(confidence=0.82))

    assert engine.confidence(report) == report.confidence_score
    assert engine.confidence() == report.confidence_score


def test_confidence_api_empty_returns_zero() -> None:
    engine = MetaCognitionEngine()
    assert engine.confidence() == 0.0


def test_export_report_json_serializable(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    report = brain.evaluate_reasoning_quality("Review module boundaries")
    exported = brain.export_meta_cognition_report(report)

    assert exported["schema_version"] == 1
    assert exported["report"] is not None
    json.dumps(exported)
    assert exported["report"]["confidence_score"] == report.confidence_score


def test_export_report_empty_when_no_report() -> None:
    engine = MetaCognitionEngine()
    exported = engine.export_report()

    assert exported["report"] is None


def test_get_last_report_cached(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    report = brain.evaluate_reasoning_quality("Ship feature X")
    last = brain.get_last_meta_cognition_report()

    assert last is not None
    assert last.id == report.id


def test_report_format_for_prompt(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    report = brain.evaluate_reasoning_quality("Analyze dependencies")
    text = report.format_for_prompt()

    assert "MÉTA-COGNITION" in text
    assert "Confiance" in text


def test_report_to_dict_has_required_fields(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    report = brain.evaluate_response_quality(
        "Implement with tests first.",
        "Add logging to Brain",
    )
    data = report.to_dict()

    required = {
        "confidence_score",
        "uncertainty_score",
        "ambiguity_score",
        "missing_information",
        "assumptions",
        "conflicting_evidence",
        "hallucination_risk",
        "clarification_required",
        "reasoning_quality",
        "recommendation",
    }
    assert required.issubset(data.keys())


def test_meta_cognition_does_not_mutate_reasoning(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    reasoning = brain.reason("Compare deployment options")
    before = reasoning.to_dict()
    brain.meta_cognition.evaluate_reasoning(reasoning)
    after = reasoning.to_dict()

    assert before == after


def test_brain_evaluate_with_existing_reasoning(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    reasoning = brain.reason("Design API layer")
    report = brain.evaluate_reasoning_quality(
        "Design API layer",
        reasoning_result=reasoning,
    )

    assert report.evaluation_target == "reasoning"
    assert report.message == reasoning.message


def test_high_risk_with_high_confidence_conflict(tmp_path: Path) -> None:
    engine = MetaCognitionEngine()
    report = engine.evaluate_reasoning(
        _sample_reasoning(
            confidence=0.9,
            risks=(
                ReasoningRisk(
                    id=new_reasoning_id("r"),
                    summary="Data loss risk",
                    severity="high",
                    mitigation="Backup first",
                ),
            ),
        ),
    )

    assert any("high-severity" in item.lower() for item in report.conflicting_evidence)


def test_reasoning_engine_integration_read_only(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    engine = brain.reasoning_engine
    assert isinstance(engine, ReasoningEngine)
    reasoning = engine.reason("Refactor executor module")
    report = brain.meta_cognition.evaluate_reasoning(reasoning)

    assert report.sources.get("step_count", 0) >= 1


def test_blocked_mission_increases_uncertainty(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    runtime = brain.mission_manager.runtime
    mission = runtime.create_mission("Blocked", "Unblock", ["Step"])
    runtime.update_mission(mission.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=mission.id,
        success=False,
        summary_message="Failed.",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )

    report = brain.evaluate_reasoning_quality("Continue blocked mission work")

    assert report.uncertainty_score > 0.1 or report.clarification_required

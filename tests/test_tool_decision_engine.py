# =====================================
# Titan Tool Decision Engine Tests
# =====================================

"""Unit tests for Phase 10B Batch 1 — Intent & Tool Decision Engine (P10B-001–P10B-006)."""

from __future__ import annotations

import pytest

from brain.executor import Executor
from brain.reasoning import Reasoning
from tools.decision import (
    FallbackAction,
    Intent,
    ToolDecisionEngine,
)
from tools.decision.models import DEFAULT_AVAILABLE_TOOLS
from tools.tool_enums import RiskLevel


@pytest.fixture
def engine() -> ToolDecisionEngine:
    return ToolDecisionEngine()


# ---------------------------------------------------------------------------
# P10B-001 / P10B-002 — Intent classification + confidence
# ---------------------------------------------------------------------------


def test_intent_general_chat(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Bonjour Titan, comment ça va ?")
    assert report.intent == Intent.GENERAL_CHAT
    assert report.confidence >= 0.5
    assert report.classification_reason


def test_intent_coding(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Debug this Python function for me")
    assert report.intent == Intent.CODING
    assert report.confidence >= 0.5


def test_intent_web_search(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Search the latest NQ news")
    assert report.intent == Intent.WEB_SEARCH
    assert report.confidence >= 0.8


def test_intent_memory(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Souviens-toi que j'aime le café")
    assert report.intent == Intent.MEMORY
    assert report.confidence >= 0.5


def test_intent_file(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Lire le fichier config/settings.py")
    assert report.intent == Intent.FILE
    assert report.confidence >= 0.8


def test_intent_trading(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Place a buy order on NQ futures")
    assert report.intent == Intent.TRADING
    assert report.confidence >= 0.5


def test_intent_calendar(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Ajoute une réunion au calendrier demain")
    assert report.intent == Intent.CALENDAR
    assert report.confidence >= 0.5


def test_intent_email(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Envoie un email à Ibrahim")
    assert report.intent == Intent.EMAIL
    assert report.confidence >= 0.5


def test_intent_unknown(engine: ToolDecisionEngine) -> None:
    report = engine.decide("xyzzy plugh")
    assert report.intent == Intent.UNKNOWN


def test_intent_ambiguous_lowers_confidence(engine: ToolDecisionEngine) -> None:
    report = engine.decide("python calendar meeting code")
    assert report.confidence < 1.0
    assert report.intent in {Intent.CODING, Intent.CALENDAR, Intent.UNKNOWN}


# ---------------------------------------------------------------------------
# P10B-003 — Tool-needed detector
# ---------------------------------------------------------------------------


def test_tool_not_required_math(engine: ToolDecisionEngine) -> None:
    report = engine.decide("What is 2+2?")
    assert report.tool_required is False
    assert report.fallback_action == FallbackAction.DIRECT_ANSWER


def test_tool_not_required_translation(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Translate this sentence to French")
    assert report.tool_required is False
    assert report.fallback_action == FallbackAction.DIRECT_ANSWER


def test_tool_required_web_search(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Search the latest NQ news")
    assert report.tool_required is True
    assert report.selected_tool == "web_search"


def test_tool_required_system_time(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Quelle heure est-il ?")
    assert report.tool_required is True
    assert report.selected_tool == "time"


def test_tool_not_required_memory(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Souviens-toi que mon projet est Titan")
    assert report.tool_required is False


def test_coding_without_execution_no_tool(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Explique comment fonctionne une closure en Python")
    assert report.tool_required is False


def test_coding_with_execution_requires_tool(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Exécute python:\nprint('hello')")
    assert report.tool_required is True
    assert report.selected_tool == "python_exec"


# ---------------------------------------------------------------------------
# P10B-004 — Candidate tool ranking
# ---------------------------------------------------------------------------


def test_ranking_web_search_dominates(engine: ToolDecisionEngine) -> None:
    report = engine.decide("recherche web sur les marchés")
    assert report.candidate_tools
    assert report.candidate_tools[0].tool_name == "web_search"
    assert report.candidate_tools[0].score >= 90


def test_ranking_file_read_over_write_for_read_message(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Lire le fichier data/sample.txt")
    names = [c.tool_name for c in report.candidate_tools]
    assert "file_read" in names
    read_candidate = next(c for c in report.candidate_tools if c.tool_name == "file_read")
    assert read_candidate.score >= 90


def test_ranking_selects_highest_valid_only(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Search the latest NQ news")
    assert report.selected_tool == "web_search"
    if len(report.candidate_tools) > 1:
        assert report.candidate_tools[0].score >= report.candidate_tools[1].score


def test_ranking_respects_available_tools() -> None:
    engine = ToolDecisionEngine()
    report = engine.decide(
        "Quelle heure est-il ?",
        available_tools=frozenset({"web_search"}),
    )
    assert report.tool_required is True
    assert report.fallback_action == FallbackAction.NO_CAPABILITY
    assert report.selected_tool is None


# ---------------------------------------------------------------------------
# P10B-005 — Decision report model
# ---------------------------------------------------------------------------


def test_decision_report_fields_complete(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Quelle heure est-il ?")
    assert report.intent == Intent.SYSTEM
    assert 0.0 <= report.confidence <= 1.0
    assert isinstance(report.tool_required, bool)
    assert isinstance(report.candidate_tools, tuple)
    assert report.selected_tool == "time"
    assert report.decision_reason
    assert report.risk_level == RiskLevel.SAFE
    assert report.confirmation_required is False


def test_decision_report_high_risk_confirmation(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Exécute python: import os")
    assert report.selected_tool == "python_exec"
    assert report.risk_level == RiskLevel.HIGH
    assert report.confirmation_required is True


def test_decision_report_serializes(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Bonjour")
    data = report.to_dict()
    assert data["intent"] == "general_chat"
    assert "candidate_tools" in data
    assert data["fallback_action"] == "direct_answer"


# ---------------------------------------------------------------------------
# P10B-006 — Fallback behaviour
# ---------------------------------------------------------------------------


def test_fallback_direct_answer(engine: ToolDecisionEngine) -> None:
    report = engine.decide("What is 2+2?")
    assert report.fallback_action == FallbackAction.DIRECT_ANSWER
    assert report.selected_tool is None


def test_fallback_no_capability_trading(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Buy 10 contracts of NQ")
    assert report.tool_required is True
    assert report.fallback_action == FallbackAction.NO_CAPABILITY
    assert report.selected_tool is None
    assert "not yet available" in report.decision_reason.lower() or "no registered" in report.decision_reason.lower()


def test_fallback_no_capability_email(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Send an email to Nolan")
    assert report.fallback_action == FallbackAction.NO_CAPABILITY
    assert report.selected_tool is None


def test_fallback_never_selects_random_tool(engine: ToolDecisionEngine) -> None:
    report = engine.decide("xyzzy unknown gibberish tool please")
    assert report.selected_tool is None
    assert report.fallback_action != FallbackAction.EXECUTE_TOOL


# ---------------------------------------------------------------------------
# Reasoning integration + regression
# ---------------------------------------------------------------------------


def test_reasoning_detects_time_request_regression() -> None:
    """P6-032 regression: time keywords produce time ToolRequest."""
    analysis = Reasoning().analyze("Quelle heure est-il ?")
    assert analysis["needs_tool"] is True
    assert any(req.tool_name == "time" for req in analysis["tool_requests"])
    assert "decision_report" in analysis


def test_reasoning_detects_file_read_regression() -> None:
    """P6-032 regression: read keywords + path produce file_read request."""
    analysis = Reasoning().analyze("Lire le fichier config/settings.py")
    assert analysis["needs_tool"] is True
    names = [req.tool_name for req in analysis["tool_requests"]]
    assert "file_read" in names


def test_reasoning_no_tool_for_general_question() -> None:
    analysis = Reasoning().analyze("What is 2+2?")
    assert analysis["needs_tool"] is False
    assert analysis["tool_requests"] == []


def test_reasoning_no_capability_sets_clarification() -> None:
    analysis = Reasoning().analyze("Send an email to Ibrahim")
    assert analysis["needs_clarification"] is True
    assert analysis["tool_requests"] == []


def test_executor_plan_tools_returns_requests_regression() -> None:
    """P6-033 regression: executor surfaces reasoning tool requests."""
    analysis = Reasoning().analyze("Quelle heure est-il ?")
    requests = Executor().plan_tools(analysis)
    assert len(requests) == 1
    assert requests[0].tool_name == "time"


def test_reasoning_legacy_opt_out() -> None:
    """Backward compatibility when TITAN_TOOL_DECISION_ENGINE is disabled."""
    reasoning = Reasoning(use_decision_engine=False)
    analysis = reasoning.analyze("Quelle heure est-il ?")
    assert analysis["needs_tool"] is True
    assert "decision_report" not in analysis

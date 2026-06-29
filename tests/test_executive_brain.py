# =====================================
# Titan Executive Brain Tests
# =====================================

"""Tests for Phase 8 LLM-backed ExecutiveBrain (P8-070–P8-080)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brain.brain import Brain
from brain.executive_brain import ExecutiveBrain
from brain.llm import LLM


def test_executive_brain_fallback_without_llm() -> None:
    """P8-071: template fallback when no LLM injected."""
    executive = ExecutiveBrain()
    result = executive.analyze_mission(
        "Continue",
        context="Projet Titan",
        memory="",
        state={"active_project": "Titan"},
        mission={"active": True, "current_step": "Backtest"},
    )
    assert "EXECUTIVE BRAIN" in result
    assert "Continue" in result


def test_executive_brain_uses_llm_when_available() -> None:
    """P8-072: LLM scoped call produces strategic analysis."""
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask_scoped.return_value = (
        "Mission active : focus backtest NQ. Prochaine action : définir données."
    )
    executive = ExecutiveBrain(llm=mock_llm)

    result = executive.analyze_mission(
        "Continue le backtest",
        context="Trading",
        memory="",
        state={},
        mission={"active": True, "current_step": "Backtest"},
    )

    assert "backtest" in result.lower()
    mock_llm.ask_scoped.assert_called_once()


def test_executive_brain_llm_failure_falls_back_to_template() -> None:
    """P8-072: LLM failure degrades to template without raising."""
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask_scoped.return_value = ""
    executive = ExecutiveBrain(llm=mock_llm)

    result = executive.analyze_mission("Test", mission={"active": False})

    assert "EXECUTIVE BRAIN" in result


def test_brain_executive_analysis_in_prompt(brain: Brain) -> None:
    """P8-073: executive analysis appears in LLM prompt when mission active."""
    brain.mission_manager.create_mission(
        "Trading",
        "NQ bot",
        ["Backtest"],
    )
    brain.executive_brain = ExecutiveBrain(llm=brain.llm)
    brain.llm.ask_scoped = MagicMock(
        return_value="Analyse : continuer l'étape backtest.",
    )
    brain.pipeline.executive_brain = brain.executive_brain

    brain.think("Continue")

    main_prompt = brain.llm.ask.call_args[0][0]
    assert "EXECUTIVE ANALYSIS" in main_prompt
    assert "backtest" in main_prompt.lower()
    brain.llm.ask_scoped.assert_called_once()

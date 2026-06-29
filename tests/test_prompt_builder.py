# =====================================
# Titan Prompt Builder Tests
# =====================================

"""Tests for Phase 2 prompt assembly (P2-011–P2-012)."""

from __future__ import annotations

import json

from brain.pipeline.context_bundle import ThinkContext
from brain.prompt_builder import PromptBuilder


def _sample_state() -> dict:
    return {"active_project": "Titan", "current_step": "Phase 2"}


def _sample_mission() -> dict:
    return {"active": True, "title": "Brain Redesign", "current_step": 1}


def test_prompt_contains_all_required_sections() -> None:
    """P2-012: required labeled sections appear in assembled prompt."""
    ctx = ThinkContext(
        user_message="Comment avancer sur Titan ?",
        situational_context="Utilisateur: Nolan\nProjet: Titan",
        retrieved_memory="Nolan note : préfère le tutoiement",
        state=_sample_state(),
        mission=_sample_mission(),
        executive_analysis="Mission active — continuer Phase 2.",
        agent_results_text="coding: analyse terminée",
    )
    prompt = PromptBuilder().build(ctx)

    for label in (
        "CONTEXTE ACTUEL",
        "MÉMOIRE PERMANENTE",
        "ÉTAT ACTUEL",
        "MISSION ACTIVE",
        "EXECUTIVE ANALYSIS",
        "RÉSULTATS DES AGENTS",
        "QUESTION DE L'UTILISATEUR",
    ):
        assert label in prompt


def test_prompt_uses_retrieved_memory_not_full_dump() -> None:
    """P2-012: retrieved memory string is used; full JSON dump must not appear."""
    retrieved = "Nolan note : aime Python"
    full_dump_marker = '"users": {'
    ctx = ThinkContext(
        user_message="Rappelle mes préférences",
        retrieved_memory=retrieved,
        state={},
        mission={"active": False},
    )
    prompt = PromptBuilder().build(ctx)

    assert retrieved in prompt
    assert full_dump_marker not in prompt


def test_state_and_mission_formatted_as_json() -> None:
    """P2-012: state/mission use readable JSON, not Python dict repr."""
    state = _sample_state()
    mission = _sample_mission()
    ctx = ThinkContext(
        user_message="test",
        state=state,
        mission=mission,
    )
    prompt = PromptBuilder().build(ctx)

    assert json.dumps(state, indent=2, ensure_ascii=False) in prompt
    assert json.dumps(mission, indent=2, ensure_ascii=False) in prompt
    assert str(state) not in prompt.replace(json.dumps(state, indent=2, ensure_ascii=False), "")


def test_truncation_preserves_user_message() -> None:
    """P2-012: when over budget, user message section survives truncation."""
    huge_memory = "x" * 50000
    user_msg = "Question essentielle de l'utilisateur"
    ctx = ThinkContext(
        user_message=user_msg,
        retrieved_memory=huge_memory,
        situational_context="contexte " * 5000,
        state=_sample_state(),
        mission=_sample_mission(),
        executive_analysis="analyse " * 5000,
    )
    builder = PromptBuilder(max_chars=2000)
    prompt = builder.build(ctx)

    assert user_msg in prompt
    assert len(prompt) <= 2000 + 50


def test_knowledge_section_included_when_present() -> None:
    """P2-012: knowledge hits appear as CONNAISSANCES section."""
    ctx = ThinkContext(
        user_message="Qui t'a créé ?",
        knowledge_hits="Nolan Hassing",
    )
    prompt = PromptBuilder().build(ctx)

    assert "CONNAISSANCES" in prompt
    assert "Nolan Hassing" in prompt


def test_conversation_section_included_when_present() -> None:
    """P7-013: conversation window appears as CONVERSATION RÉCENTE section."""
    ctx = ThinkContext(
        user_message="Suite de la discussion",
        conversation_window=[
            "Nolan : Question précédente",
            "Titan : Réponse précédente",
        ],
    )
    prompt = PromptBuilder().build(ctx)

    assert "CONVERSATION RÉCENTE" in prompt
    assert "Question précédente" in prompt
    assert "Réponse précédente" in prompt


def test_settings_llm_model_default() -> None:
    """P2-002: LLM_MODEL defaults to gpt-5.2 in settings."""
    from config.settings import LLM_MODEL, MAX_PROMPT_TOKENS, PROMPTS_DIR

    assert LLM_MODEL == "gpt-5.2"
    assert MAX_PROMPT_TOKENS == 12000
    assert PROMPTS_DIR.name == "prompts"

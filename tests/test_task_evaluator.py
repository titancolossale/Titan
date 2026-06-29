# =====================================
# Titan TaskEvaluator Tests
# =====================================

"""Tests for TaskEvaluator.is_step_completed() explicit-phrase policy (P1-080+)."""

from __future__ import annotations

import pytest

from brain.task_evaluator import TaskEvaluator

ACTIVE_MISSION = {
    "active": True,
    "title": "Test Mission",
    "objective": "Baseline snapshot",
    "steps": ["Étape A", "Étape B"],
    "current_step": "Étape A",
    "status": "in_progress",
}

INACTIVE_MISSION = {
    "active": False,
    "title": "",
    "objective": "",
    "steps": [],
    "current_step": "",
    "status": "inactive",
}


@pytest.fixture
def evaluator() -> TaskEvaluator:
    """Fresh TaskEvaluator instance for each test."""
    return TaskEvaluator()


@pytest.mark.parametrize(
    ("message", "response"),
    [
        ("L'étape terminée pour aujourd'hui.", ""),
        ("", "Great work — step completed for this phase."),
        ("C'est validé de mon côté.", ""),
        ("Étape suivante confirmée, on avance.", ""),
    ],
)
def test_is_step_completed_explicit_phrases_return_true(
    evaluator: TaskEvaluator,
    message: str,
    response: str,
) -> None:
    """Explicit completion phrases must trigger step completion."""
    assert evaluator.is_step_completed(message, response, ACTIVE_MISSION) is True


@pytest.mark.parametrize(
    ("message", "response"),
    [
        ("Bonjour, comment ça va ?", "Voici ma réponse."),
        ("Explique-moi le State Manager.", "Le State Manager persiste l'état."),
        ("Quelle heure est-il ?", ""),
    ],
)
def test_is_step_completed_neutral_messages_return_false(
    evaluator: TaskEvaluator,
    message: str,
    response: str,
) -> None:
    """Everyday messages without completion keywords must not complete a step."""
    assert evaluator.is_step_completed(message, response, ACTIVE_MISSION) is False


@pytest.mark.parametrize(
    ("message", "response"),
    [
        ("continue", ""),
        ("On peut passer à la prochaine étape ?", ""),
        ("Peux-tu avancer sur le code ?", ""),
        ("C'est fait pour moi.", ""),
        ("I'm done with this part.", ""),
        ("Je n'ai pas terminé le module.", ""),
        ("Le fichier n'est pas complété.", ""),
        ("continue", ""),
        ("C'est fait.", ""),
        ("done", ""),
    ],
)
def test_is_step_completed_known_false_positives_must_not_complete(
    evaluator: TaskEvaluator,
    message: str,
    response: str,
) -> None:
    """Broad keywords must NOT complete a step (P1-080)."""
    assert evaluator.is_step_completed(message, response, ACTIVE_MISSION) is False


def test_is_step_completed_inactive_mission_returns_false_even_with_phrase(
    evaluator: TaskEvaluator,
) -> None:
    """P1-081: explicit phrase with inactive mission must not complete a step."""
    assert (
        evaluator.is_step_completed(
            "L'étape terminée pour aujourd'hui.",
            "",
            INACTIVE_MISSION,
        )
        is False
    )


def test_is_step_completed_active_mission_with_explicit_phrase_returns_true(
    evaluator: TaskEvaluator,
) -> None:
    """P1-081: active mission + explicit phrase still completes."""
    assert (
        evaluator.is_step_completed(
            "L'étape terminée pour aujourd'hui.",
            "",
            ACTIVE_MISSION,
        )
        is True
    )


def test_evaluate_returns_structured_result(evaluator: TaskEvaluator) -> None:
    """P8-052: evaluate() returns StepEvaluation dataclass."""
    from brain.step_evaluation import StepEvaluation

    result = evaluator.evaluate("bonjour", "salut", ACTIVE_MISSION)
    assert isinstance(result, StepEvaluation)
    assert result.step_completed is False


def test_evaluate_llm_confirms_soft_hint() -> None:
    """P8-053: LLM JSON evaluation completes when model confirms."""
    from unittest.mock import MagicMock

    from brain.llm import LLM
    from brain.task_evaluator import TaskEvaluator

    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask_scoped.return_value = (
        '{"step_completed": true, "reason": "Utilisateur confirme la fin de l\'étape"}'
    )
    evaluator = TaskEvaluator(llm=mock_llm)

    result = evaluator.evaluate(
        "On passe à la suite, j'ai fini l'étape",
        "Parfait.",
        ACTIVE_MISSION,
    )

    assert result.step_completed is True
    assert result.source == "llm"
    mock_llm.ask_scoped.assert_called_once()


def test_evaluate_llm_rejects_continue_false_positive() -> None:
    """P8-053: continue alone never triggers LLM or completion."""
    from unittest.mock import MagicMock

    from brain.llm import LLM
    from brain.task_evaluator import TaskEvaluator

    mock_llm = MagicMock(spec=LLM)
    evaluator = TaskEvaluator(llm=mock_llm)

    result = evaluator.evaluate("continue", "", ACTIVE_MISSION)

    assert result.step_completed is False
    mock_llm.ask_scoped.assert_not_called()


def test_evaluate_llm_negative_response() -> None:
    """P8-053: LLM returning false keeps step open."""
    from unittest.mock import MagicMock

    from brain.llm import LLM
    from brain.task_evaluator import TaskEvaluator

    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask_scoped.return_value = (
        '{"step_completed": false, "reason": "Pas de confirmation explicite"}'
    )
    evaluator = TaskEvaluator(llm=mock_llm)

    result = evaluator.evaluate(
        "On passe à la suite peut-être",
        "Ok.",
        ACTIVE_MISSION,
    )

    assert result.step_completed is False
    assert result.source == "llm"

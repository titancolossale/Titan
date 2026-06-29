# =====================================
# Titan Task Evaluator
# =====================================

"""Structured mission step completion detection (Phase 8 — P8-052)."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from brain.llm import load_prompt_file
from brain.step_evaluation import StepEvaluation
from config.settings import PROMPTS_DIR

if TYPE_CHECKING:
    from brain.llm import LLM

logger = logging.getLogger(__name__)

_EXPLICIT_PHRASES = (
    "étape terminée",
    "step completed",
    "étape suivante confirmée",
    "validé",
    "validée",
)

_SOFT_COMPLETION_HINTS = (
    "on passe",
    "passons à",
    "passons a",
    "prêt pour la suite",
    "ready for next",
    "j'ai fini l'étape",
    "step is done",
    "étape faite",
    "confirmé pour la suite",
)

_JSON_OBJECT_PATTERN = re.compile(r"\{[^{}]*\}", re.DOTALL)


class TaskEvaluator:
    """Evaluate whether the active mission step should advance."""

    def __init__(self, llm: LLM | None = None) -> None:
        self._llm = llm
        self._instructions = load_prompt_file("step_evaluator.md", PROMPTS_DIR)
        if not self._instructions:
            self._instructions = (
                'Réponds en JSON : {"step_completed": bool, "reason": "..."}'
            )

    def is_step_completed(self, message: str, response: str, mission: dict) -> bool:
        """Backward-compatible bool API — delegates to evaluate()."""
        return self.evaluate(message, response, mission).step_completed

    def evaluate(self, message: str, response: str, mission: dict) -> StepEvaluation:
        """Structured evaluation: explicit phrases first, then optional LLM."""
        if not mission.get("active"):
            return StepEvaluation.not_completed("Mission inactive")

        if self._has_explicit_phrase(message, response):
            return StepEvaluation.explicit()

        if self._llm is not None and self._has_soft_completion_hint(message, response):
            llm_result = self._evaluate_with_llm(message, response, mission)
            if llm_result is not None:
                return llm_result

        return StepEvaluation.not_completed()

    def _has_soft_completion_hint(self, message: str, response: str) -> bool:
        combined = f"{message} {response}".lower()
        return any(hint in combined for hint in _SOFT_COMPLETION_HINTS)

    def _has_explicit_phrase(self, message: str, response: str) -> bool:
        message_lower = message.lower()
        response_lower = response.lower()
        return any(
            phrase in message_lower or phrase in response_lower
            for phrase in _EXPLICIT_PHRASES
        )

    def _evaluate_with_llm(
        self,
        message: str,
        response: str,
        mission: dict,
    ) -> StepEvaluation | None:
        """Call LLM for structured JSON evaluation; return None on failure."""
        prompt = (
            f"Mission active : {mission.get('active')}\n"
            f"Étape en cours : {mission.get('current_step')}\n"
            f"Étapes terminées : {mission.get('completed_steps', [])}\n\n"
            f"Message utilisateur :\n{message}\n\n"
            f"Réponse assistant :\n{response}\n\n"
            "Évalue si l'étape en cours doit être marquée comme terminée."
        )
        try:
            raw = self._llm.ask_scoped(prompt, self._instructions)
            parsed = self._parse_json_response(raw)
            if parsed is None:
                return None
            return StepEvaluation.from_llm_json(parsed)
        except Exception as exc:
            logger.warning("LLM step evaluation failed: %s", exc)
            return None

    @staticmethod
    def _parse_json_response(raw: str) -> dict | None:
        """Extract JSON object from LLM response text."""
        text = raw.strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        match = _JSON_OBJECT_PATTERN.search(text)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                return None
        return None

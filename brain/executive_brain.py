# =====================================
# Titan Executive Brain
# =====================================

"""LLM-backed strategic mission analysis (Phase 8 — P8-071)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from brain.llm import load_prompt_file
from config.settings import PROMPTS_DIR

if TYPE_CHECKING:
    from brain.llm import LLM

logger = logging.getLogger(__name__)

_FALLBACK_TEMPLATE = """
==============================
EXECUTIVE BRAIN (template)
==============================

Message utilisateur :
{message}

Contexte :
{context}

Mémoire pertinente :
{memory}

État actuel :
{state}

Mission actuelle :
{mission}

Décision :
- Si une mission est active, Titan doit respecter la mission actuelle.
- Titan doit répondre selon l'étape actuelle de la mission.
- Titan ne doit pas revenir à une étape déjà complétée.
- Si l'utilisateur dit "continue", Titan doit continuer l'étape actuelle.
==============================
"""


class ExecutiveBrain:
    """Provide strategic framing for the active mission and user intent."""

    def __init__(self, llm: LLM | None = None) -> None:
        self._llm = llm
        self._instructions = load_prompt_file("executive_analysis.md", PROMPTS_DIR)
        if not self._instructions:
            self._instructions = (
                "Analyse stratégique concise en français pour Titan."
            )

    def analyze_mission(
        self,
        message: str,
        context: str | None = None,
        memory: str | None = None,
        state: dict | None = None,
        mission: dict | None = None,
    ) -> str:
        """Return strategic analysis — LLM when available, template fallback."""
        if self._llm is not None and self._should_use_llm(mission or {}):
            llm_result = self._analyze_with_llm(
                message,
                context or "",
                memory or "",
                state or {},
                mission or {},
            )
            if llm_result:
                return llm_result

        return self._fallback_analysis(
            message,
            context or "",
            memory or "",
            state or {},
            mission or {},
        )

    def _analyze_with_llm(
        self,
        message: str,
        context: str,
        memory: str,
        state: dict,
        mission: dict,
    ) -> str | None:
        prompt = (
            f"Message utilisateur :\n{message}\n\n"
            f"Contexte :\n{context}\n\n"
            f"Mémoire pertinente :\n{memory}\n\n"
            f"État :\n{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"
            f"Mission :\n{json.dumps(mission, ensure_ascii=False, indent=2)}\n\n"
            "Produis l'analyse exécutive."
        )
        try:
            result = self._llm.ask_scoped(prompt, self._instructions)
            if result and result.strip():
                return result.strip()
        except Exception as exc:
            logger.warning("Executive LLM analysis failed: %s", exc)
        return None

    @staticmethod
    def _should_use_llm(mission: dict) -> bool:
        """Use LLM executive analysis when a mission is active."""
        return bool(mission.get("active"))

    def _fallback_analysis(
        self,
        message: str,
        context: str,
        memory: str,
        state: dict,
        mission: dict,
    ) -> str:
        mission_text = json.dumps(mission, ensure_ascii=False, indent=2)
        state_text = json.dumps(state, ensure_ascii=False, indent=2)
        return _FALLBACK_TEMPLATE.format(
            message=message,
            context=context,
            memory=memory,
            state=state_text,
            mission=mission_text,
        ).strip()

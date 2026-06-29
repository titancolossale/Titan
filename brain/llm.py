# =====================================
# Titan LLM Connector
# =====================================

"""OpenAI gateway for Titan — single entry point for model calls."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from brain.identity import IDENTITY
from brain.llm_provider import LLMProvider
from config.settings import LLM_MODEL, PROMPTS_DIR

logger = logging.getLogger(__name__)

LLM_ERROR_MESSAGE = (
    "Désolé, je n'ai pas pu contacter le modèle. Réessaie dans un instant."
)
MAX_RETRIES = 2
BACKOFF_SECONDS = (1, 2)


def load_prompt_file(filename: str, prompts_dir: Path | None = None) -> str:
    """Load a prompt template from ``prompts/``; return empty string if missing."""
    base = prompts_dir if prompts_dir is not None else PROMPTS_DIR
    path = base / filename
    if not path.exists():
        logger.warning("Prompt file not found: %s", path)
        return ""
    return path.read_text(encoding="utf-8").strip()


def build_system_instructions(prompts_dir: Path | None = None) -> str:
    """Assemble system instructions from base rules, identity, and constitution summary."""
    base = load_prompt_file("system_instructions.md", prompts_dir)
    constitution = load_prompt_file("constitution_summary.md", prompts_dir)
    parts = [base, IDENTITY.strip()]
    if constitution:
        parts.append(f"---\nCONSTITUTION (résumé)\n---\n{constitution}")
    return "\n\n".join(part for part in parts if part)


class LLM(LLMProvider):

    def __init__(
        self,
        *,
        model: str | None = None,
        prompts_dir: Path | None = None,
    ) -> None:
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model if model is not None else LLM_MODEL
        self._prompts_dir = prompts_dir
        self._system_instructions = build_system_instructions(prompts_dir)

    @property
    def system_instructions(self) -> str:
        return self._system_instructions

    def _is_transient_error(self, exc: Exception) -> bool:
        """Return True for rate limit, timeout, and connection failures."""
        return isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError))

    def _create_response(self, prompt: str) -> Any:
        """Call the OpenAI Responses API with Titan system instructions."""
        return self._create_scoped_response(prompt, self._system_instructions, self.model)

    def ask(self, prompt: str) -> str:
        """Send a prompt to the model; retry transient failures; never raise to callers."""
        return self.ask_scoped(prompt, self._system_instructions)

    def ask_scoped(
        self,
        prompt: str,
        instructions: str,
        *,
        model: str | None = None,
    ) -> str:
        """Send a prompt with custom system instructions (agent-scoped calls — P5-030)."""
        model_name = model if model is not None else self.model
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._create_scoped_response(prompt, instructions, model_name)
                return response.output_text
            except Exception as exc:
                if self._is_transient_error(exc) and attempt < MAX_RETRIES:
                    wait = BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "LLM transient error (attempt %d/%d): %s — retry in %ds",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                logger.error("LLM scoped request failed: %s", exc)
                return LLM_ERROR_MESSAGE

        return LLM_ERROR_MESSAGE

    def ask_with_model(self, prompt: str, *, model: str | None = None) -> str:
        """Send a prompt using an explicit model override (P9-070 routing)."""
        model_name = model if model is not None else self.model
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._create_scoped_response(
                    prompt,
                    self._system_instructions,
                    model_name,
                )
                return response.output_text
            except Exception as exc:
                if self._is_transient_error(exc) and attempt < MAX_RETRIES:
                    wait = BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "LLM transient error (attempt %d/%d): %s — retry in %ds",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                logger.error("LLM request failed (model=%s): %s", model_name, exc)
                return LLM_ERROR_MESSAGE

        return LLM_ERROR_MESSAGE

    def _create_scoped_response(self, prompt: str, instructions: str, model: str) -> Any:
        """Call the OpenAI Responses API with custom instructions and model."""
        return self.client.responses.create(
            model=model,
            instructions=instructions,
            input=prompt,
        )

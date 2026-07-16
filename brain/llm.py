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
from config.settings import TITAN_LLM_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

LLM_ERROR_MESSAGE = (
    "Désolé, je n'ai pas pu contacter le modèle. Réessaie dans un instant."
)
LLM_TIMEOUT_MESSAGE = (
    "Titan n’a pas pu répondre dans le délai prévu. Réessaie."
)
MAX_RETRIES = 2
BACKOFF_SECONDS = (1, 2)
PROVIDER_TIMEOUT_CODE = "provider_timeout"


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
        timeout_s = float(TITAN_LLM_TIMEOUT_SECONDS)
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=timeout_s,
        )
        self.model = model if model is not None else LLM_MODEL
        self._prompts_dir = prompts_dir
        self._system_instructions = build_system_instructions(prompts_dir)
        self._timeout_seconds = timeout_s
        # Last safe provider error code for diagnostics (no secrets).
        self.last_error_code: str | None = None

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
        request_id: str | None = None,
    ) -> str:
        """Send a prompt with custom system instructions (agent-scoped calls — P5-030)."""
        model_name = model if model is not None else self.model
        started = time.perf_counter()
        self.last_error_code = None
        corr_id = request_id or getattr(self, "_active_request_id", None) or "-"
        logger.info(
            "CHAT_PROVIDER_START request_id=%s model=%s elapsed_ms=0 stage=provider",
            corr_id,
            model_name,
        )
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._create_scoped_response(prompt, instructions, model_name)
                logger.info(
                    "CHAT_PROVIDER_END request_id=%s status=ok duration_ms=%d "
                    "elapsed_ms=%d stage=provider model=%s",
                    corr_id,
                    int((time.perf_counter() - started) * 1000),
                    int((time.perf_counter() - started) * 1000),
                    model_name,
                )
                return response.output_text
            except Exception as exc:
                if isinstance(exc, APITimeoutError):
                    self.last_error_code = PROVIDER_TIMEOUT_CODE
                    logger.warning(
                        "CHAT_PROVIDER_END request_id=%s status=timeout duration_ms=%d "
                        "elapsed_ms=%d stage=provider model=%s code=%s",
                        corr_id,
                        int((time.perf_counter() - started) * 1000),
                        int((time.perf_counter() - started) * 1000),
                        model_name,
                        PROVIDER_TIMEOUT_CODE,
                    )
                    return LLM_TIMEOUT_MESSAGE
                if self._is_transient_error(exc) and attempt < MAX_RETRIES:
                    wait = BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "LLM transient error (attempt %d/%d): %s — retry in %ds",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        type(exc).__name__,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                self.last_error_code = "provider_unavailable"
                logger.error(
                    "CHAT_PROVIDER_END request_id=%s status=error duration_ms=%d "
                    "elapsed_ms=%d stage=provider model=%s code=provider_unavailable",
                    corr_id,
                    int((time.perf_counter() - started) * 1000),
                    int((time.perf_counter() - started) * 1000),
                    model_name,
                )
                return LLM_ERROR_MESSAGE

        self.last_error_code = "provider_unavailable"
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

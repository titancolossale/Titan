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
from brain.request_deadline import (
    BrainTimeoutError,
    RequestCancelledError,
    check_deadline,
    get_request_deadline,
)
from config.settings import LLM_MODEL, PROMPTS_DIR
from config.settings import TITAN_LLM_MAX_RETRIES, TITAN_LLM_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

LLM_ERROR_MESSAGE = (
    "Désolé, je n'ai pas pu contacter le modèle. Réessaie dans un instant."
)
LLM_TIMEOUT_MESSAGE = (
    "Titan n’a pas pu répondre dans le délai prévu. Réessaie."
)
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
        self._max_retries = max(0, int(TITAN_LLM_MAX_RETRIES))
        # Last safe provider error code for diagnostics (no secrets).
        self.last_error_code: str | None = None
        self.last_prompt_chars: int = 0
        self.last_prompt_tokens_est: int = 0
        self.last_provider_calls: int = 0

    @property
    def system_instructions(self) -> str:
        return self._system_instructions

    def _is_transient_error(self, exc: Exception) -> bool:
        """Return True for rate limit and connection failures (not hard timeouts)."""
        return isinstance(exc, (APIConnectionError, RateLimitError))

    def _resolve_timeout(self) -> float:
        deadline = get_request_deadline()
        if deadline is None:
            return float(self._timeout_seconds)
        return deadline.provider_timeout_seconds(configured=self._timeout_seconds)

    def _create_response(self, prompt: str) -> Any:
        """Call the OpenAI Responses API with Titan system instructions."""
        return self._create_scoped_response(prompt, self._system_instructions, self.model)

    def ask(self, prompt: str) -> str:
        """Send a prompt to the model; retry transient failures; never raise to callers."""
        return self.ask_scoped(prompt, self._system_instructions)

    def ask_with_budget(
        self,
        prompt: str,
        *,
        max_output_tokens: int | None = None,
        request_id: str | None = None,
    ) -> str:
        """Conversational ask honoring the global deadline and optional output cap."""
        return self.ask_scoped(
            prompt,
            self._system_instructions,
            request_id=request_id,
            max_output_tokens=max_output_tokens,
        )

    def ask_scoped(
        self,
        prompt: str,
        instructions: str,
        *,
        model: str | None = None,
        request_id: str | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Send a prompt with custom system instructions (agent-scoped calls — P5-030)."""
        model_name = model if model is not None else self.model
        started = time.perf_counter()
        self.last_error_code = None
        self.last_prompt_chars = len(prompt or "") + len(instructions or "")
        self.last_prompt_tokens_est = max(1, (self.last_prompt_chars + 3) // 4)
        self.last_provider_calls = 0
        corr_id = request_id or getattr(self, "_active_request_id", None) or "-"
        deadline = get_request_deadline()

        logger.info(
            "CHAT_PROVIDER_START request_id=%s model=%s elapsed_ms=%s "
            "remaining_budget_ms=%s stage=provider prompt_chars=%d "
            "prompt_tokens_est=%d attempt=1",
            corr_id,
            model_name,
            deadline.elapsed_ms() if deadline else 0,
            deadline.remaining_ms() if deadline else None,
            self.last_prompt_chars,
            self.last_prompt_tokens_est,
        )

        max_attempts = self._max_retries + 1
        for attempt in range(max_attempts):
            try:
                check_deadline("provider_start")
            except (BrainTimeoutError, RequestCancelledError):
                self.last_error_code = PROVIDER_TIMEOUT_CODE
                logger.warning(
                    "CHAT_PROVIDER_END request_id=%s status=timeout duration_ms=%d "
                    "elapsed_ms=%s remaining_budget_ms=%s stage=provider model=%s "
                    "attempt=%d code=%s",
                    corr_id,
                    int((time.perf_counter() - started) * 1000),
                    deadline.elapsed_ms() if deadline else int((time.perf_counter() - started) * 1000),
                    deadline.remaining_ms() if deadline else None,
                    model_name,
                    attempt + 1,
                    PROVIDER_TIMEOUT_CODE,
                )
                return LLM_TIMEOUT_MESSAGE

            try:
                response = self._create_scoped_response(
                    prompt,
                    instructions,
                    model_name,
                    max_output_tokens=max_output_tokens,
                    timeout_seconds=self._resolve_timeout(),
                )
                self.last_provider_calls += 1
                duration_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "CHAT_PROVIDER_END request_id=%s status=ok duration_ms=%d "
                    "elapsed_ms=%s remaining_budget_ms=%s stage=provider model=%s "
                    "attempt=%d",
                    corr_id,
                    duration_ms,
                    deadline.elapsed_ms() if deadline else duration_ms,
                    deadline.remaining_ms() if deadline else None,
                    model_name,
                    attempt + 1,
                )
                return response.output_text
            except Exception as exc:
                self.last_provider_calls += 1
                duration_ms = int((time.perf_counter() - started) * 1000)
                if isinstance(exc, (APITimeoutError, TimeoutError, BrainTimeoutError)):
                    self.last_error_code = PROVIDER_TIMEOUT_CODE
                    logger.warning(
                        "CHAT_PROVIDER_END request_id=%s status=timeout duration_ms=%d "
                        "elapsed_ms=%s remaining_budget_ms=%s stage=provider model=%s "
                        "attempt=%d code=%s",
                        corr_id,
                        duration_ms,
                        deadline.elapsed_ms() if deadline else duration_ms,
                        deadline.remaining_ms() if deadline else None,
                        model_name,
                        attempt + 1,
                        PROVIDER_TIMEOUT_CODE,
                    )
                    return LLM_TIMEOUT_MESSAGE
                if self._is_transient_error(exc) and attempt < max_attempts - 1:
                    # Only retry when remaining budget allows another attempt.
                    remaining = deadline.remaining_seconds() if deadline else self._timeout_seconds
                    wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    if remaining < wait + 1.0:
                        self.last_error_code = PROVIDER_TIMEOUT_CODE
                        logger.warning(
                            "CHAT_PROVIDER_END request_id=%s status=timeout duration_ms=%d "
                            "elapsed_ms=%s remaining_budget_ms=%s stage=provider model=%s "
                            "attempt=%d code=%s",
                            corr_id,
                            duration_ms,
                            deadline.elapsed_ms() if deadline else duration_ms,
                            deadline.remaining_ms() if deadline else None,
                            model_name,
                            attempt + 1,
                            PROVIDER_TIMEOUT_CODE,
                        )
                        return LLM_TIMEOUT_MESSAGE
                    logger.warning(
                        "LLM transient error (attempt %d/%d): %s — retry in %ds",
                        attempt + 1,
                        max_attempts,
                        type(exc).__name__,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                self.last_error_code = "provider_unavailable"
                logger.error(
                    "CHAT_PROVIDER_END request_id=%s status=error duration_ms=%d "
                    "elapsed_ms=%s remaining_budget_ms=%s stage=provider model=%s "
                    "attempt=%d code=provider_unavailable error_type=%s",
                    corr_id,
                    duration_ms,
                    deadline.elapsed_ms() if deadline else duration_ms,
                    deadline.remaining_ms() if deadline else None,
                    model_name,
                    attempt + 1,
                    type(exc).__name__,
                )
                return LLM_ERROR_MESSAGE

        self.last_error_code = "provider_unavailable"
        return LLM_ERROR_MESSAGE

    def ask_with_model(self, prompt: str, *, model: str | None = None) -> str:
        """Send a prompt using an explicit model override (P9-070 routing)."""
        return self.ask_scoped(prompt, self._system_instructions, model=model)

    def _create_scoped_response(
        self,
        prompt: str,
        instructions: str,
        model: str,
        *,
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> Any:
        """Call the OpenAI Responses API with custom instructions and model."""
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": prompt,
        }
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = int(max_output_tokens)
        # Per-call timeout via request options — never stack beyond global deadline.
        timeout = timeout_seconds if timeout_seconds is not None else self._resolve_timeout()
        return self.client.with_options(timeout=timeout).responses.create(**kwargs)

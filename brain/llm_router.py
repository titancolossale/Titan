# =====================================
# Titan LLM Router
# =====================================

"""Multi-model routing by call type — no external provider coupling (Phase 9 — P9-070)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from brain.llm_provider import LLMProvider
from config.settings import (
    LLM_MODEL,
    LLM_MODEL_AGENT,
    LLM_MODEL_CLASSIFICATION,
    LLM_MODEL_EVALUATION,
)


class LLMCallType(str, Enum):
    """Categories of LLM calls for model routing."""

    SYNTHESIS = "synthesis"
    CLASSIFICATION = "classification"
    AGENT = "agent"
    EVALUATION = "evaluation"


@dataclass(frozen=True)
class ModelRoutingTable:
    """Maps call types to model names."""

    synthesis: str = LLM_MODEL
    classification: str = LLM_MODEL_CLASSIFICATION
    agent: str = LLM_MODEL_AGENT
    evaluation: str = LLM_MODEL_EVALUATION

    def model_for(self, call_type: LLMCallType) -> str:
        """Return model name for the given call type."""
        mapping = {
            LLMCallType.SYNTHESIS: self.synthesis,
            LLMCallType.CLASSIFICATION: self.classification,
            LLMCallType.AGENT: self.agent,
            LLMCallType.EVALUATION: self.evaluation,
        }
        return mapping[call_type]


class LLMRouter:
    """Routes LLM calls to appropriate models via a single provider gateway."""

    def __init__(
        self,
        provider: LLMProvider,
        routing: ModelRoutingTable | None = None,
    ) -> None:
        self._provider = provider
        self._routing = routing or ModelRoutingTable()
        self._last_call_type: LLMCallType | None = None
        self._last_model: str | None = None

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def routing(self) -> ModelRoutingTable:
        return self._routing

    @property
    def last_model(self) -> str | None:
        """Model used in the most recent routed call."""
        return self._last_model

    def ask(
        self,
        prompt: str,
        call_type: LLMCallType = LLMCallType.SYNTHESIS,
    ) -> str:
        """Route prompt to model for call type; delegate to provider."""
        model = self._routing.model_for(call_type)
        self._last_call_type = call_type
        self._last_model = model
        return self._ask_with_model(prompt, model)

    def ask_scoped(
        self,
        prompt: str,
        instructions: str,
        call_type: LLMCallType = LLMCallType.AGENT,
    ) -> str:
        """Scoped agent call with routing."""
        model = self._routing.model_for(call_type)
        self._last_call_type = call_type
        self._last_model = model
        ask_scoped = getattr(self._provider, "ask_scoped", None)
        if ask_scoped is None:
            return self._provider.ask(prompt)
        return ask_scoped(prompt, instructions, model=model)

    def _ask_with_model(self, prompt: str, model: str) -> str:
        """Invoke provider with optional per-call model override."""
        ask_with_model = getattr(self._provider, "ask_with_model", None)
        if ask_with_model is not None:
            return ask_with_model(prompt, model=model)
        return self._provider.ask(prompt)

# =====================================
# Titan LLM Router Tests
# =====================================

"""Tests for Phase 9 multi-model routing (P9-070)."""

from __future__ import annotations

from unittest.mock import MagicMock

from brain.llm_provider import LLMProvider
from brain.llm_router import LLMCallType, LLMRouter, ModelRoutingTable


class _StubProvider(LLMProvider):
    def __init__(self) -> None:
        self.last_model: str | None = None
        self._instructions = "test"

    @property
    def system_instructions(self) -> str:
        return self._instructions

    def ask(self, prompt: str) -> str:
        return "ok"

    def ask_with_model(self, prompt: str, *, model: str | None = None) -> str:
        self.last_model = model
        return f"model:{model}"


def test_router_selects_model_by_call_type() -> None:
    """Different call types route to configured models."""
    provider = _StubProvider()
    routing = ModelRoutingTable(
        synthesis="gpt-large",
        classification="gpt-small",
        agent="gpt-agent",
        evaluation="gpt-eval",
    )
    router = LLMRouter(provider, routing=routing)

    assert router.ask("test", call_type=LLMCallType.CLASSIFICATION) == "model:gpt-small"
    assert provider.last_model == "gpt-small"
    assert router.last_model == "gpt-small"


def test_router_scoped_delegates_to_provider() -> None:
    """Scoped agent calls use agent model routing."""
    provider = _StubProvider()

    class _ScopedProvider(_StubProvider):
        def ask_scoped(
            self,
            prompt: str,
            instructions: str,
            *,
            model: str | None = None,
        ) -> str:
            self.last_model = model
            return "scoped"

    scoped = _ScopedProvider()
    router = LLMRouter(
        scoped,
        routing=ModelRoutingTable(agent="gpt-agent"),
    )
    result = router.ask_scoped("prompt", "instructions", call_type=LLMCallType.AGENT)

    assert result == "scoped"
    assert scoped.last_model == "gpt-agent"

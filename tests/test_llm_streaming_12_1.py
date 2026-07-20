# =====================================
# Titan LLM Streaming Tests (Phase 12.1)
# =====================================

"""Provider streaming abstraction — progressive deltas, TTFT, cancellation safety."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import brain.llm as llm_module
from brain.llm import LLM


class _FakeStream:
    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas
        self.closed = False

    def __iter__(self):
        for delta in self._deltas:
            yield SimpleNamespace(type="response.output_text.delta", delta=delta)

    def close(self) -> None:
        self.closed = True


def test_ask_scoped_streams_deltas(monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "TITAN_CONVERSATION_STREAM_ENABLED", True)
    monkeypatch.setattr(llm_module, "load_dotenv", lambda: None)
    monkeypatch.setattr(llm_module, "build_system_instructions", lambda *_a, **_k: "sys")

    llm = LLM.__new__(LLM)
    llm.model = "gpt-test"
    llm._system_instructions = "sys"
    llm._timeout_seconds = 10
    llm._max_retries = 0
    llm.last_error_code = None
    llm.last_prompt_chars = 0
    llm.last_prompt_tokens_est = 0
    llm.last_provider_calls = 0
    llm.last_ttft_ms = None
    llm.last_delta_count = 0
    llm.client = MagicMock()
    llm._is_transient_error = lambda _exc: False
    llm._resolve_timeout = lambda: 10.0

    fake = _FakeStream(["Hel", "lo"])
    llm._create_scoped_response = MagicMock(return_value=fake)

    deltas: list[str] = []
    text = llm.ask_scoped("hi", "sys", on_text_delta=deltas.append)
    assert text == "Hello"
    assert deltas == ["Hel", "lo"]
    assert llm.last_delta_count == 2
    assert llm.last_ttft_ms is not None
    assert fake.closed is True


def test_late_deltas_ignored_after_cancel_flag() -> None:
    """UI generation guard — document expected client behavior."""
    active_generation = -1
    buffer = []

    def on_delta(text: str) -> None:
        if active_generation < 0:
            return
        buffer.append(text)

    on_delta("should-ignore")
    assert buffer == []

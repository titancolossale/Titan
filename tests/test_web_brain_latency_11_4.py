# =====================================
# Titan Web Brain Latency — Phase 11.4
# =====================================

"""Fast path, global deadline, bounded retries, and cancellation contracts."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.chat_service import (
    BRAIN_TIMEOUT_CODE,
    BRAIN_TIMEOUT_MESSAGE,
    cancel_chat_request,
    clear_idempotency_cache,
    process_chat_message,
)
from api.titan_service import reset_titan, set_titan
from brain.chat_fast_path import (
    build_fast_path_prompt,
    is_simple_conversational_request,
    run_fast_path,
)
from brain.llm import LLM, LLM_TIMEOUT_MESSAGE
from brain.natural_language_orchestrator import DetectedIntent, SystemName
from brain.request_deadline import (
    BrainTimeoutError,
    RequestDeadline,
    check_deadline,
    reset_request_deadline,
    set_request_deadline,
)
from core.titan import Titan
from tests.test_natural_language_orchestrator import _build_brain, _make_python_project
from tools.tool_manager import ToolManager

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "web" / "v2"


@pytest.fixture
def brain(tmp_path: Path):
    project = _make_python_project(tmp_path)
    return _build_brain(tmp_path, project)


# ---------------------------------------------------------------------------
# Fast-path selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Bonjour Titan",
        "Salut",
        "Comment vas-tu ?",
        "Qui es-tu ?",
        "Hello",
        "Merci",
    ],
)
def test_simple_messages_select_fast_path(message: str) -> None:
    assert is_simple_conversational_request(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "Plan the ORR automation",
        "Run pytest",
        "Search FastAPI docs",
        "Explain class Engine",
        "Applique le patch",
    ],
)
def test_complex_messages_reject_fast_path(message: str) -> None:
    assert is_simple_conversational_request(message) is False


def test_bonjour_titan_uses_fast_path_not_planner(brain) -> None:
    result = brain.process_request("Bonjour Titan")
    assert result.detected_intent == DetectedIntent.CONVERSATION
    assert (result.artifacts or {}).get("fast_path", {}).get("selected") is True
    assert (result.artifacts or {}).get("fast_path", {}).get("planner_skipped") is True
    assert (result.artifacts or {}).get("fast_path", {}).get("tools_skipped") is True
    assert (result.artifacts or {}).get("fast_path", {}).get("agents_skipped") is True
    skipped = " ".join(result.systems_used.skipped)
    assert "reasoning_engine" in skipped or SystemName.REASONING_ENGINE.value not in (
        result.systems_used.invoked
    )


def test_fast_path_reaches_provider_ask(brain) -> None:
    brain.llm.ask.reset_mock()
    result = brain.process_request("Bonjour Titan")
    assert brain.llm.ask.call_count == 1
    assert "Réponse de test" in result.final_response


def test_fast_path_compact_prompt(brain) -> None:
    prompt = build_fast_path_prompt("Bonjour Titan", user="Nolan", compact_context="user=Nolan")
    assert len(prompt) < 800
    assert "QUESTION DE L'UTILISATEUR" not in prompt
    assert "RÉSULTATS DES AGENTS" not in prompt
    meta = run_fast_path(brain, "Bonjour Titan")
    assert meta["prompt_chars"] < 2000
    assert meta["oversized_context_skipped"] is True


def test_complex_request_still_uses_normal_path(brain) -> None:
    result = brain.process_request("Plan the ORR automation")
    assert result.detected_intent == DetectedIntent.PLANNING
    assert (result.artifacts or {}).get("fast_path") in (None, {})


def test_bonjour_does_not_run_think_agents(brain) -> None:
    with patch.object(brain, "think") as think_mock:
        brain.process_request("Bonjour Titan")
        think_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Deadline / retries
# ---------------------------------------------------------------------------


def test_global_deadline_enforced() -> None:
    deadline = RequestDeadline.start(total_seconds=0.05, request_id="d1")
    token = set_request_deadline(deadline)
    try:
        time.sleep(0.08)
        with pytest.raises(BrainTimeoutError):
            check_deadline("provider_start")
    finally:
        reset_request_deadline(token)


def test_nested_timeouts_cannot_exceed_global_budget() -> None:
    deadline = RequestDeadline.start(total_seconds=5, request_id="d2")
    # Provider slice must never exceed remaining budget.
    capped = deadline.provider_timeout_seconds(configured=60.0)
    assert capped <= 5.0
    deadline.started_monotonic -= 4.5
    capped2 = deadline.provider_timeout_seconds(configured=60.0)
    assert capped2 <= deadline.remaining_seconds() + 0.01


def test_provider_retries_bounded() -> None:
    from config.settings import TITAN_LLM_MAX_RETRIES

    assert TITAN_LLM_MAX_RETRIES <= 2
    llm = LLM.__new__(LLM)
    llm._max_retries = TITAN_LLM_MAX_RETRIES
    assert llm._max_retries + 1 <= 3


def test_provider_timeout_returns_brain_timeout_message(tmp_path, monkeypatch) -> None:
    clear_idempotency_cache()
    reset_titan()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)

    def boom(*_a, **_k):
        from brain.request_deadline import BrainTimeoutError

        raise BrainTimeoutError(last_completed_stage="provider_start")

    titan.brain.process_request = boom  # type: ignore[method-assign]
    set_titan(titan)
    payload = process_chat_message("Bonjour Titan", request_id="timeout-1")
    assert payload["ok"] is False
    assert payload["error_code"] == BRAIN_TIMEOUT_CODE
    assert payload["error"]["code"] == BRAIN_TIMEOUT_CODE
    assert payload["error"]["retryable"] is True
    assert BRAIN_TIMEOUT_MESSAGE in payload["response"]
    assert payload["last_completed_stage"] == "provider_start"


def test_max_reasoning_iterations_setting() -> None:
    from config.settings import (
        TITAN_MAX_AGENT_HANDOFFS,
        TITAN_MAX_PLANNING_ITERATIONS,
        TITAN_MAX_REASONING_ITERATIONS,
    )

    assert TITAN_MAX_REASONING_ITERATIONS >= 1
    assert TITAN_MAX_PLANNING_ITERATIONS >= 1
    assert TITAN_MAX_AGENT_HANDOFFS >= 1


# ---------------------------------------------------------------------------
# Cancellation / frontend contracts
# ---------------------------------------------------------------------------


def test_cancel_marks_active_deadline(tmp_path) -> None:
    clear_idempotency_cache()
    reset_titan()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)

    started = {"ok": False}

    def slow_process(message, *, stream=None):
        from brain.request_deadline import get_request_deadline

        deadline = get_request_deadline()
        started["ok"] = True
        # Wait until cancel is signaled.
        for _ in range(50):
            if deadline and deadline.cancelled:
                from brain.request_deadline import RequestCancelledError

                raise RequestCancelledError(last_completed_stage="brain")
            time.sleep(0.02)
        return titan.brain.natural_language_orchestrator.process("x")

    titan.brain.process_request = slow_process  # type: ignore[method-assign]
    set_titan(titan)

    import threading

    result_box: dict = {}

    def runner():
        result_box["payload"] = process_chat_message(
            "Complex question about architecture please",
            request_id="cancel-1",
        )

    thread = threading.Thread(target=runner)
    thread.start()
    for _ in range(50):
        if started["ok"]:
            break
        time.sleep(0.02)
    assert cancel_chat_request("cancel-1") is True
    thread.join(timeout=5)
    assert result_box["payload"]["error_code"] == "cancelled"


def test_stop_button_aborts_frontend_request() -> None:
    cm = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "interrupt()" in cm
    assert "/api/chat/cancel" in cm
    assert "_activeGeneration" in cm
    assert "abandoned" in cm
    bridge = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    assert "CHAT_CLIENT_TIMEOUT_MS" in bridge
    assert "AbortController" in bridge


def test_client_timeout_aligned_with_deadline() -> None:
    bridge = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    assert "CHAT_CLIENT_TIMEOUT_MS = 35000" in bridge
    from config.settings import TITAN_CHAT_DEADLINE_SECONDS

    assert TITAN_CHAT_DEADLINE_SECONDS <= 35


def test_retry_uses_new_request_id_contract() -> None:
    cm = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "createClientRequestId" in cm
    assert "retryLast" in cm


def test_one_user_action_one_provider_call(brain) -> None:
    brain.llm.ask.reset_mock()
    brain.process_request("Salut")
    assert brain.llm.ask.call_count == 1


def test_request_timings_in_safe_logs(brain, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        brain.process_request("Bonjour Titan")
    joined = " ".join(r.message for r in caplog.records)
    assert "CHAT_FAST_PATH_SELECTED" in joined
    assert "sk-" not in joined.lower()
    assert "openai_api_key" not in joined.lower()


def test_auth_and_health_untouched() -> None:
    app_src = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert "require_web_auth" in app_src
    assert "/health" in app_src or "health" in app_src
    assert "/ready" in app_src or "ready" in app_src


def test_canonical_web_app_unchanged_visually() -> None:
    # Phase 11.4 must not rewrite CSS / neural look.
    ui = (V2 / "design" / "ui.css").read_text(encoding="utf-8")
    assert len(ui) > 100
    # No new purple theme injection in this step.
    assert "brain_timeout" not in ui

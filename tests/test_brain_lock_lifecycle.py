# =====================================
# Titan Brain Lock Lifecycle Tests
# =====================================

"""Prove cancelled/busy/timeout paths never leave the global Brain lock held."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from api.chat_service import (
    BRAIN_BUSY_CODE,
    CANCELLED_CODE,
    PROVIDER_TIMEOUT_CODE,
    _brain_lock,
    _brain_lock_owner_snapshot,
    cancel_chat_request,
    clear_idempotency_cache,
    process_chat_message,
    reset_brain_lock_for_tests,
)
from api.titan_service import reset_titan, set_titan
from brain.llm import LLM_TIMEOUT_MESSAGE
from brain.natural_language_orchestrator import (
    DetectedIntent,
    OrchestrationResult,
    PipelineDecision,
    RequestAnalysis,
    SystemsUsed,
)
from brain.request_deadline import RequestCancelledError
from core.titan import Titan
from core.web_conversations.db import apply_migrations, create_conversation_engine, reset_engine
from core.web_conversations.models import MessageStatus
from core.web_conversations.service import (
    ConversationService,
    reset_conversation_service,
)
from tools.tool_manager import ToolManager

ROOT = Path(__file__).resolve().parent.parent


def _orchestration_result(
    *,
    response: str = "OK",
    artifacts: dict | None = None,
) -> OrchestrationResult:
    analysis = RequestAnalysis(
        request="test",
        normalized="test",
        tokens=("test",),
        user="Nolan",
    )
    return OrchestrationResult(
        request_analysis=analysis,
        detected_intent=DetectedIntent.CONVERSATION,
        pipeline_decision=PipelineDecision(
            intent=DetectedIntent.CONVERSATION,
            systems=(),
            awareness_systems=(),
            rationale="test",
        ),
        systems_used=SystemsUsed(planned=(), invoked=["brain_think"], skipped=[]),
        reasoning_summary="ok",
        confidence=0.9,
        final_response=response,
        artifacts=artifacts or {},
        duration_seconds=0.01,
    )


@pytest.fixture(autouse=True)
def _clean_lock_state(monkeypatch: pytest.MonkeyPatch):
    clear_idempotency_cache()
    reset_titan()
    reset_brain_lock_for_tests()
    monkeypatch.setattr(
        "api.chat_service.TITAN_BRAIN_LOCK_TIMEOUT_SECONDS",
        0.4,
    )
    monkeypatch.setattr(
        "config.settings.TITAN_BRAIN_LOCK_TIMEOUT_SECONDS",
        0.4,
    )
    yield
    reset_brain_lock_for_tests()
    clear_idempotency_cache()
    reset_titan()
    reset_conversation_service()
    reset_engine()


def _make_titan(tmp_path: Path) -> Titan:
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.tool_manager = titan.tools
    titan.status = "ONLINE"
    set_titan(titan)
    return titan


def test_normal_request_acquires_and_releases_lock(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    titan = _make_titan(tmp_path)
    titan.brain.process_request = MagicMock(return_value=_orchestration_result())
    with caplog.at_level(logging.INFO):
        payload = process_chat_message("Bonjour", request_id="lock-ok-1")
    assert payload["ok"] is True
    assert _brain_lock_owner_snapshot() is None
    assert _brain_lock.acquire(timeout=0.05)
    _brain_lock.release()
    joined = " ".join(r.message for r in caplog.records)
    assert "CHAT_BRAIN_LOCK_WAIT" in joined
    assert "CHAT_BRAIN_LOCK_ACQUIRED" in joined
    assert "CHAT_BRAIN_LOCK_RELEASED" in joined
    assert "CHAT_BRAIN_START" in joined


def test_exception_inside_protected_section_releases_lock(tmp_path: Path) -> None:
    titan = _make_titan(tmp_path)

    def boom(message, *, stream=None):
        raise RuntimeError("brain boom")

    titan.brain.process_request = boom  # type: ignore[method-assign]
    payload = process_chat_message("fail", request_id="lock-exc-1")
    assert payload["error_code"] == "brain_failure"
    assert _brain_lock_owner_snapshot() is None
    assert _brain_lock.acquire(timeout=0.05)
    _brain_lock.release()


def test_provider_timeout_releases_lock(tmp_path: Path) -> None:
    titan = _make_titan(tmp_path)
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(
            response=LLM_TIMEOUT_MESSAGE,
            artifacts={"error": PROVIDER_TIMEOUT_CODE},
        )
    )
    payload = process_chat_message("slow", request_id="lock-timeout-1")
    assert payload["error_code"] == PROVIDER_TIMEOUT_CODE
    assert _brain_lock_owner_snapshot() is None


def test_client_cancellation_releases_lock(tmp_path: Path) -> None:
    titan = _make_titan(tmp_path)
    started = threading.Event()

    def slow(message, *, stream=None):
        from brain.request_deadline import get_request_deadline

        started.set()
        deadline = get_request_deadline()
        for _ in range(100):
            if deadline and deadline.cancelled:
                raise RequestCancelledError(last_completed_stage="brain")
            time.sleep(0.02)
        return _orchestration_result()

    titan.brain.process_request = slow  # type: ignore[method-assign]
    box: dict = {}

    def runner() -> None:
        box["payload"] = process_chat_message("x", request_id="lock-cancel-1")

    thread = threading.Thread(target=runner)
    thread.start()
    assert started.wait(2.0)
    assert cancel_chat_request("lock-cancel-1") is True
    thread.join(timeout=5)
    assert box["payload"]["error_code"] == CANCELLED_CODE
    assert _brain_lock_owner_snapshot() is None


def test_stop_request_releases_or_abandons_safely(tmp_path: Path) -> None:
    """Stop while waiting for lock must not steal another owner's lock."""
    titan = _make_titan(tmp_path)
    hold = threading.Event()
    released = threading.Event()

    def holder(message, *, stream=None):
        hold.set()
        released.wait(timeout=3)
        return _orchestration_result(response="holder")

    titan.brain.process_request = holder  # type: ignore[method-assign]
    t1 = threading.Thread(
        target=lambda: process_chat_message("hold", request_id="owner-1"),
    )
    t1.start()
    assert hold.wait(2.0)
    assert _brain_lock_owner_snapshot() == "owner-1"

    # Second request waits; Stop cancels it before acquire.
    box: dict = {}

    def waiter() -> None:
        box["payload"] = process_chat_message("wait", request_id="waiter-1")

    t2 = threading.Thread(target=waiter)
    t2.start()
    time.sleep(0.15)
    assert cancel_chat_request("waiter-1") is True
    t2.join(timeout=3)
    assert box["payload"]["error_code"] == CANCELLED_CODE
    # Owner must still hold until it finishes — cancellation must not release it.
    assert _brain_lock_owner_snapshot() == "owner-1"
    released.set()
    t1.join(timeout=3)
    assert _brain_lock_owner_snapshot() is None


def test_generator_close_style_cancel_releases_lock(tmp_path: Path) -> None:
    """Simulate StreamingResponse finally → cancel_chat_request while Brain runs."""
    titan = _make_titan(tmp_path)
    entered = threading.Event()

    def slow(message, *, stream=None):
        from brain.request_deadline import get_request_deadline

        entered.set()
        deadline = get_request_deadline()
        for _ in range(100):
            if deadline and deadline.cancelled:
                raise RequestCancelledError(last_completed_stage="provider")
            time.sleep(0.02)
        return _orchestration_result()

    titan.brain.process_request = slow  # type: ignore[method-assign]
    box: dict = {}

    def runner() -> None:
        box["payload"] = process_chat_message("stream", request_id="gen-close-1")

    thread = threading.Thread(target=runner)
    thread.start()
    assert entered.wait(2.0)
    # Same path as app.py generate() finally.
    cancel_chat_request("gen-close-1")
    thread.join(timeout=5)
    assert box["payload"]["error_code"] == CANCELLED_CODE
    assert _brain_lock_owner_snapshot() is None


def test_second_request_bounded_lock_timeout_returns_brain_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_TIMEOUT_SECONDS", 0.25)
    titan = _make_titan(tmp_path)
    hold = threading.Event()
    release = threading.Event()

    def holder(message, *, stream=None):
        hold.set()
        release.wait(timeout=5)
        return _orchestration_result()

    titan.brain.process_request = holder  # type: ignore[method-assign]
    t1 = threading.Thread(
        target=lambda: process_chat_message("a", request_id="busy-owner"),
    )
    t1.start()
    assert hold.wait(2.0)

    started = time.monotonic()
    payload = process_chat_message("b", request_id="busy-waiter")
    waited = time.monotonic() - started
    assert payload["error_code"] == BRAIN_BUSY_CODE
    assert payload["retryable"] is True
    assert payload["ok"] is False
    assert waited < 2.0  # never multi-minute hang
    release.set()
    t1.join(timeout=3)
    assert _brain_lock_owner_snapshot() is None


def test_request_after_cancelled_can_acquire_lock(tmp_path: Path) -> None:
    titan = _make_titan(tmp_path)
    started = threading.Event()

    def cancellable(message, *, stream=None):
        from brain.request_deadline import get_request_deadline

        started.set()
        deadline = get_request_deadline()
        for _ in range(100):
            if deadline and deadline.cancelled:
                raise RequestCancelledError(last_completed_stage="brain")
            time.sleep(0.02)
        return _orchestration_result()

    titan.brain.process_request = cancellable  # type: ignore[method-assign]
    t1 = threading.Thread(
        target=lambda: process_chat_message("c1", request_id="after-cancel-1"),
    )
    t1.start()
    assert started.wait(2.0)
    cancel_chat_request("after-cancel-1")
    t1.join(timeout=5)

    titan.brain.process_request = MagicMock(return_value=_orchestration_result())
    payload = process_chat_message("c2", request_id="after-cancel-2")
    assert payload["ok"] is True
    assert titan.brain.process_request.call_count == 1


def test_database_setup_occurs_outside_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titan = _make_titan(tmp_path)
    titan.brain.process_request = MagicMock(return_value=_orchestration_result())

    engine = create_conversation_engine(
        force_sqlite=True,
        sqlite_path=tmp_path / "conversations.db",
    )
    apply_migrations(engine)
    service = ConversationService(
        repository=__import__(
            "core.web_conversations.repository",
            fromlist=["ConversationRepository"],
        ).ConversationRepository(engine=engine)
    )
    monkeypatch.setattr(
        "api.chat_service.TITAN_CONVERSATION_PERSISTENCE_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "api.chat_service.get_conversation_service",
        lambda: service,
    )

    order: list[str] = []
    real_ensure = service.ensure_ready

    def tracked_ensure() -> None:
        order.append("ensure_ready")
        # Lock must not be owned yet when DB setup runs.
        assert _brain_lock_owner_snapshot() is None
        real_ensure()

    service.ensure_ready = tracked_ensure  # type: ignore[method-assign]

    original_acquire = __import__("api.chat_service", fromlist=["_acquire_brain_lock"])._acquire_brain_lock

    def tracked_acquire(request_id, deadline, **kwargs):
        order.append("lock_acquire")
        return original_acquire(request_id, deadline, **kwargs)

    monkeypatch.setattr("api.chat_service._acquire_brain_lock", tracked_acquire)

    payload = process_chat_message(
        "persist please",
        request_id="db-outside-1",
        conversation_id="conv-db-1",
        user="Nolan",
    )
    assert payload["ok"] is True
    assert "ensure_ready" in order
    assert "lock_acquire" in order
    assert order.index("ensure_ready") < order.index("lock_acquire")


def test_conversation_persistence_remains_functional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titan = _make_titan(tmp_path)
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(response="Persisted reply"),
    )
    engine = create_conversation_engine(
        force_sqlite=True,
        sqlite_path=tmp_path / "conversations.db",
    )
    apply_migrations(engine)
    from core.web_conversations.repository import ConversationRepository

    repo = ConversationRepository(engine=engine)
    service = ConversationService(repository=repo)
    monkeypatch.setattr(
        "api.chat_service.TITAN_CONVERSATION_PERSISTENCE_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "api.chat_service.get_conversation_service",
        lambda: service,
    )

    payload = process_chat_message(
        "Hello durable",
        request_id="persist-1",
        conversation_id="conv-persist-1",
        user="Nolan",
    )
    assert payload["ok"] is True
    messages, total = repo.list_messages("conv-persist-1", "Nolan", limit=20, offset=0)
    assert total >= 2
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles
    assistant = [m for m in messages if m.role == "assistant"][-1]
    assert assistant.status == MessageStatus.COMPLETED.value
    assert "Persisted" in assistant.content


def test_no_duplicate_assistant_message_finalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titan = _make_titan(tmp_path)
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(response="Once"),
    )
    engine = create_conversation_engine(
        force_sqlite=True,
        sqlite_path=tmp_path / "conversations.db",
    )
    apply_migrations(engine)
    from core.web_conversations.repository import ConversationRepository

    repo = ConversationRepository(engine=engine)
    service = ConversationService(repository=repo)
    monkeypatch.setattr(
        "api.chat_service.TITAN_CONVERSATION_PERSISTENCE_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "api.chat_service.get_conversation_service",
        lambda: service,
    )
    process_chat_message(
        "dup check",
        request_id="dup-asst-1",
        conversation_id="conv-dup-1",
        user="Nolan",
    )
    # Idempotent begin_assistant for same request_id.
    again = service.begin_assistant_message(
        conversation_id="conv-dup-1",
        user_id="Nolan",
        request_id="dup-asst-1",
        model="test",
    )
    assistants = [
        m
        for m in repo.list_messages("conv-dup-1", "Nolan", limit=50, offset=0)[0]
        if m.role == "assistant" and m.request_id == "dup-asst-1"
    ]
    assert len(assistants) == 1
    assert again.id == assistants[0].id


def test_late_deltas_after_cancellation_are_ignored() -> None:
    from brain.llm import LLM

    llm = LLM.__new__(LLM)
    llm.last_delta_count = 0
    llm.last_ttft_ms = None
    llm._active_request_id = "other-request"
    emitted: list[str] = []

    class _Evt:
        def __init__(self, delta: str) -> None:
            self.type = "response.output_text.delta"
            self.delta = delta

    class _Stream:
        def __iter__(self):
            yield _Evt("late")

        def close(self) -> None:
            return None

    llm._create_scoped_response = MagicMock(return_value=_Stream())  # type: ignore[method-assign]
    text = LLM._stream_scoped_response(
        llm,
        "p",
        "i",
        "gpt-test",
        on_text_delta=emitted.append,
        request_id="cancelled-req",
    )
    assert text == "late"  # assembled for return, but callback ignored
    assert emitted == []


def test_background_modules_do_not_acquire_chat_lock() -> None:
    for rel in (
        "brain/proactive_intelligence.py",
        "brain/project_intelligence.py",
        "brain/executive_function.py",
    ):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "_brain_lock" not in src
        assert "api.chat_service" not in src


def test_fast_path_still_reaches_provider(tmp_path: Path) -> None:
    titan = _make_titan(tmp_path)
    called = {"ok": False}

    def process(message, *, stream=None):
        called["ok"] = True
        return _orchestration_result(
            response="Salut",
            artifacts={"fast_path": {"selected": True}},
        )

    titan.brain.process_request = process  # type: ignore[method-assign]
    payload = process_chat_message("Bonjour Titan", request_id="fast-1")
    assert called["ok"] is True
    assert payload.get("fast_path") is True
    assert payload["ok"] is True


def test_contention_harness_release_then_third_acquires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic local reproduction of lock contention + recovery."""
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_TIMEOUT_SECONDS", 0.3)
    titan = _make_titan(tmp_path)
    hold = threading.Event()
    release = threading.Event()

    def first(message, *, stream=None):
        from brain.request_deadline import get_request_deadline

        hold.set()
        deadline = get_request_deadline()
        for _ in range(200):
            if deadline and deadline.cancelled:
                raise RequestCancelledError(last_completed_stage="brain")
            if release.is_set():
                break
            time.sleep(0.02)
        if deadline and deadline.cancelled:
            raise RequestCancelledError(last_completed_stage="brain")
        return _orchestration_result(response="first")

    titan.brain.process_request = first  # type: ignore[method-assign]
    box1: dict = {}
    t1 = threading.Thread(
        target=lambda: box1.update(
            payload=process_chat_message("1", request_id="harness-1")
        ),
    )
    t1.start()
    assert hold.wait(2.0)

    # Second waits → brain_busy within timeout.
    started = time.monotonic()
    payload2 = process_chat_message("2", request_id="harness-2")
    assert time.monotonic() - started < 2.0
    assert payload2["error_code"] == BRAIN_BUSY_CODE

    # Cancel first; confirm third can acquire immediately after release.
    cancel_chat_request("harness-1")
    release.set()
    t1.join(timeout=5)
    assert box1["payload"]["error_code"] == CANCELLED_CODE
    assert _brain_lock_owner_snapshot() is None

    titan.brain.process_request = MagicMock(return_value=_orchestration_result())
    started3 = time.monotonic()
    payload3 = process_chat_message("3", request_id="harness-3")
    assert time.monotonic() - started3 < 1.0
    assert payload3["ok"] is True
    assert _brain_lock_owner_snapshot() is None


def test_postgres_connect_timeout_configured() -> None:
    src = (ROOT / "core" / "web_conversations" / "db.py").read_text(encoding="utf-8")
    assert "connect_timeout" in src
    assert "statement_timeout" in src
    assert "TITAN_DB_CONNECT_TIMEOUT_SECONDS" in src

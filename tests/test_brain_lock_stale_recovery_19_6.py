# =====================================
# Titan Phase 19.6 — Brain Lock Self-Recovery
# =====================================

"""Focused proofs for ownership tokens, heartbeat stale reclaim, and SSE safety."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from api.brain_lock import (
    BrainLockManager,
    BrainLockState,
    load_brain_lock_config,
)
from api.chat_service import (
    BRAIN_BUSY_CODE,
    CANCELLED_CODE,
    PROVIDER_TIMEOUT_CODE,
    STALE_OWNER_CODE,
    _acquire_brain_lock,
    _brain_lock,
    _brain_lock_manager,
    _brain_lock_owner_snapshot,
    _heartbeat_brain_lock,
    _ownership_still_valid,
    _release_brain_lock,
    _set_brain_lock_acquired_monotonic,
    brain_lock_diagnostics,
    cancel_chat_request,
    clear_idempotency_cache,
    process_chat_message,
    register_active_deadline,
    reset_brain_lock_for_tests,
    unregister_active_deadline,
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
from brain.request_deadline import RequestCancelledError, RequestDeadline
from core.titan import Titan
from core.web_conversations.db import apply_migrations, create_conversation_engine, reset_engine
from core.web_conversations.models import MessageStatus
from core.web_conversations.repository import ConversationRepository
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
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_TIMEOUT_SECONDS", 0.25)
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_STALE_SECONDS", 0.4)
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr("api.chat_service.TITAN_BRAIN_LOCK_RECLAIM_ENABLED", True)
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


def test_config_fallback_safe() -> None:
    cfg = load_brain_lock_config(
        wait_timeout="nope",
        stale_seconds=-1,
        heartbeat_seconds="x",
        reclaim_enabled="maybe",
    )
    assert cfg.wait_timeout_seconds == 5.0
    assert cfg.stale_seconds >= cfg.wait_timeout_seconds
    assert cfg.heartbeat_seconds < cfg.stale_seconds / 3.0
    assert cfg.reclaim_enabled is True

    cfg2 = load_brain_lock_config(
        wait_timeout=10,
        stale_seconds=5,  # invalid: <= wait
        heartbeat_seconds=20,  # invalid: too large
        reclaim_enabled=False,
    )
    assert cfg2.stale_seconds > cfg2.wait_timeout_seconds
    assert cfg2.heartbeat_seconds < cfg2.stale_seconds / 3.0
    assert cfg2.reclaim_enabled is False


def test_normal_acquire_and_release() -> None:
    d = RequestDeadline.start(total_seconds=5, request_id="n1")
    gen = _acquire_brain_lock("n1", d)
    assert gen is not None and gen > 0
    assert _brain_lock_owner_snapshot() == "n1"
    assert _release_brain_lock("n1", gen) is True
    assert _brain_lock_owner_snapshot() is None
    assert brain_lock_diagnostics()["lock_state"] in {
        BrainLockState.IDLE.value,
        BrainLockState.RELEASED.value,
    }


def test_healthy_long_running_owner_never_reclaimed() -> None:
    d1 = RequestDeadline.start(total_seconds=30, request_id="healthy")
    register_active_deadline(d1)
    gen = _acquire_brain_lock("healthy", d1)
    assert gen is not None
    # Age lock far beyond stale, but keep heartbeat fresh + owner active.
    _set_brain_lock_acquired_monotonic(time.monotonic() - 120.0)
    _heartbeat_brain_lock("healthy", gen, state=BrainLockState.RUNNING.value, force_log=True)

    d2 = RequestDeadline.start(total_seconds=5, request_id="waiter")
    acquired = _acquire_brain_lock("waiter", d2, timeout_seconds=0.2)
    assert acquired is None
    assert _brain_lock_owner_snapshot() == "healthy"
    _release_brain_lock("healthy", gen)
    unregister_active_deadline("healthy")


def test_abandoned_owner_becomes_stale_and_reclaimed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    d1 = RequestDeadline.start(total_seconds=30, request_id="stale-owner")
    register_active_deadline(d1)
    gen = _acquire_brain_lock("stale-owner", d1)
    assert gen is not None
    # Simulate abandoned ownership: ages exceed stale + cancelled.
    aged = time.monotonic() - 120.0
    with _brain_lock_manager._state_lock:
        _brain_lock_manager._ownership.acquired_at = aged
        _brain_lock_manager._ownership.last_heartbeat_at = aged
    d1.cancel()

    d2 = RequestDeadline.start(total_seconds=5, request_id="reclaimer")
    with caplog.at_level(logging.INFO):
        acquired = _acquire_brain_lock("reclaimer", d2, timeout_seconds=0.3)
    assert acquired is not None
    assert any("CHAT_BRAIN_LOCK_RECLAIMED" in r.getMessage() for r in caplog.records)
    assert not _ownership_still_valid(gen)
    _release_brain_lock("reclaimer", acquired)
    unregister_active_deadline("stale-owner")


def test_two_waiters_cannot_both_reclaim() -> None:
    d0 = RequestDeadline.start(total_seconds=30, request_id="owner")
    register_active_deadline(d0)
    gen0 = _acquire_brain_lock("owner", d0)
    assert gen0 is not None
    aged = time.monotonic() - 120.0
    with _brain_lock_manager._state_lock:
        _brain_lock_manager._ownership.acquired_at = aged
        _brain_lock_manager._ownership.last_heartbeat_at = aged
    d0.cancel()

    results: list[int | None] = []
    barrier = threading.Barrier(2)

    def waiter(rid: str) -> None:
        barrier.wait(timeout=2)
        d = RequestDeadline.start(total_seconds=5, request_id=rid)
        results.append(_acquire_brain_lock(rid, d, timeout_seconds=0.5))

    t1 = threading.Thread(target=waiter, args=("w1",))
    t2 = threading.Thread(target=waiter, args=("w2",))
    t1.start()
    t2.start()
    t1.join(timeout=3)
    t2.join(timeout=3)
    winners = [g for g in results if g is not None]
    assert len(winners) == 1
    assert _brain_lock_manager._ownership.stale_reclaim_count == 1
    _release_brain_lock(
        "w1" if results[0] is not None else "w2",
        winners[0],
    )
    unregister_active_deadline("owner")


def test_old_owner_cannot_release_or_overwrite_new_owner(
    caplog: pytest.LogCaptureFixture,
) -> None:
    d1 = RequestDeadline.start(total_seconds=30, request_id="old")
    register_active_deadline(d1)
    gen_old = _acquire_brain_lock("old", d1)
    assert gen_old is not None
    aged = time.monotonic() - 120.0
    with _brain_lock_manager._state_lock:
        _brain_lock_manager._ownership.acquired_at = aged
        _brain_lock_manager._ownership.last_heartbeat_at = aged
    d1.cancel()

    d2 = RequestDeadline.start(total_seconds=5, request_id="new")
    gen_new = _acquire_brain_lock("new", d2, timeout_seconds=0.4)
    assert gen_new is not None
    assert _brain_lock_owner_snapshot() == "new"

    with caplog.at_level(logging.INFO):
        assert _release_brain_lock("old", gen_old) is False
        assert _heartbeat_brain_lock("old", gen_old, state=BrainLockState.RUNNING.value) is False
    assert _brain_lock_owner_snapshot() == "new"
    joined = " ".join(r.message for r in caplog.records)
    assert "CHAT_BRAIN_LOCK_RELEASE_SKIPPED_OWNER_MISMATCH" in joined
    _release_brain_lock("new", gen_new)
    unregister_active_deadline("old")


def test_provider_timeout_and_exception_release_lock(tmp_path: Path) -> None:
    titan = _make_titan(tmp_path)
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(
            response=LLM_TIMEOUT_MESSAGE,
            artifacts={"error": PROVIDER_TIMEOUT_CODE},
        )
    )
    payload = process_chat_message("slow", request_id="pt-1")
    assert payload["error_code"] == PROVIDER_TIMEOUT_CODE
    assert _brain_lock_owner_snapshot() is None

    def boom(message, *, stream=None):
        raise RuntimeError("provider boom")

    titan.brain.process_request = boom  # type: ignore[method-assign]
    payload2 = process_chat_message("boom", request_id="pt-2")
    assert payload2["error_code"] == "brain_failure"
    assert _brain_lock_owner_snapshot() is None


def test_client_disconnect_and_generator_cancel_release(tmp_path: Path) -> None:
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
        box["payload"] = process_chat_message("stream", request_id="disc-1")

    thread = threading.Thread(target=runner)
    thread.start()
    assert entered.wait(2.0)
    cancel_chat_request("disc-1")
    thread.join(timeout=5)
    assert box["payload"]["error_code"] == CANCELLED_CODE
    assert _brain_lock_owner_snapshot() is None


def test_pending_assistant_cancelled_after_interruption(tmp_path: Path) -> None:
    engine = create_conversation_engine(
        sqlite_path=tmp_path / "conversations.db",
        force_sqlite=True,
    )
    apply_migrations(engine)
    service = ConversationService(repository=ConversationRepository(engine=engine))
    conv = service.create_conversation("u1", title="t")
    pending = service.begin_assistant_message(
        conversation_id=conv.id,
        user_id="u1",
        request_id="req-int-1",
        model="test",
    )
    assert pending.status == MessageStatus.PENDING.value
    updated = service.finalize_assistant_message(
        message_id=pending.id,
        conversation_id=conv.id,
        user_id="u1",
        content="",
        status=MessageStatus.CANCELLED.value,
        error_code=CANCELLED_CODE,
    )
    assert updated is not None
    assert updated.status == MessageStatus.CANCELLED.value

    # Completed overwrite of non-pending must be ignored.
    again = service.finalize_assistant_message(
        message_id=pending.id,
        conversation_id=conv.id,
        user_id="u1",
        content="stale overwrite",
        status=MessageStatus.COMPLETED.value,
    )
    assert again is None
    _c, messages, _total = service.get_conversation_with_messages(conv.id, "u1")
    asst = [m for m in messages if m.role == "assistant"]
    assert len(asst) == 1
    assert asst[0].status == MessageStatus.CANCELLED.value
    assert asst[0].content != "stale overwrite"


def test_no_duplicate_assistant_after_stale_owner_resume(tmp_path: Path) -> None:
    engine = create_conversation_engine(
        sqlite_path=tmp_path / "conversations.db",
        force_sqlite=True,
    )
    apply_migrations(engine)
    service = ConversationService(repository=ConversationRepository(engine=engine))
    conv = service.create_conversation("u1", title="t")
    pending = service.begin_assistant_message(
        conversation_id=conv.id,
        user_id="u1",
        request_id="dup-1",
    )
    service.finalize_assistant_message(
        message_id=pending.id,
        conversation_id=conv.id,
        user_id="u1",
        content="first",
        status=MessageStatus.COMPLETED.value,
    )
    # Stale owner resume attempting completed finalize — blocked.
    assert (
        service.finalize_assistant_message(
            message_id=pending.id,
            conversation_id=conv.id,
            user_id="u1",
            content="duplicate",
            status=MessageStatus.COMPLETED.value,
        )
        is None
    )
    _c, messages, total = service.get_conversation_with_messages(conv.id, "u1")
    assts = [m for m in messages if m.role == "assistant"]
    assert total == 1
    assert len(assts) == 1
    assert assts[0].content == "first"


def test_brain_busy_bounded_for_healthy_owner() -> None:
    d1 = RequestDeadline.start(total_seconds=30, request_id="busy-owner")
    register_active_deadline(d1)
    gen = _acquire_brain_lock("busy-owner", d1)
    assert gen is not None
    started = time.monotonic()
    d2 = RequestDeadline.start(total_seconds=5, request_id="busy-waiter")
    acquired = _acquire_brain_lock("busy-waiter", d2, timeout_seconds=0.2)
    elapsed = time.monotonic() - started
    assert acquired is None
    assert elapsed < 1.5
    _release_brain_lock("busy-owner", gen)
    unregister_active_deadline("busy-owner")


def test_diagnostics_safe_fields_no_secrets() -> None:
    d = RequestDeadline.start(total_seconds=5, request_id="diag-owner-secret-token")
    gen = _acquire_brain_lock("diag-owner-secret-token", d)
    assert gen is not None
    snap = brain_lock_diagnostics()
    assert "lock_state" in snap
    assert "generation" in snap
    assert "lock_age_ms" in snap
    assert "heartbeat_age_ms" in snap
    assert "stale_reclaim_count" in snap
    assert "password" not in str(snap).lower()
    assert "api_key" not in str(snap).lower()
    assert "openai" not in str(snap).lower()
    # Owner id is shortened, not full secret-like token dump expectation.
    assert snap["owner_request_id"] != "diag-owner-secret-token" or len(
        snap["owner_request_id"] or ""
    ) <= 16
    _release_brain_lock("diag-owner-secret-token", gen)


def test_phase19_5_disconnect_reproduction_then_recovery(tmp_path: Path) -> None:
    """Deterministic reproduction of Phase 19.5 permanent brain_busy failure."""
    titan = _make_titan(tmp_path)
    hold = threading.Event()
    cleanup_gate = threading.Event()
    first_gen_box: dict[str, int | None] = {"gen": None}

    def hung(message, *, stream=None):
        from brain.request_deadline import get_request_deadline

        # Capture generation via manager snapshot while owned.
        first_gen_box["gen"] = _brain_lock_manager.generation_snapshot()
        hold.set()
        # Simulate interrupted cleanup: stay hung until gate opens, ignoring
        # cancel briefly so ownership looks abandoned for reclaim.
        deadline = get_request_deadline()
        while not cleanup_gate.is_set():
            time.sleep(0.02)
        if deadline and deadline.cancelled:
            raise RequestCancelledError(last_completed_stage="provider")
        return _orchestration_result(response="late")

    titan.brain.process_request = hung  # type: ignore[method-assign]

    first_box: dict = {}

    def first_runner() -> None:
        first_box["payload"] = process_chat_message(
            "first hung stream",
            request_id="repro-1",
        )

    t1 = threading.Thread(target=first_runner)
    t1.start()
    assert hold.wait(3.0)

    # Client disconnect cancels; cleanup intentionally delayed.
    cancel_chat_request("repro-1")
    # Age ownership past stale while cancelled (abandoned SSE).
    aged = time.monotonic() - 120.0
    with _brain_lock_manager._state_lock:
        _brain_lock_manager._ownership.acquired_at = aged
        _brain_lock_manager._ownership.last_heartbeat_at = aged

    titan.brain.process_request = MagicMock(  # type: ignore[method-assign]
        return_value=_orchestration_result(response="second ok"),
    )
    second = process_chat_message("second after disconnect", request_id="repro-2")
    assert second.get("ok") is True
    assert second.get("error_code") is None

    # Old owner resumes cleanup — must not corrupt second ownership.
    cleanup_gate.set()
    t1.join(timeout=5)
    assert first_box["payload"]["error_code"] in {CANCELLED_CODE, STALE_OWNER_CODE}
    old_gen = first_gen_box["gen"]
    if old_gen is not None:
        assert not _ownership_still_valid(old_gen) or _brain_lock_owner_snapshot() != "repro-1"

    # Third request also completes — no permanent brain_busy.
    titan.brain.process_request = MagicMock(  # type: ignore[method-assign]
        return_value=_orchestration_result(response="third ok"),
    )
    third = process_chat_message("third", request_id="repro-3")
    assert third.get("ok") is True
    assert _brain_lock_owner_snapshot() is None
    assert _brain_lock.acquire(timeout=0.05)
    _brain_lock.release()


def test_next_request_succeeds_after_stale_reclaim(tmp_path: Path) -> None:
    d1 = RequestDeadline.start(total_seconds=30, request_id="gone")
    register_active_deadline(d1)
    gen = _acquire_brain_lock("gone", d1)
    assert gen is not None
    aged = time.monotonic() - 90.0
    with _brain_lock_manager._state_lock:
        _brain_lock_manager._ownership.acquired_at = aged
        _brain_lock_manager._ownership.last_heartbeat_at = aged
    unregister_active_deadline("gone")  # owner no longer registered

    titan = _make_titan(tmp_path)
    titan.brain.process_request = MagicMock(return_value=_orchestration_result())
    payload = process_chat_message("after reclaim", request_id="next-1")
    assert payload["ok"] is True
    assert _brain_lock_owner_snapshot() is None

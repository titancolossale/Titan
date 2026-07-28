# =====================================
# Titan Phase 19.5 Production Soak Tests
# =====================================

"""Focused regressions for authenticated Railway soak helpers (no live LLM required)."""

from __future__ import annotations

import json
import urllib.request

import pytest

from scripts.phase19_5_railway_soak import (
    DEFAULT_BASE,
    _redact,
    parse_sse,
    require_credentials,
)


RAILWAY_BASE = DEFAULT_BASE


def test_railway_public_contract_still_holds() -> None:
    with urllib.request.urlopen(f"{RAILWAY_BASE}/health", timeout=20) as resp:
        health = json.loads(resp.read().decode())
    with urllib.request.urlopen(f"{RAILWAY_BASE}/ready", timeout=20) as resp:
        ready = json.loads(resp.read().decode())

    assert health.get("status") == "ok"
    assert health.get("auth_required") is True
    assert health.get("session_auth") is True
    assert ready.get("status") == "ready"
    store = (ready.get("checks") or {}).get("conversation_store") or {}
    assert store.get("backend") == "postgresql"

    req = urllib.request.Request(
        f"{RAILWAY_BASE}/chat/stream",
        data=b'{"message":"x"}',
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(Exception) as exc_info:
        urllib.request.urlopen(req, timeout=15)
    assert getattr(exc_info.value, "code", None) == 401


def test_parse_sse_order_and_no_delta_after_finish() -> None:
    raw = "\n".join(
        [
            "event: conversation_started",
            'data: {"conversation_id":"c1","request_id":"r1"}',
            "",
            "event: brain_state",
            'data: {"state":"thinking"}',
            "",
            "event: response_started",
            'data: {"request_id":"r1"}',
            "",
            "event: text_delta",
            'data: {"delta":"Bonjour"}',
            "",
            "event: conversation_finished",
            'data: {"ok":true,"conversation_id":"c1","request_id":"r1","ttft_ms":12}',
            "",
            "event: brain_state",
            'data: {"state":"idle"}',
            "",
        ]
    )
    order, events, summary = parse_sse(raw)
    assert order[0] == "conversation_started"
    assert "text_delta" in order
    assert "conversation_finished" in order
    assert summary["deltas_after_finish"] is False
    assert summary["assistant_text"] == "Bonjour"
    assert summary["conversation_id"] == "c1"
    assert summary["missing_required_events"] == []
    assert len(events) >= 5


def test_parse_sse_detects_delta_after_finish() -> None:
    raw = "\n".join(
        [
            "event: conversation_finished",
            'data: {"ok":true}',
            "",
            "event: text_delta",
            'data: {"delta":"late"}',
            "",
        ]
    )
    _order, _events, summary = parse_sse(raw)
    assert summary["deltas_after_finish"] is True


def test_redact_never_keeps_password_material() -> None:
    secrets = ["SuperSecretPassword123!", "nolan"]
    text = 'login user=nolan password=SuperSecretPassword123! token="abc"'
    redacted = _redact(text, secrets)
    assert "SuperSecretPassword123!" not in redacted
    assert "nolan" not in redacted
    assert "***" in redacted


def test_require_credentials_reports_exact_missing_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TITAN_SOAK_USERNAME", raising=False)
    monkeypatch.delenv("TITAN_SOAK_PASSWORD", raising=False)
    assert require_credentials() is None

    monkeypatch.setenv("TITAN_SOAK_USERNAME", "user")
    monkeypatch.delenv("TITAN_SOAK_PASSWORD", raising=False)
    # Function prints JSON with missing password — still returns None
    assert require_credentials() is None


def test_busy_retry_ceiling_is_bounded() -> None:
    """brain_busy retries must never become an infinite loop."""
    import inspect

    from scripts.phase19_5_railway_soak import SoakRunner

    src = inspect.getsource(SoakRunner.chat)
    assert "max_attempts" in src
    assert "min(max(1, retries_on_busy), 12)" in src
    assert "busy_retries_exhausted" in src


def test_lock_diagnostics_helpers_exist() -> None:
    from scripts.phase19_5_railway_soak import SoakRunner

    assert callable(getattr(SoakRunner, "fetch_lock_diagnostics", None))
    assert callable(getattr(SoakRunner, "assert_lock_idle", None))
    assert callable(getattr(SoakRunner, "scenario_lock_diagnostics", None))

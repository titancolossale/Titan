# =====================================
# Titan Phase 11.1 — Web App ↔ Brain Integration Tests
# =====================================

"""Focused tests for production chat contract, auth, telemetry honesty, and frontend guards."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.chat_service import (
    PROVIDER_UNAVAILABLE_CODE,
    clear_idempotency_cache,
    process_chat_message,
)
from api.titan_service import get_titan, reset_titan, set_titan
from brain.llm import LLM_ERROR_MESSAGE
from brain.natural_language_orchestrator import (
    DetectedIntent,
    OrchestrationResult,
    PipelineDecision,
    RequestAnalysis,
    SystemsUsed,
)
from config.settings import TITAN_WEB_MAX_MESSAGE_LENGTH
from core.titan import Titan
from tools.tool_manager import ToolManager

V2 = Path(__file__).resolve().parent.parent / "web" / "v2"


def _orchestration_result(
    *,
    response: str = "Réponse Brain réelle.",
    intent: DetectedIntent = DetectedIntent.CONVERSATION,
    confidence: float = 0.91,
    artifacts: dict | None = None,
    duration: float = 0.12,
) -> OrchestrationResult:
    analysis = RequestAnalysis(
        request="test",
        normalized="test",
        tokens=("test",),
        user="Nolan",
    )
    return OrchestrationResult(
        request_analysis=analysis,
        detected_intent=intent,
        pipeline_decision=PipelineDecision(
            intent=intent,
            systems=(),
            awareness_systems=(),
            rationale="test",
        ),
        systems_used=SystemsUsed(planned=(), invoked=["brain_think"], skipped=[]),
        reasoning_summary="Routage conversation.",
        confidence=confidence,
        final_response=response,
        artifacts=artifacts or {},
        duration_seconds=duration,
    )


@pytest.fixture
def web_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "phase11-test-secret"
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", secret)
    monkeypatch.setattr("config.settings.TITAN_WEB_ENABLED", True)
    monkeypatch.setattr("config.settings.TITAN_WEB_SECRET_KEY", secret)
    return secret


@pytest.fixture
def brain_client(web_secret: str, tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    reset_titan()
    clear_idempotency_cache()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    titan.brain.tool_manager = tool_manager
    titan.status = "ONLINE"
    titan.brain.process_request = MagicMock(return_value=_orchestration_result())
    set_titan(titan)

    with patch("config.settings.TITAN_WEB_ENABLED", True), patch(
        "config.settings.get_web_secret_key", return_value=web_secret
    ), patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        yield client

    clear_idempotency_cache()
    reset_titan()


@pytest.fixture
def auth_headers(web_secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {web_secret}"}


# --- Auth & contract ---------------------------------------------------------


def test_unauthenticated_api_chat_rejected(brain_client: TestClient) -> None:
    response = brain_client.post("/api/chat", json={"message": "Bonjour"})
    assert response.status_code == 401


def test_unauthenticated_chat_stream_rejected(brain_client: TestClient) -> None:
    response = brain_client.post("/chat/stream", json={"message": "Bonjour"})
    assert response.status_code == 401


def test_authenticated_api_chat_reaches_brain(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    response = brain_client.post(
        "/api/chat",
        json={"message": "Salut Titan", "conversation_id": "c-11"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["response"] == "Réponse Brain réelle."
    assert payload["conversation_id"] == "c-11"
    assert payload["message_id"]
    assert payload["runtime"]["state"] == "finished"
    assert "receiving" in payload["runtime"]["stages"]
    assert "finished" in payload["runtime"]["stages"]
    get_titan().brain.process_request.assert_called_once()


def test_empty_message_rejected(brain_client: TestClient, auth_headers: dict) -> None:
    response = brain_client.post(
        "/api/chat",
        json={"message": "   "},
        headers=auth_headers,
    )
    assert response.status_code in {400, 422}


def test_oversized_message_rejected(brain_client: TestClient, auth_headers: dict) -> None:
    response = brain_client.post(
        "/api/chat",
        json={"message": "x" * (TITAN_WEB_MAX_MESSAGE_LENGTH + 1)},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_provider_failure_returns_retryable_error(
    web_secret: str,
    tmp_path,
    auth_headers: dict,
) -> None:
    reset_titan()
    clear_idempotency_cache()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(response=LLM_ERROR_MESSAGE),
    )
    set_titan(titan)

    with patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        response = client.post(
            "/api/chat",
            json={"message": "Test provider"},
            headers=auth_headers,
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == PROVIDER_UNAVAILABLE_CODE
    assert payload["error"]["retryable"] is True
    assert "OPENAI" not in json.dumps(payload).upper()
    clear_idempotency_cache()
    reset_titan()


def test_brain_exception_does_not_crash_server(
    web_secret: str,
    tmp_path,
    auth_headers: dict,
) -> None:
    reset_titan()
    clear_idempotency_cache()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.process_request = MagicMock(side_effect=RuntimeError("boom"))
    set_titan(titan)

    with patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        response = client.post(
            "/api/chat",
            json={"message": "Survive"},
            headers=auth_headers,
        )

    # Graceful Brain fallback → structured error, server still alive.
    assert response.status_code == 500
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["retryable"] is True
    health = client.get("/health")
    assert health.status_code == 200
    clear_idempotency_cache()
    reset_titan()


def test_successful_response_follows_canonical_contract(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    response = brain_client.post(
        "/api/chat",
        json={
            "message": "Ping",
            "client_request_id": "client-req-1",
            "conversation_id": "conv-1",
        },
        headers=auth_headers,
    )
    payload = response.json()
    assert payload["ok"] is True
    assert payload["conversation_id"] == "conv-1"
    assert payload["message_id"].startswith("msg-")
    assert payload["request_id"] == "client-req-1"
    assert isinstance(payload["response"], str) and payload["response"]
    runtime = payload["runtime"]
    assert runtime["state"] == "finished"
    assert isinstance(runtime["stages"], list)
    assert runtime["memory_used"] is False
    assert runtime["tools_used"] == []
    assert runtime["model"]
    assert isinstance(runtime["duration_ms"], int)


def test_duplicate_client_request_id_is_idempotent(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    body = {
        "message": "Idempotent turn",
        "client_request_id": "dup-req-42",
        "conversation_id": "conv-dup",
    }
    first = brain_client.post("/api/chat", json=body, headers=auth_headers)
    second = brain_client.post("/api/chat", json=body, headers=auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["message_id"] == second.json()["message_id"]
    assert first.json()["response"] == second.json()["response"]
    # Brain invoked once — second hit served from cache.
    assert get_titan().brain.process_request.call_count == 1


def test_no_provider_key_in_responses_or_frontend(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    response = brain_client.post(
        "/api/chat",
        json={"message": "Secret check"},
        headers=auth_headers,
    )
    body = json.dumps(response.json()).lower()
    assert "openai_api_key" not in body
    assert "sk-" not in body

    for relative in (
        "core/backend-bridge.js",
        "core/web-auth.js",
        "conversation/conversation-manager.js",
        "index.html",
    ):
        asset = (V2 / relative).read_text(encoding="utf-8").lower()
        assert "openai_api_key" not in asset
        assert "sk-proj" not in asset


def test_health_and_ready_remain_public(brain_client: TestClient) -> None:
    assert brain_client.get("/health").status_code == 200
    assert brain_client.get("/ready").status_code == 200


def test_canonical_app_frontend_shell_unchanged(brain_client: TestClient) -> None:
    response = brain_client.get("/app/")
    assert response.status_code == 200
    body = response.text
    assert 'name="titan-canonical-reference" content="final"' in body
    assert "titan-v2-root" in body
    assert "./design/canonical-final.css" in body


def test_runtime_telemetry_honest_without_fake_tools(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    payload = brain_client.post(
        "/api/chat",
        json={"message": "Sans outils"},
        headers=auth_headers,
    ).json()
    runtime = payload["runtime"]
    assert runtime["tools_used"] == []
    assert runtime["memory_used"] is False
    assert "executing_tools" not in runtime["stages"]
    assert "retrieving_memory" not in runtime["stages"]


def test_stream_does_not_claim_fake_tool_stages(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    response = brain_client.post(
        "/chat/stream",
        headers={**auth_headers, "Accept": "text/event-stream"},
        json={"message": "Stream test", "conversation_id": "s1"},
    )
    assert response.status_code == 200
    body = response.text
    assert "event: conversation_finished" in body
    # Pre-Brain synthetic tool_execution removed in Phase 11.1.
    assert 'label": "Exécution outil' not in body


# --- Frontend static guarantees ----------------------------------------------


def test_frontend_duplicate_submit_guard() -> None:
    bridge = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    manager = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "this._submitting" in bridge
    assert "skipped: true" in bridge
    assert "if (!text || this._busy) return" in manager


def test_frontend_renders_responses_safely() -> None:
    renderer = (V2 / "conversation" / "message-renderer.js").read_text(encoding="utf-8")
    css = (V2 / "design" / "ui.css").read_text(encoding="utf-8")
    assert "bubble.textContent = text" in renderer
    assert "innerHTML" not in renderer or "showApprovalBanner" in renderer
    # Approval banner must use textContent, not string-interpolated innerHTML.
    assert "body.textContent = String(summary" in renderer
    assert "white-space: pre-wrap" in css


def test_frontend_expired_session_redirects_to_login() -> None:
    bridge = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    auth = (V2 / "core" / "web-auth.js").read_text(encoding="utf-8")
    assert "SessionExpiredError" in bridge
    assert "redirectToLogin" in bridge
    assert "status === 401" in bridge
    assert "function redirectToLogin" in auth
    assert "/login?next=" in auth


def test_process_chat_message_provider_failure_marks_runtime() -> None:
    reset_titan()
    clear_idempotency_cache()
    titan = Titan()
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(response=LLM_ERROR_MESSAGE),
    )
    set_titan(titan)
    payload = process_chat_message("fail", request_id="prov-1")
    assert payload["ok"] is False
    assert payload["retryable"] is True
    assert payload["runtime"]["state"] == "error"
    assert "error" in payload["runtime"]["stages"]
    clear_idempotency_cache()
    reset_titan()

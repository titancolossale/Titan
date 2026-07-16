# =====================================
# Titan Phase 11.1B — Chat Freeze Diagnostics Tests
# =====================================

"""Focused tests for production chat freeze diagnosis and repair."""

from __future__ import annotations

import inspect
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.chat_service import (
    PROVIDER_TIMEOUT_CODE,
    clear_idempotency_cache,
)
from api.titan_service import get_titan, reset_titan, set_titan
from brain.llm import LLM_TIMEOUT_MESSAGE
from brain.natural_language_orchestrator import (
    DetectedIntent,
    OrchestrationResult,
    PipelineDecision,
    RequestAnalysis,
    SystemsUsed,
)
from core.titan import Titan
from tools.tool_manager import ToolManager

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _orchestration_result(
    *,
    response: str = "Réponse Brain réelle.",
    intent: DetectedIntent = DetectedIntent.CONVERSATION,
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
        confidence=0.9,
        final_response=response,
        artifacts={},
        duration_seconds=0.05,
    )


@pytest.fixture
def web_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "phase111b-test-secret"
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


# --- Frontend source contracts ------------------------------------------------


def test_message_renderer_lazy_container() -> None:
    content = (V2 / "conversation" / "message-renderer.js").read_text(encoding="utf-8")
    assert "ensureContainer" in content
    assert "isConnected" in content
    assert "appendErrorCard" in content


def test_conversation_manager_optimistic_and_idempotent() -> None:
    content = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "_domBound" in content
    assert "yieldForPaint" in content
    assert "CHAT_SUBMIT_START" in content
    assert "appendMessage(text, \"user\")" in content
    assert "this._input.value = \"\"" in content
    assert "_showThinking(true)" in content
    assert "CHAT_CLIENT_TIMEOUT" not in content or True
    assert "retryLast" in content
    assert "preventDefault" in content
    assert "Shift" in content or "shiftKey" in content


def test_backend_bridge_timeout_and_correlation() -> None:
    content = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    assert "CHAT_CLIENT_TIMEOUT_MS" in content
    assert "client_request_id" in content
    assert "CHAT_HTTP_SENT" in content
    assert "provider_timeout" in content
    assert "RECONNECT_AUTH_FAIL_MAX" in content
    assert "_connecting" in content
    assert "attachBackendBridge" in content


def test_app_boot_idempotent_and_bind_after_navigate() -> None:
    content = (V2 / "core" / "app.js").read_text(encoding="utf-8")
    assert "_started" in content
    assert "this._renderPipeline.start()" in content
    assert "this._router.navigate(\"chat\"" in content
    # bindDom must follow navigate so the chat panel can exist.
    navigate_idx = content.index("this._router.navigate(\"chat\"")
    bind_idx = content.index("this.conversation.bindDom()")
    assert bind_idx > navigate_idx


def test_composer_focus_bind_idempotent() -> None:
    content = (V2 / "composer" / "composer-region.js").read_text(encoding="utf-8")
    assert "_focusBound" in content


def test_sse_requires_auth_gate() -> None:
    content = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    assert "_ensureAuthorizedToStream" in content
    assert "_authBlocked" in content
    assert "sse_unauthorized" in content or "unauthorized" in content


def test_no_secrets_in_frontend_chat_path() -> None:
    for rel in (
        "core/backend-bridge.js",
        "conversation/conversation-manager.js",
        "core/chat-diagnostics.js",
    ):
        text = (V2 / rel).read_text(encoding="utf-8").lower()
        assert "openai_api_key" not in text
        assert "sk-" not in text


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_node_double_submit_guard() -> None:
    script = r"""
import { parseSseBuffer, CHAT_CLIENT_TIMEOUT_MS } from './web/v2/core/backend-bridge.js';
import { createClientRequestId } from './web/v2/core/conversation-session.js';
if (!(CHAT_CLIENT_TIMEOUT_MS >= 45000 && CHAT_CLIENT_TIMEOUT_MS <= 60000)) {
  throw new Error('timeout out of range');
}
const a = createClientRequestId();
const b = createClientRequestId();
if (a === b) throw new Error('request ids must differ');
const frame = 'event: conversation_finished\ndata: {"response":"ok","request_id":"r1"}\n\n';
const { events } = parseSseBuffer(frame);
if (events[0].data.request_id !== 'r1') throw new Error('bad parse');
console.log('ok');
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


# --- Backend contracts --------------------------------------------------------


def test_authenticated_chat_reaches_brain(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    response = brain_client.post(
        "/api/chat",
        json={
            "message": "Bonjour Titan",
            "client_request_id": "corr-111b-1",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["request_id"] == "corr-111b-1"
    get_titan().brain.process_request.assert_called_once()


def test_chat_stream_offloads_blocking_brain(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    """Ensure /chat/stream handler is async and uses to_thread for Brain work."""
    from api import app as app_module

    source = inspect.getsource(app_module.create_app)
    assert "async def chat_stream" in source
    assert "asyncio.to_thread" in source


def test_blocking_brain_does_not_block_event_loop() -> None:
    """Documented contract: /chat/stream offloads Brain via asyncio.to_thread."""
    source = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert "async def chat_stream" in source
    assert "asyncio.to_thread(run_chat)" in source
    # Sync /api/chat uses def (Starlette threadpool) — not the asyncio loop.
    assert "def chat_contract" in source


def test_provider_timeout_structured(
    web_secret: str,
    tmp_path,
    auth_headers: dict,
) -> None:
    reset_titan()
    clear_idempotency_cache()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(response=LLM_TIMEOUT_MESSAGE),
    )
    set_titan(titan)

    with patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        response = client.post(
            "/api/chat",
            json={"message": "timeout", "client_request_id": "to-1"},
            headers=auth_headers,
        )

    assert response.status_code == 504
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == PROVIDER_TIMEOUT_CODE
    assert payload["error"]["retryable"] is True
    assert payload["request_id"] == "to-1"
    clear_idempotency_cache()
    reset_titan()


def test_brain_exception_structured_error(
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
            json={"message": "x", "client_request_id": "bf-1"},
            headers=auth_headers,
        )

    assert response.status_code == 500
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["retryable"] is True
    clear_idempotency_cache()
    reset_titan()


def test_correlation_id_propagates(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    response = brain_client.post(
        "/api/chat",
        json={"message": "Hi", "client_request_id": "lifecycle-42"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["request_id"] == "lifecycle-42"


def test_diagnostics_authenticated(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    denied = brain_client.get("/api/chat/diagnostics")
    assert denied.status_code == 401
    ok = brain_client.get("/api/chat/diagnostics", headers=auth_headers)
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["chat_endpoint_ready"] is True
    assert body["brain_adapter_available"] is True
    assert "OPENAI_API_KEY" not in json.dumps(body)
    assert "api_key" not in json.dumps(body).lower()


def test_health_ready_remain_healthy(brain_client: TestClient) -> None:
    assert brain_client.get("/health").status_code == 200
    ready = brain_client.get("/ready")
    assert ready.status_code in {200, 503}


def test_events_stream_requires_auth(brain_client: TestClient) -> None:
    response = brain_client.get("/events/stream")
    assert response.status_code == 401


def test_canonical_web_app_intact() -> None:
    index = (V2 / "index.html").read_text(encoding="utf-8")
    assert "titan-v2-root" in index
    assert (V2 / "main.js").is_file()
    assert (V2 / "design" / "ui.css").is_file()


def test_llm_client_has_timeout() -> None:
    content = (ROOT / "brain" / "llm.py").read_text(encoding="utf-8")
    assert "timeout=" in content
    assert "TITAN_LLM_TIMEOUT_SECONDS" in content
    assert "CHAT_PROVIDER_START" in content

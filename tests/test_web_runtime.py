# =====================================
# Titan Web Runtime V1 Tests
# =====================================

"""Comprehensive tests for Web Runtime V1 — Brain.process_request() web integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.chat_service import process_chat_message, validate_message_size
from api.titan_service import get_titan, reset_titan, set_titan
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


def _orchestration_result(
    *,
    response: str = "Réponse de test depuis Brain.",
    intent: DetectedIntent = DetectedIntent.CONVERSATION,
    confidence: float = 0.92,
    artifacts: dict | None = None,
) -> OrchestrationResult:
    analysis = RequestAnalysis(
        request="Salut",
        normalized="salut",
        tokens=("salut",),
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
        duration_seconds=0.05,
    )


@dataclass
class _FakePatch:
    approved: bool = False
    patch_id: str = "patch-123"


@pytest.fixture
def web_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "test-web-runtime-secret"
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", secret)
    monkeypatch.setattr("config.settings.TITAN_WEB_ENABLED", True)
    monkeypatch.setattr("config.settings.TITAN_WEB_SECRET_KEY", secret)
    return secret


@pytest.fixture
def runtime_client(web_secret: str, tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    reset_titan()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    titan.brain.tool_manager = tool_manager
    titan.status = "ONLINE"
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(),
    )
    set_titan(titan)

    with patch("config.settings.TITAN_WEB_ENABLED", True), patch(
        "config.settings.get_web_secret_key", return_value=web_secret
    ), patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        yield client

    reset_titan()


@pytest.fixture
def auth_headers(web_secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {web_secret}"}


def test_api_chat_message_requires_auth(runtime_client: TestClient) -> None:
    response = runtime_client.post(
        "/api/chat/message",
        json={"message": "Bonjour"},
    )
    assert response.status_code == 401


def test_api_chat_message_authenticated(runtime_client: TestClient, auth_headers: dict) -> None:
    response = runtime_client.post(
        "/api/chat/message",
        json={"message": "Salut Titan", "conversation_id": "conv-abc"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "Réponse de test depuis Brain."
    assert payload["conversation_id"] == "conv-abc"
    assert payload["detected_intent"] == DetectedIntent.CONVERSATION.value
    assert payload["confidence"] == 0.92
    assert "systems_used" in payload
    assert "pipeline_summary" in payload
    assert "reasoning_summary" in payload
    assert "brain_state" in payload
    assert payload["request_id"]
    assert "timestamp" in payload
    assert "duration_seconds" in payload


def test_api_chat_message_delegates_to_process_request(
    runtime_client: TestClient,
    auth_headers: dict,
) -> None:
    runtime_client.post(
        "/api/chat/message",
        json={"message": "Test delegation"},
        headers=auth_headers,
    )
    titan = get_titan()
    titan.brain.process_request.assert_called_once()
    args, kwargs = titan.brain.process_request.call_args
    assert args[0] == "Test delegation"


def test_shared_brain_instance_reused(runtime_client: TestClient, auth_headers: dict) -> None:
    first = get_titan()
    runtime_client.post(
        "/api/chat/message",
        json={"message": "Un"},
        headers=auth_headers,
    )
    second = get_titan()
    assert first is second
    runtime_client.post(
        "/api/chat/message",
        json={"message": "Deux"},
        headers=auth_headers,
    )
    assert get_titan() is first
    assert get_titan().brain.process_request.call_count == 2


def test_conversation_id_preserved(runtime_client: TestClient, auth_headers: dict) -> None:
    response = runtime_client.post(
        "/api/chat/message",
        json={"message": "Hello", "conversation_id": "session-42"},
        headers=auth_headers,
    )
    assert response.json()["conversation_id"] == "session-42"


def test_legacy_chat_route_uses_process_request(
    runtime_client: TestClient,
    auth_headers: dict,
) -> None:
    response = runtime_client.post(
        "/chat",
        json={"message": "Legacy"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_intent"] == DetectedIntent.CONVERSATION.value
    get_titan().brain.process_request.assert_called()


def test_planning_response_serialization(
    web_secret: str,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict,
) -> None:
    reset_titan()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.tool_manager = titan.tools
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(
            response="Voici le plan.",
            intent=DetectedIntent.PLANNING,
            confidence=0.88,
        ),
    )
    set_titan(titan)

    with patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        response = client.post(
            "/api/chat/message",
            json={"message": "Planifie mon projet"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_intent"] == DetectedIntent.PLANNING.value
    assert payload["brain_state"] == "planning"
    reset_titan()


def test_approval_required_response(
    web_secret: str,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict,
) -> None:
    reset_titan()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.tool_manager = titan.tools
    patch_obj = _FakePatch(approved=False, patch_id="patch-xyz")
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(
            response="Patch généré — approbation requise.",
            intent=DetectedIntent.CODE_GENERATION,
            artifacts={"generated_patch": patch_obj},
        ),
    )
    set_titan(titan)

    with patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        response = client.post(
            "/api/chat/message",
            json={"message": "Génère le patch"},
            headers=auth_headers,
        )

    payload = response.json()
    assert payload["approval_required"] is True
    assert payload["approval_id"] == "patch-xyz"
    assert payload["brain_state"] == "awaiting_approval"
    assert payload["execution_status"] == "awaiting_approval"
    reset_titan()


def test_request_size_validation(runtime_client: TestClient, auth_headers: dict) -> None:
    oversized = "x" * (TITAN_WEB_MAX_MESSAGE_LENGTH + 1)
    response = runtime_client.post(
        "/api/chat/message",
        json={"message": oversized},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_validate_message_size_raises() -> None:
    with pytest.raises(ValueError):
        validate_message_size("a" * (TITAN_WEB_MAX_MESSAGE_LENGTH + 1))


def test_no_secret_leakage_in_response(
    web_secret: str,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict,
) -> None:
    reset_titan()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.process_request = MagicMock(
        return_value=_orchestration_result(
            artifacts={"error": "OPENAI_API_KEY=sk-secret-value"},
        ),
    )
    set_titan(titan)

    with patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        response = client.post(
            "/api/chat/message",
            json={"message": "test"},
            headers=auth_headers,
        )

    body = json.dumps(response.json())
    assert "sk-secret" not in body
    assert "OPENAI_API_KEY" not in body
    reset_titan()


def test_chat_stream_emits_orchestration_events(
    runtime_client: TestClient,
    auth_headers: dict,
) -> None:
    response = runtime_client.post(
        "/chat/stream",
        headers={**auth_headers, "Accept": "text/event-stream"},
        json={"message": "Bonjour", "conversation_id": "stream-conv"},
    )
    assert response.status_code == 200
    body = response.text
    assert "event: orchestration_started" in body
    assert "event: orchestration_finished" in body
    assert "event: conversation_finished" in body
    assert '"conversation_id": "stream-conv"' in body or '"conversation_id":"stream-conv"' in body


def test_integration_mocked_orchestration_end_to_end(
    runtime_client: TestClient,
    auth_headers: dict,
) -> None:
    """Web request → API → process_request mock → structured JSON."""
    response = runtime_client.post(
        "/api/chat/message",
        json={
            "message": "Explique le module Brain",
            "request_id": "req-integration-1",
            "client_metadata": {"source": "pytest"},
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req-integration-1"
    assert payload["response"]
    assert payload["execution_status"] in {"completed", "awaiting_approval", "error"}


def test_process_chat_message_records_conversation(tmp_path) -> None:
    reset_titan()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.process_request = MagicMock(return_value=_orchestration_result())
    set_titan(titan)

    payload = process_chat_message("Salut", conversation_id="c1")
    assert payload["conversation_id"] == "c1"
    assert titan.conversation.history[-1]["speaker"] == "Titan"
    reset_titan()

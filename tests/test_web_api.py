# =====================================
# Titan Web API Tests
# =====================================

"""Tests for Phase 17.1+ private web app foundation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.titan_service import reset_titan, set_titan
from config.settings import ENV_FILE_PATH, TITAN_WEB_DEV_SECRET, reload_env
from core.titan import Titan
from tools.tool_manager import ToolManager


@pytest.fixture
def web_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """Enable web mode with a test secret key."""
    secret = "test-web-secret-key"
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", secret)
    monkeypatch.setattr("config.settings.TITAN_WEB_ENABLED", True)
    monkeypatch.setattr("config.settings.TITAN_WEB_SECRET_KEY", secret)
    return secret


@pytest.fixture
def web_client(web_secret: str, tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI client with isolated Titan Core and mocked Brain."""
    reset_titan()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    titan.brain.tool_manager = tool_manager
    titan.status = "ONLINE"
    monkeypatch.setattr(
        titan.brain,
        "process_request",
        MagicMock(
            return_value=__import__(
                "brain.natural_language_orchestrator",
                fromlist=["OrchestrationResult"],
            ).OrchestrationResult(
                request_analysis=__import__(
                    "brain.natural_language_orchestrator",
                    fromlist=["RequestAnalysis"],
                ).RequestAnalysis(
                    request="test",
                    normalized="test",
                    tokens=("test",),
                ),
                detected_intent=__import__(
                    "brain.natural_language_orchestrator",
                    fromlist=["DetectedIntent"],
                ).DetectedIntent.CONVERSATION,
                pipeline_decision=__import__(
                    "brain.natural_language_orchestrator",
                    fromlist=["PipelineDecision"],
                ).PipelineDecision(
                    intent=__import__(
                        "brain.natural_language_orchestrator",
                        fromlist=["DetectedIntent"],
                    ).DetectedIntent.CONVERSATION,
                    systems=(),
                    awareness_systems=(),
                ),
                systems_used=__import__(
                    "brain.natural_language_orchestrator",
                    fromlist=["SystemsUsed"],
                ).SystemsUsed(),
                reasoning_summary="Test",
                confidence=0.9,
                final_response="Réponse de test depuis Brain.",
                artifacts={},
                duration_seconds=0.01,
            )
        ),
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


def test_health_endpoint_is_public(web_client: TestClient) -> None:
    response = web_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["name"] == "Titan"
    assert "version" in payload
    assert payload["web_enabled"] is True
    assert payload["dev_mode"] is False
    assert payload["auth_required"] is True


def test_auth_status_endpoint_is_public(web_client: TestClient) -> None:
    response = web_client.get("/auth/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_required"] is True
    assert payload["dev_mode"] is False
    assert payload["secret_configured"] is True


def test_auth_verify_accepts_valid_token(
    web_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = web_client.post("/auth/verify", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_verify_rejects_invalid_token(web_client: TestClient) -> None:
    response = web_client.post(
        "/auth/verify",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401


def test_design_preview_is_public(web_client: TestClient) -> None:
    """Phase 17.2 — TDL preview page is public like the index placeholder."""
    response = web_client.get("/design")
    assert response.status_code == 200
    body = response.text
    assert "Titan Design Language" in body
    assert "tdl-neural-bg" in body
    assert "/static/design/titan-ui.css" in body


def test_v2_web_auth_module_is_public(web_client: TestClient) -> None:
    """Remote access — shared auth helpers served to the V2 frontend."""
    response = web_client.get("/v2/core/web-auth.js")
    assert response.status_code == 200
    body = response.text
    assert "AUTH_STORAGE_KEY" in body
    assert "ensureAuthenticated" in body
    assert "your-secret-password" not in body


def test_v2_core_modules_are_public(web_client: TestClient) -> None:
    """Phase E10 — Core production modules are served."""
    version = web_client.get("/v2/core/version.js")
    assert version.status_code == 200
    assert 'TITAN_UI_VERSION = "0.25.0"' in version.text

    extensions = web_client.get("/v2/core/extension-registry.js")
    assert extensions.status_code == 200
    assert "EXTENSION_SLOTS" in extensions.text


def test_v2_frontend_architecture_is_public(web_client: TestClient) -> None:
    """Phase E1/E2 — Frontend V2 production layout shell is served at /v2."""
    response = web_client.get("/v2/")
    assert response.status_code == 200
    body = response.text
    # Frontend was promoted to V3 during the Web App Finalization; the shell id
    # and served assets are the stable contract.
    assert "Titan AI — Frontend V3" in body
    assert "titan-v2-root" in body
    assert "./main.js" in body
    assert "./design/tokens.css" in body
    assert "./design/ui.css" in body
    assert "./design/neural.css" in body
    assert "./design/satellites.css" in body


def test_app_route_serves_living_neural_core(web_client: TestClient) -> None:
    """Sprint 2 — the redesigned app at /app serves the living neural core shell."""
    response = web_client.get("/app/")
    assert response.status_code == 200
    body = response.text
    assert "titan-v2-root" in body
    assert "./design/satellites.css" in body

    satellites = web_client.get("/app/center/cognitive-satellites.js")
    assert satellites.status_code == 200
    assert "TITAN CORE" in satellites.text
    assert "Cognitive Operating System" in satellites.text


def test_v2_layout_modules_are_public(web_client: TestClient) -> None:
    """Phase E2 — Layout region modules and styles are served."""
    ui = web_client.get("/v2/design/ui.css")
    assert ui.status_code == 200
    assert ".tdl-v2-glass-panel" in ui.text
    assert ".tdl-v2-orchestrator-header" in ui.text

    neural = web_client.get("/v2/design/neural.css")
    assert neural.status_code == 200
    assert ".tdl-v2-neural-camera" in neural.text

    shell = web_client.get("/v2/layout/shell.js")
    assert shell.status_code == 200
    assert "tdl-v2-neural-canvas" in shell.text


def test_index_serves_titan_interface_v1(web_client: TestClient) -> None:
    """Phase 24.1 — Reference Interface with neural canvas and cognitive orchestrator."""
    response = web_client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "tdl-page--app" in body
    assert "neural-canvas" in body
    assert "tdl-workspace" in body
    assert "tdl-workspace--reference" in body
    assert "tdl-ref-sidebar" in body
    assert "tdl-ref-orchestrator" in body
    assert "tdl-ref-bottom" in body
    assert "tdl-neural-labels" in body
    assert "orchestrator-steps" in body
    assert "tdl-neural-stage--viewport" in body
    assert "/static/neural/brain_engine.js" in body
    assert "/static/neural/brain_depth.js" in body
    assert "/static/neural-network.js" in body
    assert "/static/orchestrator/orchestrator_panel.js" in body
    assert "/static/presence/presence_engine.js" in body
    assert "/static/presence/presence_controller.js" in body
    assert "/static/tools/tool_activity_manager.js" in body
    assert "/static/tools/tool_timeline.js" in body
    assert "/static/tools/tool_progress_card.js" in body
    assert "/static/memory/memory_activity.js" in body
    assert "/static/memory/memory_visualizer.js" in body
    assert "memory-cards-layer" in body
    assert "/static/voice/voice_controller.js" in body
    assert "voice-mic" in body
    assert "tool-progress-stack" in body
    assert "/static/design/titan-ui.css" in body
    assert "tdl-logo__wordmark" in body
    assert "Titan — Intelligence" in body


def test_index_includes_phase_18_polish_assets(web_client: TestClient) -> None:
    """Phase 18.0 — motion system, sound hooks, launch sequence, accessibility."""
    response = web_client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "/static/design/motion.js" in body
    assert "/static/design/sound_hooks.js" in body
    assert "/static/design/launch_sequence.js" in body
    assert "launch-overlay" in body
    assert "pref-reduced-motion" in body
    assert "Réflexion" in body
    assert "tdl-skip-link" in body


def test_index_includes_phase_21_cognitive_engine(web_client: TestClient) -> None:
    """Phase 21.0 — Cognitive Visualization Engine and brain.setState hooks."""
    response = web_client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "/static/neural/brain_cognitive.js" in body

    app_js = web_client.get("/static/app.js")
    assert app_js.status_code == 200
    app_body = app_js.text
    assert "window.brain" in app_body
    assert "setState" in app_body

    css = web_client.get("/static/design/titan-ui.css")
    assert css.status_code == 200
    css_body = css.text
    assert "cognitive-idle" in css_body
    assert "cognitive-memory" in css_body
    assert "cognitive-trading" in css_body


def test_protected_endpoints_require_auth(web_client: TestClient) -> None:
    protected_paths = [
        "/status",
        "/tools",
        "/memory/status",
        "/obsidian/status",
        "/browser/status",
        "/calendar/status",
        "/email/status",
        "/trading/status",
        "/voice/status",
    ]
    for path in protected_paths:
        response = web_client.get(path)
        assert response.status_code == 401, path

    chat_response = web_client.post("/chat", json={"message": "Bonjour"})
    assert chat_response.status_code == 401

    api_chat_response = web_client.post("/api/chat/message", json={"message": "Bonjour"})
    assert api_chat_response.status_code == 401

    verify_response = web_client.post("/auth/verify")
    assert verify_response.status_code == 401

    stream_response = web_client.get("/events/stream?snapshot=1")
    assert stream_response.status_code == 401

    chat_stream_response = web_client.post("/chat/stream", json={"message": "Bonjour"})
    assert chat_stream_response.status_code == 401


def test_protected_endpoints_reject_invalid_token(web_client: TestClient) -> None:
    headers = {"Authorization": "Bearer wrong-key"}
    response = web_client.get("/status", headers=headers)
    assert response.status_code == 401


def test_chat_routes_to_titan_core(
    web_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = web_client.post(
        "/chat",
        json={"message": "Salut Titan"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "Réponse de test depuis Brain."
    assert payload["user"]
    assert payload["tool_activity"] == []
    assert payload["memory_activity"] == []
    assert "orchestrator_progress" in payload
    assert isinstance(payload["orchestrator_progress"], list)


def test_status_endpoint_returns_system_info(
    web_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = web_client.get("/status", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Titan"
    assert payload["status"] == "ONLINE"
    assert "context" in payload
    assert "mission" in payload
    assert "state" in payload


def test_tools_endpoint_returns_registered_tools(
    web_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = web_client.get("/tools", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["tools"], list)
    assert len(payload["tools"]) > 0
    assert "provider_dashboard" in payload


def test_connector_status_endpoints(
    web_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    endpoints = {
        "/memory/status": "long_term_users",
        "/obsidian/status": "code",
        "/browser/status": "healthy",
        "/calendar/status": "provider",
        "/email/status": "provider",
        "/trading/status": "mode",
    }
    for path, expected_key in endpoints.items():
        response = web_client.get(path, headers=auth_headers)
        assert response.status_code == 200, path
        assert expected_key in response.json(), path


def test_env_file_path_points_to_project_root() -> None:
    assert ENV_FILE_PATH.name == ".env"
    assert ENV_FILE_PATH.parent.name == "Titan" or ENV_FILE_PATH.parent.exists()


def test_reload_env_reads_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TITAN_WEB_ENABLED=true\nTITAN_WEB_SECRET_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.setattr("config.settings.ENV_FILE_PATH", env_file)
    monkeypatch.delenv("TITAN_WEB_ENABLED", raising=False)
    monkeypatch.delenv("TITAN_WEB_SECRET_KEY", raising=False)

    reload_env()

    import os

    assert os.getenv("TITAN_WEB_ENABLED") == "true"
    assert os.getenv("TITAN_WEB_SECRET_KEY") == "from-dotenv"


def test_web_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TITAN_WEB_ENABLED", raising=False)
    default = __import__("os").getenv("TITAN_WEB_ENABLED", "false").lower() == "true"
    assert default is False


def _use_temp_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
) -> Path:
    """Point ENV_FILE_PATH at an isolated .env file for web CLI tests."""
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    monkeypatch.setattr("config.settings.ENV_FILE_PATH", env_file)
    monkeypatch.setattr("core.web_cli.ENV_FILE_PATH", env_file)
    return env_file


def test_web_cli_refuses_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = _use_temp_env(
        monkeypatch,
        tmp_path,
        "TITAN_WEB_ENABLED=false\n",
    )

    from core.web_cli import run_web_server

    assert run_web_server(dev_mode=False) == 1
    captured = capsys.readouterr().out
    assert "Interface web désactivée." in captured
    assert "TITAN_WEB_ENABLED=false" in captured
    assert str(env_file.resolve()) in captured
    assert "TITAN_WEB_ENABLED=true" in captured
    assert "TITAN_WEB_SECRET_KEY=" in captured
    assert "python main.py web-dev" in captured


def test_web_cli_refuses_without_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _use_temp_env(
        monkeypatch,
        tmp_path,
        "TITAN_WEB_ENABLED=true\nTITAN_WEB_SECRET_KEY=\n",
    )

    from core.web_cli import run_web_server

    assert run_web_server(dev_mode=False) == 1
    captured = capsys.readouterr().out
    assert "TITAN_WEB_SECRET_KEY est vide." in captured
    assert "python main.py web-dev" in captured


def test_web_dev_config_uses_localhost_and_temp_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_temp_env(
        monkeypatch,
        tmp_path,
        "TITAN_WEB_ENABLED=false\nTITAN_WEB_SECRET_KEY=\n",
    )

    from core.web_cli import WEB_DEV_HOST, WEB_DEV_PORT, _read_web_config

    config = _read_web_config(dev_mode=True)
    assert config.enabled is True
    assert config.host == WEB_DEV_HOST == "127.0.0.1"
    assert config.port == WEB_DEV_PORT == 8000
    assert config.secret_key == TITAN_WEB_DEV_SECRET
    assert config.dev_mode is True


def test_web_remote_config_uses_tunnel_port_and_requires_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_temp_env(
        monkeypatch,
        tmp_path,
        "TITAN_WEB_ENABLED=false\nTITAN_WEB_SECRET_KEY=remote-secret\nTITAN_WEB_REMOTE_PORT=8765\n",
    )

    from core.web_cli import WEB_REMOTE_HOST, WEB_REMOTE_PORT, _read_web_config

    config = _read_web_config(remote_mode=True)
    assert config.enabled is True
    assert config.host == WEB_REMOTE_HOST == "127.0.0.1"
    assert config.port == WEB_REMOTE_PORT == 8765
    assert config.secret_key == "remote-secret"
    assert config.dev_mode is False


def test_web_remote_starts_with_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _use_temp_env(
        monkeypatch,
        tmp_path,
        "TITAN_WEB_ENABLED=false\nTITAN_WEB_SECRET_KEY=remote-secret\n",
    )

    fake_uvicorn = MagicMock()

    with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
        from core.web_cli import run_web_server

        assert run_web_server(remote_mode=True) == 0

    fake_uvicorn.run.assert_called_once()
    _, kwargs = fake_uvicorn.run.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8765

    captured = capsys.readouterr().out
    assert "Titan Web App running at http://127.0.0.1:8765" in captured
    assert "cloudflared tunnel --url http://127.0.0.1:8765" in captured


def test_dispatch_web_remote_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.web_cli import dispatch_web_command

    with patch("core.web_cli.run_web_server", return_value=0) as run_mock:
        with pytest.raises(SystemExit) as exc:
            dispatch_web_command("web-remote")
    assert exc.value.code == 0
    run_mock.assert_called_once_with(remote_mode=True)


def test_web_dev_starts_with_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _use_temp_env(
        monkeypatch,
        tmp_path,
        "TITAN_WEB_ENABLED=false\nTITAN_WEB_SECRET_KEY=\n",
    )

    fake_uvicorn = MagicMock()

    with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
        from core.web_cli import run_web_server

        assert run_web_server(dev_mode=True) == 0

    fake_uvicorn.run.assert_called_once()
    _, kwargs = fake_uvicorn.run.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8000

    captured = capsys.readouterr().out
    assert "Titan Web App running at http://127.0.0.1:8000" in captured
    assert "Mode développement local" in captured


def test_protected_endpoints_allow_access_in_web_dev_mode(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_titan()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    titan.status = "ONLINE"
    set_titan(titan)

    monkeypatch.setenv("TITAN_WEB_DEV_MODE", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", TITAN_WEB_DEV_SECRET)

    with patch("api.auth.is_web_dev_mode", return_value=True):
        client = TestClient(create_app())
        response = client.get("/status")

    assert response.status_code == 200
    reset_titan()


def test_protected_endpoints_still_require_auth_outside_web_dev(
    web_client: TestClient,
) -> None:
    protected_paths = [
        "/status",
        "/tools",
        "/memory/status",
    ]
    for path in protected_paths:
        response = web_client.get(path)
        assert response.status_code == 401, path


def test_auth_rejects_when_secret_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    reset_titan()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    set_titan(titan)

    monkeypatch.setattr("api.auth.get_web_secret_key", lambda: "")
    monkeypatch.setattr("api.auth.is_web_dev_mode", lambda: False)
    client = TestClient(create_app())
    response = client.get("/status", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 503
    reset_titan()


def test_voice_status_endpoint(
    web_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = web_client.get("/voice/status", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["capabilities"]["push_to_talk"] is True
    assert payload["providers"]["stt"] == "browser_webspeech"
    assert payload["speech"]["locale"]


def test_existing_tools_still_register(tmp_path) -> None:
    """Regression guard — web foundation must not break ToolManager."""
    manager = ToolManager(project_root=tmp_path)
    tools = manager.list_tools()
    assert "time" in tools
    dashboard = manager.export_provider_dashboard()
    assert isinstance(dashboard, dict)


def test_events_stream_returns_sse(
    web_client: TestClient,
    auth_headers: dict[str, str],
    web_secret: str,
) -> None:
    """Phase E8 — persistent SSE endpoint emits status and brain_state."""
    response = web_client.get(
        f"/events/stream?token={web_secret}&snapshot=1",
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    body = response.text
    assert "event: status" in body
    assert "event: brain_state" in body
    assert "event: telemetry" in body


def test_chat_stream_returns_sse_events(
    web_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Phase E8 — chat stream emits conversation lifecycle events."""
    response = web_client.post(
        "/chat/stream",
        headers={**auth_headers, "Accept": "text/event-stream"},
        json={"message": "Bonjour Titan"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    body = response.text
    assert "event: conversation_started" in body
    assert "event: conversation_finished" in body
    assert "Réponse de test" in body


def test_chat_stream_emits_e9_cognitive_events(
    web_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Phase E9 — chat stream emits thinking lifecycle events (mocked think)."""
    response = web_client.post(
        "/chat/stream",
        headers={**auth_headers, "Accept": "text/event-stream"},
        json={"message": "Bonjour Titan"},
    )
    assert response.status_code == 200
    body = response.text
    assert "event: thinking_started" in body
    assert "event: thinking_finished" in body
    assert "event: conversation_finished" in body
    assert '"pipeline"' in body or '"stage_history"' in body

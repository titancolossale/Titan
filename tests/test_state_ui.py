# =====================================
# Titan State UI Integration Tests
# =====================================

"""Phase 13.4 — read-only WorkspaceState visualization for the Titan UI."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.status_builders import build_workspace_state
from api.stream_service import emit_initial_status, handle_chat_stream
from api.titan_service import reset_titan, set_titan
from core.state_manager import StateManager
from core.titan import Titan
from tools.tool_manager import ToolManager

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"

REQUIRED_STATE_FIELDS = (
    "active_project",
    "active_mission",
    "current_goal",
    "current_step",
    "next_action",
    "current_focus",
    "brain_mode",
    "progress",
    "conversation_state",
    "updated_at",
)


def _node_available() -> bool:
    return shutil.which("node") is not None


def _mock_orchestration_result(response: str = "Réponse de test depuis Brain.") -> Any:
    nlo = __import__(
        "brain.natural_language_orchestrator",
        fromlist=[
            "DetectedIntent",
            "OrchestrationResult",
            "PipelineDecision",
            "RequestAnalysis",
            "SystemsUsed",
        ],
    )
    return nlo.OrchestrationResult(
        request_analysis=nlo.RequestAnalysis(
            request="test",
            normalized="test",
            tokens=("test",),
        ),
        detected_intent=nlo.DetectedIntent.CONVERSATION,
        pipeline_decision=nlo.PipelineDecision(
            intent=nlo.DetectedIntent.CONVERSATION,
            systems=(),
            awareness_systems=(),
        ),
        systems_used=nlo.SystemsUsed(),
        reasoning_summary="Test",
        confidence=0.9,
        final_response=response,
        artifacts={},
        duration_seconds=0.01,
    )


@pytest.fixture
def web_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "test-web-secret-key"
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", secret)
    monkeypatch.setattr("config.settings.TITAN_WEB_ENABLED", True)
    monkeypatch.setattr("config.settings.TITAN_WEB_SECRET_KEY", secret)
    return secret


@pytest.fixture
def titan_with_state(tmp_path: Path) -> Titan:
    reset_titan()
    titan = Titan()
    titan.tools = ToolManager(project_root=tmp_path)
    titan.brain.tool_manager = titan.tools
    titan.status = "ONLINE"
    state_path = tmp_path / "titan_state.json"
    manager = StateManager(file_path=state_path)
    titan.state = manager
    titan.brain.state_manager = manager
    set_titan(titan)
    yield titan
    reset_titan()


@pytest.fixture
def web_client(
    web_secret: str,
    titan_with_state: Titan,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setattr(
        titan_with_state.brain,
        "process_request",
        MagicMock(return_value=_mock_orchestration_result()),
    )
    with patch("config.settings.TITAN_WEB_ENABLED", True), patch(
        "config.settings.get_web_secret_key", return_value=web_secret
    ), patch("api.auth.get_web_secret_key", return_value=web_secret), patch(
        "api.auth.is_web_dev_mode", return_value=False
    ):
        client = TestClient(create_app())
        yield client


@pytest.fixture
def auth_headers(web_secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {web_secret}"}


def test_build_workspace_state_is_live_snapshot(titan_with_state: Titan) -> None:
    """UI provider must surface the current live StateManager snapshot."""
    titan_with_state.state.update(
        active_project="Phase 13.4",
        current_goal="Visualiser WorkspaceState",
        brain_mode="focused",
    )
    payload = build_workspace_state(titan_with_state)
    for key in REQUIRED_STATE_FIELDS:
        assert key in payload
    assert payload["active_project"] == "Phase 13.4"
    assert payload["current_goal"] == "Visualiser WorkspaceState"
    assert payload["brain_mode"] == "focused"


def test_workspace_state_endpoint_returns_current_state(
    web_client: TestClient,
    auth_headers: dict[str, str],
    titan_with_state: Titan,
) -> None:
    """GET /workspace/state must return the live WorkspaceState for the UI."""
    titan_with_state.state.update(
        active_mission="State UI",
        next_action="Inspecter le panneau",
        progress="En cours",
    )
    response = web_client.get("/workspace/state", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    for key in REQUIRED_STATE_FIELDS:
        assert key in payload
    assert payload["active_mission"] == "State UI"
    assert payload["next_action"] == "Inspecter le panneau"
    assert payload["progress"] == "En cours"


def test_status_endpoint_still_embeds_state(
    web_client: TestClient,
    auth_headers: dict[str, str],
    titan_with_state: Titan,
) -> None:
    """Regression — GET /status continues to expose state for existing clients."""
    titan_with_state.state.update(current_focus="Regression")
    response = web_client.get("/status", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "state" in payload
    assert payload["state"]["current_focus"] == "Regression"


def test_events_stream_emits_workspace_state_on_connect(
    web_client: TestClient,
    web_secret: str,
    titan_with_state: Titan,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SSE attach must push workspace_state and log STATE_UI_CONNECTED."""
    titan_with_state.state.update(active_project="SSE Connect")
    with caplog.at_level(logging.INFO, logger="api.stream_service"):
        response = web_client.get(
            f"/events/stream?token={web_secret}&snapshot=1",
            headers={"Accept": "text/event-stream"},
        )
    assert response.status_code == 200
    body = response.text
    assert "event: workspace_state" in body
    assert "SSE Connect" in body
    assert any(
        record.getMessage().startswith("STATE_UI_CONNECTED")
        for record in caplog.records
    )


def test_chat_stream_emits_workspace_state_after_evolution(
    web_client: TestClient,
    auth_headers: dict[str, str],
    titan_with_state: Titan,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After a turn, SSE must refresh workspace_state (STATE_UI_REFRESH)."""
    titan_with_state.state.update(
        brain_mode="idle",
        current_goal="Avant chat",
    )

    # Evolve live state mid-turn the way Brain persistence would.
    def process_side_effect(*_args: Any, **_kwargs: Any) -> Any:
        titan_with_state.state.update(
            brain_mode="thinking",
            current_goal="Après évolution",
            next_action="Afficher dans l'UI",
        )
        return _mock_orchestration_result()

    titan_with_state.brain.process_request = MagicMock(  # type: ignore[method-assign]
        side_effect=process_side_effect,
    )

    with caplog.at_level(logging.INFO, logger="api.stream_service"):
        response = web_client.post(
            "/chat/stream",
            headers={**auth_headers, "Accept": "text/event-stream"},
            json={"message": "Continue"},
        )

    assert response.status_code == 200
    body = response.text
    assert "event: workspace_state" in body
    assert "Après évolution" in body
    assert "Afficher dans l'UI" in body
    assert any(
        record.getMessage().startswith("STATE_UI_REFRESH")
        for record in caplog.records
    )


def test_workspace_state_endpoint_is_read_only(
    web_client: TestClient,
    auth_headers: dict[str, str],
    titan_with_state: Titan,
) -> None:
    """UI contract — no mutation methods on /workspace/state."""
    before = titan_with_state.state.snapshot()
    for method in ("post", "put", "patch"):
        response = getattr(web_client, method)(
            "/workspace/state",
            headers=auth_headers,
            json={"brain_mode": "hacked", "active_project": "mutated"},
        )
        assert response.status_code in {405, 404, 401, 422}, method

    delete_response = web_client.delete("/workspace/state", headers=auth_headers)
    assert delete_response.status_code in {405, 404, 401, 422}

    after = titan_with_state.state.snapshot()
    assert after.brain_mode == before.brain_mode
    assert after.active_project == before.active_project


def test_build_workspace_state_does_not_mutate_manager(titan_with_state: Titan) -> None:
    """Mutating the returned dict must not alter StateManager live state."""
    titan_with_state.state.update(current_focus="Immutable")
    payload = build_workspace_state(titan_with_state)
    payload["current_focus"] = "Mutated by UI"
    payload["conversation_state"]["status"] = "hacked"
    live = titan_with_state.state.snapshot()
    assert live.current_focus == "Immutable"
    assert live.conversation_state.get("status") != "hacked"


def test_emit_initial_status_includes_workspace_state(titan_with_state: Titan) -> None:
    titan_with_state.state.update(progress="Ready")
    events = emit_initial_status()
    types = [event_type for event_type, _ in events]
    assert "workspace_state" in types
    payload = next(data for event_type, data in events if event_type == "workspace_state")
    assert payload["progress"] == "Ready"


def test_handle_chat_stream_publishes_workspace_state_refresh(
    titan_with_state: Titan,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        titan_with_state.brain,
        "process_request",
        MagicMock(return_value=_mock_orchestration_result()),
    )
    titan_with_state.state.update(current_step="Avant")
    emitted: list[tuple[str, dict[str, Any]]] = []

    def capture(event_type: str, data: dict[str, Any]) -> None:
        emitted.append((event_type, data))

    with caplog.at_level(logging.INFO, logger="api.stream_service"):
        handle_chat_stream("Bonjour", emit=capture)

    workspace_events = [data for event_type, data in emitted if event_type == "workspace_state"]
    assert workspace_events, "expected workspace_state refresh after chat"
    assert any(msg.startswith("STATE_UI_REFRESH") for msg in (
        record.getMessage() for record in caplog.records
    ))


def test_frontend_sources_wire_workspace_state() -> None:
    """Regression — V2 store, router, bridge, and panel expose WorkspaceState."""
    store = (V2 / "core" / "state-store.js").read_text(encoding="utf-8")
    router = (V2 / "core" / "event-router.js").read_text(encoding="utf-8")
    bridge = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    panel = (V2 / "panels" / "context-panel-region.js").read_text(encoding="utf-8")

    assert "workspaceState" in store
    assert 'case "workspace_state"' in router
    assert "STATE_UI_CONNECTED" in router
    assert "STATE_UI_REFRESH" in router
    assert '"workspace_state"' in bridge
    assert "buildWorkspaceStateList" in panel
    assert "data-readonly" in panel
    for field in REQUIRED_STATE_FIELDS:
        assert field in panel
    # Read-only contract — panel must not call StateManager mutation APIs.
    assert "state.update" not in panel
    assert "state.merge" not in panel
    assert "update_after_response" not in panel
    assert 'method: "POST"' not in panel
    assert 'method: "PUT"' not in panel
    assert 'method: "PATCH"' not in panel
    assert 'method: "DELETE"' not in panel


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_ui_receives_workspace_state_via_router() -> None:
    """Node harness — routeBackendEvent stores live WorkspaceState for the UI."""
    script = r"""
globalThis.document = {
  createElement(tag) {
    const kids = [];
    const attrs = {};
    const node = {
      tagName: String(tag).toUpperCase(),
      className: '',
      textContent: '',
      children: kids,
      attributes: attrs,
      setAttribute(k, v) { attrs[k] = String(v); },
      getAttribute(k) { return attrs[k] ?? null; },
      appendChild(child) { kids.push(child); return child; },
      append(...nodes) { for (const n of nodes) kids.push(n); },
      querySelector(sel) {
        const match = /\[data-field="([^"]+)"\]/.exec(sel);
        if (!match) return null;
        const want = match[1];
        const stack = [...kids];
        while (stack.length) {
          const cur = stack.shift();
          if (cur?.attributes?.['data-field'] === want) return cur;
          if (cur?.children) stack.push(...cur.children);
        }
        return null;
      },
    };
    return node;
  },
};

import { StateStore } from './web/v2/core/state-store.js';
import { routeBackendEvent } from './web/v2/core/event-router.js';
import { buildWorkspaceStateList, formatWorkspaceStateValue } from './web/v2/panels/context-panel-region.js';

const store = new StateStore();
const brain = {
  setState() {},
  getConversationEngine() {
    return { startFromBackend() {}, ingestStage() {}, finishFromBackend() {} };
  },
  getMemoryEngine() { return { ingest() {} }; },
  getToolEngine() { return { ingest() {} }; },
  activateTool() {},
  _pipelineStore: null,
  _neural: null,
};

routeBackendEvent(brain, store, 'workspace_state', {
  active_project: 'Titan UI',
  active_mission: 'Phase 13.4',
  current_goal: 'Visualiser',
  current_step: 'Afficher',
  next_action: 'Refresh',
  current_focus: 'State',
  brain_mode: 'focused',
  progress: '50%',
  conversation_state: { status: 'working' },
  updated_at: '2026-07-27T12:00:00Z',
});

const first = store.getState().workspaceState;
if (!first || first.active_project !== 'Titan UI') throw new Error('missing first state');
if (store.getState().activeProject !== 'Titan UI') throw new Error('activeProject not synced');

routeBackendEvent(brain, store, 'workspace_state', {
  ...first,
  brain_mode: 'thinking',
  progress: 'Après évolution',
});
const second = store.getState().workspaceState;
if (second.brain_mode !== 'thinking') throw new Error('update not applied');
if (second.progress !== 'Après évolution') throw new Error('evolution not visible');

if (formatWorkspaceStateValue(null) !== '—') throw new Error('null format');
const list = buildWorkspaceStateList(second);
if (list.getAttribute('data-readonly') !== 'true') throw new Error('not readonly');
const mode = list.querySelector('[data-field="brain_mode"]');
if (!mode || mode.textContent !== 'thinking') throw new Error('dom missing mode');

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


def test_state_manager_api_unchanged_regression() -> None:
    """Phase 13.4 must not alter StateManager's public API surface."""
    expected = {
        "load",
        "save",
        "reset",
        "snapshot",
        "update",
        "merge",
        "load_state",
        "save_state",
        "get_state",
        "update_state",
        "update_after_response",
        "show_state",
    }
    for name in expected:
        assert hasattr(StateManager, name), name

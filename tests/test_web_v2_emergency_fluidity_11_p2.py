# =====================================
# Titan Web V2 — Phase 11.P2 Emergency Fluidity + Chat Trace Tests
# =====================================

"""Contracts for Auto/Emergency performance mode and chat timing lifecycle."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_node(script: str, timeout: int = 45) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


# --- Source contracts ---------------------------------------------------------


def test_auto_mode_default_and_emergency_preset() -> None:
    qc = (V2 / "neural" / "quality-controller.js").read_text(encoding="utf-8")
    assert 'id: "auto"' in qc
    assert "EMERGENCY_PRESET" in qc
    assert "sampleRollingFps" in qc
    assert "enterEmergencyTier" in qc
    assert "maxDpr: 1.0" in qc
    assert "useStaticCache: true" in qc
    assert 'return "auto"' in qc

    cfg = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    assert 'defaultQualityMode: "auto"' in cfg


def test_static_cache_in_renderer() -> None:
    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    assert "_rebuildStaticCache" in renderer
    assert "_blitStatic" in renderer
    assert "invalidateStaticCache" in renderer
    assert "useStaticCache" in renderer
    assert "_staticRebuildCount" in renderer


def test_thinking_does_not_increase_load() -> None:
    engine = (V2 / "neural" / "engine.js").read_text(encoding="utf-8")
    assert "lightenThinking" in engine
    assert "signalLighten" in engine
    assert "targetVisualHz" in engine
    assert "sampleRollingFps" in engine
    # Chat pending throttles even while thinking (old bug skipped only !thinking).
    assert "chatPending || budgets.emergency" in engine

    signals = (V2 / "neural" / "signals.js").read_text(encoding="utf-8")
    assert "signalLighten" in signals
    assert "effectiveThinking" in signals


def test_quality_selector_reachable() -> None:
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    assert 'value="auto"' in shell
    assert "tdl-v2-visual-quality" in shell

    topbar = (V2 / "center" / "topbar-region.js").read_text(encoding="utf-8")
    assert "tdl-v2-topbar-quality" in topbar
    assert "tdl-v2-topbar-settings" in topbar

    settings = (V2 / "core" / "settings-performance.js").read_text(encoding="utf-8")
    assert "readQualityUrlOverride" in settings
    assert "tdl-v2-topbar-quality" in settings


def test_url_quality_override_helper() -> None:
    qc = (V2 / "neural" / "quality-controller.js").read_text(encoding="utf-8")
    assert "readQualityUrlOverride" in qc
    assert 'params.get("quality")' in qc


def test_chat_elapsed_feedback_and_timeout_copy() -> None:
    cm = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "Titan traite ta demande" in cm
    assert "Le traitement prend plus de temps que prévu" in cm
    assert "Titan n’a pas pu répondre dans le délai prévu" in cm
    assert "_startThinkingElapsed" in cm
    assert "_clearBusyState" in cm

    bridge = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    assert "Titan n’a pas pu répondre dans le délai prévu" in bridge


def test_server_timing_events_present() -> None:
    chat = (ROOT / "api" / "chat_service.py").read_text(encoding="utf-8")
    for event in (
        "CHAT_API_RECEIVED",
        "CHAT_BRAIN_START",
        "CHAT_BRAIN_END",
        "CHAT_RESPONSE_SERIALIZED",
        "CHAT_RESPONSE_SENT",
        "CHAT_REQUEST_TIMEOUT",
        "CHAT_REQUEST_ERROR",
        "elapsed_ms",
    ):
        assert event in chat

    llm = (ROOT / "brain" / "llm.py").read_text(encoding="utf-8")
    assert "CHAT_PROVIDER_START" in llm
    assert "CHAT_PROVIDER_END" in llm
    assert "_active_request_id" in llm


def test_no_secrets_or_cot_in_timing_logs() -> None:
    chat = (ROOT / "api" / "chat_service.py").read_text(encoding="utf-8")
    assert "never logs message content" in chat or "never logs message" in chat
    assert "chain.of.thought" not in chat.lower()
    assert "openai_api_key" not in chat.lower() or "SECRET" in chat


# --- Node runtime contracts ---------------------------------------------------


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_auto_enters_emergency_after_sustained_low_fps() -> None:
    out = _run_node(
        """
const store = new Map();
globalThis.sessionStorage = {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
globalThis.localStorage = globalThis.sessionStorage;
globalThis.window = globalThis;
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
globalThis.performance = { now: () => Date.now() };

import {
  QualityController,
  EMERGENCY_PRESET,
  QUALITY_PRESETS,
} from './web/v2/neural/quality-controller.js';

const qc = new QualityController({ mode: 'auto' });
const before = qc.getBudgets();
if (before.maxDpr > 1.0) throw new Error('Auto must start DPR<=1');
if (!before.useStaticCache) throw new Error('Auto should use static cache');

// Sustained FPS below 35 for >3s
for (let i = 0; i < 20; i++) {
  qc.sampleRollingFps(28, 1000 + i * 200);
}
if (qc.getEmergencyTier() === 'normal') {
  throw new Error('expected emergency after sustained <35 FPS');
}
const emerg = qc.getBudgets();
if (emerg.maxDpr > 1.0) throw new Error('emergency DPR must be 1.0');
if (emerg.maxEdgesDrawn >= before.maxEdgesDrawn) {
  throw new Error('emergency must cut edge budget');
}
if (emerg.maxEdgesDrawn > EMERGENCY_PRESET.maxEdgesDrawn) {
  throw new Error('emergency edges too high');
}
if (emerg.dustCount !== 0) throw new Error('emergency dust must be 0');
if (emerg.enableBokeh) throw new Error('emergency must disable bokeh');

// FPS below 25 → critical
for (let i = 0; i < 15; i++) {
  qc.sampleRollingFps(18, 6000 + i * 200);
}
if (qc.getEmergencyTier() !== 'critical') {
  throw new Error('expected critical tier below 25 FPS');
}
const crit = qc.getBudgets();
if (crit.maxEdgesDrawn >= emerg.maxEdgesDrawn) {
  throw new Error('critical must cut further');
}
if (crit.targetVisualHz > 20) throw new Error('critical visual Hz too high');

// Thinking/chat pending must not increase budgets
qc.setChatPending(true);
const pending = qc.getBudgets();
if (pending.maxEdgesDrawn > crit.maxEdgesDrawn) {
  throw new Error('chat pending must not increase load');
}
if (pending.dustCount !== 0) throw new Error('pending dust must stay 0');
if (!pending.lightenThinking) throw new Error('lightenThinking required');

const cine = QUALITY_PRESETS.cinematic;
if (emerg.maxNodeCount > cine.maxNodeCount * 0.35) {
  throw new Error('emergency node budget not cut enough vs cinematic');
}

console.log(JSON.stringify({
  ok: true,
  emergencyEdges: emerg.maxEdgesDrawn,
  criticalEdges: crit.maxEdgesDrawn,
  tier: qc.getEmergencyTier(),
}));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_static_cache_not_rebuilt_every_frame() -> None:
    out = _run_node(
        r"""
const listeners = {};
globalThis.window = globalThis;
globalThis.document = {
  hidden: false,
  documentElement: { classList: { contains: () => false, toggle: () => {}, dataset: {} } },
  getElementById: () => ({ classList: { toggle() {} }, dataset: {} }),
  createElement: (tag) => {
    const el = { width: 0, height: 0, style: {}, getContext: null };
    el.getContext = () => ({
      setTransform() {},
      fillRect() {},
      fillStyle: '',
      save() {},
      restore() {},
      beginPath() {},
      arc() {},
      fill() {},
      drawImage() {},
      createRadialGradient: () => ({ addColorStop() {} }),
      globalCompositeOperation: 'source-over',
    });
    return el;
  },
  addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
  removeEventListener: () => {},
};
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
globalThis.performance = { now: () => Date.now() };
globalThis.OffscreenCanvas = class {
  constructor(w, h) { this.width = w; this.height = h; }
  getContext() {
    return {
      setTransform() {},
      fillRect() {},
      fillStyle: '',
      save() {},
      restore() {},
      beginPath() {},
      arc() {},
      fill() {},
      createRadialGradient: () => ({ addColorStop() {} }),
      globalCompositeOperation: 'source-over',
    };
  }
};
globalThis.devicePixelRatio = 2;

const { NeuralRenderer } = await import('./web/v2/neural/renderer.js');
const canvas = {
  width: 0, height: 0, style: {},
  getContext: () => ({
    setTransform() {}, fillRect() {}, fillStyle: '', save() {}, restore() {},
    beginPath() {}, arc() {}, fill() {}, drawImage() {},
    createRadialGradient: () => ({ addColorStop() {} }),
    globalCompositeOperation: 'source-over',
    moveTo() {}, lineTo() {}, stroke() {}, strokeStyle: '', lineWidth: 1,
    quadraticCurveTo() {}, bezierCurveTo() {}, closePath() {},
  }),
};
const renderer = new NeuralRenderer(canvas);
const budgets = {
  useStaticCache: true,
  maxDpr: 1,
  maxEdgesDrawn: 100,
  maxTissueDrawn: 50,
  dustCount: 0,
  bokehCount: 0,
  ambientPatchCount: 1,
  lightenThinking: true,
  enableBokeh: false,
  enableVolumetricHaze: false,
  enableAtmosphericFog: false,
  enableLightShafts: false,
  enableBloom: false,
  enableLensDiffusion: false,
  enableForegroundFog: false,
  softHaloFarLayers: false,
  emergency: true,
  chatPending: false,
};
renderer.resize(800, 600, budgets);

const camera = {
  width: 800, height: 600, worldWidth: 800, worldHeight: 600,
  worldToScreen: (x, y) => ({ x, y }),
};
const nodes = {
  nodes: [], edges: [],
  core: { centerNodeId: null },
  getCachedLayerNodes: () => [],
  getFieldTissue: () => ({ veryFar: [], far: [], mid: [], bridge: [], near: [], foreground: [] }),
};
const state = {
  getIntensity: () => 0.4,
  isThinking: () => false,
  getVitality: () => 0.5,
  getCognitiveSignature: () => ({}),
};
const signals = { signals: [], trails: [] };

const before = renderer.getStaticRebuildCount();
renderer.render(camera, nodes, signals, state, null, null, null, budgets);
const mid = renderer.getStaticRebuildCount();
renderer.render(camera, nodes, signals, state, null, null, null, budgets);
renderer.render(camera, nodes, signals, state, null, null, null, budgets);
const after = renderer.getStaticRebuildCount();
if (mid !== before + 1) throw new Error('expected one static rebuild on first frame');
if (after !== mid) throw new Error('static cache rebuilt every frame: ' + after);
console.log(JSON.stringify({ ok: true, rebuilds: after }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_url_override_and_parse_quality() -> None:
    out = _run_node(
        """
import { parseQualityMode, QUALITY_PRESETS } from './web/v2/neural/quality-controller.js';
if (parseQualityMode('performance') !== 'performance') throw new Error('perf');
if (parseQualityMode('AUTO') !== 'auto') throw new Error('auto');
if (parseQualityMode('nope') !== null) throw new Error('invalid');
if (!QUALITY_PRESETS.auto) throw new Error('missing auto preset');
console.log('ok');
"""
    )
    assert "ok" in out


# --- Backend timing + health --------------------------------------------------


def _orchestration_result(response: str = "Bonjour.") -> object:
    from brain.natural_language_orchestrator import (
        DetectedIntent,
        OrchestrationResult,
        PipelineDecision,
        RequestAnalysis,
        SystemsUsed,
    )

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
        reasoning_summary="Routage conversation.",
        confidence=0.9,
        final_response=response,
        artifacts={},
        duration_seconds=0.05,
    )


@pytest.fixture
def web_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "phase11p2-test-secret"
    monkeypatch.setenv("TITAN_WEB_ENABLED", "true")
    monkeypatch.setenv("TITAN_WEB_SECRET_KEY", secret)
    monkeypatch.setenv("TITAN_CHAT_DIAGNOSTICS", "true")
    monkeypatch.setattr("config.settings.TITAN_WEB_ENABLED", True)
    monkeypatch.setattr("config.settings.TITAN_WEB_SECRET_KEY", secret)
    return secret


@pytest.fixture
def brain_client(web_secret: str, tmp_path, monkeypatch: pytest.MonkeyPatch):
    from api.app import create_app
    from api.chat_service import clear_idempotency_cache
    from api.titan_service import reset_titan, set_titan
    from core.titan import Titan
    from tools.tool_manager import ToolManager

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


def test_health_and_ready_remain_200(brain_client: TestClient) -> None:
    assert brain_client.get("/health").status_code == 200
    assert brain_client.get("/ready").status_code == 200


def test_chat_timing_logged_safely(
    brain_client: TestClient,
    auth_headers: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from api.titan_service import get_titan

    with caplog.at_level(logging.INFO, logger="api.chat_service"):
        response = brain_client.post(
            "/api/chat",
            json={"message": "Bonjour Titan", "client_request_id": "corr-11p2-1"},
            headers=auth_headers,
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert payload.get("request_id") == "corr-11p2-1"

    joined = "\n".join(r.message for r in caplog.records)
    assert "CHAT_API_RECEIVED" in joined
    assert "CHAT_BRAIN_START" in joined
    assert "CHAT_BRAIN_END" in joined
    assert "CHAT_RESPONSE_SENT" in joined
    assert "corr-11p2-1" in joined
    assert "Bonjour Titan" not in joined
    get_titan().brain.process_request.assert_called_once()


def test_one_chat_still_one_brain_call(
    brain_client: TestClient,
    auth_headers: dict,
) -> None:
    from api.titan_service import get_titan

    brain_client.post(
        "/api/chat",
        json={"message": "Ping", "client_request_id": "corr-11p2-once"},
        headers=auth_headers,
    )
    get_titan().brain.process_request.assert_called_once()


def test_chat_stream_still_async_offload() -> None:
    source = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert "async def chat_stream" in source
    assert "asyncio.to_thread" in source


def test_canonical_layout_intact() -> None:
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    assert "tdl-v2-neural-host" in shell
    assert "tdl-v2-settings-overlay" in shell
    assert "tdl-v2-visual-quality" in shell

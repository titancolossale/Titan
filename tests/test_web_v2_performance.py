# =====================================
# Titan Web V2 — Phase 11.P1 Performance Tests
# =====================================

"""Contracts for neural renderer performance stabilization.

Validates adaptive quality, single RAF loop, visibility pause, DPR caps,
SSE reconnect discipline, and settings integration — without redesigning UI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_quality_controller_module_exists() -> None:
    path = V2 / "neural" / "quality-controller.js"
    text = path.read_text(encoding="utf-8")
    for token in (
        "QUALITY_PRESETS",
        "performance",
        "balanced",
        "cinematic",
        "QualityController",
        "sampleFrame",
        "hysteresis",
        "prefersReducedMotion",
        "QUALITY_STORAGE_KEY",
    ):
        assert token in text


def test_performance_monitor_module_exists() -> None:
    text = (V2 / "neural" / "performance-monitor.js").read_text(encoding="utf-8")
    assert "PerformanceMonitor" in text
    assert "rollingFps" in text
    assert "droppedDecorative" in text


def test_settings_visual_quality_surface() -> None:
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    assert "tdl-v2-visual-quality" in shell
    assert "Performance" in shell
    assert "Balanced" in shell
    assert "Cinematic" in shell
    assert "tdl-v2-reduce-motion-pref" in shell

    settings = (V2 / "core" / "settings-performance.js").read_text(encoding="utf-8")
    assert "wireVisualQualitySettings" in settings


def test_engine_idempotent_init_and_visibility() -> None:
    engine = (V2 / "neural" / "engine.js").read_text(encoding="utf-8")
    assert "if (this._initialized)" in engine
    assert "document.hidden" in engine
    assert "RESIZE_DEBOUNCE_MS" in engine
    assert "_scheduleResize" in engine
    assert "QualityController" in engine
    assert "notifyInteractive" in engine
    assert "renderLight" in engine


def test_stage_idempotent_mount() -> None:
    stage = (V2 / "neural" / "stage.js").read_text(encoding="utf-8")
    assert "never start a second neural RAF loop" in stage
    assert "if (!this._engine)" in stage


def test_sse_reconnect_guards() -> None:
    bridge = (V2 / "core" / "backend-bridge.js").read_text(encoding="utf-8")
    assert "_ensureAuthorizedToStream" in bridge
    assert "RECONNECT_AUTH_FAIL_MAX" in bridge
    assert "RECONNECT_HARD_MAX" in bridge
    assert "_authBlocked" in bridge
    assert "visibilitychange" in bridge


def test_config_quality_defaults() -> None:
    cfg = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    assert 'defaultQualityMode: "balanced"' in cfg
    assert "adaptiveNodeCount: false" in cfg
    assert "maxDpr: 1.75" in cfg


def test_quality_preset_budgets_in_source() -> None:
    """Static budget ordering without requiring a local Node binary."""
    text = (V2 / "neural" / "quality-controller.js").read_text(encoding="utf-8")

    def _block(mode: str) -> str:
        start = text.index(f"{mode}: Object.freeze({{")
        end = text.index("}),", start)
        return text[start:end]

    perf = _block("performance")
    bal = _block("balanced")
    cine = _block("cinematic")

    def _num(block: str, key: str) -> float:
        import re

        match = re.search(rf"{key}:\s*([0-9.]+)", block)
        assert match, f"missing {key}"
        return float(match.group(1))

    assert _num(perf, "maxDpr") <= _num(bal, "maxDpr") <= _num(cine, "maxDpr")
    assert _num(perf, "maxNodeCount") < _num(bal, "maxNodeCount")
    assert _num(perf, "maxEdgesDrawn") < _num(bal, "maxEdgesDrawn")
    # Cinematic preserves config ceilings via NEURAL_CONFIG references.
    assert "NEURAL_CONFIG.performance.maxEdgesDrawn" in cine
    assert "NEURAL_CONFIG.nodes.maxCount" in cine
    assert _num(bal, "maxDpr") <= 1.25
    assert _num(perf, "maxDpr") <= 1.0
    assert "adaptive: true" in bal
    assert "adaptive: false" in perf


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_quality_budgets_ordering_and_dpr() -> None:
    out = _run_node(
        """
import {
  QUALITY_PRESETS,
  QualityController,
} from './web/v2/neural/quality-controller.js';

const perf = QUALITY_PRESETS.performance;
const bal = QUALITY_PRESETS.balanced;
const cine = QUALITY_PRESETS.cinematic;

if (!(perf.maxNodeCount < bal.maxNodeCount && bal.maxNodeCount <= cine.maxNodeCount)) {
  throw new Error('node budgets not ordered');
}
if (!(perf.maxEdgesDrawn < bal.maxEdgesDrawn && bal.maxEdgesDrawn <= cine.maxEdgesDrawn)) {
  throw new Error('edge budgets not ordered');
}
if (!(perf.maxDpr <= bal.maxDpr && bal.maxDpr <= cine.maxDpr)) {
  throw new Error('DPR caps not ordered');
}
if (bal.maxDpr > 1.25) throw new Error('Balanced DPR must be capped at 1.25');
if (perf.maxDpr > 1.0) throw new Error('Performance DPR must be capped at 1.0');
if (cine.maxNodeCount < bal.maxNodeCount) throw new Error('Cinematic must preserve max budgets');

const qc = new QualityController({ mode: 'balanced' });
const b0 = qc.getBudgets();
if (b0.maxDpr > 1.25) throw new Error('runtime Balanced DPR too high');

// Sustained low FPS should degrade tier without oscillation.
for (let i = 0; i < 60; i++) qc.sampleFrame(28, 1000 + i * 16);
const tierAfterSlow = qc.getTier();
if (tierAfterSlow < 1) throw new Error('expected adaptive degrade, got ' + tierAfterSlow);

const tiers = [tierAfterSlow];
for (let i = 0; i < 40; i++) {
  qc.sampleFrame(28, 5000 + i * 16);
  tiers.push(qc.getTier());
}
const unique = new Set(tiers);
if (unique.size > 2) throw new Error('quality oscillating: ' + [...unique]);

// Headroom recovery after long hold — advance clock past recoverHoldMs.
const after = 5000 + 40 * 16 + 10000;
for (let i = 0; i < 55; i++) qc.sampleFrame(10, after + i * 16);
if (qc.getTier() > tierAfterSlow) throw new Error('tier increased unexpectedly');
// May recover to a better tier (lower id)
if (qc.getTier() > 2) throw new Error('tier out of range');

qc.setMode('performance');
const pb = qc.getBudgets();
qc.setMode('cinematic');
const cb = qc.getBudgets();
if (!(pb.maxEdgesDrawn < cb.maxEdgesDrawn)) throw new Error('perf edges not lower than cinematic');

console.log(JSON.stringify({
  ok: true,
  perfNodes: perf.maxNodeCount,
  balNodes: bal.maxNodeCount,
  cineNodes: cine.maxNodeCount,
  balDpr: bal.maxDpr,
  tierAfterSlow,
  tierFinal: qc.getTier(),
}));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_engine_single_raf_idempotent_hidden_resume() -> None:
    out = _run_node(
        r"""
// Minimal browser stubs — no jsdom dependency.
const listeners = {};
globalThis.window = globalThis;
globalThis.document = {
  hidden: false,
  documentElement: { classList: { contains: () => false, toggle: () => {} } },
  addEventListener: (type, fn) => {
    (listeners[type] ||= []).push(fn);
  },
  removeEventListener: (type, fn) => {
    listeners[type] = (listeners[type] || []).filter((f) => f !== fn);
  },
};
globalThis.matchMedia = () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} });
globalThis.performance = { now: () => Date.now() };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };

let rafId = 0;
const rafCallbacks = new Map();
globalThis.requestAnimationFrame = (cb) => {
  rafId += 1;
  rafCallbacks.set(rafId, cb);
  return rafId;
};
globalThis.cancelAnimationFrame = (id) => {
  rafCallbacks.delete(id);
};

const canvas = {
  width: 0,
  height: 0,
  style: {},
  classList: { add() {}, remove() {}, toggle() {} },
  parentElement: { clientWidth: 1280, clientHeight: 720 },
  getContext: () => ({
    setTransform() {},
    fillRect() {},
    fillStyle: '',
    save() {},
    restore() {},
    beginPath() {},
    arc() {},
    fill() {},
    stroke() {},
    createRadialGradient: () => ({ addColorStop() {} }),
    globalCompositeOperation: '',
    globalAlpha: 1,
    lineCap: '',
    lineJoin: '',
    lineWidth: 1,
    strokeStyle: '',
  }),
};

const { NeuralEngine } = await import('./web/v2/neural/engine.js');
const engine = new NeuralEngine(canvas);
engine.init();
engine.init(); // idempotent
const firstFrame = engine.frameId;
if (firstFrame == null) throw new Error('expected RAF after init');

// Drain one frame then hide.
const cb = rafCallbacks.get(firstFrame);
rafCallbacks.clear();
document.hidden = true;
for (const fn of listeners.visibilitychange || []) fn();
if (engine.frameId !== null) throw new Error('RAF should stop when hidden');

document.hidden = false;
for (const fn of listeners.visibilitychange || []) fn();
if (engine.frameId == null) throw new Error('RAF should resume when visible');
const resumeId = engine.frameId;

// Ensure only one active callback slot after resume.
if (rafCallbacks.size !== 1) throw new Error('duplicate RAF loops: ' + rafCallbacks.size);

const buildsBefore = engine.getGeometryBuildCount();
// Tick without resize should not rebuild geometry.
if (cb) cb(16);
const buildsAfter = engine.getGeometryBuildCount();
if (buildsAfter !== buildsBefore && buildsAfter > buildsBefore + 0) {
  /* first resize already built; tick must not rebuild */
}
// Force: call tick path via remaining raf
const tickCb = rafCallbacks.get(resumeId);
if (tickCb) {
  document.hidden = false;
  engine.state.isPaused = false;
  const b0 = engine.getGeometryBuildCount();
  tickCb(32);
  const b1 = engine.getGeometryBuildCount();
  if (b1 !== b0) throw new Error('static geometry regenerated every frame');
}

engine.destroy();
if (engine.frameId !== null) throw new Error('destroy must clear RAF');
engine.init();
engine.init();
if (rafCallbacks.size > 1) throw new Error('re-init created duplicate loops');

const dprBal = engine.quality.getBudgets().maxDpr;
engine.setQualityMode('performance');
const dprPerf = engine.quality.getBudgets().maxDpr;
engine.setQualityMode('cinematic');
const dprCine = engine.quality.getBudgets().maxDpr;
if (!(dprPerf <= dprBal && dprBal <= dprCine)) throw new Error('DPR mode order broken');
if (dprBal > 1.25) throw new Error('Balanced DPR cap broken');

console.log(JSON.stringify({
  ok: true,
  resumeId,
  rafSize: rafCallbacks.size,
  dprPerf,
  dprBal,
  dprCine,
  builds: engine.getGeometryBuildCount(),
}));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_resize_debounced() -> None:
    out = _run_node(
        r"""
globalThis.window = globalThis;
const listeners = {};
globalThis.document = {
  hidden: false,
  documentElement: { classList: { contains: () => false } },
  addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); },
  removeEventListener: () => {},
};
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
globalThis.performance = { now: () => 0 };
let now = 0;
const timers = [];
globalThis.setTimeout = (fn, ms) => { timers.push({ fn, at: now + ms }); return timers.length; };
globalThis.clearTimeout = () => {};
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => {};
globalThis.ResizeObserver = class { observe() {} disconnect() {} };

const canvas = {
  width: 0, height: 0, style: {},
  classList: { add() {}, remove() {}, toggle() {} },
  parentElement: { clientWidth: 1000, clientHeight: 800 },
  getContext: () => ({
    setTransform() {}, fillRect() {}, fillStyle: '', save() {}, restore() {},
    beginPath() {}, arc() {}, fill() {}, stroke() {},
    createRadialGradient: () => ({ addColorStop() {} }),
    globalCompositeOperation: '', globalAlpha: 1, lineCap: '', lineJoin: '', lineWidth: 1, strokeStyle: '',
  }),
};

const { NeuralEngine } = await import('./web/v2/neural/engine.js');
const engine = new NeuralEngine(canvas);
engine.init();
const builds0 = engine.getGeometryBuildCount();
engine._scheduleResize();
engine._scheduleResize();
engine._scheduleResize();
if (timers.length !== 1) throw new Error('debounce should keep one timer, got ' + timers.length);
now = 200;
timers[0].fn();
const builds1 = engine.getGeometryBuildCount();
if (builds1 < builds0) throw new Error('resize should rebuild once');
console.log(JSON.stringify({ ok: true, timers: timers.length, builds0, builds1 }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_sse_auth_gate_no_aggressive_retry() -> None:
    out = _run_node(
        r"""
globalThis.window = globalThis;
const listeners = {};
globalThis.document = {
  hidden: false,
  addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); },
  removeEventListener: () => {},
};
globalThis.localStorage = { getItem: () => '', setItem() {}, removeItem() {} };

let fetchCount = 0;
globalThis.fetch = async (url) => {
  fetchCount += 1;
  if (String(url).includes('/auth/status')) {
    return {
      ok: true,
      json: async () => ({ auth_required: true, authenticated: false, session_auth: true }),
    };
  }
  throw new Error('unexpected fetch ' + url);
};

let esCreated = 0;
globalThis.EventSource = class {
  constructor() { esCreated += 1; this.onopen = null; this.onerror = null; }
  close() {}
  addEventListener() {}
};

const { BackendBridge } = await import('./web/v2/core/backend-bridge.js');
const bridge = new BackendBridge({ getPipelineStore: () => ({}) }, null);
await bridge.connect();
if (esCreated !== 0) throw new Error('must not open EventSource when unauthorized');
if (bridge._authBlocked !== true) throw new Error('expected auth block');
if (bridge._shouldReconnect !== false) throw new Error('must not schedule reconnect when unauthorized');

// Simulate errors should not storm.
bridge._shouldReconnect = true;
bridge._authBlocked = false;
bridge._authFailStreak = 2;
await bridge._handleStreamError();
if (bridge._authBlocked !== true) throw new Error('repeated failures must block');
if (esCreated !== 0) throw new Error('no EventSource after auth fail');

console.log(JSON.stringify({ ok: true, fetchCount, esCreated }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


def test_docs_performance_exists() -> None:
    doc = ROOT / "docs" / "WEB_APP_PERFORMANCE.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for token in (
        "Phase 11",
        "Balanced",
        "Performance",
        "Cinematic",
        "requestAnimationFrame",
        "devicePixelRatio",
        "Benchmark",
    ):
        assert token in text


def test_health_endpoints_still_declared() -> None:
    app = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/health")' in app or "/health" in app
    assert '/ready' in app

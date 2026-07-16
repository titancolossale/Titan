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
    assert "Auto" in shell
    assert "Performance" in shell
    assert "Balanced" in shell
    assert "Cinematic" in shell
    assert "tdl-v2-reduce-motion-pref" in shell

    settings = (V2 / "core" / "settings-performance.js").read_text(encoding="utf-8")
    assert "wireVisualQualitySettings" in settings
    assert "readQualityUrlOverride" in settings


def test_engine_idempotent_init_and_visibility() -> None:
    engine = (V2 / "neural" / "engine.js").read_text(encoding="utf-8")
    assert "if (this._initialized)" in engine
    assert "document.hidden" in engine
    assert "RESIZE_DEBOUNCE_MS" in engine
    assert "_scheduleResize" in engine
    assert "QualityController" in engine
    assert "notifyInteractive" in engine
    assert "renderLight" in engine
    assert "getFrameScheduler" in engine
    assert "MIN_RESIZE_DELTA_PX" in engine


def test_stage_idempotent_mount() -> None:
    stage = (V2 / "neural" / "stage.js").read_text(encoding="utf-8")
    assert "never duplicate the primary RAF" in stage or "never start a second neural RAF loop" in stage
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
    assert 'defaultQualityMode: "auto"' in cfg
    assert "adaptiveNodeCount: false" in cfg
    assert "maxDpr: 1.75" in cfg


def test_quality_preset_budgets_in_source() -> None:
    """Static budget ordering without requiring a local Node binary."""
    text = (V2 / "neural" / "quality-controller.js").read_text(encoding="utf-8")

    def _block(mode: str) -> str:
        start = text.index(f"{mode}: Object.freeze({{")
        end = text.index("}),", start)
        return text[start:end]

    auto = _block("auto")
    perf = _block("performance")
    bal = _block("balanced")
    cine = _block("cinematic")

    def _num(block: str, key: str) -> float:
        import re

        match = re.search(rf"{key}:\s*([0-9.]+)", block)
        assert match, f"missing {key}"
        return float(match.group(1))

    assert _num(auto, "maxDpr") <= 1.0
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
    assert "EMERGENCY_PRESET" in text
    assert "sampleRollingFps" in text


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
globalThis.document = {
  hidden: false,
  documentElement: { classList: { contains: () => false, toggle: () => {} }, dataset: {} },
  getElementById: () => null,
  createElement: () => ({
    width: 0, height: 0, style: {},
    getContext: () => ({
      setTransform() {}, fillRect() {}, fillStyle: '',
      save() {}, restore() {}, beginPath() {}, arc() {}, fill() {}, stroke() {},
      createRadialGradient: () => ({ addColorStop() {} }),
      createLinearGradient: () => ({ addColorStop() {} }),
      drawImage() {},
      globalCompositeOperation: '', globalAlpha: 1,
      lineCap: '', lineJoin: '', lineWidth: 1, strokeStyle: '',
    }),
  }),
  addEventListener: (type, fn) => {
    (listeners[type] ||= []).push(fn);
  },
  removeEventListener: (type, fn) => {
    listeners[type] = (listeners[type] || []).filter((f) => f !== fn);
  },
};
globalThis.OffscreenCanvas = class {
  constructor(w, h) { this.width = w; this.height = h; }
  getContext() {
    return {
      setTransform() {}, fillRect() {}, fillStyle: '',
      save() {}, restore() {}, beginPath() {}, arc() {}, fill() {}, stroke() {},
      createRadialGradient: () => ({ addColorStop() {} }),
      createLinearGradient: () => ({ addColorStop() {} }),
      drawImage() {},
      globalCompositeOperation: '', globalAlpha: 1,
      lineCap: '', lineJoin: '', lineWidth: 1, strokeStyle: '',
    };
  }
};
globalThis.window = globalThis;
globalThis.addEventListener = (...a) => document.addEventListener(...a);
globalThis.removeEventListener = (...a) => document.removeEventListener(...a);
globalThis.innerWidth = 1280;
globalThis.innerHeight = 720;
globalThis.devicePixelRatio = 1;
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

const stubCtx = () => new Proxy({
  canvas: null,
  fillStyle: '', strokeStyle: '', globalCompositeOperation: '', globalAlpha: 1,
  lineCap: '', lineJoin: '', lineWidth: 1, shadowBlur: 0, shadowColor: '',
  createRadialGradient: () => ({ addColorStop() {} }),
  createLinearGradient: () => ({ addColorStop() {} }),
}, { get: (t, p) => (p in t ? t[p] : () => t) });
const canvas = {
  width: 0,
  height: 0,
  style: {},
  classList: { add() {}, remove() {}, toggle() {} },
  parentElement: { clientWidth: 1280, clientHeight: 720 },
  getContext: () => stubCtx(),
};
document.createElement = () => ({ width: 0, height: 0, style: {}, getContext: () => stubCtx() });
globalThis.OffscreenCanvas = class {
  constructor(w, h) { this.width = w; this.height = h; }
  getContext() { return stubCtx(); }
};

const { NeuralEngine } = await import('./web/v2/neural/engine.js');
const { getFrameScheduler, resetFrameSchedulerForTests } = await import('./web/v2/neural/frame-scheduler.js');
resetFrameSchedulerForTests();
const engine = new NeuralEngine(canvas);
engine.init();
engine.init(); // idempotent
const scheduler = getFrameScheduler();
if (!scheduler.isRunning()) throw new Error('expected shared scheduler after init');
if (scheduler.getActiveRafCount() !== 1) throw new Error('expected single primary RAF');
if (engine.frameId == null) throw new Error('expected engine frame marker after init');

// Hide — shared clock must stop without duplicating.
document.hidden = true;
for (const fn of listeners.visibilitychange || []) fn();
if (scheduler.getActiveRafCount() !== 0) throw new Error('RAF should stop when hidden');
if (engine.frameId !== null) throw new Error('engine marker should clear when hidden');

document.hidden = false;
for (const fn of listeners.visibilitychange || []) fn();
if (scheduler.getActiveRafCount() !== 1) throw new Error('RAF should resume when visible');
if (engine.frameId == null) throw new Error('RAF should resume when visible');
if (rafCallbacks.size !== 1) throw new Error('duplicate RAF loops: ' + rafCallbacks.size);

// Geometry must stay stable across ticks — stub render path via light mode.
engine.setChatPending(true);
const buildsBefore = engine.getGeometryBuildCount();
engine.tick(16);
const buildsAfter = engine.getGeometryBuildCount();
if (buildsAfter !== buildsBefore) throw new Error('tick must not rebuild geometry');
engine.setChatPending(false);

engine.destroy();
if (engine.frameId !== null) throw new Error('destroy must clear RAF');
engine.init();
engine.init();
if (rafCallbacks.size > 1) throw new Error('re-init created duplicate loops');
if (getFrameScheduler().getActiveRafCount() !== 1) throw new Error('re-init must keep single RAF');

const dprBal = engine.quality.getBudgets().maxDpr;
engine.setQualityMode('performance');
const dprPerf = engine.quality.getBudgets().maxDpr;
engine.setQualityMode('cinematic');
const dprCine = engine.quality.getBudgets().maxDpr;
if (!(dprPerf <= dprBal && dprBal <= dprCine)) throw new Error('DPR mode order broken');
if (dprBal > 1.25) throw new Error('Balanced DPR cap broken');

console.log(JSON.stringify({
  ok: true,
  rafSize: rafCallbacks.size,
  activeRaf: getFrameScheduler().getActiveRafCount(),
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
const listeners = {};
globalThis.document = {
  hidden: false,
  documentElement: { classList: { contains: () => false, toggle() {} }, dataset: {} },
  getElementById: () => null,
  addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); },
  removeEventListener: () => {},
};
globalThis.window = globalThis;
globalThis.addEventListener = (...a) => document.addEventListener(...a);
globalThis.removeEventListener = (...a) => document.removeEventListener(...a);
globalThis.innerWidth = 1000;
globalThis.innerHeight = 800;
globalThis.devicePixelRatio = 1;
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
globalThis.performance = { now: () => 0 };
let now = 0;
const timers = [];
globalThis.setTimeout = (fn, ms) => {
  // Keep only the latest debounce timer (clearTimeout semantics).
  timers.length = 0;
  timers.push({ fn, at: now + ms });
  return 1;
};
globalThis.clearTimeout = () => { timers.length = 0; };
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => {};
globalThis.ResizeObserver = class { observe() {} disconnect() {} };

const stubCtx = () => new Proxy({
  fillStyle: '', strokeStyle: '',
  createRadialGradient: () => ({ addColorStop() {} }),
  createLinearGradient: () => ({ addColorStop() {} }),
}, { get: (t, p) => (p in t ? t[p] : () => t) });
const canvas = {
  width: 0, height: 0, style: {},
  classList: { add() {}, remove() {}, toggle() {} },
  parentElement: { clientWidth: 1000, clientHeight: 800 },
  getContext: () => stubCtx(),
};

const { resetFrameSchedulerForTests } = await import('./web/v2/neural/frame-scheduler.js');
resetFrameSchedulerForTests();
const { NeuralEngine } = await import('./web/v2/neural/engine.js');
const engine = new NeuralEngine(canvas);
engine.init();
const builds0 = engine.getGeometryBuildCount();
// Material size change required for rebuild under 11.P3 threshold.
canvas.parentElement.clientWidth = 1200;
canvas.parentElement.clientHeight = 900;
engine._scheduleResize();
engine._scheduleResize();
engine._scheduleResize();
if (timers.length !== 1) throw new Error('debounce should keep one timer, got ' + timers.length);
now = 200;
timers[0].fn();
const builds1 = engine.getGeometryBuildCount();
if (builds1 !== builds0 + 1) throw new Error('debounced resize should rebuild once, got ' + (builds1 - builds0));
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

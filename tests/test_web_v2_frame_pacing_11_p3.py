# =====================================
# Titan Web V2 — Phase 11.P3 Frame Pacing + Micro-Stutter Tests
# =====================================

"""Contracts for shared display clock, cache rebuild rules, and frame-time polish."""

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


# --- Source contracts ---------------------------------------------------------


def test_frame_scheduler_module_exists() -> None:
    text = (V2 / "neural" / "frame-scheduler.js").read_text(encoding="utf-8")
    assert "FrameScheduler" in text
    assert "getFrameScheduler" in text
    assert "MAX_FRAME_DELTA_MS" in text
    assert "register" in text
    assert "idempotent" in text.lower() or "Idempotent" in text


def test_engine_uses_shared_scheduler_and_delta() -> None:
    engine = (V2 / "neural" / "engine.js").read_text(encoding="utf-8")
    assert "getFrameScheduler" in engine
    assert "MIN_RESIZE_DELTA_PX" in engine
    assert "advanceFade" in engine
    assert "_onFrame" in engine
    assert "markStaticRebuildPending" in engine
    # Chat pending must not force geometry rebuild.
    assert "never rebuild static cache or geometry" in engine


def test_renderer_delta_time_not_fixed_step() -> None:
    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    assert "_time += Math.max(0, deltaMs) / 1000" in renderer or "deltaMs) / 1000" in renderer
    assert "0.016" not in renderer or "_lastDeltaMs" in renderer
    assert "markStaticRebuildPending" in renderer
    assert "_fgNodeScratch" in renderer


def test_performance_monitor_percentiles() -> None:
    text = (V2 / "neural" / "performance-monitor.js").read_text(encoding="utf-8")
    for token in (
        "medianFrameMs",
        "p95FrameMs",
        "p99FrameMs",
        "framesOver25",
        "framesOver50",
        "skippedDecorative",
        "staticRebuilds",
        "activeRafCount",
        "Float64Array",
    ):
        assert token in text


def test_quality_fade_and_no_pending_rebuild() -> None:
    qc = (V2 / "neural" / "quality-controller.js").read_text(encoding="utf-8")
    assert "advanceFade" in qc
    assert "QUALITY_FADE_RATE" in qc
    assert "decorativeCadence" in qc
    assert "never geometry / static rebuild" in qc
    assert "targetVisualHz: 60" in qc


def test_orchestrator_sparkline_uses_shared_clock() -> None:
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    assert "getFrameScheduler" in orch
    assert "titan-orchestrator-sparkline" in orch
    assert "frame.deltaMs" in orch


def test_css_avoids_layout_animation_for_breathe() -> None:
    ui = (V2 / "design" / "ui.css").read_text(encoding="utf-8")
    assert "tdl-v2-core-breathe-alt" in ui
    # Prefer opacity/transform over filter brightness in the live keyframe.
    breathe = ui.split("@keyframes tdl-v2-core-breathe-alt")[1].split("/* ---")[0]
    assert "opacity" in breathe
    assert "filter: brightness" not in breathe

    orch = (V2 / "design" / "orchestrator.css").read_text(encoding="utf-8")
    # Isolate the keyframe body only (stop before next rules).
    panel = orch.split("@keyframes tdl-orch-panel-breathe")[1].split("}")[0]
    assert "opacity" in panel

    ref = (V2 / "design" / "reference-final.css").read_text(encoding="utf-8")
    acrylic = ref.split("@keyframes tdl-v2-acrylic-breathe")[1].split("}")[0]
    assert "opacity" in acrylic
    assert "box-shadow" not in acrylic


def test_fps_overlay_throttled() -> None:
    settings = (V2 / "core" / "settings-performance.js").read_text(encoding="utf-8")
    assert "500" in settings
    assert "medianFrameMs" in settings
    assert "p95FrameMs" in settings
    assert "Throttled DOM" in settings or "never update overlay every" in settings


def test_thinking_label_cheap_text_only() -> None:
    cm = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "textContent !== text" in cm
    assert "Titan traite ta demande" in cm


# --- Node runtime -------------------------------------------------------------


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_single_primary_raf_scheduler_idempotent() -> None:
    out = _run_node(
        r"""
const listeners = {};
globalThis.window = globalThis;
globalThis.document = {
  hidden: false,
  addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); },
  removeEventListener: (t, fn) => {
    listeners[t] = (listeners[t] || []).filter((f) => f !== fn);
  },
};
let rafCount = 0;
const pending = new Map();
globalThis.requestAnimationFrame = (cb) => {
  rafCount += 1;
  const id = rafCount;
  pending.set(id, cb);
  return id;
};
globalThis.cancelAnimationFrame = (id) => pending.delete(id);

const {
  getFrameScheduler,
  resetFrameSchedulerForTests,
  MAX_FRAME_DELTA_MS,
} = await import('./web/v2/neural/frame-scheduler.js');

resetFrameSchedulerForTests();
const s = getFrameScheduler();
let calls = 0;
const un1 = s.register('a', () => { calls += 1; }, { priority: 10 });
const un1b = s.register('a', () => { calls += 1; }, { priority: 10 }); // replace
s.register('b', () => {}, { cadence: 2, priority: 1 });
if (s.getCallbackCount() !== 2) throw new Error('idempotent register broken');
if (s.getActiveRafCount() !== 1) throw new Error('expected 1 RAF');
if (pending.size !== 1) throw new Error('duplicate loops at start');

// Drive one frame with huge resume delta — must clamp.
// Drive frames through the live RAF chain (do not double-invoke the same cb).
let cb = pending.values().next().value;
pending.clear();
cb(1000);
cb = pending.values().next().value;
pending.clear();
cb(1000 + 500); // 500ms wall gap → clamped
if (MAX_FRAME_DELTA_MS > 40) throw new Error('clamp too loose');

// Hidden resume must not duplicate.
document.hidden = true;
for (const fn of listeners.visibilitychange || []) fn();
if (s.getActiveRafCount() !== 0) throw new Error('hidden must stop RAF');
pending.clear();
document.hidden = false;
for (const fn of listeners.visibilitychange || []) fn();
if (s.getActiveRafCount() !== 1) throw new Error('resume must restart single RAF');
if (pending.size !== 1) throw new Error('duplicate after resume: ' + pending.size);

un1();
un1b();
s.unregister('b');
if (s.getActiveRafCount() !== 0) throw new Error('empty scheduler must stop');

console.log(JSON.stringify({ ok: true, calls, clamp: MAX_FRAME_DELTA_MS }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_delta_clamp_and_cadence() -> None:
    out = _run_node(
        r"""
globalThis.window = globalThis;
globalThis.document = {
  hidden: false,
  addEventListener() {},
  removeEventListener() {},
};
const pending = new Map();
let id = 0;
globalThis.requestAnimationFrame = (cb) => {
  id += 1;
  pending.set(id, cb);
  return id;
};
globalThis.cancelAnimationFrame = (i) => pending.delete(i);

const {
  getFrameScheduler,
  resetFrameSchedulerForTests,
  MAX_FRAME_DELTA_MS,
} = await import('./web/v2/neural/frame-scheduler.js');
resetFrameSchedulerForTests();
const s = getFrameScheduler();
/** @type {number[]} */
const deltas = [];
let lowPri = 0;
s.register('core', (f) => deltas.push(f.deltaMs), { priority: 100 });
s.register('deco', () => { lowPri += 1; }, { cadence: 3, phase: 0, priority: 1 });

const tick = pending.values().next().value;
pending.clear();
tick(0);
tick(16.7);
tick(16.7 + 16.7);
tick(16.7 * 3);
tick(16.7 * 3 + 200); // clamp
if (deltas[deltas.length - 1] > MAX_FRAME_DELTA_MS + 0.01) {
  throw new Error('delta not clamped: ' + deltas[deltas.length - 1]);
}
if (lowPri < 1) throw new Error('cadence callback never ran');
if (lowPri >= deltas.length) throw new Error('low-pri should run less often');

console.log(JSON.stringify({ ok: true, deltas, lowPri, clamp: MAX_FRAME_DELTA_MS }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_static_cache_not_rebuilt_by_chat_telemetry() -> None:
    out = _run_node(
        r"""
const store = new Map();
globalThis.sessionStorage = {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
globalThis.localStorage = globalThis.sessionStorage;
const listeners = {};
globalThis.document = {
  hidden: false,
  documentElement: { classList: { toggle() {}, contains: () => false }, dataset: {} },
  getElementById: () => null,
  createElement: (tag) => ({
    tagName: String(tag).toUpperCase(),
    width: 0,
    height: 0,
    style: {},
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
  addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); },
  removeEventListener: (t, fn) => {
    listeners[t] = (listeners[t] || []).filter((f) => f !== fn);
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
globalThis.innerWidth = 1920;
globalThis.innerHeight = 1080;
globalThis.devicePixelRatio = 1;
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
globalThis.performance = { now: () => 1000 };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
globalThis.requestAnimationFrame = (cb) => 1;
globalThis.cancelAnimationFrame = () => {};

const canvas = {
  width: 0, height: 0, style: {},
  classList: { add() {}, remove() {}, toggle() {} },
  parentElement: { clientWidth: 1920, clientHeight: 1080 },
  getContext: () => ({
    setTransform() {}, fillRect() {}, fillStyle: '',
    save() {}, restore() {}, beginPath() {}, arc() {}, fill() {}, stroke() {},
    createRadialGradient: () => ({ addColorStop() {} }),
    createLinearGradient: () => ({ addColorStop() {} }),
    drawImage() {},
    globalCompositeOperation: '', globalAlpha: 1,
    lineCap: '', lineJoin: '', lineWidth: 1, strokeStyle: '',
  }),
};

const { resetFrameSchedulerForTests } = await import('./web/v2/neural/frame-scheduler.js');
resetFrameSchedulerForTests();
const { NeuralEngine } = await import('./web/v2/neural/engine.js');
const engine = new NeuralEngine(canvas);
engine.init();
engine.quality.markGeometryClean();
const geo0 = engine.getGeometryBuildCount();
const static0 = engine.renderer.getStaticRebuildCount();

// Chat pending + notifyInteractive must not rebuild geometry or mark dirty.
engine.setChatPending(true);
engine.setChatPending(true); // idempotent
engine.notifyInteractive(100);
engine.setChatPending(false);
const geo1 = engine.getGeometryBuildCount();
if (geo1 !== geo0) throw new Error('chat pending rebuilt geometry');
if (engine.quality.needsGeometryRebuild()) throw new Error('pending must not dirty geometry');
if (engine.renderer.getStaticRebuildCount() !== static0) {
  throw new Error('chat pending must not rebuild static cache');
}

// Minor resize under threshold — no rebuild.
engine._lastWidth = 1920;
engine._lastHeight = 1080;
canvas.parentElement.clientWidth = 1924; // +4 < 8
canvas.parentElement.clientHeight = 1082;
engine.resize();
if (engine.getGeometryBuildCount() !== geo1) {
  throw new Error('minor resize rebuilt geometry');
}

// Material resize rebuilds at most once.
canvas.parentElement.clientWidth = 1600;
canvas.parentElement.clientHeight = 900;
engine.resize({ immediate: true });
const geo2 = engine.getGeometryBuildCount();
if (geo2 !== geo1 + 1) throw new Error('material resize should rebuild once, got ' + (geo2 - geo1));

// Quality change stages at most one rebuild.
const beforeQ = engine.getGeometryBuildCount();
engine.setQualityMode('performance');
const afterQ = engine.getGeometryBuildCount();
if (afterQ - beforeQ > 1) throw new Error('quality transition rebuilt more than once');

console.log(JSON.stringify({
  ok: true,
  geo0, geo1, geo2, beforeQ, afterQ,
  static0,
  afterStatic: engine.renderer.getStaticRebuildCount(),
}));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_quality_fade_and_monitor_percentiles() -> None:
    out = _run_node(
        r"""
const store = new Map();
globalThis.sessionStorage = {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
globalThis.localStorage = globalThis.sessionStorage;
globalThis.document = {
  documentElement: { classList: { contains: () => false } },
};
globalThis.window = globalThis;
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
globalThis.performance = { now: () => 5000 };

const { QualityController } = await import('./web/v2/neural/quality-controller.js');
const { PerformanceMonitor } = await import('./web/v2/neural/performance-monitor.js');

const qc = new QualityController({ mode: 'balanced' });
const b0 = qc.getBudgets();
qc._tier = 2;
qc._budgetsCache = null;
qc._fadeEdge = 1;
qc._targetEdge = 0.48;
qc.advanceFade(80); // partial step — must interpolate, not pop
const faded = qc._fadeEdge;
if (!(faded < 0.99 && faded > 0.48)) throw new Error('fade did not interpolate: ' + faded);

qc.markGeometryClean();
qc.setChatPending(true);
if (qc.needsGeometryRebuild()) throw new Error('pending must not set geometry dirty');
const pending = qc.getBudgets();
if (pending.maxEdgesDrawn > b0.maxEdgesDrawn) throw new Error('pending increased edges');

const mon = new PerformanceMonitor({ sampleWindow: 40 });
for (let i = 0; i < 40; i++) {
  mon.recordFrame(i % 5 === 0 ? 28 : 16.5);
}
mon.recordDroppedDecorative();
mon.recordStaticRebuild(2);
mon.updateMeta({ rafLoops: 1, dpr: 1, qualityMode: 'auto', qualityTier: 'high' });
const snap = mon.getSnapshot();
if (snap.medianFrameMs == null) throw new Error('missing median');
if (snap.p95FrameMs == null) throw new Error('missing p95');
if (snap.p99FrameMs == null) throw new Error('missing p99');
if (snap.framesOver25 < 1) throw new Error('expected frames over 25');
if (snap.staticRebuilds < 2) throw new Error('static rebuild count missing');
if (snap.activeRafCount !== 1) throw new Error('raf count missing');

console.log(JSON.stringify({ ok: true, snap, faded }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_resize_debounce_constant() -> None:
    out = _run_node(
        r"""
const { RESIZE_DEBOUNCE_MS, MIN_RESIZE_DELTA_PX } = await import('./web/v2/neural/engine.js');
if (RESIZE_DEBOUNCE_MS < 100) throw new Error('debounce too short');
if (MIN_RESIZE_DELTA_PX < 4) throw new Error('threshold too small');
console.log(JSON.stringify({ ok: true, RESIZE_DEBOUNCE_MS, MIN_RESIZE_DELTA_PX }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")


# --- Backend health / auth contracts -----------------------------------------


def test_health_endpoints_declared() -> None:
    """Route contracts — full 200 readiness uses the brain_client fixture elsewhere."""
    app_src = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert "/health" in app_src
    assert "/ready" in app_src


def test_canonical_composition_markers_intact() -> None:
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    assert "tdl-v2-neural-canvas" in shell
    assert "tdl-v2-visual-quality" in shell
    ui = (V2 / "design" / "ui.css").read_text(encoding="utf-8")
    assert "tdl-v2-glass" in ui or "backdrop-filter" in ui

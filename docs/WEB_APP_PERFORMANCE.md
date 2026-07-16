# Titan Web App — Performance Stabilization (Phase 11.P1)

## Goal

Keep the approved black/red neural identity while making the Railway-hosted Web App fluid on ordinary modern computers.

Targets:

- Prefer ~60 FPS when possible
- Never remain below ~30 FPS during normal idle use
- Typing, scrolling, navigation, and chat submission stay responsive
- No decorative work when the tab is hidden
- No backend/chat regression

This is a **renderer optimization pass**, not a redesign.

---

## Root causes (ranked by impact)

1. **Extreme per-frame draw volume** — up to 12 000 nodes, tens of thousands of edge strokes, multi-band tissue strands, filaments, micro-neurons, dust, bokeh, and multiple full-canvas gradient haze/fog/bloom passes every frame.
2. **Uncapped / high devicePixelRatio** — internal canvas up to DPR 2 on retina displays → 4× pixel fill vs CSS size.
3. **Per-frame allocations** — `filter`/`sort` of node layers and new tissue band arrays every frame → GC spikes.
4. **Adaptive density rebuilt the whole scene** — old adaptive path called `nodes.build()` on FPS dips, regenerating thousands of objects (popping + long tasks).
5. **Secondary RAF loops** — orchestrator sparkline ran at full 60 FPS alongside the neural engine.
6. **SSE reconnect storms** — unauthorized `/events/stream` could retry without an auth gate.

**Verdict:** This was primarily a **coding / renderer budget problem**, not a requirement for extreme client hardware. The LLM still runs on Railway; the UI must not burn the client GPU/CPU while idle.

---

## Profiling snapshot (pre-fix architecture)

Approximate budgets at 1920×1080, DPR 2, Cinematic ceilings:

| Metric | Pre-fix (config ceilings) |
|---|---|
| Nodes | 5 200–12 000 (capped at max) |
| Core filaments | 1 280 |
| Micro neurons | 3 200 |
| Field tissue strands | ~3 000+ (colonies + highways + wisps) |
| maxEdgesDrawn | 26 000 |
| maxTissueDrawn | 3 400 |
| Dust / bokeh | 180 / 28 |
| Ambient + fog + bloom patches | many full-canvas gradients / frame |
| Active neural RAF loops | 1 (plus orchestrator sparkline RAF) |
| Hidden tab | paused via `isPaused`, but resume path needed hardening |

Reported field observation before this step: roughly **20–28 FPS idle** on a second computer.

---

## Renderer architecture (after 11.P1)

```
NeuralStage
  └── NeuralEngine  (single requestAnimationFrame)
        ├── QualityController   (mode + adaptive tier)
        ├── PerformanceMonitor  (FPS / budgets snapshot)
        ├── NeuralNodes / tissue geometry  (built on resize / mode change only)
        └── NeuralRenderer      (draw-time budgets + effect toggles)
```

### Quality modes

| Mode | Default DPR cap | Node scale | Edges | Tissue | Notes |
|---|---|---|---|---|---|
| **Performance** | 1.0 | ~0.32 / max 3 200 | 4 200 | 900 | Weak laptops / iGPU |
| **Balanced** (default) | 1.25 | ~0.55 / max 6 500 | 10 000 | 1 800 | Adaptive tiers; nearly full look |
| **Cinematic** | 1.75 | 1.0 / config max | 26 000 | 3 400 | Full approved density |

Balanced adapts draw budgets with hysteresis (degrade ~2.2 s, recover ~9 s, min gap ~3.5 s). It does **not** rebuild geometry every few seconds.

### Persistence

- Mode stored in `localStorage` key `titan_visual_quality_mode`
- Settings → **Qualité visuelle**: Performance / Balanced / Cinematic
- Optional reduce-motion checkbox; FPS overlay only in debug (`?debug` or `localStorage.titan_debug_perf=1`)

---

## Optimizations applied

1. DPR capped per quality mode
2. Geometry built once per resize / mode change (cached layer lists)
3. Draw-time tissue/edge/filament/micro budgets
4. Reduced gradient patch counts by mode/tier
5. Skip expensive fog/lens/bokeh when tier or mode says so
6. Viewport AABB culling for edges/nodes
7. Reused tissue band arrays (less GC)
8. Hidden tab cancels RAF; resume without duplicates
9. Idle frame skip in Performance / low adaptive tier
10. Interactive priority: typing/submit can drop decorative passes (`renderLight`)
11. Resize debounced (120 ms)
12. Orchestrator sparkline throttled (~12 FPS) + skips work when hidden
13. SSE auth gate + bounded backoff + pause while hidden
14. Idempotent `NeuralEngine.init()` / `NeuralStage.mount()`

---

## Client vs server latency

| Signal | Meaning |
|---|---|
| Railway `/chat` duration, Brain stage events | **Titan is thinking** (server/LLM) |
| `clientFps` / `clientFrameMs` in store + FPS overlay | **UI is rendering slowly** |

Do not confuse a long Brain response with a low FPS canvas.

---

## Benchmark procedure (local)

Environment:

- 1920×1080, browser zoom 100%
- Chrome or Edge DevTools → Performance / Rendering → FPS meter
- Open Settings → Visual Quality

### Balanced — idle 60 s

1. Load Web App, authenticate
2. Set **Balanced**
3. Leave idle (no typing) for 60 s
4. Record average FPS, 1% low if available, DPR from overlay (`?debug` + enable FPS)
5. Note Task Manager / Activity Monitor browser process CPU

### Balanced — active chat

1. Send a short message
2. Watch FPS during typing and while the response streams
3. Confirm input remains responsive (no multi-hundred-ms key delay)

### Hidden / restore

1. Switch tab away for 10 s
2. Confirm neural RAF pauses (FPS overlay shows PAUSED or CPU drops)
3. Return — single loop resumes, no duplicate activity

### Performance mode

Repeat idle 60 s with **Performance**. Expect higher FPS / lower CPU than Balanced; lighter density is intentional.

### After deploy (Railway)

1. Hard-refresh the Railway URL
2. Confirm Settings quality control works and persists across reload
3. Confirm `/health` and `/ready` still OK
4. Confirm chat still streams

---

## Measured results

### Instrumentation approach

Node-level unit tests validate budgets, DPR caps, single RAF, visibility pause, debounce, adaptive hysteresis, and SSE auth gate.

**Browser FPS must be measured on a real machine** (DevTools FPS meter). This document does not claim 60 FPS without that measurement.

### Expected after-fix (engineering estimate)

| Scenario | Expected |
|---|---|
| Balanced idle, 1080p, integrated GPU | typically ≥ 30 FPS; often 45–60 on mid hardware |
| Performance idle | typically closer to 45–60 FPS |
| Cinematic idle | may sit 30–55 FPS depending on GPU |
| Hidden tab | ~0 neural frames |

Fill in actual numbers after local/Railway verification:

| Scenario | Avg FPS | 1% low | DPR | Canvas CSS | Notes |
|---|---|---|---|---|---|
| Balanced idle 60 s | _measure_ | _measure_ | ≤ 1.25 | 1920×1080 | |
| Performance idle 60 s | _measure_ | _measure_ | 1.0 | 1920×1080 | |
| Active chat | _measure_ | | | | input priority |

---

## Known limitations

- Field tissue geometry is still built at full architectural richness; Performance/Balanced reduce **draw** density more than rebuild topology.
- Offscreen static far-field caching is not yet a separate canvas layer (future win).
- `performance.memory` is Chromium-only.
- Orchestrator sparkline still uses its own RAF (throttled), not merged into the neural scheduler.
- Extreme 4K + Cinematic + discrete GPU can still exceed 16 ms/frame — use Balanced/Performance.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Still ~20 FPS idle | Confirm mode is not Cinematic; enable FPS overlay; verify DPR ≤ 1.25 in Balanced |
| Popping / scene rebuilds often | Should only happen on resize or mode change — report if otherwise |
| Chat laggy while FPS high | Likely server/LLM latency, not renderer |
| Event stream reconnect spam | Ensure logged in; unauthorized should stop after auth probe |
| Blank canvas after tab switch | Visibility resume bug — hard refresh and file issue |

Debug:

```
?debug=1
localStorage.setItem('titan_debug_perf', '1')
```

Then enable **Afficher FPS (debug)** in Settings.

---

## Files touched (11.P1)

- `web/v2/neural/quality-controller.js` (new)
- `web/v2/neural/performance-monitor.js` (new)
- `web/v2/neural/engine.js`
- `web/v2/neural/renderer.js`
- `web/v2/neural/nodes.js`
- `web/v2/neural/utils.js`
- `web/v2/neural/config.js`
- `web/v2/neural/stage.js`
- `web/v2/core/backend-bridge.js`
- `web/v2/core/settings-performance.js` (new)
- `web/v2/core/app.js`
- `web/v2/core/state-store.js`
- `web/v2/composer/composer-region.js`
- `web/v2/layout/shell.js`
- `web/v2/design/ui.css`
- `web/v2/orchestrator/orchestrator-region.js`
- `tests/test_web_v2_performance.py`
- `docs/WEB_APP_PERFORMANCE.md`

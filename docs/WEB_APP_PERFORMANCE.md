# Titan Web App — Performance Stabilization (Phase 11.P1 + 11.P2 + 11.P3)

## Goal

Keep the approved black/red neural identity while making the Railway-hosted Web App feel **consistently smooth** — not merely report a high average FPS.

Targets:

- Prefer ~60 FPS with stable ~16.7 ms frame times when hardware permits
- Measure median / p95 / p99 frame time (FPS alone is insufficient)
- No persistent visible hitching or periodic cache-rebuild spikes
- Typing, scrolling, navigation, and chat submission stay responsive
- No decorative work when the tab is hidden
- Single primary `requestAnimationFrame` display clock
- Canvas `devicePixelRatio` capped per mode
- No backend/chat regression

This is a **renderer polish pass**, not a redesign.

---

## Why 11.P2 still felt uneven (micro-stutter audit)

11.P2 raised production FPS to ~60 on average, but motion still hitchied. Verified causes (not guesses):

| # | Cause | Evidence |
|---|---|---|
| 1 | **Irregular whole-frame skips** | `targetVisualHz` 28–30 + `idleFrameSkip` + chat-pending modulo skips produced alternating heavy/light frames |
| 2 | **Fixed per-paint clock** | Renderer advanced `_time += 0.016` instead of delta time → jumps when frames were skipped |
| 3 | **Multiple independent RAF loops** | Neural engine + orchestrator sparkline + AnimationEngine each owned a RAF |
| 4 | **Aggressive static invalidation** | Every `resize()` invalidated cache; 1 px threshold; emergency rebuild mid-tick |
| 5 | **CSS filter / box-shadow animation** | Core breathe used `filter: brightness`; acrylic/orchestrator panels animated `box-shadow` |
| 6 | **Per-frame allocations** | `getBudgets()` object spreads; `filter()` in fog path; `shift()` on FPS samples |
| 7 | **Monitor / telemetry noise** | Overlay updates were fine at 400 ms, but frame-time percentiles were missing |

Combination: **frame pacing + multiple clocks + cache invalidation + CSS + GC pressure**.

---

## Shared display clock (11.P3)

```
requestAnimationFrame  →  FrameScheduler (one primary loop)
                              ├── neural-engine (priority 100, cadence 1)
                              ├── animation-engine (priority 50, when tasks exist)
                              └── orchestrator-sparkline (priority 10, cadence 5 ≈ 12 Hz)
```

Rules:

- One primary RAF; subsystems register idempotent callbacks by id
- Shared `timestamp` + clamped `deltaMs` (`MAX_FRAME_DELTA_MS = 33.5`)
- Hidden-tab stop; resume resets clock (first frame uses nominal delta — no catch-up storm)
- No multi-step simulation catch-up in one visible frame
- Decorative work may be skipped when over budget; Core stays continuous

Module: `web/v2/neural/frame-scheduler.js`

---

## Frame pacing model

| Layer | Cadence | Notes |
|---|---|---|
| Titan Core + static blit | every display frame | continuous presence |
| Live signals / near tissue | every frame when under budget | skipped via `renderLight` when over budget / chat pending |
| Far-field / sparkline / card micro | reduced (`decorativeCadence`, `farFieldCadence`) | interpolated via delta time between updates |
| CSS panel breathe | opacity-only or frozen under `.tdl-v2--perf-light` | no animated box-shadow / filter |

Auto / Performance / Balanced target **60 Hz** visual clock with static cache. Emergency keeps Core on the display clock and raises decorative cadence instead of skipping whole frames irregularly.

---

## Static cache rebuild rules

Rebuild **only** when:

- viewport size changes by ≥ `MIN_RESIZE_DELTA_PX` (8 px)
- quality mode / emergency tier changes (staged)
- scene geometry rebuild (seed / density)
- explicit regeneration

Do **not** rebuild from:

- chat telemetry / elapsed “traite ta demande…” text
- adaptive tier samples (draw-scale fade only)
- minor browser chrome resize (&lt; 8 px)
- panel DOM updates

Resize debounce: `RESIZE_DEBOUNCE_MS = 160`.

Staging: `markStaticRebuildPending()` keeps the last valid blit visible until the new cache is ready. Emergency / quality rebuilds are deferred to the next frame (no mid-draw hitch).

---

## Allocation reductions

- Circular `Float64Array` frame buffer (no `shift()` per frame)
- Reused foreground-node scratch array (no per-frame `filter`)
- Cached quality budgets object (invalidated on real input changes)
- Soft quality fades mutate scalars; Adaptive tiers do not rebuild geometry
- Scheduler ordered-callback list rebuilt only on register/unregister
- Thinking label updates `textContent` only when the string changes

---

## Quality transitions

| Mode | Behavior |
|---|---|
| Auto (default) | Hysteresis + emergency watchdog; draw scales fade via `advanceFade` |
| Performance | Low budgets, static cache, 60 Hz Core |
| Balanced | Near reference look, static cache, 60 Hz target |
| Cinematic | Full draw path, optional no static cache |

Switching modes stages geometry/cache rebuild; current frame remains visible. Chat pending trims draw budgets only — never geometry / static rebuild.

---

## Performance monitor (debug)

`?debug=1` or `localStorage.titan_debug_perf=1` overlay (throttled **500 ms**):

- rolling FPS
- median / p95 / p99 frame time
- frames &gt; 25 ms / &gt; 50 ms
- skipped decorative count
- cache rebuild count
- active RAF count (primary clock)
- quality tier + canvas DPR

Do not update the overlay every animation frame.

---

## Measured budgets (architectural, 1920×1080 CSS)

| Mode | DPR cap | maxEdges | maxTissue | maxNodes | dust | display clock |
|---|---|---|---|---|---|---|
| Auto (11.P3) | 1.0 | 5 200 | 1 100 | 3 800 | 28 | 60 Hz + static cache |
| Performance | 1.0 | 4 200 | 900 | 3 200 | 24 | 60 Hz + static cache |
| Emergency | 1.0 | 2 800 | 520 | 2 200 | 0 | 60 Hz Core; deco cadence ↑ |
| Critical | 1.0 | ~1 820 | ~338 | ~1 430 | 0 | same; heavier deco skip |
| Balanced | 1.25 | 10 000 | 1 800 | 6 500 | 72 | 60 Hz + static cache |
| Cinematic | 1.75 | 26 000 | 3 400 | config max | 180 | 60 Hz full path |

### Browser frame-time Benchmark (fill after Railway / local verify)

Measure ≥ 60 s at 1920×1080, zoom 100%, production-like mode. Prefer DevTools Performance + FPS overlay percentiles.

| Scenario | Avg FPS | Median ms | p95 ms | p99 ms | &gt;25 ms | &gt;50 ms | Cache rebuilds | Active RAF |
|---|---|---|---|---|---|---|---|---|
| Before 11.P2 (field) | ~20 | — | — | — | high | high | continuous redraw | ≥2 |
| After 11.P2 Auto idle | ~60 | uneven | hitchy | — | periodic | spikes | occasional | 2–3 |
| After 11.P3 Auto idle | _measure_ | _measure_ | prefer &lt;22 | _measure_ | few | rare | 0 while idle | **1** |
| After 11.P3 Balanced | _measure_ | | | | | | | 1 |
| After 11.P3 Performance | _measure_ | | | | | | | 1 |
| Typing | | | | | | | 0 | 1 |
| Chat pending | | | | | | | 0 | 1 |
| Tab hide/restore | | | | | | | 0 (no dup loops) | 0→1 |

**Do not claim smoothness from average FPS alone.**

---

## Thinking / chat-pending performance

When a chat request is pending:

- Core + last static blit stay continuous (`renderLight`)
- Signal density stays lightened (`signalLighten`) — thinking does **not** densify particles
- Elapsed UI is text-only (`textContent`); no layout / cache rebuild
- Decorative cadence increases; network/Brain progress does not add canvas work
- Stop button and typing remain interactive

---

## CSS / DOM notes

- Smoked-glass `backdrop-filter` remains for identity (static panels)
- Continuous animation prefers **opacity / transform**
- `.tdl-v2--perf-light` freezes expensive panel breathe animations
- Avoid animating `box-shadow`, `filter`, width/height/top/left for ambient loops

---

## Client vs server latency

| Signal | Meaning |
|---|---|
| Railway `CHAT_*` timing + `request_id` | Brain / provider latency |
| FPS overlay percentiles | UI renderer cost |

A long “Titan réfléchit…” with healthy frame times is a **server/provider** wait, not a canvas problem.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Still hitching at ~60 FPS | Inspect p95/p99; look for cache rebuild spikes; confirm active RAF = 1 |
| Periodic freeze every few seconds | Adaptive emergency rebuild? Overlay? ResizeObserver noise? |
| Quality control missing | Top-right compact select + Settings gear |
| Chat laggy while frame times good | Railway logs `CHAT_` + `request_id` |
| Duplicate motion clocks | Confirm orchestrator/animation use `getFrameScheduler()` |

Debug:

```
/app/?debug=1
/app/?quality=performance
localStorage.setItem('titan_debug_perf', '1')
```

---

## Remaining limitations (honest)

- Static cache freezes far-field parallax until the next rebuild (by design).
- Field tissue geometry is still *built* richly; Emergency mainly cuts **draw** + cadence.
- `performance.memory` is Chromium-only; GC spikes are inferred from frame-time outliers.
- Authenticated Railway Brain latency is independent of FPS fixes.
- Integrated GPUs / thermal throttling can still raise p95 under Cinematic.
- One-shot `requestAnimationFrame` for pointer coalescing / opacity transitions may still appear briefly (not persistent loops).

---

## Files touched (11.P3)

- `web/v2/neural/frame-scheduler.js` — **new** shared display clock
- `web/v2/neural/engine.js` — scheduler integration, resize threshold, staged rebuilds
- `web/v2/neural/renderer.js` — delta-time clock, staged cache, allocation reuse
- `web/v2/neural/quality-controller.js` — 60 Hz targets, fades, pending ≠ rebuild
- `web/v2/neural/performance-monitor.js` — percentiles, circular buffer
- `web/v2/neural/stage.js` / `utils.js`
- `web/v2/animation/animation-engine.js` — shared scheduler
- `web/v2/orchestrator/orchestrator-region.js` — sparkline on shared clock
- `web/v2/core/settings-performance.js` — throttled percentile overlay
- `web/v2/conversation/conversation-manager.js` — cheap thinking label
- `web/v2/design/ui.css` / `orchestrator.css` / `reference-final.css` — opacity breathes
- `tests/test_web_v2_frame_pacing_11_p3.py`
- `tests/test_web_v2_performance.py` / `test_web_v2_emergency_fluidity_11_p2.py`
- `docs/WEB_APP_PERFORMANCE.md`

---

## Recommended next product step

After Railway verification of p95 frame time under Auto idle + chat pending: ship Phase 12 product work (tools / Obsidian / missions) rather than further decorative renderer redesign — unless production p95 remains above ~22 ms on target hardware.

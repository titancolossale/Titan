# Titan Web App — Performance Stabilization (Phase 11.P1 + 11.P2)

## Goal

Keep the approved black/red neural identity while making the Railway-hosted Web App fluid on ordinary modern computers.

Targets:

- Prefer ~60 FPS when possible
- Never remain below ~30 FPS during normal idle use
- Auto mode must escalate to Emergency when rolling FPS stays low
- Typing, scrolling, navigation, and chat submission stay responsive
- No decorative work when the tab is hidden
- Single neural `requestAnimationFrame` loop; canvas `devicePixelRatio` capped per mode
- No backend/chat regression

This is a **renderer optimization pass**, not a redesign.

---

## Why the first performance pass (11.P1) was insufficient

11.P1 added quality modes, DPR caps, adaptive tiers, and interactive `renderLight`. Field reports after deploy still showed ~**20 FPS**.

Root causes that remained:

1. **Default was Balanced** — still drew far too much tissue/edges/effects for integrated GPUs.
2. **No automatic emergency escape hatch** — if FPS stayed at 20, the renderer never forced a hard cut.
3. **Full scene redraw every frame** — far-field highways, colonies, and dust were stroked every RAF tick.
4. **Thinking made things worse** — chat pending only throttled when *not* thinking; once the orchestrator went active, decorative spawn density increased.
5. **Quality control hard to reach** — Settings gear existed, but production users did not find a visible quality selector.

11.P2 addresses those gaps directly.

---

## Emergency tier (Phase 11.P2)

Explicit `EMERGENCY_PRESET` (and `critical` sub-tier):

| Control | Emergency | Critical (FPS &lt; 25) |
|---|---|---|
| Canvas DPR | **1.0 hard cap** | 1.0 |
| Visual update rate | ~24 Hz | ~20 Hz |
| Edges / tissue / nodes | ~2800 / 520 / 2200 | ×0.65 further |
| Dust / bokeh / fog / plasma | off | off |
| Glow / shadowBlur / gradients | minimal (1 bloom spot max) | bloom off |
| Titan Core + main arteries | kept | kept (restrained) |
| Panels / composer / orchestrator | untouched | untouched |

### Auto-performance watchdog

Default production mode: **Auto**.

1. Page load starts with conservative Auto budgets (DPR ≤ 1.0, static cache on).
2. If rolling FPS &lt; 35 for **&gt; 3 seconds** → enter **Emergency** (session-persisted).
3. If rolling FPS &lt; 25 → escalate to **Critical**.
4. Does not wait for Settings.
5. Chat pending further reduces decorative budgets and never increases thinking particle density.

---

## Static vs dynamic layers

```
Offscreen static cache (rebuild on resize / quality / seed / explicit regen only)
  ├── far-field tissue
  ├── most neural highways / mid colonies
  ├── background edge/node layers
  └── static dust speckles

Dynamic foreground (each visual update)
  ├── Titan Core breathing
  ├── near/foreground tissue accents
  ├── live signal particles (capped)
  └── restrained pulse / vignette
```

Never rebuild the full neural civilization every frame.

---

## Quality selection access

| Surface | Control |
|---|---|
| Top-right | Compact **Auto / Perf / Balanced / Cinema** select |
| Settings overlay (gear) | Full **Qualité visuelle** select + reduce motion |
| URL override | `/app/?quality=performance` (also `auto`, `balanced`, `cinematic`) |
| Debug overlay | `?debug=1` or `localStorage.titan_debug_perf=1` |

Default: **Auto**.

Persistence: `localStorage.titan_visual_quality_mode`  
Emergency session lock: `sessionStorage.titan_visual_emergency_tier`

---

## Measured budgets (architectural, 1920×1080 CSS)

| Mode | DPR cap | maxEdges | maxTissue | maxNodes | dust | target visual Hz |
|---|---|---|---|---|---|---|
| Pre-11.P1 cinematic ceilings | ≤2.0 | 26 000 | 3 400 | ~12 000 | 180 | ~60 (uncapped cost) |
| Auto (11.P2 default) | 1.0 | 5 200 | 1 100 | 3 800 | 28 | 30 |
| Performance | 1.0 | 4 200 | 900 | 3 200 | 24 | 28 |
| Emergency | 1.0 | 2 800 | 520 | 2 200 | 0 | 24 |
| Critical | 1.0 | ~1 820 | ~338 | ~1 430 | 0 | 20 |
| Balanced | 1.25 | 10 000 | 1 800 | 6 500 | 72 | 45 |
| Cinematic | 1.75 | 26 000 | 3 400 | config max | 180 | 60 |

### Browser FPS Benchmark (must be measured on real hardware)

Fill after local/Railway verification with DevTools FPS meter:

| Scenario | Avg FPS | 1% low | DPR | Notes |
|---|---|---|---|---|
| Before (field) | ~20 | — | often 1.5–2 | continuous full redraw |
| Auto idle after 11.P2 | _measure_ | _measure_ | ≤1.0 | expect ≥30; ideally 45–60 |
| Auto/Emergency idle | _measure_ | | 1.0 | |
| Pending chat | _measure_ | | 1.0 | must stay responsive |
| Balanced | _measure_ | | ≤1.25 | |
| Typing latency | _measure_ | | | keys must feel immediate |

**Do not claim 60 FPS without DevTools measurement on the target machine.**

---

## Thinking-state performance

When a chat request is pending:

- Decorative canvas work is reduced further (`renderLight` / static blit + Core)
- Signal spawn uses idle density (`signalLighten`) — thinking does **not** densify particles
- DOM atmosphere particles paused via `.tdl-v2--perf-light`
- Input, message list, and network processing stay first priority

---

## Client vs server latency

| Signal | Meaning |
|---|---|
| Railway `CHAT_*` timing + `request_id` | Brain / provider latency |
| FPS overlay / `clientFps` | UI renderer cost |

A long “Titan réfléchit…” with healthy FPS is a **server/provider** wait, not a canvas problem.

---

## Known limitations

- Static cache freezes far-field parallax until the next rebuild (resize / quality change).
- Field tissue geometry is still *built* richly; Emergency mainly cuts **draw** + update rate.
- `performance.memory` is Chromium-only.
- Orchestrator sparkline still has its own throttled RAF.
- Authenticated Railway Brain latency is independent of FPS fixes.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Still ~20 FPS | Confirm Auto/Emergency in overlay; DPR must be 1.0; hard refresh |
| Quality control missing | Top-right compact select + Settings gear |
| Chat laggy while FPS high | Search Railway logs for `CHAT_` + `request_id` |
| Permanent “réfléchit…” | Client timeout 55s; should show error card + retry |

Debug:

```
/app/?debug=1
/app/?quality=performance
localStorage.setItem('titan_debug_perf', '1')
```

---

## Files touched (11.P2)

- `web/v2/neural/quality-controller.js` — Auto + Emergency + FPS watchdog
- `web/v2/neural/renderer.js` — static/dynamic split
- `web/v2/neural/engine.js` — visual Hz cap, thinking lighten, emergency rebuild
- `web/v2/neural/signals.js` / `state.js` — signal lighten
- `web/v2/neural/config.js` / `stage.js`
- `web/v2/core/settings-performance.js` / `state-store.js`
- `web/v2/layout/shell.js` / `center/topbar-region.js` / `design/ui.css`
- `web/v2/conversation/conversation-manager.js`
- `web/v2/core/backend-bridge.js`
- `api/chat_service.py` / `brain/llm.py`
- `tests/test_web_v2_emergency_fluidity_11_p2.py`
- `docs/WEB_APP_PERFORMANCE.md` / `docs/WEB_APP_CHAT_DIAGNOSTICS.md`

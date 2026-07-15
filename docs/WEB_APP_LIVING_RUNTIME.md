# Titan Web App — Phase 7 Living Runtime Experience

**Phase:** Living Runtime Experience (presentation only)  
**Scope:** top bar telemetry life · floating workspace micro-reactions · global atmosphere  
**Constraint:** No Titan Core, neural renderer redesign, sidebar redesign, floating workspace
structure rebuild, top bar layout redesign, composer, backend, API, Brain, runtime, or
memory-system changes — only local presentation wired to existing frontend state.

---

## Goal

Titan must feel alive. Every visible telemetry and workspace surface subtly reacts to
honest runtime state — never a static dashboard.

Animations stay restrained: soft fades, opacity transitions, neural pulses, tiny scan
sweeps, breathing glows, slow orbital motion. Never flashy. Never animate the whole page.

---

## Runtime activities

| Activity | Source (frontend only) |
|----------|------------------------|
| Idle | default / connected calm |
| Thinking | `pipelineThinking`, `presence===thinking`, cognitive thinking/reasoning |
| Planning | `cognitiveState===planning` |
| Working | `activeToolCount > 0`, tool_execution |
| Searching | browser tool / `browser_research` |
| Remembering | `recallActive`, `memory_recall` |

Dominant activity is resolved in `TopbarRegion._resolveRuntime()` and written to:

- `host.dataset.runtime` (top bar)
- `root.dataset.runtime` (atmosphere hooks)
- per-pill `data-activity`

---

## Top bar telemetry

Mémoire · Réflexion · Présence · Outils · **Cerveau** · Runtime

Each pill carries `data-status` + `data-activity`. CSS (`living-runtime.css`) drives
gentle dot animations per state. The Cerveau pill label maps activity → Veille /
Réflexion / Plan / Travail / Recherche / Mémoire.

---

## Floating workspaces

| Card | Living cues |
|------|-------------|
| Recent Memory | slow scan · small pulse · timestamp fade · `data-activity=remembering` |
| Obsidian | vault glow · sync pulse · quiet activity · `syncing` when live |
| Browser | connection indicator · search animation · idle shimmer |
| Cognitive State | soft breathing glow · state transition on `data-activity` |
| Presence | calm breathing ring · engagement pulse |

---

## Global atmosphere

- `tdl-v2-glow-ambient--living` — very slow light variation
- `tdl-v2-living-comms` — tiny neural communication nodes + slow orbit
- Root `data-runtime` slightly biases ambient filter on active states only

---

## Styles load order

1. … existing cascade …
2. `floating-workspaces.css`
3. `living-orchestrator.css` (Phase 6)
4. **`living-runtime.css`** ← Phase 7 authority (loaded last)

---

## Files changed

| File | Role |
|------|------|
| `web/v2/design/living-runtime.css` | Phase 7 living authority |
| `web/v2/center/topbar-region.js` | Runtime activity mapping + pill datasets |
| `web/v2/status/status-region.js` | Workspace `data-activity` wiring |
| `web/v2/layout/shell.js` | Living atmosphere + root datasets |
| `web/v2/core/version.js` | UI version → `0.46.0` |
| `web/v2/index.html` | Load living-runtime.css last · meta version |
| `config/settings.py` | Project version → `0.41.0` |
| `tests/test_web_v2_living_runtime.py` | Phase 7 contracts |
| `scripts/capture_phase7_living_runtime_screenshots.py` | Screenshot capture |

---

## Screenshots

| Capture | Path |
|---------|------|
| Full desktop idle | `docs/design/screenshots/phase-7-living-runtime-full.png` |
| Top bar crop | `docs/design/screenshots/phase-7-living-runtime-topbar.png` |
| Workspaces crop | `docs/design/screenshots/phase-7-living-runtime-workspaces.png` |
| Active demo | `docs/design/screenshots/phase-7-living-runtime-active.png` |

---

## Verify

```bash
pytest tests/test_web_v2_living_runtime.py tests/test_web_v2_floating_workspaces.py tests/test_web_v2_living_orchestrator.py -v
python scripts/capture_phase7_living_runtime_screenshots.py
```

Local URL: `http://127.0.0.1:8000/app/`

---

## Related

- `docs/WEB_APP_LIVING_ORCHESTRATOR.md` — Phase 6 command center
- `docs/WEB_APP_FLOATING_WORKSPACES.md` — Phase 5.4 workspace cards
- `docs/TITAN_DESIGN_CONSTITUTION.md` — living / restrained motion

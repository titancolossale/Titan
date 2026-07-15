# Titan Web App — Phase 8 Living Presence

**Phase:** Living Presence (presentation only)  
**Scope:** Titan Core presence · satellite light packets · atmospheric life ·
workspace wake · orchestrator subtle telemetry life  
**Constraint:** No layout redesign, color changes, neural renderer rewrite,
sidebar rebuild, composer changes, backend, API, Brain, runtime, or memory-system
changes — presentation only, wired to existing frontend state.

---

## Goal

Titan must feel like an intelligent entity occupying the interface — not a
dashboard. Every idle surface stays alive: breathing, tiny attention shifts,
occasional neural synchronization. Premium. Minimal. Organic. Never flashy.

---

## Presence layers

| Layer | Behavior |
|-------|----------|
| Titan Core | Soft heartbeat · energy breath · wave rings through nearby tissue · micro attention |
| Satellite nodes | Occasional slow light packets between satellites · unique paths · never repetitive |
| Atmosphere | Tiny floating particles · distant flashes · very slow ambient brightness |
| Workspaces | Calm when idle · local wake on runtime activity (Memory scan · Browser listen · Obsidian sync · Presence breath · Cognitive react) |
| Right orchestrator | Pipeline pulses · objective breathe · soft status / activity markers — frontend telemetry only |

---

## Styles load order

1. … existing cascade …
2. `living-orchestrator.css` (Phase 6)
3. `living-runtime.css` (Phase 7)
4. **`living-presence.css`** ← Phase 8 authority (loaded last)

---

## Files changed

| File | Role |
|------|------|
| `web/v2/design/living-presence.css` | Phase 8 presence authority |
| `web/v2/layout/shell.js` | Atmosphere particles + flashes · `data-phase=8` |
| `web/v2/center/cognitive-satellites.js` | Core heartbeat/energy/waves · inter-satellite packets |
| `web/v2/center/topbar-region.js` | Living presence datasets |
| `web/v2/status/status-region.js` | Workspace `data-living=8` |
| `web/v2/orchestrator/orchestrator-region.js` | Presence class + activity markers |
| `web/v2/core/version.js` | UI version → `0.47.0` |
| `web/v2/index.html` | Load living-presence.css last · meta version |
| `config/settings.py` | Project version → `0.42.0` |
| `tests/test_web_v2_living_presence.py` | Phase 8 contracts |
| `scripts/capture_phase8_living_presence_screenshots.py` | Screenshot capture |

---

## Screenshots

| Capture | Path |
|---------|------|
| Full desktop idle | `docs/design/screenshots/phase-8-living-presence-full.png` |
| Core / satellites crop | `docs/design/screenshots/phase-8-living-presence-core.png` |
| Workspaces crop | `docs/design/screenshots/phase-8-living-presence-workspaces.png` |
| Orchestrator crop | `docs/design/screenshots/phase-8-living-presence-orchestrator.png` |

---

## Verify

```bash
pytest tests/test_web_v2_living_presence.py tests/test_web_v2_living_runtime.py tests/test_web_v2_living_orchestrator.py -v
python scripts/capture_phase8_living_presence_screenshots.py
```

Local URL: `http://127.0.0.1:8000/app/`

---

## Related

- `docs/WEB_APP_LIVING_RUNTIME.md` — Phase 7 runtime reactions
- `docs/WEB_APP_LIVING_ORCHESTRATOR.md` — Phase 6 command center
- `docs/TITAN_DESIGN_CONSTITUTION.md` — living / restrained motion

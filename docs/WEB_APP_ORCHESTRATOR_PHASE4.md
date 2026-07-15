# Titan Web App — Phase 4.2 Cognitive Orchestrator Reconstruction

**Phase:** Component Reconstruction — RIGHT COGNITIVE ORCHESTRATOR ONLY  
**Scope:** `web/v2/design/orchestrator.css`, `web/v2/orchestrator/orchestrator-region.js`, load order, UI version  
**Constraint:** No backend, API, Brain, Memory, Voice Runtime, neural renderer, sidebar, top bar, bottom workspaces, or center composition changes  
**Canonical visual target:** Titan Design Constitution + `docs/design/screenshots/sprint-2.7-reference-composition.png`

---

**Superseded visually by:** `docs/WEB_APP_ORCHESTRATOR_PHASE43.md` (Phase 4.3 pixel fidelity).

---

## Goal

Rebuild the right panel as Titan’s **executive command center** — not a settings panel, not a dashboard. The user should immediately understand: Titan is actively thinking (or calmly ready).

---

## Objectives → Result

| Objective | Result |
|-----------|--------|
| **Top header** | COGNITIVE ORCHESTRATOR + animated neural glyph + En ligne · soft divider · deep glass |
| **Current Objective** | Large active objective, current mission, LIVE/IDLE chip, quiet activity bars |
| **Execution Pipeline** | Numbered 9-step list with Finished / ACTIVE / Waiting + subtle progress |
| **Active Tools** | Floating instrument cards: Obsidian · Memory · Browser · Trading · Calendar |
| **Neural Activity** | Soft waveform + tiny pulses — slow, restrained, no bright chrome |
| **Honesty** | Idle never fakes busy execution; presence truth retained as hidden hooks |

---

## Files changed

| File | Role |
|------|------|
| `web/v2/design/orchestrator.css` | **New** Phase 4.2 reconstruction layer (loaded last) |
| `web/v2/index.html` | Loads `orchestrator.css` after `sidebar.css` |
| `web/v2/orchestrator/orchestrator-region.js` | Command-center mount + pipeline/tools/neural |
| `web/v2/core/version.js` | UI version → `0.29.0` |
| `tests/test_web_v2_orchestrator_phase42.py` | Phase 4.2 contracts |
| `tests/test_web_v2_reference_*.py` / presence / sidebar | Story + version assertions |
| `scripts/capture_phase42_orchestrator_screenshots.py` | Screenshot capture |
| `docs/design/screenshots/phase-4.2-orchestrator-*.png` | Captures |

---

## Section map

```
┌─────────────────────────────┐
│ ✦ COGNITIVE ORCHESTRATOR    │  En ligne
├─────────────────────────────┤
│ CURRENT OBJECTIVE           │
│   large objective · mission │
│   LIVE/IDLE · activity      │
├─────────────────────────────┤
│ EXECUTION PIPELINE          │
│   1…9 status · progress     │
├─────────────────────────────┤
│ ACTIVE TOOLS                │
│   floating instrument cards │
├─────────────────────────────┤
│ NEURAL ACTIVITY             │
│   waveform · pulses         │
└─────────────────────────────┘
```

---

## Screenshots

| Capture | Path |
|---------|------|
| Full desktop | `docs/design/screenshots/phase-4.2-orchestrator-full.png` |
| Orchestrator panel | `docs/design/screenshots/phase-4.2-orchestrator-panel.png` |
| Right crop | `docs/design/screenshots/phase-4.2-orchestrator-crop.png` |
| Active demo | `docs/design/screenshots/phase-4.2-orchestrator-active.png` |

---

## Verify

```bash
pytest tests/test_web_v2_orchestrator_phase42.py tests/test_web_v2_sidebar_phase4.py tests/test_web_v2_reference_final.py tests/test_web_v2_reference_composition.py tests/test_web_v2_presence_os.py -v
python scripts/capture_phase42_orchestrator_screenshots.py
```

Local URL: `http://127.0.0.1:8000/app/`

---

## Related

- `docs/TITAN_DESIGN_CONSTITUTION.md`
- `docs/WEB_APP_SIDEBAR_PHASE4.md`
- `docs/WEB_APP_LAYOUT.md`
- `docs/WEB_APP_REFERENCE_COMPOSITION.md`

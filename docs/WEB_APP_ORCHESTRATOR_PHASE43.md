# Titan Web App — Phase 4.3 Pixel-Perfect Cognitive Orchestrator

**Phase:** Component Reconstruction — RIGHT COGNITIVE ORCHESTRATOR ONLY  
**Scope:** `web/v2/design/orchestrator.css`, `web/v2/orchestrator/orchestrator-region.js`, UI version, docs/tests/screenshots  
**Constraint:** No backend, API, Brain, Memory, Voice Runtime, neural renderer, sidebar, top bar, bottom workspaces, or center composition changes  
**Canonical visual target:** `docs/design/screenshots/sprint-2.7-reference-composition.png` + Titan Design Constitution

---

## Goal

Make the right panel visually almost indistinguishable from the reference: executive command center, not a dashboard. Deep smoked glass, large breathing room, minimal text, perfect hierarchy.

Phase 4.2 rebuilt the structure. Phase 4.3 locks pixel fidelity.

---

## Objectives → Result

| Objective | Result |
|-----------|--------|
| **Top header** | Neural glyph · COGNITIVE ORCHESTRATOR · tiny LIVE indicator — perfectly aligned |
| **Current Objective** | Large mission headline · current task · secondary objective · LIVE/IDLE chip · glowing neural bars |
| **Execution Pipeline** | Large numbered 1…9 list · title · status · mark · sub-label · green completed · red active · calm waiting |
| **Active Tools** | Elegant vertical list (no oversized cards) · icon · status · recent action · soft dividers |
| **Neural Activity** | Soft waveform · tiny pulses — restrained |
| **Material** | Black glass · heavy blur · almost invisible border · fine reflections · large padding · reference radius |

---

## Files changed

| File | Role |
|------|------|
| `web/v2/design/orchestrator.css` | Phase 4.3 pixel-perfect layer (loaded last) |
| `web/v2/orchestrator/orchestrator-region.js` | Command-center mount + list tools + green pipeline marks |
| `web/v2/core/version.js` | UI version → `0.30.0` |
| `tests/test_web_v2_orchestrator_phase43.py` | Phase 4.3 contracts |
| `tests/test_web_v2_orchestrator_phase42.py` | Forward-compatible with 4.3 |
| `scripts/capture_phase43_orchestrator_screenshots.py` | Screenshot capture |
| `docs/design/screenshots/phase-4.3-orchestrator-*.png` | Captures |

---

## Section map

```
┌─────────────────────────────┐
│ ✦ COGNITIVE ORCHESTRATOR    │  LIVE
├─────────────────────────────┤
│ CURRENT OBJECTIVE           │
│   large mission · task      │
│   secondary · LIVE/IDLE     │
│   neural bars               │
├─────────────────────────────┤
│ EXECUTION PIPELINE          │
│   1…9 · status · sub-label  │
├─────────────────────────────┤
│ ACTIVE TOOLS                │
│   list · soft dividers      │
├─────────────────────────────┤
│ NEURAL ACTIVITY             │
│   waveform · pulses         │
└─────────────────────────────┘
```

---

## Screenshots

| Capture | Path |
|---------|------|
| Full desktop | `docs/design/screenshots/phase-4.3-orchestrator-full.png` |
| Orchestrator panel | `docs/design/screenshots/phase-4.3-orchestrator-panel.png` |
| Right crop | `docs/design/screenshots/phase-4.3-orchestrator-crop.png` |
| Active demo | `docs/design/screenshots/phase-4.3-orchestrator-active.png` |

---

## Verify

```bash
pytest tests/test_web_v2_orchestrator_phase43.py tests/test_web_v2_orchestrator_phase42.py tests/test_web_v2_sidebar_phase4.py tests/test_web_v2_reference_final.py tests/test_web_v2_reference_composition.py tests/test_web_v2_presence_os.py -v
python scripts/capture_phase43_orchestrator_screenshots.py
```

Local URL: `http://127.0.0.1:8000/app/`

---

## Related

- `docs/WEB_APP_ORCHESTRATOR_PHASE4.md` — Phase 4.2 reconstruction
- `docs/TITAN_DESIGN_CONSTITUTION.md`
- `docs/WEB_APP_SIDEBAR_PHASE4.md`
- `docs/WEB_APP_LAYOUT.md`
- `docs/WEB_APP_REFERENCE_COMPOSITION.md`

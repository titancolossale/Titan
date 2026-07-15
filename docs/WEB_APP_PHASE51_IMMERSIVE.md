# Titan Web App — Phase 5.1 Immersive Neural Stage

**Phase:** Immersive Neural Stage (presentation only)  
**Scope:** `web/v2/design/immersive-neural-stage.css`, buried Titan Core markup, atmosphere depth bands, UI version, docs/tests/screenshots  
**Constraint:** No Brain, API, Memory, Voice Runtime, neural renderer logic, routes, or state management changes  
**Canonical visual targets:**
- `docs/assets/living-neural-core-closeup.png`
- `docs/design/screenshots/sprint-2.7-reference-composition.png`
- `docs/assets/living-neural-idle.png`

---

## Goal

Eliminate the feeling of “a dashboard placed over a neural background.”

The interface must read as **one living neural universe** where chrome elements naturally exist inside the field.

---

## What changed

| Surface | Reconstruction |
|---------|----------------|
| **Atmosphere** | Depth bands re-enabled (void · far fog · mid tissue · vignette); stronger volumetric darkness |
| **Center stage** | Removed clipped / rounded glass rectangle; stage opens into the field |
| **Titan Core** | No pill / glass plate; organic glow; filaments cross over typography |
| **Satellites** | Distant clusters — light type, near-transparent, brighten only when active |
| **Global chrome** | Quieter borders, deeper glass, more negative space |

---

## Files

| File | Role |
|------|------|
| `web/v2/design/immersive-neural-stage.css` | **Visual authority** (loaded last) |
| `web/v2/design/phase5-layout.css` | Removed core glass pill; open center stack |
| `web/v2/center/cognitive-satellites.js` | Tissue / filament / veil markup over Core |
| `web/v2/layout/shell.js` | Phase marker `5.1` / `immersive-neural` |
| `web/v2/index.html` | Loads immersive CSS; meta `0.41.0` |
| `web/v2/core/version.js` | UI version → `0.41.0` |
| `tests/test_web_v2_immersive_neural_stage.py` | Phase 5.1 contracts |
| `scripts/capture_phase51_immersive_screenshots.py` | Screenshot capture |

---

## Intentionally untouched

- Neural canvas renderer / shaders / engine JS
- Brain, APIs, routes, voice, memory, agents
- Orchestrator / sidebar / composer behavior wiring

---

## Screenshots

| Capture | Path |
|---------|------|
| Full shell | `docs/design/screenshots/phase-5.1-immersive-full.png` |
| Center stage | `docs/design/screenshots/phase-5.1-immersive-stage.png` |
| Titan Core close-up | `docs/design/screenshots/phase-5.1-titan-core.png` |

---

## Verification

```bash
pytest tests/test_web_v2_immersive_neural_stage.py tests/test_web_v2_phase5_layout.py tests/test_web_v2_reference_final.py tests/test_web_v2_presence_os.py -v
python scripts/capture_phase51_immersive_screenshots.py
```

1. Center must not read as a translucent rectangle.
2. TITAN CORE appears inside the neural tangle (filaments over type).
3. Satellites feel distant until active.
4. Edges are darker void; center glow emerges from the organism.

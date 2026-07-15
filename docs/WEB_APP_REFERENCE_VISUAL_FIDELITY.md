# Titan Web App — Reference Visual Fidelity

**Phase:** Titan Web App Finalization — Sprint 2.10  
**Scope:** Frontend-only chrome (`web/v2/`)  
**Constraint:** No Brain, API, Memory, Voice Runtime, or neural renderer changes  
**Canonical visual target:** `docs/design/screenshots/sprint-2.7-reference-composition.png`

---

## Goal

Reproduce the reference visual language as closely as possible while preserving
all existing Titan functionality. Not inspiration — fidelity.

---

## Objectives → Result

| Objective | Result |
|-----------|--------|
| **Premium materials** | Smoked acrylic panels — hairline outline, inset reflection, neural bleed; no thick borders |
| **Visual rhythm** | Wider gaps, thinner sidebar (200px), quieter separations |
| **Sidebar** | Integrated rail — soft red active pill, quieter type, minimal chrome |
| **Orchestrator** | Story hierarchy: Presence → Cognitive State → Timeline → Instruments → Neural Field |
| **Bottom workspaces** | Floating glass environments with top-edge specular highlight |
| **Typography** | Lighter weights, smaller instrument labels, more letter-spacing |
| **Lighting** | CSS atmospheric glow + vignette on glow layer; panels absorb neural-red tint |
| **Cinematic depth** | Foreground chrome / midground workspace / background neural field |
| **Alignment** | Geometry tokens retuned for grid consistency |

---

## Files Changed

| File | Role |
|------|------|
| `web/v2/design/reference-final.css` | **New** reference fidelity layer (loaded last) |
| `web/v2/index.html` | Loads `reference-final.css` |
| `web/v2/orchestrator/orchestrator-region.js` | Story section titles |
| `web/v2/core/version.js` | UI version → `0.27.0` |
| `web/v2/sidebar/sidebar-region.js` | Sprint marker only |
| `web/v2/status/status-region.js` | Sprint marker only |
| `tests/test_web_v2_reference_final.py` | Sprint contracts |
| `tests/test_web_v2_reference_composition.py` | Section title assertions |
| `tests/test_web_v2_presence_os.py` | Load-order + version tolerance |

Styles load order (final wins):

1. tokens → layout → neural → satellites → ui → shell → premium → composition → presence  
2. **`reference-final.css`** ← Sprint 2.10

---

## Screenshots

| Shot | Path |
|------|------|
| Reference (canonical) | `docs/design/screenshots/sprint-2.7-reference-composition.png` |
| Idle fidelity (desktop) | `docs/design/screenshots/sprint-2.10-reference-fidelity.png` |
| Orchestrator crop | `docs/design/screenshots/sprint-2.10-orchestrator.png` |
| Sidebar + dock crop | `docs/design/screenshots/sprint-2.10-sidebar-dock.png` |

---

## Visual comparison vs reference

### Matches closely

- Deep black void with central neural field as primary light
- Left nav rail with soft red active Chat treatment
- Top telemetry strip + outline Cerveau control language
- Bottom row of floating glass workspaces + composer pill
- Thin system status strip
- Right cognitive panel with generous vertical rhythm

### Remaining differences (honest)

1. **Neural tissue density / node layout** — canvas organism from Sprint 2.6+; not pixel-matched to the reference still render. Renderer intentionally untouched this sprint.
2. **Satellite orbit positions / labels** — living engine placement may differ slightly from the reference frame.
3. **Orchestrator content model** — live System Presence + idle timeline story; reference frame may show a different panel mode (e.g. Context slots). Functionality preserved over cosmetic content swap.
4. **Font rasterization** — Inter via Google Fonts vs reference capture environment; tracking/size retuned, glyph metrics may still differ.
5. **Exact red intensity** — acrylic bleed and Core glow are calibration approximations without altering neural shaders.
6. **Micro chrome** — a few functional controls (sidebar collapse, card close) remain quieter than the reference but are still present for operability.

---

## Verification

1. Open `/app` idle — panels read as acrylic, not bordered dashboard cards.
2. Sidebar feels thinner and integrated; Chat has soft red pill, not a hard box.
3. Orchestrator sections have no nested boxes — hierarchy is typography + spacing.
4. Composer shows "Message à Titan…" (reference copy).
5. Bottom cards float with top specular highlight over the neural field.
6. Atmosphere vignette visible at screen edges without killing center illumination.
7. `pytest tests/test_web_v2_reference_final.py tests/test_web_v2_presence_os.py tests/test_web_v2_reference_composition.py -v`
8. Optional screenshots: `python scripts/capture_sprint_210_screenshots.py`

---

## Related

- `docs/WEB_APP_REFERENCE_COMPOSITION.md` (Sprint 2.7)
- `docs/WEB_APP_LIVING_COGNITIVE_OS.md` (Sprint 2.9)
- `docs/TITAN_DESIGN_CONSTITUTION.md`

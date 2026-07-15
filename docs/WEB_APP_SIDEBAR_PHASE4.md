# Titan Web App — Phase 4 Sidebar Reconstruction

**Phase:** Component Reconstruction — LEFT SIDEBAR ONLY  
**Scope:** `web/v2/design/sidebar.css`, `web/v2/sidebar/sidebar-region.js`, load order, UI version  
**Constraint:** No backend, API, Brain, Memory, Voice Runtime, neural renderer, orchestrator, top bar, bottom workspaces, or center composition changes  
**Canonical visual target:** `docs/design/screenshots/sprint-2.7-reference-composition.png`

---

## Goal

Move the left rail from “web app navigation menu” toward a carved Cognitive OS instrument — smoked glass, quiet type, integrated presence.

---

## Objectives → Result

| Objective | Result |
|-----------|--------|
| **Proportions** | 204px rail (scales 216/228 ultrawide), generous padding, quieter vertical rhythm |
| **Materials** | Deeper smoked glass, hairline edge, inset reflection, neural bleed, soft orb lighting |
| **Typography** | Weight 300 identity / nav; wider tracking; muted secondary copy |
| **Navigation** | Soft active wash (no border chrome); Conversation CTA quiet; BIENTÔT badges faint |
| **Icons** | 10px glyphs, reduced opacity, aligned to type |
| **Status panel** | Presence flattened into the rail — no nested glass card; tool chips removed from rail |
| **Depth** | Layered shadows + internal radial light; no extra visual noise |
| **Reference** | Continuously matched against sprint-2.7 composition |

---

## Files changed

| File | Role |
|------|------|
| `web/v2/design/sidebar.css` | **New** Phase 4 reconstruction layer (loaded last) |
| `web/v2/index.html` | Loads `sidebar.css` after `reference-final.css` |
| `web/v2/sidebar/sidebar-region.js` | Flattened presence block; removed tool chips; phase marker |
| `web/v2/core/version.js` | UI version → `0.28.0` |
| `tests/test_web_v2_sidebar_phase4.py` | Phase 4 contracts |
| `tests/test_web_v2_reference_final.py` | Version assertion tolerance |
| `scripts/capture_phase4_sidebar_screenshots.py` | Screenshot capture |
| `docs/design/screenshots/phase-4-sidebar-*.png` | Captures |

---

## Screenshots

| Capture | Path |
|---------|------|
| Full desktop | `docs/design/screenshots/phase-4-sidebar-full.png` |
| Sidebar element | `docs/design/screenshots/phase-4-sidebar-rail.png` |
| Left crop | `docs/design/screenshots/phase-4-sidebar-crop.png` |

---

## Remaining sidebar differences vs reference

1. **Nav labels** — live routes use English Title Case (`Projects`, `Exploration`, …) plus Obsidian; the reference still may use slightly different naming order.
2. **Active Conversation wash** — soft left→right red glow matches intent; exact fill density / corner radius may differ from the still frame.
3. **Presence waveform** — CSS idle envelope vs a single captured activity frame in the reference.
4. **Font rasterization** — Inter vs reference capture environment; tracking retuned, glyph metrics may still differ.
5. **Collapse/peek chrome** — RÉDUIRE + hover peek remain for operability; reference assumes a pinned desktop rail.
6. **Context-drawer restore** — Phase 4 restores absolute positioning for the closed context drawer so the sidebar column can stretch (a `reference-final` workspace `position: relative` rule had collapsed nav height to 0). Not a visual redesign of the drawer.

---

## Verify

```bash
pytest tests/test_web_v2_sidebar_phase4.py tests/test_web_v2_reference_final.py tests/test_web_v2_reference_composition.py -v
python scripts/capture_phase4_sidebar_screenshots.py
```

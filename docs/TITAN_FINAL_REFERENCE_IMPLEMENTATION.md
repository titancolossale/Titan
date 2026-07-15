# Titan Final Reference Implementation

**Phase:** Canonical Final Reference (UI 0.50.0)  
**Frontend:** `web/v2/` — single production root served at `/app` and `/v2`  
**Canonical image:** `docs/design/screenshots/titan-final-canonical-reference.png`

This document records the approved visual reconstruction of the Titan Web App.
The attached final reference image is the **source of truth**. Prior mockups,
CSS experiments, and sprint screenshots are historical unless they still match
the canonical composition.

---

## 1. Canonical Reference

| Item | Value |
|------|--------|
| Image | `docs/design/screenshots/titan-final-canonical-reference.png` |
| Product version (brand) | `v0.43.0` (`config/settings.py` → `VERSION`) |
| UI finalization version | `0.50.0` (`web/v2/core/version.js`) |
| CSS authority | `web/v2/design/canonical-final.css` (**loaded last**) |
| Shell marker | `#titan-v2-root[data-canonical="final"][data-phase="10"]` |

---

## 2. Layout Proportions (Desktop)

| Region | Token / target |
|--------|----------------|
| Left sidebar | `--tdl-sidebar-width: 228px` |
| Right orchestrator | `--tdl-orchestrator-width: 312px` |
| Top telemetry height | `--tdl-topbar-height: 52px` |
| Floating cards height | `--tdl-status-cards-height: 118px` |
| Composer min height | `--tdl-composer-min-height: 52px` |
| Workspace gap | `--tdl-workspace-gap: 0.75rem` |

Desktop fidelity is primary. Narrower breakpoints reduce widths and hide
micro-sparklines; they must not redesign the seven-region composition.

---

## 3. Component Hierarchy

```
#titan-v2-root[data-canonical="final"]
├── #tdl-v2-layer-neural          NeuralStage
├── #tdl-v2-layer-glow            ambient / presence (quiet under canonical CSS)
├── #tdl-v2-layer-workspace
│   └── #tdl-v2-composition
│       ├── #tdl-v2-workspace-grid
│       │   ├── #tdl-v2-region-sidebar         SidebarRegion + Titan logo
│       │   ├── #tdl-v2-region-main
│       │   │   ├── #tdl-v2-region-topbar      TopbarRegion (6 modules + sparklines)
│       │   │   └── center stack
│       │   │       ├── #tdl-v2-neural-labels  CenterRegion + CognitiveSatelliteField
│       │   │       └── #tdl-v2-region-center
│       │   └── #tdl-v2-region-orchestrator    OrchestratorRegion
│       └── #tdl-v2-region-dock
│           ├── #tdl-v2-dock-status-cards      StatusRegion (5 workspaces)
│           ├── #tdl-v2-dock-status-lines
│           ├── #tdl-v2-dock-composer          ComposerRegion
│           └── #tdl-v2-dock-telemetry         StatusRegion strip
└── overlay / floating cards layer
```

---

## 4. Visual Tokens

- Void black `#000000`
- Titan red `#e11d2e` / hot `#ff6b75`
- Live/complete green `#32c48d`
- Smoked glass panels, 1px edges, restrained red edge light
- Lightweight uppercase micro-labels with tracked letter-spacing

Defined in `canonical-final.css` (`--tdl-cf-*`) and layered over historical
token/CSS files without inventing a second frontend.

---

## 5. Logo Usage Rules

**Approved**

- Sidebar brand toggle
- Sidebar presence mark (replaces decorative sphere)
- Cognitive Orchestrator header
- Top-bar operator identity glyph (Nolan profile)

**Forbidden**

- Large decorative red balls as branding
- Replacing functional status dots with the logo

Implementation: `web/v2/components/titan-logo.js`, `web/v2/assets/titan-logo.svg`.

---

## 6. State Sources (Real)

| Surface | Source |
|---------|--------|
| Top telemetry modules | `cognitive-os-telemetry.js` ← `StateStore` / `CognitiveStateEngine` |
| Orchestrator objective / pipeline / systems | `OrchestratorRegion` ← brain + pipeline store + store |
| Floating workspaces | `StatusRegion` ← memory/tool/conversation engines + store |
| Bottom strip FPS / BRAIN / MEMORY / TOOLS / RUNTIME | `StatusRegion` telemetry |
| Neural satellite activity | `neural-status-adapter.js` ← store tool/memory presence |

No duplicate Brain, API, or runtime instances are introduced.

---

## 7. Honest Presentation Fallbacks

| Surface | Idle fallback |
|---------|----------------|
| Objectif | `Comprendre et assister` |
| Mission line | `Analyser la demande, orchestrer les ressources nécessaires` |
| Mode | `Assistance adaptative` / `En veille` |
| Pipeline | 9 French steps, all `En attente` when no live workflow |
| Mémoire card | `Aucune note récente` |
| Obsidian | Vault `Titan AI`, veille when no activity |
| Browser | `Navigation en réserve` |
| Présence | calm engagement from store `presenceLevel` (presentation mapping only) |

Never fabricate tool execution, memory reads, or pipeline progress.

---

## 8. Responsive Strategy

- Desktop (≥1280): full three-column composition
- ≤1280: tighter sidebar/orchestrator widths
- ≤1100: hide topbar micro-sparklines
- Tablet/phone: existing drawer/orchestrator collapse paths in `LayoutEngine` /
  `ResponsiveEngine` remain; cards may wrap but keep the same five identities

---

## 9. Reduced Motion

`canonical-final.css` disables waveform breathing and card hover transform under
`prefers-reduced-motion: reduce`. Neural canvas respects the existing reduced-
motion path in the neural stage.

---

## 10. Retired / Superseded Visual Layers

Historical stylesheets remain loaded for compatibility, but **visual authority**
for chrome geometry, branding, and panel treatment is now:

`canonical-final.css` (after `cognitive-os.css`)

Superseded as visual truth (kept for contracts / hooks only):

- Decorative CSS orbs used as brand identity
- Prior “LAST stylesheet” claims in older phase CSS comments
- English marketing titles that conflict with the French canonical panel copy

---

## 11. Remaining Differences vs Reference Image

Honest gaps after reconstruction:

1. **Neural tissue** is canvas-generated; density/asymmetry approximates the
   reference organism but cannot be pixel-identical to a static render.
2. **Idle pipeline** shows all steps `En attente` (honest). The reference still
   may depict mid-cycle completed/active coloring for visual illustration.
3. **Font metrics** depend on Inter loading; slight tracking/weight variance vs
   the static PNG is possible.
4. **Connection-dependent badges** (ONLINE vs HORS LIGNE, Mode Erreur) reflect
   real `connectionState` / brain presence. Static screenshot boot without a
   live SSE Brain can show offline/error chrome even after presentation pins —
   against a running `uvicorn` `/app` session, ONLINE / Assistance adaptative
   appear when the bridge is connected.
5. **Orchestrator vertical density** — full 9 steps + systèmes + waveform fit via
   scroll on shorter viewports; the reference frame is taller / denser.

---

## 12. Related Documents

- `docs/TITAN_DESIGN_CONSTITUTION.md` — supreme visual law
- `docs/WEB_APP_LAYOUT.md` — region ownership
- `docs/ROADMAP.md` — milestone tracking
- `docs/ARCHITECTURE.md` — `/app` mount note

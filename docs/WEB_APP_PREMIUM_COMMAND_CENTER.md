# Titan Web App — Premium Command Center

**Phase:** Titan Web App Finalization — Sprint 2.2  
**Scope:** Frontend-only visual polish of the production UI (`web/v2/`)  
**Constraint:** No Brain, Reasoning, Memory, Workflow, World Model, Meta-Cognition, or API contract changes

---

## Goal

Transform the functional OS shell into a **premium AI command center**: darker glass, quieter red, clearer hierarchy, intentional chrome, and subtle motion — without changing architecture or cognitive systems.

---

## Visual Improvements

| Area | Change |
|------|--------|
| **Glass panels** | Darker translucent black, thinner cool borders, softer inset highlight, panels blend into the void |
| **Color** | Pure black void · graphite surfaces · Titan red reserved for active / attention only |
| **Typography** | Display welcome titles, clearer section labels (tracked xs), more whitespace |
| **Sidebar** | Refined spacing, left-edge active rail, hover slide, intentional collapsed icon column |
| **Top bar** | Taller elegant strip, quieter connection pill, cleaner crumbs, Nolan profile + role |
| **Orchestrator** | Softer separators, quieter headers, execution timeline with track + node dots |
| **Status cards** | Minimal live indicators, smaller icons, shorter copy, softer float |
| **Composer** | Focus glow ring, refined send (subtle radial + soft bloom), cleaner placeholder |
| **Motion** | Panel enter stagger, hover/active/focus micro-interactions, `prefers-reduced-motion` respected |

---

## Files Changed

| File | Role |
|------|------|
| `web/v2/design/tokens.css` | Darker glass tokens, type scale, softer glow, consistent radius |
| `web/v2/design/premium.css` | **New** Sprint 2.2 polish layer (loaded last) |
| `web/v2/design/shell.css` | Rail width, peek shadow, profile responsive hide |
| `web/v2/index.html` | Loads `premium.css` |
| `web/v2/status/status-region.js` | Indicator dots + live toggle; tighter card copy |
| `web/v2/composer/composer-region.js` | Premium placeholder copy |
| `web/v2/center/topbar-region.js` | Nolan profile meta (name + role) |
| `web/v2/orchestrator/orchestrator-region.js` | Timeline label structure |

---

## Performance Impact

| Concern | Assessment |
|---------|------------|
| New libraries | **None** |
| Extra network | One CSS file (~12 KB uncompressed); no fonts added |
| Paint / compositing | Same glass `backdrop-filter` budget as Sprint 1; softer shadows |
| Animation | CSS-only enters/hovers; disabled under reduced motion |
| JS cost | Negligible — indicator class toggles only |

Expected: **no measurable regression** on the neural canvas path; chrome stays GPU-friendly transitions.

---

## Screenshots

Captured from `/app` (desktop 1600×1000 and ultrawide 2560×1440):

| Shot | Path |
|------|------|
| Full command center | `docs/design/screenshots/sprint-2.2-command-center.png` |
| Composer focus ring | `docs/design/screenshots/sprint-2.2-composer-focus.png` |
| Sidebar hover peek | `docs/design/screenshots/sprint-2.2-sidebar-peek.png` |
| Ultrawide scaling | `docs/design/screenshots/sprint-2.2-ultrawide.png` |

---

## Verification

1. Open `/app` at desktop (≥1280px) and ultrawide (≥1920px / ≥2560px).
2. Confirm glass reads as near-black over the neural field (not opaque maroon blocks).
3. Collapse sidebar — icon rail should feel intentional; hover peek smooth.
4. Focus composer — soft red ring, not a heavy fill.
5. Toggle reduced motion — panel enters and floats stop.

---

## Related

- `docs/WEB_APP_LAYOUT.md` — Sprint 1 shell
- `docs/WEB_APP_NEURAL_CORE.md` — Sprint 2 / 2.1 neural core
- `docs/design/TITAN_UI_PRODUCTION_SPEC.md` — production visual contract

# Titan Web App Layout

**Phase:** Canonical Final Reference (UI 0.50.0) — supersedes prior visual sprints
**Frontend:** `web/v2/` (single production frontend — evolved in place)
**Served at:** `/app/` (canonical production entry) and `/v2/` (same sources). `/` redirects to `/app/`. Legacy V1 remains at `/static/index.html` only — never the default.
**Canonical visual:** `docs/design/screenshots/titan-final-canonical-reference.png`  
**Implementation record:** `docs/TITAN_FINAL_REFERENCE_IMPLEMENTATION.md`

This document describes the layout foundation of the Titan desktop web
application. The **canonical final reference image** is the visual source of
truth. Historical Phase 5 / Sprint 2.7 docs remain useful for migration notes
(`docs/WEB_APP_PHASE5_LAYOUT.md`, `docs/WEB_APP_REFERENCE_COMPOSITION.md`).

It is a **frontend-only** evolution of the existing production frontend. The
Brain, Cognitive Operating System, and all reasoning systems are unchanged; the
web layer still talks to the shared Brain through the existing FastAPI Web API
(see `docs/WEB_RUNTIME.md`).

---

## 1. Layout Philosophy

Titan is presented as a **premium, futuristic AI operating system**, not a
dashboard or admin template. The design language is deliberately restrained:

- **Pure black canvas** (`--tdl-bg-void: #030303`) with high contrast text.
- **Subtle red accent**, unified with Titan's living neural core.
- **Near-black translucent panels**, thin borders, minimal red glow.
- **The neural core is the centre of gravity.** Chrome frames the core; panels
  stay glass so the living brain shows through.
- **Dense but intentional** — reference composition density without clutter.
- **Motion is calm** — smooth fades and slides only; disabled under
  `prefers-reduced-motion`.

The interface is **desktop-first** and degrades gracefully to smaller viewports.

---

## 2. Major Screen Regions (Sprint 2.7)

```
┌──────────┬───────────────────────────────────────────┬────────────────────┐
│ SIDEBAR  │ Top intelligence / telemetry strip          │ COGNITIVE          │
│ full     ├───────────────────────────────────────────┤ ORCHESTRATOR        │
│ height   │ CENTRAL WORKSPACE (neural + Titan Core +  │ permanent desktop  │
│ nav +    │ subsystem satellites)                     │ panel              │
│ presence │                                            │                    │
├──────────┴───────────────────────────────────────────┴────────────────────┤
│ Floating cards · status lines · composer · system status strip              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Top Bar — `web/v2/center/topbar-region.js`
Cognitive telemetry strip: memory / tools / reflection / presence pills,
center presence copy, Brain/Cerveau mode control, settings, profile.

### Left Sidebar — `web/v2/sidebar/sidebar-region.js`
**Full-height navigation by default** (pinned). Includes branding, version,
Chat · Projects · Memory · Exploration · Obsidian · Calendar · Trading · Tools ·
Settings. Lower **Titan Presence** block: TITAN ONLINE, CERVEAU ACTIF, presence
card, mini activity preview. Collapse/peek remains available for later and for
narrow viewports. Unimplemented items are marked **BIENTÔT**.

### Main Workspace — `web/v2/center/center-region.js`
Living neural field + Titan Core label (`Conscience & Orchestrateur`) + embedded
subsystem satellites (MEMORY, PLANNING, BROWSER, OBSIDIAN, TOOLS,
COMMUNICATION, TRADING, CALENDAR). No large marketing welcome headline.

### Right Cognitive Orchestrator — `web/v2/orchestrator/orchestrator-region.js`
**Permanent on desktop.** Phase 4.3 pixel-perfect command center: Current Objective,
Execution Pipeline (9-step numbered list, green completed / red active), Active Tools
(elegant list with soft dividers), Neural Activity. Idle plan is presentation-only when
no workflow is active. Becomes a drawer on tablet/phone. Styles:
`web/v2/design/orchestrator.css` (loaded last).

See `docs/WEB_APP_ORCHESTRATOR_PHASE43.md`.

### Lower Floating Cards + Dock — `web/v2/status/status-region.js`
Cards: Recent Memory · Obsidian · Browser · Cognitive State · Presence.
Composer: mic · attach · message · red SEND.
Bottom strip: FPS · Brain · Memory · Tools · Reflection · clock.

---

## 3. Component Hierarchy

```
TitanAppV2 (core/app.js)
├── Shell (layout/shell.js)
│   ├── Neural layer  → NeuralStage
│   ├── Glow layer
│   ├── Workspace layer
│   │   ├── Grid: Sidebar · Main(Topbar + Center) · Orchestrator
│   │   ├── Dock: floating cards · status lines · composer · telemetry
│   │   └── Context Panel (optional inspector drawer)
│   ├── Floating layer (cards)
│   └── Overlay layer (settings)
├── LayoutEngine
├── StateStore
└── Regions (sidebar, topbar, center, orchestrator, composer, status, …)
```

**State defaults (Sprint 2.7):** `sidebarPinned: true` (full sidebar on desktop).

### Styling
1. `tokens.css`
2. `layout.css`
3. `neural.css`
4. `satellites.css`
5. `ui.css`
6. `shell.css`
7. `premium.css`
8. `composition.css` — Sprint 2.7 density / hierarchy / materials
9. `presence.css`
10. `reference-final.css` — Sprint 2.10 acrylic
11. `sidebar.css` — Phase 4 sidebar
12. `orchestrator.css` — Phase 4.3 orchestrator
13. **`phase5-layout.css`** — Phase 5 full composition authority
14. `immersive-neural-stage.css` — Phase 5.1 immersive atmosphere
15. `cinematic-living.css` — Phase 5.2 cinematic living field
16. **`reference-scene.css`** — Phase 5.3 Core gravity / orbits / highways (loaded last)

---

## 4. Responsive Strategy

| Mode | Width | Sidebar | Orchestrator | Cards |
|------|-------|---------|--------------|-------|
| `ultrawide` / `wide` / `desktop` | ≥1280 | full (default) | permanent | equal row |
| `laptop` | 1024–1279 | full / collapsible | permanent | row |
| `tablet` | 768–1023 | 56px rail | drawer | horizontal scroll |
| `phone` | <768 | hidden | drawer | horizontal scroll |

---

## 5. Serving & Runtime

```bash
python main.py web-dev      # http://127.0.0.1:8000/app/
```

- Mount: `/app` → `web/v2/` in `api/app.py`
- No build step (ES modules + CSS)
- Chat still flows through `Brain.process_request()` (`docs/WEB_RUNTIME.md`)

---

## Related Documents

- `docs/WEB_APP_PHASE5_LAYOUT.md` — Phase 5 reference layout reconstruction
- `docs/WEB_APP_ORCHESTRATOR_PHASE43.md` — Phase 4.3 pixel-perfect Cognitive Orchestrator
- `docs/WEB_APP_ORCHESTRATOR_PHASE4.md` — Phase 4.2 Cognitive Orchestrator reconstruction
- `docs/WEB_APP_SIDEBAR_PHASE4.md` — Phase 4 Sidebar reconstruction
- `docs/WEB_APP_REFERENCE_COMPOSITION.md` — Sprint 2.7 composition authority
- `docs/WEB_APP_NEURAL_CORE.md` — Living Neural Core
- `docs/WEB_APP_PREMIUM_COMMAND_CENTER.md` — Sprint 2.2 polish
- `docs/WEB_RUNTIME.md` — Web Runtime V1
- `docs/ARCHITECTURE.md` — runtime paths

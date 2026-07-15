# Titan Web App — Reference Composition Reconstruction

**Phase:** Titan Web App Finalization — Sprint 2.7  
**Frontend:** `web/v2/` (served at `/app`)  
**Constraint:** Frontend composition only — Brain, APIs, neural renderer internals unchanged

---

## Goal

Rebuild the **visible application structure** so the Web App matches the approved
reference composition: a dense AI cognitive command center, not a sparse dashboard.

The neural field remains the approved living background. This sprint does **not**
redesign the neural renderer.

---

## Final Desktop Composition

```
┌──────────┬───────────────────────────────────────────┬────────────────────┐
│          │ Top intelligence / telemetry strip          │                    │
│ LEFT     ├───────────────────────────────────────────┤ RIGHT              │
│ SIDEBAR  │                                            │ COGNITIVE          │
│ 218px    │     CENTRAL COGNITIVE WORKSPACE            │ ORCHESTRATOR       │
│ full     │     (neural field + Titan Core +           │ 318px permanent    │
│ height   │      subsystem satellites)                  │                    │
│          │                                            │                    │
├──────────┴───────────────────────────────────────────┴────────────────────┤
│ Lower floating cards · status lines · chat composer · system status strip   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Regions

| Region | Role |
|--------|------|
| **Left sidebar** | Titan AI branding, version, full nav, Titan Presence |
| **Top bar** | Cognitive telemetry pills + Brain/Cerveau controls |
| **Center workspace** | Neural field, Titan Core, embedded subsystem satellites |
| **Right panel** | Permanent Cognitive Orchestrator |
| **Lower cards** | Recent Memory · Obsidian · Browser · Cognitive State · Presence |
| **Composer** | Wide glass command input (mic · attach · message · SEND) |
| **Bottom strip** | FPS · Brain · Memory · Tools · Reflection · clock |

---

## Component Hierarchy

```
TitanAppV2
└── Shell
    ├── Neural layer (unchanged engine)
    ├── Workspace grid
    │   ├── SidebarRegion          ← full nav + presence (default expanded)
    │   ├── Main
    │   │   ├── TopbarRegion       ← telemetry strip
    │   │   └── CenterRegion       ← satellite field + Titan Core
    │   └── OrchestratorRegion     ← permanent desktop panel
    └── Dock
        ├── StatusRegion cards     ← floating card row
        ├── Status lines
        ├── ComposerRegion
        └── Telemetry strip
```

Styles load order (new last):

1. `tokens.css`
2. `layout.css`
3. `neural.css`
4. `satellites.css`
5. `ui.css`
6. `shell.css`
7. `premium.css`
8. **`composition.css`** ← Sprint 2.7

---

## Data Sources

| UI surface | Source | Fallback |
|------------|--------|----------|
| Connection / online pills | `connectionState` | "Connexion…" / "Hors ligne" |
| Presence copy | `presence`, pipeline flags | "Présent — en attente" |
| Tool counts / tools used | `activeToolIds` / tool activity engine | "0" / "veille" |
| Memory card / pill | `memoryStatusLine`, `recallActive` | "Aucune note récente" |
| Obsidian / Browser cards | Active tool membership | Vault / session "en veille" |
| Cognitive State card | Cognitive state engine label | "En attente" |
| Orchestrator plan | `conversationPlanSteps` when live | Canonical 9-step idle plan (`waiting`) |
| Neural satellites | `resolveNeuralStatus(StateStore)` | All `idle` |
| FPS | Neural engine `getFps()` | `—` with `data-fallback="true"` |
| Reflection depth | `pipelineThinking` / presence | `—` (presentation placeholder) |
| Clock | `Date` locale FR | `--:--:--` until first tick |

**Rule:** Fallbacks are presentation-only. They never invent backend execution,
missions, or tool results.

---

## Placeholder-Only Areas

| Item | Marking |
|------|---------|
| Calendar, Trading, Tools nav routes | `BIENTÔT` badge · placeholder panels |
| Idle 9-step orchestrator plan | Shown when no live workflow |
| Reflection depth when idle | `—` |
| FPS before engine reports | `—` |
| Resource CPU/RAM meters | Removed from sidebar presence (not real) |

---

## Responsive Strategy

| Mode | Behavior |
|------|----------|
| **Desktop (≥1280)** | Full sidebar (default pinned) · permanent orchestrator · card row |
| **Laptop** | Same grid; top presence copy may hide |
| **Tablet** | Sidebar → 56px rail · orchestrator → drawer · cards horizontal scroll |
| **Phone** | Sidebar hidden · orchestrator drawer · composer compact SEND |

Desktop composition is the approved target. Mobile must not force the desktop
layout into a thin empty shell.

---

## Differences: Real Telemetry vs Presentation

| Real | Presentation |
|------|----------------|
| Connection state, tool activity, memory recall flags | Idle plan step list when no workflow |
| Cognitive state labels | "BIENTÔT" routes without backends |
| Live FPS when the canvas engine reports it | Reflection "profonde" only while thinking |
| Pipeline / conversation plan steps when provided | Canonical 9-step waiting timeline |

---

## Preserved Integrations

- Chat send / stop / mic / attach DOM ids
- Backend bridge + SSE event router
- Neural status adapter (updated satellite ids only)
- `/app` StaticFiles mount → `web/v2/`
- No Brain, memory engine, workflow engine, or API contract changes

---

## Related

- `docs/WEB_APP_LAYOUT.md` — layout foundation (updated for 2.7)
- `docs/WEB_APP_NEURAL_CORE.md` — neural core (unchanged this sprint)
- `docs/WEB_APP_PREMIUM_COMMAND_CENTER.md` — Sprint 2.2 polish
- `docs/TITAN_DESIGN_CONSTITUTION.md` — visual law (no amendment required)
- `docs/ROADMAP.md` — phase checklist

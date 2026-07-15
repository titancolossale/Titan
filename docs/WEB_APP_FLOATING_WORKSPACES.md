# Titan Web App — Phase 5.4 Floating Cognitive Workspaces

**Phase:** Floating Cognitive Workspaces (presentation only)  
**Scope:** `web/v2/status/status-region.js`, `web/v2/design/floating-workspaces.css`, dock chrome, UI version, docs/tests/screenshots  
**Constraint:** No Brain, API, Memory engine, Voice Runtime, Titan Core, neural renderer, satellite position, sidebar, top telemetry, routes, or chat-logic changes  
**Canonical visual targets:**
- `docs/design/screenshots/sprint-2.7-reference-composition.png`
- `docs/TITAN_DESIGN_CONSTITUTION.md`
- `docs/design/screenshots/phase-5-floating-dock.png`

---

## Goal

Reconstruct the five lower floating cards so they read as **living cognitive workspaces** currently open inside Titan — not empty dashboard widgets.

Cards:

1. Recent Memory  
2. Obsidian  
3. Browser  
4. Cognitive State  
5. Presence  

---

## Component hierarchy

```
Dock (data-role="floating-workspaces")
└── Workspace dock (.tdl-v2-workspace-dock)
    ├── Recent Memory   (.tdl-v2-workspace-card[data-kind="memory"])
    ├── Obsidian        (.tdl-v2-workspace-card[data-kind="obsidian"])
    ├── Browser         (.tdl-v2-workspace-card[data-kind="browser"])
    ├── Cognitive State (.tdl-v2-workspace-card[data-kind="cognitive"])
    └── Presence        (.tdl-v2-workspace-card[data-kind="presence"])
├── Status lines (tools · memory · conversation)
├── Composer (unchanged behavior)
└── System telemetry strip
```

Styles load order (workspace authority last):

1. … existing cascade …
2. `reference-scene.css`
3. **`floating-workspaces.css`** ← Phase 5.4

---

## State sources

| Workspace | Real sources | Notes |
|-----------|--------------|-------|
| **Recent Memory** | `CognitiveStateEngine` → `MemoryActivityEngine.getActiveMemories()`, `memoryStatusLine`, `recallActive` | Up to 3 rows: icon · title · relative time |
| **Obsidian** | Active tool `obsidian`, `toolStatusLine`, optional `systemsUsed.obsidian` counts | Vault label presentation default: **Titan AI** |
| **Browser** | Active tool `browser`, `toolStatusLine`, optional tab count on tool/systems payload | No fake browsing execution |
| **Cognitive State** | Cognitive state engine snapshot + `connectionState` | Mapped to Idle / Listening / Thinking / Planning / Executing / Learning / Error / Offline |
| **Presence** | `presenceLevel` (store) + cognitive snapshot | Ring % only from real telemetry; calm personal copy when idle |

**Rule:** Fallbacks are presentation-only. They never invent backend execution, missions, vault mutations, or fabricated memory filenames.

---

## Idle fallbacks

| Card | Idle presentation |
|------|-------------------|
| Recent Memory | `Mémoire en veille` · `Aucune note récente` |
| Obsidian | `Vault : Titan AI` · `Vault connecté — en veille` |
| Browser | `Navigation en réserve` · `Aucune recherche active` |
| Cognitive State | `Idle` · `Présent — en attente` |
| Presence | `Présent — calme` · `Activité faible` · `En attente de Nolan` · ring from `presenceLevel` |

---

## Interaction rules

- Soft hover elevation (`translateY(-3px)`), quiet border clarification, slight reflected light
- Collapse/close control on every card (`data-collapsed`)
- No bounce, no strong scale, no flashy global motion
- When a subsystem goes live: local red accent strengthens; indicator flips to live
- Idle life: breathing opacity, restrained scan line (memory), cognitive pulse bars, presence breath ring
- `prefers-reduced-motion` / `.tdl-v2--reduced-motion` disables ambient motion

---

## Responsive behavior

| Mode | Behavior |
|------|----------|
| Desktop | Five cards in a centered horizontal dock with varied flex widths |
| Tablet / Phone | Horizontal overflow scroll · snap proximity · cards keep readable min-width |

Dock max-height is capped so cards **never climb over Titan Core**.

---

## Visual relationship to the reference

Matches the reference hierarchy:

- Suspended smoked glass above the composer
- Varied but controlled widths
- Thin edges, restrained blur, soft neural-red reflection
- Quiet uppercase headers + tiny indicators
- Presence meter as the personal living signal
- Composer + status lines + telemetry read as one lower command area

Does **not** reinterpret cards as SaaS metric widgets or opaque black slabs.

---

## Files

| File | Role |
|------|------|
| `web/v2/status/status-region.js` | Workspace card DOM + state wiring |
| `web/v2/design/floating-workspaces.css` | Material / layout / living-state authority |
| `web/v2/index.html` | Loads Phase 5.4 CSS; meta `0.44.0` |
| `web/v2/core/version.js` | UI version → `0.44.0` |
| `web/v2/layout/shell.js` | Phase marker `5.4` (dock region IDs unchanged) |
| `tests/test_web_v2_floating_workspaces.py` | Phase 5.4 contracts |
| `scripts/capture_phase54_floating_workspaces_screenshots.py` | Screenshot capture |

---

## Intentionally untouched

- Titan Core / neural field / satellite orbits
- Sidebar / top telemetry / Cognitive Orchestrator layout
- Brain, APIs, routes, chat send/stop pipeline
- Memory / Obsidian / Browser backend functionality

---

## Screenshots

| Capture | Path |
|---------|------|
| Full shell | `docs/design/screenshots/phase-5.4-floating-workspaces-full.png` |
| Workspace dock | `docs/design/screenshots/phase-5.4-workspace-dock.png` |
| Memory idle | `docs/design/screenshots/phase-5.4-memory-idle.png` |

---

## Verification

```bash
pytest tests/test_web_v2_floating_workspaces.py tests/test_web_v2_phase5_layout.py tests/test_web_v2_reference_composition.py tests/test_web_v2_reference_scene.py -v
python scripts/capture_phase54_floating_workspaces_screenshots.py
```

1. Five smoked-glass workspaces float above the composer.
2. Idle states are calm and honest — no fabricated memory filenames.
3. Live tool/memory/cognitive activity updates the matching card only.
4. Titan Core remains fully visible above the dock.
5. Composer send / mic / attach still work; `/app` loads.

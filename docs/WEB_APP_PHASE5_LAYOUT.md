# Titan Web App — Phase 5 Reference Layout Reconstruction

**Phase:** Complete visual layout reconstruction  
**Scope:** `web/v2/layout/shell.js`, `web/v2/design/phase5-layout.css`, region phase markers, UI version, docs/tests/screenshots  
**Constraint:** No Brain, API, Memory, Voice Runtime, neural renderer internals, or backend changes  
**Canonical visual target:** `docs/design/screenshots/sprint-2.7-reference-composition.png` + Titan Design Constitution

---

## Goal

Rebuild the **visible application structure** so the interface immediately matches the reference composition when compared side by side.

This is **not** a redesign, polish sprint, or architecture refactor.

Composition first. Replicate. Reconnect.

---

## Composition (reference truth)

```
┌──────────┬───────────────────────────────────────────┬────────────────────┐
│ LEFT     │ Top intelligence / telemetry strip          │ RIGHT              │
│ SIDEBAR  ├───────────────────────────────────────────┤ COGNITIVE          │
│ 218px    │ CENTRAL WORKSPACE                         │ ORCHESTRATOR       │
│ full     │ neural organism + Titan Core + satellites │ 318px command      │
│ height   │                                            │ center             │
├──────────┴───────────────────────────────────────────┴────────────────────┤
│ Floating workspace cards · status lines · composer pill · telemetry strip │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## What changed

| Surface | Reconstruction |
|---------|----------------|
| **Shell hierarchy** | New `#tdl-v2-composition` frame wrapping grid + floating dock |
| **Left sidebar** | Reference proportions, glass, nav rhythm, Titan Presence |
| **Top bar** | Flat telemetry hierarchy (dots + caps), CERVEAU pill, operator profile |
| **Center** | Transparent workspace — neural organism owns the stage |
| **Right orchestrator** | Permanent command center (objective · pipeline · tools · neural) |
| **Bottom dock** | Truly floating cards + premium composer pill (not a docked strip) |

---

## Files

| File | Role |
|------|------|
| `web/v2/layout/shell.js` | Phase 5 composition frame; region IDs preserved |
| `web/v2/design/phase5-layout.css` | **Visual authority** (loaded last) |
| `web/v2/index.html` | Loads `phase5-layout.css`; meta `0.40.0` |
| `web/v2/core/version.js` | UI version → `0.40.0` |
| `web/v2/sidebar/sidebar-region.js` | Phase marker reconnect |
| `web/v2/center/topbar-region.js` | Phase 5 hierarchy class |
| `web/v2/orchestrator/orchestrator-region.js` | Phase 5 composition marker |
| `web/v2/status/status-region.js` | Floating cards phase marker |
| `tests/test_web_v2_phase5_layout.py` | Phase 5 contracts |
| `scripts/capture_phase5_layout_screenshots.py` | Screenshot capture |

---

## Preserved (reconnected)

- Chat send / stop / mic / attach
- Backend bridge + SSE
- Neural renderer engine (unchanged)
- Cognitive Orchestrator live/idle logic
- Sidebar routes + presence
- Floating card data wiring
- Context panel drawer (overlay, not the right grid column)

---

## Screenshots

| Capture | Path |
|---------|------|
| Full desktop | `docs/design/screenshots/phase-5-reference-layout-full.png` |
| Sidebar | `docs/design/screenshots/phase-5-sidebar.png` |
| Orchestrator | `docs/design/screenshots/phase-5-orchestrator.png` |
| Floating dock | `docs/design/screenshots/phase-5-floating-dock.png` |
| Top bar | `docs/design/screenshots/phase-5-topbar.png` |
| Canonical reference | `docs/design/screenshots/sprint-2.7-reference-composition.png` |

---

## Visual comparison vs reference

### Matches closely

- 3-column composition: sidebar · neural workspace · Cognitive Orchestrator
- Full-height left nav with soft red Chat pill + BIENTÔT markers
- Top telemetry strip + CERVEAU control + operator profile
- Center as open neural stage (Titan Core + subsystem satellites)
- Floating glass workspace cards above a pill composer
- Thin system telemetry strip
- Smoked glass / hairline edges / neural-bleed lighting language

### Remaining differences (honest)

1. **Neural tissue density / node layout** — living canvas organism from the neural renderer; not pixel-matched to the reference still. Renderer intentionally untouched.
2. **Satellite orbit positions** — engine placement may differ slightly from the reference frame.
3. **Right panel content model** — live Cognitive Orchestrator (objective · pipeline · tools · neural). The reference still may also depict an alternate Context-slots mode; product keeps the live command center.
4. **Idle connection chrome** — without a live Brain socket, some presence/connection labels may read quieter than the reference “online” frame until `/app` is served with the API.
5. **Font rasterization** — Inter via Google Fonts vs reference capture environment.
6. **Micro chrome** — functional controls (card close, collapse) remain quieter than pure mock chrome for operability.
7. **CSS debt** — Phase 5 consolidates geometry as the last authority layer; older chrome sheets remain underneath for compatibility and should be pruned in a later cleanup pass.

---

## Verify

```bash
pytest tests/test_web_v2_phase5_layout.py tests/test_web_v2_orchestrator_phase43.py tests/test_web_v2_sidebar_phase4.py tests/test_web_v2_reference_composition.py tests/test_web_v2_reference_final.py tests/test_web_v2_presence_os.py -v
python scripts/capture_phase5_layout_screenshots.py
```

Local URL: `http://127.0.0.1:8000/app/`

---

## Related

- `docs/WEB_APP_REFERENCE_COMPOSITION.md`
- `docs/WEB_APP_LAYOUT.md`
- `docs/WEB_APP_ORCHESTRATOR_PHASE43.md`
- `docs/WEB_APP_SIDEBAR_PHASE4.md`
- `docs/TITAN_DESIGN_CONSTITUTION.md`

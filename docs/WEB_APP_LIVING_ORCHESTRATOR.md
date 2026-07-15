# Titan Web App — Phase 6 Living Cognitive Orchestrator

**Phase:** Living Cognitive Orchestrator (presentation only)  
**Scope:** `web/v2/orchestrator/orchestrator-region.js`, `web/v2/design/living-orchestrator.css`, UI version, docs/tests/screenshots  
**Constraint:** No Titan Core, neural field, sidebar, floating workspaces, composer, top telemetry, backend, API, Brain, runtime, or memory-logic changes  
**Canonical visual targets:**
- `docs/design/screenshots/sprint-2.7-reference-composition.png`
- `docs/TITAN_DESIGN_CONSTITUTION.md`

---

## Goal

Rebuild the right panel into Titan's **living command center** — not placeholder settings.

Deep smoked glass · quiet separators · premium type · operational presence.
Idle stays alive (soft waveform, breathing LIVE, tiny activity). Active systems
raise local highlights only — never flash the whole panel.

---

## Section map

```
┌─────────────────────────────┐
│ ✦ COGNITIVE ORCHESTRATOR    │  LIVE + activity scan
├─────────────────────────────┤
│ CURRENT OBJECTIVE           │
│   large title · mission     │
│   description · mode · chip │
├─────────────────────────────┤
│ EXECUTION PIPELINE          │
│   1…9 · Finished/Active/    │
│   Waiting/Error             │
├─────────────────────────────┤
│ ACTIVE TOOLS                │
│   Memory · Browser ·        │
│   Obsidian · Trading ·      │
│   Calendar · Voice          │
├─────────────────────────────┤
│ NEURAL ACTIVITY             │
│   restrained waveform       │
├─────────────────────────────┤
│ RUNTIME STATUS              │
│   Mode · Latency · Runtime  │
│   Subsystems · Connection   │
└─────────────────────────────┘
```

---

## State sources (honest only)

| Surface | Source | Notes |
|---------|--------|-------|
| Objective title / mission | `conversationThinkingLine`, `pipelineLabel`, `reasoningSummary`, cognitive snapshot | No fabricated missions |
| Operating mode | `presence`, `pipelineThinking`, `activeToolCount`, `recallActive`, cognitive id | Presentation mapping |
| Pipeline steps | `conversationPlanSteps` + idle reserve list | Idle shows waiting reserve |
| Step statuses | live steps + thinking/error flags | Finished / Active / Waiting / Error |
| Active tools | `CognitiveStateEngine.getActiveTools()` | Catalog always visible; pulse when active |
| Neural waveform | RAF canvas driven by presence / tool count | Amplitude rises when busy |
| Footer Mode | same mode resolver | — |
| Footer Latency | `orchestrationDuration` | `—` when unknown |
| Footer Runtime | `systemVersion` or UI version label | — |
| Footer Subsystems | `systemsUsed` keys or catalog length | — |
| Footer Connection | `connectionState` | Connected / Connecting / Offline |

**Rule:** Never fake backend execution. Fallbacks are presentation-only.

---

## Styles load order

1. … existing cascade …
2. `orchestrator.css` (Phase 4.3 base)
3. `phase5-layout.css` · immersive · cinematic · reference-scene · floating-workspaces
4. **`living-orchestrator.css`** ← Phase 6 authority (loaded last)

---

## Files changed

| File | Role |
|------|------|
| `web/v2/design/living-orchestrator.css` | Phase 6 smoked-glass command center |
| `web/v2/orchestrator/orchestrator-region.js` | Living sections + Runtime Status footer |
| `web/v2/core/version.js` | UI version → `0.45.0` |
| `web/v2/index.html` | Load living CSS last · meta version |
| `config/settings.py` | Project version → `0.40.0` |
| `tests/test_web_v2_living_orchestrator.py` | Phase 6 contracts |
| `scripts/capture_phase6_orchestrator_screenshots.py` | Screenshot capture |
| `docs/design/screenshots/phase-6-orchestrator-*.png` | Captures |

---

## Screenshots

| Capture | Path |
|---------|------|
| Full desktop | `docs/design/screenshots/phase-6-orchestrator-full.png` |
| Orchestrator panel | `docs/design/screenshots/phase-6-orchestrator-panel.png` |
| Right crop | `docs/design/screenshots/phase-6-orchestrator-crop.png` |
| Active demo | `docs/design/screenshots/phase-6-orchestrator-active.png` |

---

## Verify

```bash
pytest tests/test_web_v2_living_orchestrator.py tests/test_web_v2_orchestrator_phase43.py tests/test_web_v2_orchestrator_phase42.py -v
python scripts/capture_phase6_orchestrator_screenshots.py
```

Local URL: `http://127.0.0.1:8000/app/`

---

## Related

- `docs/WEB_APP_ORCHESTRATOR_PHASE43.md` — Phase 4.3 pixel fidelity
- `docs/WEB_APP_ORCHESTRATOR_PHASE4.md` — Phase 4.2 reconstruction
- `docs/WEB_APP_FLOATING_WORKSPACES.md` — Phase 5.4 dock cards
- `docs/TITAN_DESIGN_CONSTITUTION.md`

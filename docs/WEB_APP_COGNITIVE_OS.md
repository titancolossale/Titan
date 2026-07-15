# Titan Web App — Phase 9 Cognitive Operating System

**Phase:** Cognitive Operating System (presentation only)  
**Scope:** Top-bar module states · floating workspace surfaces · orchestrator
runtime monitor · restrained micro-interactions  
**Constraint:** No layout redesign, color changes, neural renderer rewrite,
sidebar rebuild, composer changes, backend, API, Brain, runtime, or memory-system
changes — frontend telemetry only, wired to existing StateStore /
CognitiveStateEngine.

---

## Goal

Transform the interface from a beautiful visualization into a **believable
cognitive operating system**. The UI always communicates what Titan knows, is
doing, is thinking, is planning, and is waiting for — without becoming noisy.

---

## Module cognitive states

Every top-bar module exposes one of:

| State | Meaning |
|-------|---------|
| Idle | Quiet / en veille |
| Reading | Memory / vault / listening |
| Searching | Browser / tool search |
| Planning | Structured planning |
| Reasoning | Active reasoning |
| Writing | Streaming / synthesis |
| Waiting | Connected but awaiting |
| Finished | Cycle completed (honest signals only) |

Modules: **Mémoire · Réflexion · Présence · Outils · Cerveau · Runtime**

Resolved in `web/v2/core/cognitive-os-telemetry.js` — never invents backend work.

---

## Workspaces (live cognitive surfaces)

| Card | Surfaces |
|------|----------|
| Memory | Recent recalls · confidence · memory scan |
| Obsidian | Vault state · last sync · note activity |
| Browser | Search state · navigation · network |
| Cognitive State | Attention · reasoning depth · confidence |
| Presence | Engagement · focus · availability |

---

## Right panel — Runtime Monitor

Adds a **Runtime Monitor** section between Current Objective and Execution Pipeline:

- Reasoning stage
- Execution queue
- Connected systems
- Running tools
- Memory access
- Latency
- Model state
- Planning queue

All values derive from existing frontend state fields
(`pipelineLabel`, `conversationPlanSteps`, `activeToolIds`, `systemsUsed`,
`orchestrationDuration`, `orchestrationConfidence`, `recallActive`, …).

---

## Styles load order

1. … existing cascade …
2. `living-runtime.css` (Phase 7)
3. `living-presence.css` (Phase 8)
4. **`cognitive-os.css`** ← Phase 9 authority (loaded last)

---

## Files changed

| File | Role |
|------|------|
| `web/v2/core/cognitive-os-telemetry.js` | Pure module-state resolver |
| `web/v2/design/cognitive-os.css` | Phase 9 visual authority |
| `web/v2/center/topbar-region.js` | Module `data-cognitive` telemetry |
| `web/v2/status/status-region.js` | Workspace OS surfaces |
| `web/v2/orchestrator/orchestrator-region.js` | Runtime Monitor |
| `web/v2/layout/shell.js` | Phase 9 root datasets |
| `web/v2/design/living-presence.css` | Phase 9 selector compatibility |
| `web/v2/core/version.js` | UI version → `0.48.0` |
| `web/v2/index.html` | Load cognitive-os.css last · meta version |
| `config/settings.py` | Project version → `0.43.0` |
| `tests/test_web_v2_cognitive_os.py` | Phase 9 contracts |
| `scripts/capture_phase9_cognitive_os_screenshots.py` | Screenshot capture |

---

## Screenshots

| Capture | Path |
|---------|------|
| Full desktop idle | `docs/design/screenshots/phase-9-cognitive-os-full.png` |
| Top bar crop | `docs/design/screenshots/phase-9-cognitive-os-topbar.png` |
| Workspaces crop | `docs/design/screenshots/phase-9-cognitive-os-workspaces.png` |
| Orchestrator / monitor | `docs/design/screenshots/phase-9-cognitive-os-orchestrator.png` |

---

## Verify

```bash
pytest tests/test_web_v2_cognitive_os.py tests/test_web_v2_living_presence.py tests/test_web_v2_living_runtime.py -v
python scripts/capture_phase9_cognitive_os_screenshots.py
```

Local URL: `http://127.0.0.1:8000/app/`

---

## Related

- `docs/WEB_APP_LIVING_PRESENCE.md` — Phase 8
- `docs/WEB_APP_LIVING_RUNTIME.md` — Phase 7
- `docs/WEB_APP_LIVING_ORCHESTRATOR.md` — Phase 6
- `docs/TITAN_DESIGN_CONSTITUTION.md` — visual discipline

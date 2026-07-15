# Mission Runtime V1

Mission Runtime gives Titan the ability to maintain **long-running objectives** composed of multiple steps executed over explicit turns. It is mission **state management** — not autonomous scheduling, not background execution, and not duplicate mission planning.

## Architecture

Mission Runtime extends the existing `MissionManager` / `titan_mission.json` persistence path. No parallel subsystem is introduced.

```
Brain API
    ↓
MissionManager (v2-compatible facade)
    ↓
MissionRuntime (V1 lifecycle engine)
    ↓
data/titan_mission.json (schema v3)
```

### Integrations

| Subsystem | Role |
|-----------|------|
| **Brain** | Exposes `create_mission`, `resume_mission`, `update_mission`, `complete_mission`, `list_active_missions` |
| **Executive Function** | Read-only ranking of active missions; recommends which mission deserves attention (never mutates) |
| **Workspace Awareness** | Reads active missions into `WorkspaceSnapshot` for Brain context (never mutates) |
| **Cognitive Loop** | Observes active mission state and executive focus recommendations |
| **Tool Intelligence** | Plans tools independently; mission context informs cognition |
| **Tool Execution Engine** | On `Brain.execute_request()` completion, mission progress is recorded automatically |
| **Memory** | Cognitive loop and Executive Function use memory retrieval for relevance |

## Models

Defined in `core/mission_models.py`:

| Model | Purpose |
|-------|---------|
| `MissionState` | Lifecycle enum: `CREATED`, `PLANNING`, `READY`, `RUNNING`, `WAITING`, `BLOCKED`, `COMPLETED`, `FAILED`, `CANCELLED` |
| `MissionPriority` | `LOW`, `NORMAL`, `HIGH`, `CRITICAL` |
| `Goal` | High-level objective attached to a mission |
| `Task` | Structured step with `id`, `description`, `order`, `state` |
| `Mission` | Full mission document |
| `MissionProgress` | Computed snapshot: counts, percent, current step |
| `MissionHistoryEntry` | Append-only audit trail |

## Mission Document Fields

Each mission stores:

- `id` — UUID
- `title` — short label
- `objective` — user-facing goal description
- `created_at` / `updated_at` — ISO timestamps
- `state` — `MissionState` value
- `priority` — `MissionPriority` value
- `current_step` — active step description
- `completed_steps` — finished step descriptions
- `remaining_steps` — computed pending steps
- `progress_percent` — computed 0–100
- `steps` — ordered step list
- `history` — event log (`mission_created`, `step_completed`, `tool_execution_completed`, etc.)
- `goal` — structured goal object
- `tasks` — structured task list synced with steps

## Persistence (Schema v3)

`data/titan_mission.json` uses schema version 3:

```json
{
  "schema_version": 3,
  "active_mission_id": "uuid-or-null",
  "missions": { "uuid": { "...mission fields..." } },
  "active": true,
  "title": "...",
  "status": "in_progress"
}
```

Legacy v1/v2 single-mission documents are **auto-migrated** on load via `core/mission_migrator.py`. The flat `active` / `title` / `status` fields remain for Brain pipeline backward compatibility.

## Brain API

```python
# Create a mission with explicit steps
mission = brain.create_mission(
    title="Build Trading Bot",
    objective="Automate NQ strategy",
    steps=["Backtest", "Execution", "Risk"],
    priority="HIGH",
)

# Resume a waiting mission
brain.resume_mission(mission.id)

# Update fields
brain.update_mission(mission.id, state="RUNNING", priority="CRITICAL")

# Mark complete
brain.complete_mission(mission.id)

# List non-terminal missions
active = brain.list_active_missions()

# Progress snapshot
progress = brain.get_mission_progress(mission.id)
```

### Tool Execution Hook

When `brain.execute_request(message)` finishes, Mission Runtime automatically:

1. Appends a `tool_execution_completed` or `tool_execution_failed` history entry
2. Recalculates `progress_percent`
3. Transitions `READY → RUNNING` on success
4. Sets `BLOCKED` when tool execution fails with failed steps

No background worker runs — this only fires on explicit `execute_request()` calls.

## REPL Commands (unchanged)

Existing French REPL commands still work via `MissionManager.handle_command()`:

- `statut mission` / `mission status`
- `terminer étape` / `complete step`
- `annuler mission` / `cancel mission`

## Logging

Structured log events (via `logging`):

| Event | Level |
|-------|-------|
| Mission created | `INFO` |
| Mission updated | `INFO` |
| Mission completed | `INFO` |
| Mission failed | `INFO` |
| Mission resumed | `INFO` |
| Mission cancelled | `INFO` |
| Tool execution recorded | `INFO` |

## Explicit Execution Only

Mission Runtime **does not**:

- Start background workers
- Use timers or cron
- Schedule autonomous execution
- Run missions without a user or Brain turn

Progress advances only when:

- User sends a REPL command (`terminer étape`)
- Brain API methods are called explicitly
- `execute_request()` completes and records tool progress
- Brain pipeline `evaluate_mission_step` stage completes a step

## Tests

```bash
pytest tests/test_mission_runtime.py tests/test_mission_manager.py tests/test_mission_v2.py -v
```

Coverage includes:

- Mission creation, progress, completion, failure, resume
- Mission history and list_active_missions
- Tool execution progress hook
- Brain API integration
- Cognitive loop mission observations

## Files

| Path | Responsibility |
|------|----------------|
| `core/mission_models.py` | Dataclasses and enums |
| `core/mission_runtime.py` | Lifecycle engine |
| `core/mission_manager.py` | Facade + REPL commands |
| `core/mission_migrator.py` | Schema v3 migration |
| `brain/brain.py` | Brain API surface |
| `brain/cognitive_loop.py` | Mission observations |

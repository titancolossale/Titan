# Tool Execution Engine V1

The Tool Execution Engine executes `ToolExecutionPlan` objects produced by Tool Intelligence. Every action runs through **`ActionDispatcher`** — tools are never called directly.

---

## Purpose

| Stage | Module | Executes? |
|-------|--------|-----------|
| Planning | `ToolIntelligence` | No |
| Execution | `ToolExecutionEngine` | Yes (via `ActionDispatcher`) |
| Permission gates | `PermissionManager` | Checked inside dispatcher |
| Tool logic | `BaseTool.execute_action` | Called by dispatcher only |

---

## Pipeline

```
User message
    ↓
Brain.execute_request(message)
    ↓
ToolIntelligence.plan(message)  →  ToolExecutionPlan
    ↓
ToolExecutionEngine.execute(plan)
    ↓
ActionDispatcher.dispatch(tool_id, action_id, parameters)  [per step]
    ↓
ToolExecutionResult  →  RequestExecutionResult
```

---

## Architecture

```
ToolExecutionPlan
    execution_order: ("obsidian", "browser", ...)
    selected_tools: [ SelectedTool → PlannedAction(s) ]

ToolExecutionEngine
    ├── block per tool in execution_order
    ├── sequential actions within block (dependent)
    └── independent blocks for multi-tool plans (e.g. compare)

ActionDispatcher
    ├── ToolRegistry.get_tool
    ├── ActionRegistry.get_action
    ├── PermissionManager.check_permission
    └── BaseTool.execute_action
```

### Independence rules

| Scenario | Behavior |
|----------|----------|
| Single-tool plan, action fails | Stop; mark remaining actions in block as skipped |
| Multi-tool / compare plan, block fails | Continue to next tool block if independent |
| Unknown tool or action | Unrecoverable — stop all remaining steps |
| Permission denied | Record failure; same rules as action failure |
| Empty plan (conversation) | Return immediately with success |

---

## API

### `ToolExecutionEngine`

```python
from brain.tool_execution_engine import ToolExecutionEngine, build_core_tool_runtime

runtime = build_core_tool_runtime()
engine = runtime.engine
result = engine.execute(plan)
```

| Method | Description |
|--------|-------------|
| `execute(plan: ToolExecutionPlan) -> ToolExecutionResult` | Run all planned steps |

### `ToolExecutionResult`

| Field | Description |
|-------|-------------|
| `plan` | Original plan |
| `success` | Overall success |
| `completed_steps` | Successful `StepExecutionRecord` entries |
| `failed_steps` | Failed steps |
| `skipped_steps` | Steps skipped after failure or early stop |
| `execution_duration` | Total wall time (seconds) |
| `tool_outputs` | Last successful `data` payload per tool id |
| `messages` | Aggregated human-readable messages |
| `stopped_early` | Whether execution halted before all steps |
| `summary_message` | Final summary string |

### Brain integration

```python
result = brain.execute_request("Read my ORR notes")
print(result.summary_message)
print(result.execution.tool_outputs)
```

`Brain` wires a shared **`CoreToolRuntime`** so Tool Intelligence and the execution engine use the same `ToolRegistry` and `ActionDispatcher`.

---

## Runtime bootstrap

`build_core_tool_runtime()`:

1. Loads tools via **`ToolLoader`**
2. Syncs actions and permissions into shared registries (`sync_action_runtime`)
3. Creates **`ActionDispatcher`**
4. Returns `CoreToolRuntime` with `intelligence` and `engine`

---

## Logging

INFO logs:

- Execution start (request, intent, tools, order)
- Each tool/action start and finish (duration, success)
- Final summary (counts, duration, success)

WARNING logs:

- Failed action results

ERROR logs:

- Unknown tool blocks

---

## Testing

```bash
pytest tests/test_tool_execution_engine.py -v
```

Coverage:

- Single-tool execution
- Multi-tool execution with ordering
- Empty / conversation plan
- Tool failure and skipped dependent actions
- Permission denied
- Unknown tool (early stop)
- Independent block continuation on compare
- Output and message aggregation
- Brain `execute_request` integration

---

## Files

| Path | Role |
|------|------|
| `brain/tool_execution_engine.py` | Engine, models, runtime bootstrap |
| `brain/brain.py` | `execute_request()` |
| `tests/test_tool_execution_engine.py` | Unit tests |
| `docs/TOOL_EXECUTION.md` | This document |

---

## Related

- [Tool Intelligence V1](./TOOL_INTELLIGENCE.md) — plan production
- `core/actions/action_dispatcher.py` — universal dispatch layer

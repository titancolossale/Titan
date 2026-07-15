# Tool Intelligence V1

Tool Intelligence is Titan's metadata-driven layer for deciding **which tools** and **which actions** should handle a natural-language request. The user never names a tool — Titan chooses based on registered tool metadata, capabilities, and actions.

This module lives at `brain/tool_intelligence.py` and integrates with the existing Brain without creating a second cognitive entry point.

---

## Purpose

| Responsibility | Owner |
|----------------|-------|
| Intent analysis | `ToolIntelligence` |
| Tool selection | `ToolRegistry` metadata |
| Action selection | Action Framework (`Action` objects from each tool) |
| Execution | **Not** Tool Intelligence — downstream orchestrators / dispatchers |

Tool Intelligence **only produces an execution plan**. It does not call `ActionDispatcher`, `ToolManager`, or any tool runtime.

---

## Architecture

```
User message
    ↓
Brain.plan_tool_execution(message)
    ↓
ToolIntelligence.plan(message)
    ↓
ToolRegistry.list_enabled_tools()
    ├── tool metadata (id, name, description, category, capabilities)
    └── tool.list_actions() → Action(id, permission_id, parameters, metadata)
    ↓
ToolExecutionPlan
    ├── intent
    ├── selected_tools (+ reasons + planned actions)
    ├── execution_order
    └── confidence
```

### Dependencies (reused, not duplicated)

- **`ToolRegistry`** — source of truth for available tools
- **`ToolLoader`** — discovers tools under `core/tools/` (Browser, Obsidian, demos)
- **Action Framework** — each tool exposes `list_actions()`; plans reference `action_id` and inferred parameters
- **`PermissionManager`** — not invoked at plan time; actions carry `permission_id` for downstream gates

---

## API

### `ToolIntelligence`

```python
from brain.tool_intelligence import ToolIntelligence, build_default_tool_intelligence

intelligence = build_default_tool_intelligence()
plan = intelligence.plan("Read my ORR notes")
```

| Method | Description |
|--------|-------------|
| `plan(request: str) -> ToolExecutionPlan` | Analyze request and return a structured plan |
| `refresh() -> None` | Rebuild metadata profiles after registry changes |

### `ToolExecutionPlan`

| Field | Type | Description |
|-------|------|-------------|
| `request` | `str` | Original user message |
| `intent` | `ToolIntent` | Classified intent (`conversation`, `read`, `compare`, …) |
| `intent_summary` | `str` | Human-readable intent explanation |
| `selected_tools` | `tuple[SelectedTool, …]` | Ranked tools with reasons and planned actions |
| `execution_order` | `tuple[str, …]` | Tool ids in recommended run order |
| `confidence` | `float` | Overall plan confidence (0.0–1.0) |
| `requires_tools` | `bool` | `False` for conversation-only requests |
| `reasoning_summary` | `str` | Compact debug summary |

Each `SelectedTool` includes:

- `tool_id`, `tool_name`, `category`
- `confidence`, `reason`
- `actions`: list of `PlannedAction` (`tool_id`, `action_id`, `parameters`, `reason`, `confidence`)

### Brain integration

```python
plan = brain.plan_tool_execution("Compare my ORR notes with FastAPI docs")
```

`Brain` constructs a default `ToolIntelligence` via `build_default_tool_intelligence()` unless one is injected for tests.

---

## Decision model

### No hardcoded tools

Selection scores are computed from **runtime registry metadata**:

- Tool `id`, `name`, `description`, `category`
- Capability strings
- Registered `Action` ids, names, descriptions, and capability tags

Tools are never referenced by name in selection logic — only through metadata loaded from `ToolRegistry`.

### Intent classification

| Intent | Typical trigger |
|--------|-----------------|
| `conversation` | Greetings with no tool signal |
| `read` | Read/open/view verbs + metadata match |
| `compare` | Compare / vs / with patterns + multiple category matches |
| `search` | List/enumerate verbs |
| `write` | Create/edit/delete verbs |
| `unknown` | No confident metadata match |

### Examples

| Request | Tools | Order |
|---------|-------|-------|
| "Read my ORR notes" | Obsidian | obsidian |
| "Read the FastAPI documentation" | Browser | browser |
| "Compare my ORR notes with FastAPI docs" | Obsidian, Browser | obsidian → browser |
| "Hello" | *(none)* | — |

### Confidence

- **0.9+** — conversation-only (high confidence that no tool is needed)
- **0.35–0.98** — tool plan strength based on metadata overlap and ambiguity penalties
- **≤ 0.4** — unknown or weak matches

When two tools score closely, confidence is reduced to reflect ambiguity.

### Multi-tool ordering

For `compare` intents, tools are ordered by **category priority** from metadata:

1. `notes`
2. `web`
3. Other categories

Within a category, higher confidence runs first.

---

## Logging

`ToolIntelligence` logs at INFO:

- Intent
- Selected tool ids
- Confidence
- Execution order
- Intent summary

DEBUG logs include per-tool scores and the full serialized plan (`plan.to_dict()`).

---

## Testing

```bash
pytest tests/test_tool_intelligence.py -v
```

Coverage includes:

- Single-tool selection (Obsidian, Browser)
- Multi-tool compare with ordering
- Conversation-only (no tools)
- Unknown / ambiguous requests
- Confidence scoring
- Plan serialization
- Brain integration smoke test

---

## Future integration

Planned consumers (not executed in V1):

1. **`ExecutionCoordinator`** — enrich `Reasoning.analyze()` output before planning
2. **`CognitiveOrchestrator.create_plan()`** — seed planner steps from `PlannedAction`
3. **`ActionDispatcher`** — map `PlannedAction` → `dispatch(tool_id, action_id, parameters)`

Future Brain components should call `ToolIntelligence.plan()` or `Brain.plan_tool_execution()` directly rather than duplicating routing logic.

---

## Files

| Path | Role |
|------|------|
| `brain/tool_intelligence.py` | Core module |
| `brain/brain.py` | `plan_tool_execution()` facade |
| `tests/test_tool_intelligence.py` | Unit tests |
| `docs/TOOL_INTELLIGENCE.md` | This document |

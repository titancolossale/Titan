# Titan Capability Registry

**Version:** 0.39.0  
**Last updated:** July 13, 2026

This document describes Titan's **shared Capability Registry** and **Dynamic Tool Discovery V1** sprint. It extends the existing core tool runtime — it does not introduce a second loader, registry, or Tool Runtime.

---

## Architecture

```
Brain
  ├── list_capabilities()
  ├── search_capabilities()
  ├── find_tools_for_task()
  ├── describe_tool()
  └── summarize_installed_tools()
        ↓
Tool Intelligence  (metadata-driven planning + discovery queries)
        ↓
Capability Registry  (self-describing installed tool metadata)
        ↓
Tool Registry  (live BaseTool instances)
        ↓
Tool Loader  (filesystem discovery)
        ↓
Runtime  (ActionDispatcher → ToolExecutionEngine)
```

**Single source of truth:** Every installed tool publishes metadata into `core/tools/capability_registry.py`. The Brain and Tool Intelligence consume this registry — never a hardcoded catalog.

The legacy Phase 10A `tools/capability_catalog.py` (Tool Runtime V2 stack) remains unchanged. Core tools discovered under `core/tools/` flow through the **core Capability Registry**.

---

## Metadata Model

Each tool exposes metadata through `BaseTool` properties and actions. The registry materializes an immutable `CapabilityRecord`:

| Field | Source |
|-------|--------|
| `id` | `BaseTool.id` |
| `display_name` | `BaseTool.name` |
| `version` | `BaseTool.version` (semver) |
| `description` | `BaseTool.description` |
| `category` | `BaseTool.category` |
| `author` | `BaseTool.author` (default: Titan) |
| `capabilities` | `BaseTool.capabilities` |
| `supported_actions` | `BaseTool.list_actions()` |
| `permissions_required` | Action `permission_id` values |
| `requires_confirmation` | `BaseTool.requires_confirmation` |
| `input_schema` / `output_schema` | Aggregated from actions |
| `examples` | `BaseTool.examples` |
| `configuration_requirements` | `BaseTool.configuration_requirements` |
| `status` | Derived: active, disabled, experimental, deprecated |
| `enabled` | `BaseTool.enabled` |
| `experimental` / `deprecated` | Tool properties |
| `cost_estimate` | Tool property (default: low) |
| `risk_level` | Tool property (default: low/medium) |
| `execution_traits` | read_only, read_write, network, local, interactive |
| `streaming_support` | Tool property |
| `tags` | Tool property |

Models live in `core/tools/capability_models.py`.

---

## Registration Lifecycle

1. **Discovery** — `ToolLoader` scans `core/tools/` (and optional extra paths) for concrete `BaseTool` subclasses.
2. **Tool registration** — `ToolRegistry.register_tool()` stores the live instance.
3. **Capability publish** — When a `CapabilityRegistry` is attached, `register_tool()` also builds and validates a `CapabilityRecord`.
4. **Action sync** — `sync_action_runtime()` registers actions and permissions for execution.
5. **Refresh** — `ToolIntelligence.refresh()` rebuilds planner profiles and refreshes capability records after registry changes.
6. **Unregister** — `ToolRegistry.unregister_tool()` removes both the tool instance and capability metadata.

Adding a folder such as `core/tools/slack/` with a concrete `BaseTool` subclass automatically registers the tool — **no Brain changes required**.

---

## Validation

`CapabilityRegistry.register_tool()` validates metadata before acceptance:

- Duplicate tool ids
- Missing required fields (id, name, description, category)
- Invalid semver versions
- Invalid categories (optional strict mode)
- Unknown permissions (when permission allowlist is set)
- Duplicate action ids within a tool
- Invalid parameter / input / output schemas
- Circular registration (re-entrant register for same id)

Validation errors surface as `CapabilityValidationError` with human-readable messages. Non-strict mode logs warnings for soft issues (default for discovery).

---

## Brain APIs

| Method | Purpose |
|--------|---------|
| `brain.list_capabilities()` | All installed `CapabilityRecord` entries |
| `brain.search_capabilities(query, exact=False)` | Metadata search |
| `brain.find_tools_for_task(task)` | Rank tools for a NL task |
| `brain.describe_tool(name)` | Full record by id or display name |
| `brain.summarize_installed_tools()` | Aggregate summary for NL and UI |

### Natural-language examples

| User question | Registry path |
|---------------|---------------|
| "What tools do you have?" | `summarize_installed_tools()` |
| "Can you modify files?" | `search_capabilities("read_write")` / `find_by_capability("edit")` |
| "What can access GitHub?" | `search_capabilities("github")` |
| "What tools require confirmation?" | `find_requiring_confirmation()` |
| "What can search the internet?" | `search_capabilities("internet")` |
| "What tools support streaming?" | `find_streaming()` |
| "What tools can execute code?" | `find_tools_for_task("execute code")` |
| "What tools are experimental?" | `find_experimental()` |

---

## Search

`CapabilityRegistry.search()` supports:

- **Exact search** — id, name, or tag equality
- **Partial search** — substring match across metadata
- **Tag search** — tool tags
- **Capability search** — tool and action capabilities
- **Category search** — via `find_by_category()`
- **Permission search** — via `find_by_permission()`
- **Action search** — via `find_by_action()`

Results are ranked `CapabilitySearchResult` objects with match scores and matched fields.

---

## Future UI Integration

`CapabilityRegistry.export()` returns JSON-serializable data:

```json
{
  "summary": {
    "total_tools": 7,
    "enabled_tools": 7,
    "categories": {"web": 2, "notes": 1},
    "risk_levels": {"low": 5, "medium": 2}
  },
  "tools": [
    {
      "id": "browser",
      "display_name": "Browser",
      "version": "1.0.0",
      "enabled": true,
      "capabilities": ["open_url", "fetch_html"],
      "risk_level": "low",
      "permissions_required": ["browser.open_url"]
    }
  ]
}
```

A future Settings page can render Installed Tools, Version, Enabled, Capabilities, Risk, Permissions, and Status without additional backend work.

---

## Related Modules

| Module | Role |
|--------|------|
| `core/tools/capability_models.py` | `CapabilityRecord`, validation |
| `core/tools/capability_registry.py` | Shared registry, search, export |
| `core/tools/tool_loader.py` | Filesystem discovery |
| `core/tools/tool_registry.py` | Live tool instances |
| `core/tools/base_tool.py` | Self-describing tool contract |
| `brain/tool_intelligence.py` | Planning + discovery queries |
| `brain/tool_execution_engine.py` | `CoreToolRuntime` wiring |
| `brain/brain.py` | Public Brain APIs |
| `brain/knowledge_learning_engine.py` | Experience → verified knowledge (V1) |
| `brain/world_model.py` | Environmental state snapshot (V1) |
| `brain/meta_cognition.py` | Self-evaluation of reasoning/responses (V1) |

---

## Brain cognitive capabilities (cross-reference)

The Capability Registry covers **installed tools**. Cognitive capabilities such as
Reasoning Engine, Proactive Intelligence, Knowledge & Learning Engine, World
Model, Cognitive Context Builder, and Meta-Cognition Engine are separate Brain
subsystems — they do not register as `BaseTool` instances.

| Subsystem | Module | Learns from experience? |
|-----------|--------|-------------------------|
| Capability Registry | `core/tools/capability_registry.py` | No — tool metadata only |
| Reasoning Engine | `brain/reasoning_engine.py` | No — analyzes requests |
| Proactive Intelligence | `brain/proactive_intelligence.py` | No — surfaces attention items |
| Knowledge & Learning Engine | `brain/knowledge_learning_engine.py` | **Yes** — extracts verified knowledge |
| World Model | `brain/world_model.py` | No — aggregates current state belief |
| Cognitive Context Builder | `brain/cognitive_context_builder.py` | No — assembles read-only context |
| Meta-Cognition Engine | `brain/meta_cognition.py` | No — evaluates reasoning quality |
| Autonomous Workflow Engine | `brain/autonomous_workflow_engine.py` | **Yes** — learns via Knowledge Learning Engine after execution |
| Cognitive Operating System | `brain/cognitive_operating_system.py` | **Yes** — learns via Knowledge Learning Engine in learn stage |

The Autonomous Workflow Engine orchestrates Reasoning, Executive Function,
Meta-Cognition, Cognitive Orchestrator, and Knowledge Learning — it does not
register tools or bypass the Capability Registry execution path.

The Cognitive Operating System sits **above** all cognitive subsystems as the
single coordination layer. It routes work through explicit lifecycle stages
(receive → context → reason → evaluate → plan → confirm → execute → learn →
complete), produces `ExecutionPlan` artifacts, and tracks `ExecutionTrace` and
`ExecutionMetrics`. It may delegate execution to Autonomous Workflow Engine
for multi-step objectives but never duplicates subsystem logic.

See `docs/COGNITIVE_OPERATING_SYSTEM.md`, `docs/AUTONOMOUS_WORKFLOW_ENGINE.md`, `docs/KNOWLEDGE_LEARNING_ENGINE.md`, `docs/WORLD_MODEL.md`, `docs/COGNITIVE_CONTEXT.md`, and `docs/META_COGNITION.md`.

---

## Tests

`tests/test_capability_registry.py` covers registration, discovery, validation, Brain APIs, search, filtering, serialization, dynamic loading, and export shape compatibility.

Run:

```bash
pytest tests/test_capability_registry.py -v
```

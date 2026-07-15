# World Model V1

**Version:** 0.40.0  
**Module:** `brain/world_model.py`

## Purpose

The World Model is Titan's **structured representation of reality as Titan currently believes it exists**. It answers questions like:

- "What is the current state of my projects?"
- "What is blocked right now?"
- "What tools and integrations are available?"
- "What tasks are open vs completed?"
- "What deserves focus?"

The World Model **never executes actions**. It only aggregates read-only signals from existing subsystems into one coherent snapshot.

## Architecture

```
Read-only subsystem signals
  ├── Project Intelligence   → architecture, modules, dependencies, health
  ├── Mission Runtime        → active missions, open/completed tasks
  ├── Developer Workflow     → (peer dependency; dev context via workspace)
  ├── Knowledge Learning     → verified knowledge as opportunity hints
  ├── Memory Service         → user goals and priorities (retrieval)
  ├── Code Intelligence      → (peer; modules via Project Intelligence)
  ├── Executive Function     → focus, blockers, idle missions
  ├── Proactive Intelligence → attention recommendations (if evaluated)
  ├── Workspace Awareness    → workspace, documents, repositories
  ├── Tool Intelligence      → installed tools / capabilities
  └── State Manager          → runtime continuity (version, progress)
        ↓
WorldModel.build_world_model()
  ├── refresh workspace (explicit)
  ├── evaluate executive missions
  ├── analyze project architecture
  ├── partition mission tasks
  ├── assess project health
  ├── collect blockers / risks / opportunities
  └── cache WorldModelSnapshot
        ↓
Brain APIs → prompts, NLO, future UI
```

No second Brain, memory system, planner, orchestrator, or learning engine is created.

## World Model vs Memory

| Dimension | Memory (`memory/`) | World Model (`brain/world_model.py`) |
|-----------|------------------|--------------------------------------|
| Stores | Durable user notes, preferences, goals | Nothing — ephemeral aggregated snapshot |
| Nature | What the user asked to remember | What Titan believes is true **right now** |
| Persistence | JSON via managers | In-memory cache (export only) |
| Updates | On memory write pipeline | On explicit `build_world_model()` / `refresh()` |
| Scope | User-isolated facts | Full environmental state |

Memory **feeds** the World Model through `MemoryService.retrieve()` for goal hints. The World Model does not write memory.

## World Model vs Knowledge

| Dimension | Knowledge Learning Engine | World Model |
|-----------|---------------------------|-------------|
| Purpose | Generalize lessons from experience | Represent current environmental state |
| Content | Verified patterns, workflows, strategies | Projects, tasks, tools, blockers, focus |
| Lifecycle | Candidate → verified/rejected | Rebuilt on demand |
| Time horizon | Past experience → future reuse | Present moment only |

Verified knowledge may surface as **opportunity hints** in the World Model. Knowledge does not replace the World Model snapshot.

## World Model vs Reasoning

| Dimension | Reasoning Engine | World Model |
|-----------|------------------|-------------|
| Purpose | Structured thinking about a request | Factual state aggregation |
| Output | Steps, options, risks analysis, strategy | Snapshot of believed reality |
| Mutates state | No | No |
| Executes tools | No | No |

Reasoning **consumes** context; the World Model **provides** structured situational context. Reasoning analyzes; the World Model represents.

## World Model vs Proactive Intelligence

| Dimension | Proactive Intelligence | World Model |
|-----------|------------------------|-------------|
| Purpose | Rank what deserves **attention** | Describe what **is** |
| Output | Recommendations with lifecycle | Neutral state snapshot |
| Persistence | `data/proactive_intelligence.json` | In-memory (export JSON) |
| Bias | Action-oriented suggestions | Descriptive belief |

Proactive Intelligence may contribute blocker/opportunity signals when a digest exists. The World Model remains descriptive, not advisory.

## Snapshot structure

`WorldModelSnapshot` maintains structured representations of:

| Field | Source |
|-------|--------|
| `active_projects` | Context, workspace, architecture |
| `project_health` | Executive + architecture + workspace signals |
| `project_dependencies` | Project Intelligence dependency graph |
| `open_tasks` / `completed_tasks` | Mission Runtime task states |
| `active_missions` | Mission Runtime |
| `available_tools` | Capability Registry via Tool Intelligence |
| `connected_integrations` | Tool install + env configuration |
| `runtime_status` | State Manager + Context Manager + version |
| `current_workspace` | Workspace Awareness |
| `known_repositories` | Workspace root + git branch |
| `documents` | Workspace documentation files |
| `code_modules` | Workspace + Project Intelligence |
| `user_goals` | Memory retrieval + verified knowledge titles |
| `current_focus` | Executive Function |
| `blockers` | Executive, missions, workspace, proactive |
| `risks` | Architecture violations, idle missions, workspace |
| `opportunities` | Executive focus, workspace, proactive, knowledge |

## Brain APIs

| Method | Purpose |
|--------|---------|
| `brain.build_world_model(message="")` | Full rebuild |
| `brain.refresh_world_model(message="")` | Alias rebuild with workspace refresh |
| `brain.get_world_model_snapshot()` | Cached snapshot (build if empty) |
| `brain.get_project_state()` | Project-centric slice |
| `brain.get_workspace_state()` | Workspace-centric slice |
| `brain.get_world_blockers()` | Known blockers |
| `brain.get_world_opportunities()` | Known opportunities |
| `brain.get_world_dependencies()` | Dependency map |
| `brain.get_world_active_focus()` | Current focus belief |
| `brain.export_world_model()` | JSON export for UI / debugging |

Direct `WorldModel` class methods mirror these (`build_world_model`, `refresh`, `get_snapshot`, etc.).

## Export format

`export_world_model()` returns:

```json
{
  "schema_version": 1,
  "exported_at": "2026-07-13T03:00:00+00:00",
  "world_model": { "...": "full snapshot to_dict()" }
}
```

Suitable for a future dashboard or Settings UI panel ("Titan's view of the world").

## Future roadmap

| Phase | Enhancement |
|-------|-------------|
| V1.1 | NLO intent `WORLD_STATE` for "what's the current state?" queries |
| V1.2 | Prompt injection via `format_for_prompt()` in Think pipeline |
| V1.3 | Diff tracking between snapshots (what changed since last build) |
| V2 | Event-driven partial refresh (mission update → invalidate slice) |
| V2 | Multi-project namespaces with user isolation |
| V3 | External environment probes (CI status, deployment health) read-only |

## Related documents

- `docs/ARCHITECTURE.md` — runtime execution path
- `docs/PROJECT_INTELLIGENCE.md` — architecture analysis
- `docs/EXECUTIVE_FUNCTION.md` — mission focus
- `docs/WORKSPACE_AWARENESS.md` — workspace snapshot
- `docs/PROACTIVE_INTELLIGENCE.md` — attention recommendations
- `docs/KNOWLEDGE_LEARNING_ENGINE.md` — verified knowledge

## Tests

```bash
pytest tests/test_world_model.py -v
```

# Cognitive Context Builder V1

**Version:** 0.41.0  
**Module:** `brain/cognitive_context_builder.py`

## Purpose

The Cognitive Context Builder is Titan's **single assembly point** for all signals
needed before reasoning, planning, or prompt synthesis. It answers:

- "What does Titan know right now?"
- "What is relevant to this specific request?"
- "What missions, tools, memory, and knowledge should inform the next thought?"

Reasoning Engine and downstream cognition consume **one** `CognitiveContext` object.
They must not query Memory, Knowledge Learning Engine, World Model, Project
Intelligence, or Proactive Intelligence individually.

The builder is **read-only**. It never mutates memory, knowledge, missions, or files,
and never executes tools.

## Architecture

```
Read-only subsystem signals
  ├── Memory Service           → relevant memories (retrieval)
  ├── Knowledge Learning       → verified knowledge (search / list)
  ├── World Model              → environmental snapshot
  ├── Mission Runtime          → active missions
  ├── Context Manager          → situational context (user, project, phase)
  ├── Workspace Awareness      → active workspace snapshot
  ├── Executive Function       → mission priorities and focus
  ├── Proactive Intelligence   → ranked recommendations
  ├── Project Intelligence     → architecture (request / project modes)
  ├── Code Intelligence        → code task context
  ├── Developer Workflow       → dev plan (code task mode)
  ├── Tool Intelligence        → available tools + task candidates
  ├── Development Session      → active coding session
  ├── State Manager            → runtime continuity (via World Model)
  └── Conversation Engine      → recent dialogue window
        ↓
CognitiveContextBuilder.build_*()
  ├── resolve user / project
  ├── load world model baseline
  ├── retrieve memories + knowledge (when message present)
  ├── evaluate executive + proactive (pass-through if pre-supplied)
  ├── domain-specific slices (architecture, code, workflow)
  └── cache CognitiveContext
        ↓
Reasoning Engine / Brain APIs / future prompt assembly
```

No second Brain, memory system, World Model, planner, or learning engine is created.

## Cognitive Context vs World Model

| Dimension | World Model | Cognitive Context |
|-----------|-------------|-------------------|
| Scope | Environmental belief (projects, tasks, tools, blockers) | Full cognitive input for one operation |
| Memory | Goal hints only | Retrieved relevant memories |
| Knowledge | Opportunity hints | Verified knowledge search results |
| Conversation | Not included | Recent dialogue window |
| Executive / Proactive | Partial (focus, blockers) | Full evaluation objects |
| Build modes | Single `build_world_model()` | General, request, project, code, mission |

The Cognitive Context Builder **consumes** the World Model as one slice — it does not
replace it.

## Context Assembly Pipeline

1. **Resolve identity** — user and project from `ContextManager` when not supplied.
2. **Workspace** — refresh or reuse `WorkspaceSnapshot`.
3. **World Model** — `WorldModel.build_world_model()` for baseline environmental state.
4. **Executive Function** — `evaluate_missions()` unless pre-computed evaluation passed.
5. **Memory** — `MemoryService.retrieve(user, message)` when a message is present.
6. **Knowledge** — `search_knowledge(verified_only=True)` or `list_verified_knowledge()`.
7. **Missions** — `list_active_missions()` or single mission for mission mode.
8. **Proactive** — `evaluate()` with executive/workspace pass-through.
9. **Situational + conversation** — `ContextManager.get_context()` and
   `ConversationEngine.get_prompt_window()`.
10. **Request extras** (request / project / code modes) — architecture, code context,
    developer workflow plan, tool candidates.
11. **Summary + cache** — assemble `CognitiveContext`, store as `_last_context`.

## Priority Rules

1. **Pre-computed pass-through wins** — if `executive_evaluation` or
   `proactive_evaluation` is supplied, the builder does not recompute them.
2. **World Model is the environmental baseline** — project health, tools, runtime
   status, and focus come from the snapshot when available.
3. **Request message drives retrieval** — memory and knowledge search use the
   request text; empty message skips memory retrieval.
4. **Domain filtering** — architecture loads for SOFTWARE/ARCHITECTURE/CODE/PLANNING
   domains in request mode; code task mode forces architecture + code + workflow.
5. **Graceful degradation** — each subsystem is wrapped in try/except; failures set
   `sources[subsystem] = False` and continue.

## Filtering

| Build mode | Memory | Knowledge | Architecture | Code | Workflow | Tool candidates |
|------------|--------|-----------|--------------|------|----------|-----------------|
| `GENERAL` | if message | always (limited) | no | no | no | no |
| `REQUEST` | if message | if message | domain-based | domain-based | no | yes |
| `PROJECT` | if message | if message | yes | no | no | yes |
| `CODE_TASK` | if message | if message | yes | yes | yes | yes |
| `MISSION` | if message | if message | no | no | no | no |

Mission mode filters `active_missions` to the focused mission id only.

## Brain APIs

| Method | Purpose |
|--------|---------|
| `build_cognitive_context(message)` | General full context |
| `build_cognitive_context_for_request(message)` | Request-aware context |
| `build_cognitive_context_for_project(project_id)` | Project-centric context |
| `build_cognitive_context_for_code_task(message)` | Code-optimized context |
| `build_cognitive_context_for_mission(mission_id)` | Mission-focused context |
| `get_last_cognitive_context()` | Cached last build |
| `export_cognitive_context()` | JSON export |

## Reasoning Engine Integration

`ReasoningEngine._gather_context()` delegates exclusively to
`CognitiveContextBuilder.build_for_request()`. All reasoning stages read from
`CognitiveContext` fields (`architecture`, `active_missions`, `tool_candidates`,
`sources`, etc.) — never from individual subsystem calls.

The builder is wired on `Brain.__init__` after `WorldModel` and attached to
`ReasoningEngine` via `attach_context_builder()`.

## Future Improvements

- Inject pre-computed `ReasoningResult` into builder for NLO awareness pass reuse
- Token budget trimming / prioritization before prompt injection
- Embedding-based memory and knowledge ranking inside the builder
- `ThinkContext.cognitive_context` field in the think() pipeline
- Persisted context snapshots for session replay and debugging UI
- Per-user context namespaces with explicit isolation checks

## Related Documents

- `docs/WORLD_MODEL.md` — environmental snapshot layer
- `docs/REASONING_ENGINE.md` — structured thinking consumer
- `docs/ARCHITECTURE.md` — official runtime path
- `docs/CAPABILITY_REGISTRY.md` — tool discovery slice

# Natural Language Orchestrator V1

The Natural Language Orchestrator is the **canonical front door of the Brain** for high-level natural-language requests.

It decides **which existing Brain systems** should participate, **in which order**, and **why** — then delegates. It does not execute tools, generate code, edit files, or bypass permissions.

> Orchestration only. Every action is delegated to the existing architecture.

## Architecture

```
User natural language
    ↓
Brain.process_request(message)          ← primary high-level Brain API
    ↓
NaturalLanguageOrchestrator.process()
    ├── RequestAnalysis                 (session / missions / workspace / memory cues)
    ├── DetectedIntent + confidence
    ├── PipelineDecision                (ordered SystemName list)
    ├── Conversation awareness          (Context, Workspace, Memory, Missions,
    │                                    Development Session, Executive Function)
    ├── Developer enrichment (if needed)
    └── Intent handler → existing Brain APIs only
    ↓
OrchestrationResult
    ├── RequestAnalysis
    ├── DetectedIntent
    ├── PipelineDecision
    ├── SystemsUsed
    ├── ReasoningSummary
    ├── Confidence
    └── FinalResponse
```

### What this is not

| System | Role | Relationship |
|--------|------|----------------|
| `ThinkPipeline` / `Brain.think()` | Conversational cognitive synthesis | Called for conversation/question intents |
| `tools/natural_language_planner.py` | NL → tool `PlannerResult` | Unchanged; used inside tool path |
| `CognitiveOrchestrator` | Tool plan → execute → verify | Unchanged |
| `ToolOrchestrator` / Tool Runtime | Permissioned tool dispatch | Reached only via `Brain.execute_request` |

No second Brain. No duplicate planner, runtime, executor, workflow, registry, or intelligence system.

## Reused systems

| System | When selected |
|--------|----------------|
| Workspace Awareness | Always (awareness); workspace queries; developer mode |
| Memory / Context Manager | Always (awareness); memory intents |
| Mission Runtime | Always (awareness); mission management; continuation |
| Executive Function | Always (awareness); missions; continuation; developer mode |
| Long-Term Planner | Planning intents (`plan_goal`) |
| Project Intelligence | Architecture / project analysis; developer enrichment |
| Code Intelligence | Code explanation; developer enrichment |
| Developer Workflow | Development continuation; developer mode |
| Tool Intelligence | Research, tool request, memory+Obsidian |
| Code Modification Planner | Code planning / generation |
| Code Generation Engine | Code generation (never applies) |
| Controlled Patch (`CodeEditorTool`) | Patch preview / application only |
| Development Session | Continuation; awareness |
| Tool Execution Engine | Research / tool request (via `execute_request`) |
| `Brain.think()` | Conversation / question |

## Intent model

| Intent | Example | Primary systems |
|--------|---------|-----------------|
| `conversation` | "Bonjour" | `think()` |
| `question` | "What is Titan?" | `think()` |
| `research` | "Search FastAPI docs" | Tool Intelligence → Tool Execution |
| `planning` | "Plan the ORR automation" | Long-Term Planner |
| `architecture` | "Show the architecture" | Project Intelligence |
| `project_analysis` | "Analyze the project" | Project Intelligence |
| `code_explanation` | "Explain class Engine" | Code Intelligence |
| `code_planning` | "Plan a code change…" | Code Modification Planner |
| `code_generation` | "Generate code…" | Planner → Generator (**no apply**) |
| `patch_preview` | "Preview the patch" | Controlled Patch |
| `patch_application` | "Apply the approved patch" | Controlled Patch |
| `workspace_query` | "Current workspace?" | Workspace Awareness |
| `mission_management` | "List active missions" | Mission Runtime + Executive Function |
| `memory` | "Read my ORR notes" | Memory + Tool Intelligence (Obsidian) |
| `tool_request` | "Run pytest" | Tool Intelligence → Tool Execution |
| `development_continuation` | "Continue Titan" | Workspace + Mission + Executive + Developer Workflow |

## Pipeline

Canonical order for every request:

1. **Intent analysis**
2. **Conversation awareness** — context, workspace, memory, missions, development session, executive function
3. **Developer enrichment** (when development-related) — project + code intelligence signals
4. **Intent-specific systems** (see table above)
5. **Natural response** — structured `OrchestrationResult.final_response`

### Routing examples

```
"Continue Titan"
  → Workspace → Mission → Executive Function → Developer Workflow

"Explain this class Engine"
  → Workspace → Code Intelligence

"Plan the ORR automation"
  → Long-Term Planner

"Apply the approved patch"
  → Controlled Patch (requires approved session patch + confirmation)

"Read my ORR notes"
  → Memory → Obsidian (via Tool Intelligence / Execution)

"Search FastAPI docs"
  → Browser Tool (via Tool Execution Engine)

"Generate code"
  → Code Modification Planner → Code Generation Engine
  → (never Controlled Patch apply)
```

## Brain API

```python
result = brain.process_request("Plan the ORR automation")

result.detected_intent      # DetectedIntent.PLANNING
result.pipeline_decision    # ordered systems
result.systems_used         # invoked / skipped
result.reasoning_summary
result.confidence
result.final_response
result.to_dict()
```

`Brain.think(message)` remains available for direct conversational synthesis. Conversation intents from `process_request` call `think()` internally.

## Execution rules

The orchestrator:

- never edits code itself
- never executes tools itself (delegates to Tool Execution Engine)
- never bypasses permissions or confirmation gates
- never mutates the repository except by delegating to Controlled Patch after approval
- never invents missing patch objects — returns a clear message when none exist

## Logging

Logs (no secrets):

- request (redacted)
- detected intent
- selected / invoked systems
- confidence
- duration

## Limitations (V1)

- Intent detection is rule/pattern-based (not LLM-classified).
- Patch apply/preview requires a recoverable `GeneratedPatch` on the active development session.
- Mixed multi-intent requests pick the strongest single intent (no parallel multi-pipeline yet).
- Tool execution still subject to existing permission / confirmation policy.

## Future roadmap

- LLM-assisted intent classification with confidence calibration
- Multi-intent pipelines (ordered sub-goals in one turn)
- Tighter Development Session ↔ patch artifact reconstruction
- Optional dry-run mode that never calls Tool Execution Engine
- REPL / web UI defaulting to `process_request` instead of raw `think`

## Related documents

- `docs/ARCHITECTURE.md` — official execution path
- `docs/LONG_TERM_PLANNER.md`
- `docs/DEVELOPER_WORKFLOW.md`
- `docs/CODE_INTELLIGENCE.md`
- `docs/CONTROLLED_PATCH_APPLICATION.md`
- `docs/TOOL_INTELLIGENCE.md`
- `docs/DEVELOPMENT_SESSION.md`

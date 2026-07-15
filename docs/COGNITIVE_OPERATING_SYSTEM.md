# Cognitive Operating System V1

**Version:** 0.39.0+  
**Module:** `brain/cognitive_operating_system.py`

## Purpose

The Cognitive Operating System (COS) is Titan's **central cognitive coordination layer**. It sits above all cognitive subsystems and routes work between them without replacing their logic.

It answers:

> Given a high-level request, which cognitive pipeline stages are required, in what order, and how do we track the full lifecycle?

COS **never duplicates**:

- Reasoning Engine
- Executive Function
- Meta-Cognition
- Cognitive Context Builder
- World Model
- Knowledge Learning Engine
- Memory
- Project Intelligence
- Developer Workflow
- Autonomous Workflow Engine
- Cognitive Orchestrator

It **orchestrates** them through a single lifecycle with explicit stages, execution plans, traces, and metrics.

## Architecture

```
High-level request
    ↓
CognitiveOperatingSystem
    ├── receive          → register execution
    ├── context          → Cognitive Context Builder + World Model + Memory retrieval
    ├── reason           → Reasoning Engine
    ├── evaluate         → Executive Function + Meta-Cognition (+ Project Intelligence for code)
    ├── plan             → Developer Workflow (code) + Cognitive Orchestrator plan
    ├── confirm          → meta-cognition / plan / confirmation gates
    ├── execute          → Cognitive Orchestrator OR Autonomous Workflow Engine
    ├── learn            → Knowledge Learning Engine
    └── complete         → finalize status, trace, metrics
    ↓
CognitiveProcessResult (plan, execution, learning, trace)
```

### Subsystem orchestration

| Subsystem | Stage(s) | Role |
|-----------|----------|------|
| `WorkspaceAwareness` | context | Refresh workspace before context assembly |
| `CognitiveContextBuilder` | context | Unified `CognitiveContext` |
| `WorldModel` | context | Environmental belief snapshot |
| `MemoryService` | context | Relevant memory retrieval (read-only) |
| `ReasoningEngine` | reason | Structured multi-step analysis |
| `ExecutiveFunction` | evaluate | Mission focus ranking |
| `MetaCognitionEngine` | evaluate, confirm | Quality gate and confidence |
| `ProjectIntelligence` | evaluate | Architecture summary for code domains |
| `DeveloperWorkflow` | plan | Dev recommendations for code domains |
| `CognitiveOrchestrator` | plan, execute | Tool plan creation and execution |
| `AutonomousWorkflowEngine` | execute | Multi-step workflow path (optional) |
| `KnowledgeLearningEngine` | learn | Outcome and strategy learning |

### Relationship to other layers

| Layer | Relationship |
|-------|--------------|
| `Brain.process_request()` | NLO front door — unchanged; routes NL intents |
| `Brain.run_cognitive_cycle()` | COS front door — full cognitive lifecycle |
| `AutonomousWorkflowEngine` | Optional execute delegate for multi-step workflows |
| `NaturalLanguageOrchestrator` | Independent; may call Brain subsystems directly |

COS does not replace NLO or `think()`. Brain exposes thin facades that delegate to COS.

## Execution lifecycle

### Stages

| Stage | Meaning |
|-------|---------|
| `receive` | Request validated and execution registered |
| `context` | Context, world model, and memory assembled |
| `reason` | Reasoning Engine produces `ReasoningResult` |
| `evaluate` | Executive + meta-cognition (+ project intelligence when relevant) |
| `plan` | Developer plan (code) + cognitive execution plan |
| `confirm` | User or safety gate before execution |
| `execute` | Tool plan or workflow execution |
| `learn` | Knowledge extraction from outcomes |
| `complete` | Terminal status and final trace entry |

### Execution statuses

| Status | Meaning |
|--------|---------|
| `received` | Execution registered |
| `building_plan` | Plan stages in progress |
| `awaiting_confirmation` | User approval required |
| `executing` | Tool or workflow execution running |
| `completed` | Lifecycle finished successfully |
| `failed` | Verification failed or unrecoverable error |
| `cancelled` | User or system cancelled |

### Typical flow

```
build_execution_plan(message)
    → receive → context → reason → evaluate → plan
    → ExecutionPlan (may require confirmation)

execute_plan(plan_id, confirmed=True)
    → confirm → execute → learn → complete
    → CognitiveProcessResult
```

Or in one call:

```
process_request(message, confirmed=True)
    → full pipeline
```

## Execution tracing

Each stage appends a `StageTraceEntry` to an `ExecutionTrace`:

- `stage` — lifecycle stage name
- `started_at` — UTC timestamp
- `duration_ms` — elapsed since prior stage
- `success` — whether the stage completed without gate failure
- `summary` — human-readable outcome
- `subsystem` — primary subsystem invoked
- `artifact_keys` — artifact keys stored for this stage

Access via:

- `get_execution_trace(execution_id)`
- `export_execution(execution_id)` — includes trace, metrics, plan, artifacts

## Execution metrics

`ExecutionMetrics` aggregates per execution:

| Field | Description |
|-------|-------------|
| `total_duration_ms` | Sum of inter-stage durations |
| `stage_durations_ms` | Per-stage timing |
| `subsystem_calls` | Call counts per subsystem |
| `confirmation_gates` | Number of confirmation blocks |
| `learning_items` | Learning stage completions |
| `stages_completed` / `stages_failed` | Stage outcome counts |

## Brain API

| Brain method | COS method |
|--------------|------------|
| `run_cognitive_cycle(message)` | `process_request()` |
| `build_cognitive_execution_plan(message)` | `build_execution_plan()` |
| `execute_cognitive_plan(plan_id)` | `execute_plan()` |
| `cancel_cognitive_execution(execution_id)` | `cancel_execution()` |
| `get_cognitive_execution_trace(execution_id)` | `get_execution_trace()` |
| `get_cognitive_execution_metrics(execution_id)` | `get_execution_metrics()` |
| `export_cognitive_execution(execution_id)` | `export_execution()` |

`Brain.process_request()` remains the Natural Language Orchestrator entry — backward compatible.

## Workflow engine selection

By default, COS uses `CognitiveOrchestrator` directly for execution. When:

- `use_workflow_engine=True` is passed, or
- the cognitive plan has more than two steps and AWF is wired,

execution delegates to `AutonomousWorkflowEngine` for the execute stage.

## Future roadmap

- **V2:** Persist executions and traces to `data/cognitive_executions.json`
- **V2:** NLO integration — route complex intents through COS automatically
- **V2:** Meta-cognition may block or adjust responses based on trace signals
- **V3:** Cross-session execution resume and distributed trace export
- **V3:** UI dashboard for stage traces and subsystem metrics

## Related documents

- `docs/ARCHITECTURE.md` — official execution path
- `docs/AUTONOMOUS_WORKFLOW_ENGINE.md` — workflow orchestration
- `docs/REASONING_ENGINE.md` — structured reasoning
- `docs/COGNITIVE_CONTEXT.md` — context assembly
- `docs/META_COGNITION.md` — self-evaluation
- `docs/KNOWLEDGE_LEARNING_ENGINE.md` — experience learning

## Tests

```bash
pytest tests/test_cognitive_operating_system.py -v
```

# Autonomous Workflow Engine V1

**Version:** 0.39.0+  
**Module:** `brain/autonomous_workflow_engine.py`

## Purpose

The Autonomous Workflow Engine is Titan's **generic workflow orchestration layer**. It coordinates existing cognitive systems to execute multi-step objectives end-to-end.

It answers:

> Given a high-level objective, how do I analyze, plan, execute, validate, and learn — using systems that already exist?

The engine **does not replace**:

- Reasoning Engine
- Executive Function
- Meta-Cognition
- Cognitive Orchestrator
- Tool Runtime

It **orchestrates** them in a single workflow lifecycle with explicit state, confirmation gates, and outcome learning.

## Architecture

```
High-level objective
    ↓
AutonomousWorkflowEngine
    ├── Cognitive Context Builder   → unified CognitiveContext
    ├── Reasoning Engine            → ReasoningResult
    ├── Executive Function          → ExecutiveEvaluation
    ├── Meta-Cognition Engine       → MetaCognitionReport (safety gate)
    ├── confirmation check          → awaiting_confirmation if needed
    ├── Cognitive Orchestrator      → plan → execute → verify
    └── Knowledge Learning Engine   → learn_from_execution / learn_from_reasoning
    ↓
WorkflowRunResult (status, artifacts, learning)
```

### Reused components

| Component | Role in workflow |
|-----------|------------------|
| `CognitiveContextBuilder` | Assembles read-only context before reasoning |
| `ReasoningEngine` | Multi-step structured analysis of the objective |
| `ExecutiveFunction` | Mission focus ranking with reasoning input |
| `MetaCognitionEngine` | Confidence, clarification, and quality gate |
| `CognitiveOrchestrator` | Plan creation, tool execution, verification |
| `KnowledgeLearningEngine` | Records execution outcomes and strategy lessons |
| `ConfirmationGate` | Detects pending tool approvals (optional) |

No second Brain, no duplicate planner, no direct ToolManager calls.

## Workflow lifecycle

### States

| State | Meaning |
|-------|---------|
| `created` | Workflow registered, not yet started |
| `analyzing` | Building context, reasoning, executive, meta-cognition |
| `planning` | Cognitive Orchestrator creating execution plan |
| `awaiting_confirmation` | User approval required before proceeding |
| `executing` | Tool plan running via Cognitive Orchestrator |
| `validating` | Post-execution verification |
| `completed` | Workflow finished successfully |
| `failed` | Verification failed or unrecoverable error |
| `cancelled` | User or system cancelled the workflow |
| `paused` | Workflow suspended (resume restores prior phase) |

### Typical flow

```
create_workflow(objective)
    → created
start_workflow(workflow_id)
    → analyzing → planning → executing → validating → completed | failed
```

When confirmation is required:

```
start_workflow(workflow_id)
    → analyzing → awaiting_confirmation
start_workflow(workflow_id, confirmed=True)
    → planning → executing → validating → completed | failed
```

## Integration points

### Brain APIs

```python
brain.create_workflow("Research FastAPI middleware patterns")
brain.start_workflow(workflow_id)
brain.start_workflow(workflow_id, confirmed=True)  # after user approval
brain.pause_workflow(workflow_id)
brain.resume_workflow(workflow_id)
brain.cancel_workflow(workflow_id)
brain.get_workflow(workflow_id)
brain.list_workflows(status=WorkflowStatus.EXECUTING)
brain.export_workflow(workflow_id)
```

### Cognitive Orchestrator

Tool execution flows through the **official path**:

```
CognitiveOrchestrator.create_plan()
  → CognitiveOrchestrator.execute_plan()
  → CognitiveOrchestrator.verify_plan()
```

The workflow engine never calls `ToolManager` or `ActionDispatcher` directly.

### Knowledge Learning

On completion (success or failure), the engine notifies:

- `learn_from_execution()` — strategy success/failure from tool outcomes
- `learn_from_reasoning()` — recommended strategies and risks from reasoning

Learning is best-effort; workflow completion is not blocked if learning fails.

## Human confirmation model

Confirmation is required when **any** of the following is true (unless `confirmed=True`):

1. Meta-cognition reports `clarification_required`
2. Meta-cognition confidence is below threshold (default: 0.45)
3. Reasoning has open questions
4. Cognitive plan has `clarification_required` or `requires_confirmation`
5. Tool execution suspends pending confirmation
6. Confirmation Gate has pending approvals (when wired)

When paused at `awaiting_confirmation`, the workflow stores:

- `confirmation_reason` — human-readable explanation
- Full cognitive artifacts in `export_workflow()` for UI review

Titan never silently executes risky tool steps when confirmation is required.

## Data model

### WorkflowRecord

Mutable in-memory workflow state: objective, status, user, project, mission link, timestamps, confirmation metadata, and execution summaries.

### WorkflowRunResult

Frozen result of `start_workflow` / `resume_workflow` including optional references to reasoning, executive evaluation, meta-cognition report, cognitive context, plan, execution result, and learning result.

## Future roadmap

| Phase | Capability |
|-------|------------|
| V1 (current) | Single-turn workflow orchestration, confirmation gates, in-memory state |
| V1.1 | Persist workflows to `data/workflows.json` |
| V2 | Multi-step mission-linked workflows across sessions |
| V2 | Natural Language Orchestrator intent routing (`AUTONOMOUS_WORKFLOW`) |
| V3 | Scheduler integration for deferred workflow starts |
| V3 | Meta-cognition may block low-confidence execution (behavior influence) |
| V4 | Workflow templates and reusable step sequences from verified knowledge |

## Related documents

- `docs/ARCHITECTURE.md` — official execution paths
- `docs/REASONING_ENGINE.md` — reasoning pipeline
- `docs/EXECUTIVE_FUNCTION.md` — mission prioritization
- `docs/META_COGNITION.md` — self-evaluation layer
- `docs/KNOWLEDGE_LEARNING_ENGINE.md` — outcome learning
- `docs/COGNITIVE_CONTEXT.md` — unified context assembly

## Tests

```bash
pytest tests/test_autonomous_workflow_engine.py -v
```

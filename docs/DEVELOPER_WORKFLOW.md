# Developer Workflow V1

Developer Workflow gives Titan a structured way to **understand and assist with software development** end-to-end — without autonomous coding or self-modification.

It is **not** an auto-coder, **not** a self-modification engine, and **not** a command runner.

> Plan only. Recommend tools and commands. Never execute. Tool Execution Engine runs after approval.

## Architecture

```
Brain.plan_development_workflow(message)
    ↓
WorkspaceAwareness.refresh()
ExecutiveFunction.evaluate_missions()
    ↓
DeveloperWorkflow.plan()
    ├── WorkspaceSnapshot (files, modules, git, docs)
    ├── ExecutiveEvaluation (mission focus)
    ├── MemoryService (optional hints)
    └── ToolIntelligence.plan() (tool recommendations)
    ↓
DeveloperWorkflowPlan
    ├── goal / context_summary
    ├── relevant_files
    ├── recommended_tools / recommended_commands
    ├── test_plan / documentation_updates
    ├── risk_level / requires_confirmation
    └── next_steps
```

### Reused components

| Component | Role |
|-----------|------|
| **Brain** | Public API: `plan_development_workflow(message)` |
| **Workspace Awareness** | Project, modules, recent files, docs, git branch |
| **Executive Function** | Mission ranking and focus recommendation |
| **Mission Runtime** | Active mission context (read-only) |
| **Tool Intelligence** | Metadata-driven tool recommendations |
| **Tool Execution Engine** | **Not called** — execution stays downstream after approval |
| **Memory** | Optional retrieval hints for the request |
| **ContextManager** | Current user / active project |

No second framework. No autonomous edits. No direct shell execution.

## Responsibilities

| Does | Does not |
|------|----------|
| Analyze development requests | Write or patch code |
| Inspect workspace context | Run git / pytest / shell |
| Identify relevant files/modules | Mutate missions or memory |
| Recommend tools and commands | Call Tool Execution Engine |
| Recommend tests and doc updates | Self-modify Titan |
| Classify risk and confirmation | Invent a parallel tool stack |

## Supported request styles

| Example | Intent |
|---------|--------|
| "Continue Titan development" | `continue_development` |
| "Find what needs to be fixed" | `find_fixes` |
| "Run the relevant tests" | `run_tests` |
| "Prepare the next implementation sprint" | `prepare_sprint` |
| "Check what changed" | `check_changes` |
| "Summarize the current codebase state" | `summarize_codebase` |

French phrasing is also recognized where common (e.g. continuer le développement, lancer les tests).

## `DeveloperWorkflowPlan` fields

| Field | Description |
|-------|-------------|
| `goal` | Concise development goal (may include mission focus) |
| `context_summary` | Workspace + mission + memory snapshot summary |
| `relevant_files` | Ranked paths correlated with the request / missions |
| `recommended_tools` | Tool ids (e.g. `terminal`, `python`, `github`, `obsidian`, `browser`) |
| `recommended_commands` | Advisory shell/git/pytest commands — **not executed** |
| `test_plan` | Suggested test targets |
| `risk_level` | `RiskLevel` (`safe` … `critical`) |
| `next_steps` | Ordered human/agent follow-ups |
| `requires_confirmation` | Whether downstream execution should ask first |
| `intent` | Classified `WorkflowIntent` |
| `documentation_updates` | Suggested doc / changelog touch-ups |
| `mission_context` | Compact active/recommended mission string |
| `reasoning_summary` | Debug-friendly one-liner |
| `confidence` | Plan confidence (0.0–1.0) |
| `request` | Original user message |

## Risk model

| Level | Typical intents / signals | Confirmation |
|-------|---------------------------|--------------|
| `safe` | Check changes, summarize codebase | No |
| `low` | Run tests, read-only git | No |
| `medium` | Continue development, find fixes, prepare sprint | Yes |
| `high` | Deploy / push / production language | Yes |
| `critical` | Force push, destructive wipe language | Yes |

Confirmation here is a **plan flag**. Actual tool gates still apply inside Tool Execution Engine / PermissionManager when something is later executed.

## Brain API

```python
plan = brain.plan_development_workflow("Continue Titan development")

print(plan.goal)
print(plan.relevant_files)
print(plan.recommended_commands)
print(plan.test_plan)
print(plan.risk_level, plan.requires_confirmation)
print(plan.format_for_prompt())
```

`Brain` constructs `DeveloperWorkflow` with shared Workspace Awareness, Executive Function, Mission Manager, Memory, Context, and Tool Intelligence.

## Logging

On each plan, Developer Workflow logs:

- Intent, risk, confirmation flag
- File count and recommended tool ids
- Goal / reasoning at debug level

## Integration notes

- **Workspace Awareness** remains the source of filesystem/project context; Developer Workflow does not rescan independently beyond asking for a refresh/snapshot.
- **Executive Function** remains the source of mission attention; Developer Workflow never switches focus.
- **Tool Intelligence** may contribute tool ids; Developer Workflow may also add intent defaults (`terminal`, `python`, `github`, …).
- **Tool Execution Engine** is intentionally not invoked. Callers that want execution must take the plan, obtain approval, then use existing execution APIs.
- Existing tools (GitHub, Terminal, Python, Obsidian, Browser) are **recommended by id**, not reimplemented.

## Tests

```bash
pytest tests/test_developer_workflow.py -v
```

Coverage includes workspace-aware planning, relevant file detection, test recommendation, git-related requests, mission-related requests, risk classification, and Brain integration.

## Definition of Done

Titan can receive a development request and produce a structured, workspace-aware software development plan using existing tools — without executing anything automatically.

# Development Session Runtime V1

Development Session Runtime maintains a **persistent development session** while
Titan works on a feature — tracking progress across an entire coding session.

It is **not** an executor, **not** an auto-coder, and **not** a patch applier.

> Track only. Never execute tools. Never write repository files. Never apply patches.

## Architecture

```
Brain.start/update/pause/resume/end_development_session()
        ↓
DevelopmentSessionRuntime  (brain/development_session.py)
        ├── Mission Runtime      (mission_id / focus — read/link only)
        ├── Workspace Awareness  (opened modules / open files)
        ├── Developer Workflow   (plans → session.plans)
        ├── Project Intelligence (feature / module context)
        ├── Code Intelligence    (reviewed symbols/files)
        ├── Code Modification Planner (plans tracked, not applied)
        ├── Code Generation Engine   (patches tracked, not executed)
        ├── Memory               (optional session summary notes)
        └── Executive Function   (focus alignment — no mutation)
        ↓
DevelopmentSession → SessionSummary
```

### Reused components

| Component | Role |
|-----------|------|
| **Brain** | Public API: start / update / pause / resume / end / summarize |
| **Workspace Awareness** | Open modules / files merged into session context |
| **Executive Function** | Mission focus link on session start (read-only) |
| **Mission Runtime** | Optional `mission_id` association |
| **Developer Workflow** | Plans stored as advisory artifacts |
| **Code Modification Planner** | Plans stored; never applied |
| **Code Generation Engine** | Patches stored as proposals (`_applied: false`) |
| **Memory** | Optional short-term note on pause/end |
| **ContextManager** | Current user / active project defaults |

No second framework. No autonomous edits. No Tool Execution Engine calls.

## Responsibilities

| Does | Does not |
|------|----------|
| Track current feature | Write or patch code |
| Track opened modules / reviewed files | Run tools or shell commands |
| Track generated plans and patches | Apply `GeneratedPatch` diffs |
| Track completed / pending work | Mutate missions |
| Track decisions and rejected ideas | Call Tool Execution Engine |
| Persist session JSON | Self-modify Titan |
| Summarize today’s work | Invent missing facts |

## Output models

| Model | Role |
|-------|------|
| `DevelopmentSession` | Full session state (feature, files, plans, patches, tasks, decisions) |
| `SessionSummary` | Concise snapshot for “summarize today’s work” |
| `SessionDecision` | Recorded choice + rationale |
| `PendingTask` | Remaining work item |
| `CompletedTask` | Finished step |
| `SessionState` | `ACTIVE` \| `PAUSED` \| `ENDED` |

## Persistence

Sessions are stored in `data/development_sessions.json` (UTF-8 JSON via pathlib):

```json
{
  "schema_version": 1,
  "active_session_id": "...",
  "sessions": { "<id>": { "...": "..." } }
}
```

Override the path with `DevelopmentSessionRuntime(file_path=...)` (tests use `tmp_path`).

## Brain API

```python
session = brain.start_development_session(
    "Auth refactor",
    pending=["Audit auth", "Add tests"],
    open_modules=["brain", "core"],
)

brain.update_development_session(
    reviewed_files=["brain/brain.py"],
    plan=workflow_plan,          # or CodeModificationPlan / dict
    patch=generated_patch,       # stored only — never applied
    decision="Keep track-only policy",
    decision_rationale="No autonomous execution",
    complete_task="Audit auth",
)

summary = brain.summarize_development_session()
print(summary.format_for_prompt())

brain.pause_development_session()
brain.resume_development_session()   # latest paused, or pass session_id
brain.end_development_session()
```

### Optional auto-hooks (`record_to_session=True`)

| Brain call | Session update |
|------------|----------------|
| `plan_development_workflow(..., record_to_session=True)` | `update(plan=plan)` if session active |
| `plan_code_change(..., record_to_session=True)` | `update(plan=plan)` |
| `generate_code(..., record_to_session=True)` | `update(patch=patch)` — proposal only |
| `refresh_workspace(..., record_to_session=True)` | merge open files / modules |
| `explain_*` / `summarize_module(..., record_to_session=True)` | append path to `reviewed_files` |

Default is `False` so session state is never mutated by surprise.

## Example request mapping

| User | API |
|------|-----|
| "Continue yesterday's feature." | `resume_development_session()` → `summarize_development_session()` |
| "Summarize today's work." | `summarize_development_session()` |
| "What remains?" | `get_development_session().pending_tasks` / `summary.remaining` |
| "What decisions have we made?" | `session.decisions` |
| "Resume implementation." | `resume_development_session()` |

## Hard rules

1. **Track only** — plans and patches are advisory artifacts.
2. **Never execute** — no Tool Execution Engine, no shell, no git apply.
3. **Never write repo files** — persistence is limited to `data/development_sessions.json`.
4. **Never apply patches** — stored patches always carry `_applied: false`.
5. **Reuse Brain systems** — inject WA / EF / Mission / Memory / Context; do not duplicate them.

## Tests

```bash
pytest tests/test_development_session.py -v
```

Coverage includes lifecycle, pause/resume, summary, decisions, pending/completed,
persistence round-trip, Brain integration, and no-execution guarantees.

## Definition of Done

| Criterion | How |
|-----------|-----|
| Coherent session start→finish | Lifecycle + JSON persistence |
| No lost context | opened modules, reviewed files, plans, patches, tasks, decisions |
| No code execution | Runtime never calls Tool Execution Engine / never writes repo files |
| Reuses Brain systems | Injected WA / EF / Mission / Memory / Context; records DW / CMP / CGE artifacts |

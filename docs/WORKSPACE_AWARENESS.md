# Workspace Awareness V1

Workspace Awareness gives Titan a structured view of its **current development environment** before cognition begins.

It is **not** autonomous monitoring, **not** a filesystem watcher, and **not** a tool runner.

> Refresh only when the Brain asks. Provide context. Never execute.

## Architecture

```
Brain.get_workspace()
Brain.refresh_workspace()
Brain.generate_thoughts(message)
    ↓
WorkspaceAwareness.refresh()     ← explicit only
    ├── filesystem scan (once)
    ├── Mission Runtime (active missions)
    ├── MemoryService (optional project hints)
    └── ContextManager (active project)
    ↓
WorkspaceSnapshot
    ↓
ExecutiveFunction (mission relevance boost)
CognitiveLoop (workspace observations / thoughts)
```

### Reused components

| Component | Role |
|-----------|------|
| **Brain** | Public API: `get_workspace()`, `refresh_workspace()` |
| **Executive Function** | Uses snapshot for mission relevance / summary |
| **Cognitive Loop** | Observes workspace signals (`source=workspace`) |
| **Mission Runtime** | Supplies active mission summaries into the snapshot |
| **Memory** | Optional retrieval hints for the active project |
| **ContextManager** | Resolves `current_project` when not overridden |

No second runtime. No background threads. No tool execution.

## Responsibilities

| Does | Does not |
|------|----------|
| Collect workspace metadata on demand | Poll or watch the filesystem |
| Build a `WorkspaceSnapshot` | Execute tools |
| Correlate missions to related files | Mutate missions or memory |
| Emit advisory recommendations | Schedule autonomous work |
| Cache last snapshot until refresh | Create a parallel project store |

## `WorkspaceSnapshot` fields

| Field | Description |
|-------|-------------|
| `workspace_root` | Absolute path of the scanned root |
| `current_project` | Active project name (context / override / root) |
| `open_files` | Optional caller-provided open file list |
| `recently_modified_files` | Newest source/doc files under the project |
| `git_branch` | Current branch from `.git/HEAD` when available |
| `project_language` | Detected primary language (e.g. Python) |
| `detected_modules` | Top-level packages / modules |
| `documentation_files` | README / CHANGELOG / `docs/**/*.md` |
| `active_missions` | Compact Mission Runtime summaries |
| `timestamp` | UTC refresh time |
| `projects` | Detected nested projects (multi-project roots) |
| `recommendations` | Advisory signals (docs, modules, missions, …) |
| `summary` | One-line workspace summary for logs / prompts |
| `memory_hints` | Optional memory snippets for the project |

## Recommendations (advisory only)

| Kind | Meaning |
|------|---------|
| `documentation_changed` | Docs newer than code, or code significantly newer than docs |
| `new_modules` | Module directories touched recently |
| `missing_documentation` | Modules without matching documentation coverage |
| `large_unfinished_feature` | Many recent files under one module prefix |
| `mission_related_files` | Paths correlated with an active mission title/objective |

These are **context signals** for the Brain — they never trigger tools or writes.

## Brain API

```python
# Cached snapshot (refreshes once if empty)
snapshot = brain.get_workspace()

# Explicit rebuild — only path that rescans the workspace
snapshot = brain.refresh_workspace(open_files=["brain/brain.py"])

# Cognition path refreshes workspace once, then ranks missions
result = brain.generate_thoughts("What should I work on next?")
```

## Logging

On each refresh, Workspace Awareness logs:

- Workspace refresh (root, project, language, branch, counts)
- Detected project + modules
- Workspace summary line

## Integration notes

- **Mission Runtime** remains the source of truth for missions; Workspace Awareness only reads `list_active_missions()`.
- **Memory** is queried with a project-scoped hint string; failures are logged and ignored.
- **Tool Intelligence / Tool Execution Engine** are intentionally not called.
- Existing Phase 11 workspace *intelligence* tools (`context/workspace_map.py`, planners) remain for NL workspace *operations*. Workspace Awareness is the Brain-side *context* layer and does not replace them.

## Definition of Done

Titan can understand the current development workspace and provide structured contextual information to the Brain before cognition begins — with no background monitoring and no autonomous behavior.

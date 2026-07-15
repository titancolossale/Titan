# Project Intelligence V1

Project Intelligence gives Titan **architectural understanding of its own codebase**.

It is **not** a planner, **not** a refactor engine, and **not** a tool runner.

> Analyze only. Explain structure, ownership, dependencies, and change impact. Never modify code. Never execute tools.

## Architecture

```
Brain.analyze_project()
Brain.find_feature(name)
Brain.explain_module(name)
Brain.analyze_change_impact(target)
    ↓
WorkspaceAwareness.refresh()          ← structure / modules / missions
ExecutiveFunction.evaluate_missions()  ← optional focus signal
    ↓
ProjectIntelligence
    ├── WorkspaceSnapshot
    ├── context.workspace_map (folder / area ownership)
    ├── static import scan (AST) → DependencyGraph
    ├── feature catalog + path heuristics → FeatureLocation
    ├── Mission Runtime (active mission summaries, read-only)
    └── MemoryService (optional architecture hints)
    ↓
ArchitectureSummary | ModuleDescription | FeatureLocation | ImpactAnalysis
```

### Reused components

| Component | Role |
|-----------|------|
| **Brain** | Public API for architecture questions |
| **Workspace Awareness** | Detected modules, language, docs, missions |
| **Executive Function** | Mission focus signal on full project analysis |
| **Mission Runtime** | Active mission summaries (read-only) |
| **Memory** | Optional retrieval hints about architecture |
| **Developer Workflow** | Sibling Brain capability — planning stays there; Project Intelligence does not plan or execute |
| **Tool Intelligence** | **Not called** — no tool selection or execution |
| **context/workspace_map** | Curated area labels and key files |

No second planner. No autonomous edits. No shell/git execution.

## Responsibilities

| Does | Does not |
|------|----------|
| Map project structure and folder ownership | Rewrite architecture |
| Build a package dependency graph from imports | Create another planner |
| Locate feature ownership | Modify source files |
| Explain why a module exists | Execute tools automatically |
| Estimate change impact (advisory) | Mutate missions or memory |
| Summarize subsystem responsibilities | Watch the filesystem in the background |

## Output models

| Model | Purpose |
|-------|---------|
| `ArchitectureSummary` | Full project picture: modules, graph, pipeline, boundaries |
| `DependencyGraph` | Directed package edges + optional file→package edges |
| `FeatureLocation` | Primary/related files and owner module for a feature |
| `ImpactAnalysis` | Dependents, related features, risk, recommendations |
| `ModuleDescription` | Responsibility, deps, key files, boundary rules |

## Brain API

```python
summary = brain.analyze_project()
print(summary.summary)
print(summary.execution_pipeline)
print(summary.dependency_graph.format_for_prompt())

auth = brain.find_feature("authentication")
print(auth.primary_files)  # e.g. api/auth.py

mission = brain.explain_module("Mission Runtime")
print(mission.responsibility)
print(mission.depends_on, mission.depended_on_by)

impact = brain.analyze_change_impact("ToolManager")
# or: brain.analyze_change_impact("tools/tool_manager.py")
print(impact.risk_level, impact.direct_dependents)
```

### Example questions this answers

| Question | API |
|----------|-----|
| Where is authentication implemented? | `find_feature("authentication")` |
| What happens if I modify ToolManager? | `analyze_change_impact("ToolManager")` |
| Which modules depend on Memory? | `explain_module("memory").depended_on_by` or graph |
| Explain Mission Runtime. | `explain_module("Mission Runtime")` |
| Which files implement Browser Tool? | `find_feature("browser")` |
| What is the execution pipeline? | `analyze_project().execution_pipeline` |

## Feature catalog

Curated entries cover high-value Titan capabilities (auth, ToolManager, Memory, Mission Runtime, Browser, execution pipeline, Workspace Awareness, Developer Workflow, Executive Function, Tool Intelligence, Obsidian, Cognitive Loop, Project Intelligence). Unknown names fall back to `workspace_map` areas and path-token heuristics.

## Dependency & boundary detection

- Scans Python files under the workspace (AST `import` / `from … import`).
- Collapses imports to top-level packages (`brain`, `core`, `memory`, `agents`, `tools`, …).
- Flags edges that conflict with rulebook dependency direction (e.g. `memory → brain`) as **boundary notes** — informational only.

## Impact analysis

Advisory blast-radius estimate:

1. Resolve target as **file** or **module**
2. Collect direct dependents (importers / package dependents)
3. Map related features from the catalog
4. Assign `low` / `medium` / `high` risk
5. Emit recommendations (tests, invariants, docs) — **never executes them**

## Logging

On analysis, Project Intelligence logs:

- Project name, module count, edge count, mission count
- Feature lookup hits
- Module explanations
- Impact target / risk / dependent count

## Definition of Done

Titan can explain its own architecture, locate features, understand dependencies, and estimate change impact **without executing or modifying anything**.

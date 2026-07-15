# Code Intelligence V1

Code Intelligence gives Titan **semantic understanding of Python source code**.

It is **not** a refactor engine, **not** an executor, and **not** a second architecture layer.

> Analyze only. Explain functions and classes, locate symbols, map calls, and flag unused candidates. Never modify files. Never execute code.

## Architecture

```
Brain.explain_function(name)
Brain.explain_class(name)
Brain.find_symbol(name)
Brain.find_callers(name)
Brain.find_unused_candidates()
Brain.summarize_module(module)
    ↓
WorkspaceAwareness          ← project root / modules
ProjectIntelligence         ← optional package-level fallback
ExecutiveFunction           ← mission focus signal on summaries
Mission Runtime             ← active mission context (read-only)
MemoryService               ← optional retrieval hints
    ↓
CodeIntelligence
    └── AST index (functions, classes, imports, inheritance, calls)
    ↓
FunctionSummary | ClassSummary | ModuleSummary
CallGraph | SymbolLocation | UnusedCandidate
```

### Reused components

| Component | Role |
|-----------|------|
| **Brain** | Public API for code questions |
| **Workspace Awareness** | Workspace root and module detection |
| **Project Intelligence** | Sibling — package/architecture; used as fallback for unknown module paths |
| **Developer Workflow** | May resolve symbol tokens to relevant files when planning (still plan-only) |
| **Executive Function** | Mission focus string on module summaries |
| **Mission Runtime** | Active mission context (read-only) |
| **Memory** | Optional hints when summarizing modules |
| **Tool Intelligence / Tool Execution** | **Not called** — no tool selection or execution |

No file writes. No `exec` / importlib loading of analyzed modules. No mission mutations.

## Responsibilities

| Does | Does not |
|------|----------|
| Parse Python with `ast` | Execute analyzed code |
| Explain functions and methods | Rewrite or patch source |
| Explain classes and inheritance | Create a parallel Brain pipeline |
| Build static call relationships | Run tools or shell commands |
| Locate symbol definitions | Mutate missions or memory |
| Summarize modules | Watch the filesystem in the background |
| Flag unused-code **candidates** | Prove dead code with certainty |
| Estimate modification impact from callers | Apply refactors |

## Output models

| Model | Purpose |
|-------|---------|
| `FunctionSummary` | Signature, purpose, calls, callers, impact |
| `ClassSummary` | Bases, methods, purpose, references, impact |
| `ModuleSummary` | Imports, classes, functions, inheritance, purpose |
| `CallGraph` | Root symbol, caller locations, callees, edges |
| `SymbolLocation` | Name, kind, file, line, qualified name |
| `UnusedCandidate` | Heuristic unused definition with confidence |

## Brain API

```python
fn = brain.explain_function("execute_request")
print(fn.purpose, fn.called_by)

cls = brain.explain_class("ToolManager")
print(cls.methods, cls.modification_impact)

locs = brain.find_symbol("ToolExecutionPlan")
for loc in locs:
    print(loc.format_for_prompt())

graph = brain.find_callers("execute")
print(graph.summary)

unused = brain.find_unused_candidates()
for item in unused[:10]:
    print(item.format_for_prompt())

mod = brain.summarize_module("project_intelligence.py")
# or: brain.summarize_module("brain/project_intelligence.py")
print(mod.purpose, mod.classes)
```

### Example questions this answers

| Question | API |
|----------|-----|
| Explain ToolManager. | `explain_class("ToolManager")` |
| What does execute_request() do? | `explain_function("execute_request")` |
| Where is ToolExecutionPlan used? | `find_symbol("ToolExecutionPlan")` + `find_callers(...)` |
| Find every call to execute(). | `find_callers("execute")` |
| Explain Brain.think(). | `explain_function("Brain.think")` |
| Summarize project_intelligence.py. | `summarize_module("project_intelligence.py")` |

## How analysis works

1. **Index** — walk `*.py` under the workspace (ignore venv/cache/data), parse with AST.
2. **Definitions** — record classes, functions, methods, signatures, docstrings, decorators.
3. **Imports & inheritance** — store import paths and base classes.
4. **Calls** — collect `ast.Call` targets inside each function body (static names only).
5. **Query** — resolve `Name`, `Class.method`, or dotted module paths against the index.

Modification impact is derived from static caller counts (`low` / `medium` / `high` / `unknown`).

Unused detection is **heuristic**: private helpers with no callers score higher; public API surfaces may appear unused to a static graph and must be verified before removal.

## Relationship to Project Intelligence

| Layer | Question |
|-------|----------|
| **Project Intelligence** | Where does authentication live? What depends on `memory/`? |
| **Code Intelligence** | What does `Brain.think()` do? Who calls `execute()`? |

Use both: architecture first, then symbols.

## Logging

On analysis, Code Intelligence logs:

- Index build (file / function / class counts)
- Function and class explanations
- Symbol lookup match counts
- Call graph caller/callee counts
- Unused candidate counts
- Module summaries

## Definition of Done

Titan can explain its own codebase at the **function/class level** without modifying or executing anything.

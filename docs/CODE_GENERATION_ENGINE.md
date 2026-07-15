# Code Generation Engine V1

Code Generation Engine turns an **approved** `CodeModificationPlan` into
implementation-ready **patch proposals**.

It is **not** an auto-applier, **not** a git client, and **not** an executor.

> Generate patches only. Never write files. Never execute. Never commit. Never push.

## Architecture

```
Brain.plan_code_change(request)          ← Code Modification Planner
    ↓
CodeModificationPlan (approve via with_approval())
    ↓
Brain.generate_code(plan)
    ↓
WorkspaceAwareness.refresh()
ExecutiveFunction.evaluate_missions()
    ↓
CodeGenerationEngine.generate(plan)
    ├── CodeModificationPlan (approved)
    ├── Workspace / project root (read-only baselines)
    ├── Code Intelligence (optional symbol enrichment)
    ├── Project Intelligence / Developer Workflow (context signals)
    └── Mission Runtime / Memory (read-only sources metadata)
    ↓
GeneratedPatch
    ├── GeneratedFile[]      (new file proposals)
    ├── GeneratedEdit[]      (edits + unified diffs)
    ├── ReviewItem[]         (manual review checkpoints)
    ├── GenerationSummary
    └── unified_diff_bundle
```

### Reused components

| Component | Role |
|-----------|------|
| **Code Modification Planner** | Supplies the approved plan Titan generates from |
| **Code Intelligence** | Optional symbol hints on edited modules |
| **Project Intelligence** | Architectural placement signals (via planner / sources) |
| **Developer Workflow** | Sibling development planning — not executed here |
| **Workspace Awareness** | Project root and workspace snapshot (read baselines only) |
| **Executive Function** | Mission focus metadata on the generation run |
| **Mission Runtime** | Read-only mission context in `sources` |
| **Memory** | Optional contextual signal (no writes) |
| **Patch preview helpers** | `tools.decision.patch_preview` for unified diffs |

No filesystem mutation. No Tool Execution Engine call during generation.
Application is a separate confirmed path — see
`docs/CONTROLLED_PATCH_APPLICATION.md`.

## Responsibilities

| Does | Does not |
|------|----------|
| Generate new-file proposals | Write or delete repository files |
| Generate edits + unified diffs | Apply patches |
| Attach rationale per change | Execute generated code |
| Estimate confidence | Commit or push |
| Identify manual review points | Bypass plan approval (default) |
| Bundle a full diff for review | Call Tool Execution Engine |

## Output models

| Model | Purpose |
|-------|---------|
| `GeneratedFile` | Path, full proposed content, rationale, confidence |
| `GeneratedEdit` | Original vs proposed, unified diff, symbols, rationale |
| `ReviewItem` | Severity + message for human review |
| `GenerationSummary` | Counts, risk/complexity echo, review required flag |
| `GeneratedPatch` | Top-level proposal bundle returned by Brain |

## Approval rule

By default the engine **rejects** unapproved plans and returns an empty
`GeneratedPatch` with a critical `ReviewItem`.

```python
plan = brain.plan_code_change("Add Discord integration.")
approved = plan.with_approval()
patch = brain.generate_code(approved)
```

`force=True` on `CodeGenerationEngine.generate` is reserved for explicit dry-run
tests — Brain's public `generate_code` does not expose it.

## Example requests

| Request (via planner) | Typical proposals |
|-----------------------|-------------------|
| Generate TradingView connector | Edits under `tools/connectors/tradingview_*` + review for no live trading |
| Generate Browser Tool improvement | Edits under `core/tools/browser/` with refactor markers |
| Refactor ToolManager | Edit hints on `tools/tool_manager.py` + importer review items |
| Implement Discord integration | New `tools/discord_tool.py`, ToolManager registration edit, tests, `.env.example` |

## Brain API

```python
plan = brain.plan_code_change("Implement Discord integration.")
patch = brain.generate_code(plan.with_approval())

print(patch.summary.files_created, patch.summary.files_edited)
print(patch.confidence)
print(patch.unified_diff_bundle[:500])
for item in patch.review_items:
    print(item.severity, item.message)
print(patch.format_for_prompt())
```

## Hard rules

1. **Never write files** — proposals live in memory only.
2. **Never execute** generated code.
3. **Never commit / push**.
4. **Only return** `GeneratedPatch` (and nested models).
5. Application, if ever enabled, remains a **separate** confirmed path
   (existing Phase 12 patch application stack) — not this engine.

## Logging

Each generation logs created/edited counts, review count, confidence, and
approval state at INFO.

## Tests

See `tests/test_code_generation_engine.py`:

- single-file generation
- multi-file generation
- edit generation
- new-file generation
- review generation
- brain integration
- repository unchanged after generation

# Controlled Patch Application V1

Controlled Patch Application lets Titan **validate**, **preview**, **apply**, and
**rollback** a previously generated `GeneratedPatch` against the local
repository — only after explicit human approval.

> No silent modification. No automatic commits. No pushes. No autonomous approval.

## Architecture

```
CodeModificationPlanner → CodeModificationPlan.with_approval()
        ↓
CodeGenerationEngine → GeneratedPatch
        ↓
GeneratedPatch.with_approval()          ← human approves the proposal
        ↓
Brain.validate_generated_patch()        ← CodeEditorTool.validate_patch
Brain.preview_generated_patch()         ← CodeEditorTool.preview_patch
Brain.apply_generated_patch(confirmed=True)
        ↓
PatchValidator → PatchApplier
        ↓
.titan/backups/<transaction_id>/        ← backups + manifest
        ↓
Brain.rollback_patch(transaction_id, confirmed=True)
```

### Package layout

| Module | Role |
|--------|------|
| `core/tools/code_editor/code_editor_tool.py` | Core `BaseTool` + Brain-facing API |
| `core/tools/code_editor/patch_validator.py` | Diff / path / hash / conflict checks |
| `core/tools/code_editor/patch_applier.py` | Atomic apply + rollback |
| `core/tools/code_editor/models.py` | Serializable result models |
| `core/tools/code_editor/exceptions.py` | Typed failures |

### Reused systems

| System | Role |
|--------|------|
| Code Generation Engine | Supplies `GeneratedPatch` proposals |
| Development Session Runtime | Optional recording of validation / apply / rollback |
| Permission Manager | `SAFE` / `CONFIRMATION_REQUIRED` gates |
| Action Framework | Tool actions + dispatcher |
| `tools.decision.patch_utils` | Unified diff apply + binary detection |
| `tools.path_guard` | Workspace path containment |
| Workspace Awareness / Project root | Target repository root |

Does **not** create a second planner, generator, Brain, or session runtime.

## Approval workflow

1. Plan a change: `brain.plan_code_change(...)`
2. Approve the plan: `plan.with_approval()`
3. Generate a proposal: `brain.generate_code(plan)` → `GeneratedPatch`
4. Human reviews the proposal
5. Approve the patch: `patch = patch.with_approval()`
6. Validate / preview (safe, no mutation)
7. Apply only with `confirmed=True`
8. Optionally rollback with `confirmed=True`

`apply_patch` rejects when any of the following is true:

- `GeneratedPatch.approved` is false
- `confirmed` is false
- permission is denied
- validation fails (malformed diff, path escape, stale hash, binary, conflict)
- workspace root does not match the generation workspace

## Permissions

| Permission | Action | Level |
|------------|--------|-------|
| `code_editor.validate` | `validate_patch` | SAFE |
| `code_editor.preview` | `preview_patch` | SAFE |
| `code_editor.apply` | `apply_patch` | CONFIRMATION_REQUIRED |
| `code_editor.rollback` | `rollback_patch` | CONFIRMATION_REQUIRED |

`CONFIRMATION_REQUIRED` actions also require the explicit `confirmed=True`
argument on the Brain / tool API. ActionDispatcher still blocks apply/rollback
until a higher-level SAFE override is granted.

## Validation rules

Before apply, `PatchValidator` checks:

1. Unified diff syntax (non-empty, recognizable ops / hunks)
2. Every target path stays inside the configured workspace (`path_guard`)
3. Source-file SHA-256 hashes still match generation baselines
4. Conflicts (missing targets, existing create targets, hash mismatch)
5. Binary / secret paths are rejected
6. Structured report of creates / modifies / deletes / renames

Validation never mutates the repository.

## Preview behavior

`preview_patch` returns:

- affected files
- additions / deletions
- new / removed / renamed files
- conflict warnings
- risk level
- human-readable change summary

Preview never writes files.

## Backups and rollback

Before any successful apply path mutates files:

1. Create `.titan/backups/<transaction_id>/`
2. Copy every existing affected file into the transaction folder
3. Write `manifest.json` (paths, hashes, status — **never** source contents or secrets)

On mid-apply failure:

- stop immediately
- restore already-modified files from backups
- remove files created in this transaction
- mark the transaction `failed`

`rollback_patch(transaction_id, confirmed=True)` restores the exact
pre-application state from the manifest and marks the transaction
`rolled_back`.

`.titan/` is gitignored.

## Transaction lifecycle

```
pending → applied
       ↘ failed (auto-restored)
applied → rolled_back
failed  → rolled_back (optional explicit restore)
```

## Brain API examples

```python
plan = brain.plan_code_change("Add helper module")
patch = brain.generate_code(plan.with_approval())

# Human review...
patch = patch.with_approval()

validation = brain.validate_generated_patch(patch)
preview = brain.preview_generated_patch(patch)

# Explicit confirmation required
result = brain.apply_generated_patch(
    patch,
    confirmed=True,
    record_to_session=True,
)

# Restore if needed
brain.rollback_patch(
    result.transaction_id,
    confirmed=True,
    record_to_session=True,
)
```

## Development Session recording

When `record_to_session=True` and a session is active:

- validation / preview / application / rollback records are stored
- approval and transaction id are recorded
- affected files are added to reviewed files
- completed / pending tasks are updated
- the session is **not** ended automatically

## Security boundaries

| Allowed | Forbidden |
|---------|-----------|
| Apply approved patches inside workspace | Silent apply |
| Explicit `confirmed=True` | Autonomous approval |
| Timestamped local backups | Commits / pushes |
| Path containment + secret path block | Escaping the workspace |
| Structured audit logs (paths, ids, status) | Logging source code or secrets |

## Output models

All serializable via `to_dict()`:

- `PatchValidationResult`
- `PatchPreview`
- `PatchTransaction`
- `PatchApplicationResult`
- `PatchRollbackResult`
- `AffectedFileChange`

## Tests

`tests/test_controlled_patch_application.py` covers validation, rejection
paths, preview, multi-file apply, new-file creation, rollback, partial-failure
restore, session recording, and Brain facades — using temporary repositories only.

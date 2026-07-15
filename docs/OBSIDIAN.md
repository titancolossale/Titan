# Titan Obsidian Connector — Architecture

The core Obsidian integration lives in `core/tools/obsidian/` and exposes bounded read/write access to the user's **existing** Obsidian vault through the Action Framework.

Obsidian is the user's personal note space — not Titan memory. Titan must never create a new vault during setup.

## Layered Architecture

```
core/tools/obsidian/obsidian_tool.py     ← BaseTool facade + Action registration
    ├── obsidian_client.py               ← Filesystem vault client (read/write)
    ├── obsidian_config.py               ← Vault path, extensions, exclusions
    ├── vault_helpers.py                 ← Backups, text editing, path helpers
    ├── models.py                        ← NoteContent, NoteMetadata
    └── exceptions.py                    ← Vault-specific errors

core/actions/                            ← ActionRegistry + ActionDispatcher
core/permissions/                        ← PermissionManager + policy levels
```

## Orchestration Path

```
ActionDispatcher
  → PermissionManager.check_permission(action.permission_id)
  → ObsidianTool.execute_action(action_id, **params)
  → ObsidianClient (filesystem)
```

Legacy callers may still use `ObsidianTool.execute(action=...)` which performs permission checks before delegating to `execute_action`.

## Registered Actions

| Action | Permission | Default Level |
|--------|------------|---------------|
| `read_note` | `obsidian.read_note` | SAFE |
| `list_notes` | `obsidian.list_notes` | SAFE |
| `list_folders` | `obsidian.list_folders` | SAFE |
| `metadata` | `obsidian.read_note` | SAFE |
| `create_note` | `obsidian.create_note` | CONFIRMATION_REQUIRED |
| `edit_note` | `obsidian.edit_note` | CONFIRMATION_REQUIRED |
| `append_note` | `obsidian.edit_note` | CONFIRMATION_REQUIRED |
| `replace_note` | `obsidian.edit_note` | CONFIRMATION_REQUIRED |
| `delete_note` | `obsidian.delete_note` | BLOCKED |
| `rename_note` | `obsidian.edit_note` | CONFIRMATION_REQUIRED |
| `move_note` | `obsidian.edit_note` | CONFIRMATION_REQUIRED |
| `create_folder` | `obsidian.manage_folders` | CONFIRMATION_REQUIRED |
| `delete_folder` | `obsidian.delete_folder` | BLOCKED |

Each action returns an `ActionResult` with a JSON-serializable `data` payload.

## Write Operations

### Create

```python
dispatcher.dispatch("obsidian", "create_note", {
    "path": "projects/new-idea.md",
    "content": "# New Idea\n",
})
```

### Edit modes

| Action | Behavior |
|--------|----------|
| `edit_note` | Overwrite full note body (backup created) |
| `append_note` | Append content to existing body |
| `replace_note` | Replace first occurrence of `search` with `replacement` (backup created) |

### Destructive operations

`delete_note`, `replace_note`, `rename_note`, and `move_note` create a timestamped backup under `.vault_backups/` before mutating vault content.

Backup filenames use UTC timestamps and flatten the original relative path:

```
.vault_backups/20260707T061500Z__projects__alpha.md
```

`.vault_backups/` is excluded from normal folder and note listing.

## Safety Rules

The client rejects:

- Empty paths
- Absolute paths
- `..` traversal segments
- Paths resolving outside the vault root
- Symbolic links pointing outside the vault
- Writes to excluded folders (`.obsidian`, `.trash`, `.git`, `.vault_backups`)

## Configuration

Vault path is configured through `ObsidianConfig`:

```python
ObsidianConfig.for_vault("/path/to/existing/vault")
ObsidianConfig.from_environment()  # uses TITAN_OBSIDIAN_VAULT_PATH
```

Default development vault: `sample_vault/` at project root.

## Testing

```bash
pytest tests/test_core_obsidian_tool.py tests/test_obsidian_write_operations.py tests/test_action_framework.py -v
```

Write tests use isolated temporary vaults. Permission-denied scenarios use `PermissionLevel.BLOCKED`.

## Related Production Stack

`tools/obsidian_tool.py` and `tools/connectors/obsidian_connector.py` remain the Brain/ToolManager production path with advanced features (search, patch modes, backlinks, vault health). The core stack documented here is the Action Framework integration target for consolidation.

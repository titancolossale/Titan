# Titan Python Runtime V1 — Sandboxed Execution (Core Tools)

Python Runtime V1 is Titan's **production sandboxed Python execution tool** in the `core/tools/` framework. It runs snippets and scripts inside an isolated working directory and returns structured results — it is **not** part of the Brain and never executes autonomously.

## Scope (V1)

**Implemented:**

| Action | Permission | Description |
|--------|------------|-------------|
| `run_snippet` | `python.execute` | Execute Python source in an isolated workspace |
| `run_script` | `python.execute` | Execute a workspace-relative `.py` file |
| `syntax_check` | `python.syntax_check` | Validate syntax without execution |
| `format_code` | `python.format` | Normalize whitespace / trailing newlines (no exec) |

**Captured on every execution:**

- `stdout`
- `stderr`
- `exit_code`
- `duration`
- `files_created`
- `success`

**Limits:**

| Limit | Default | Env var |
|-------|---------|---------|
| Execution timeout | 5s | `TITAN_PYTHON_RUNTIME_TIMEOUT_SECONDS` |
| Max execution ceiling | 5s | `TITAN_PYTHON_RUNTIME_MAX_EXECUTION_SECONDS` |
| Max output size | 64 KiB | `TITAN_PYTHON_RUNTIME_MAX_OUTPUT_BYTES` |
| Max workspace files | 50 | `TITAN_PYTHON_RUNTIME_MAX_FILE_COUNT` |

**Never allowed (V1):**

- Network access (`socket`, `urllib`, `requests`, …)
- Arbitrary shell execution (`subprocess`, `os.system`, …)
- System modification outside the isolated workspace
- Path traversal for `run_script`

**Deferred:**

- Package installation
- Persistent multi-session REPLs
- GPU / native extensions
- Full AST-based sandboxing beyond static import/call blocks

## Architecture

```
core/tools/python/
├── python_tool.py      ← BaseTool facade (actions + permissions)
├── python_client.py    ← Subprocess runner + static safety checks
├── python_config.py    ← Timeout, output, file-count limits
├── models.py           ← ExecutionResult, SyntaxCheckResult, FormatResult
└── exceptions.py       ← Domain errors
```

### Integration with existing frameworks

```
ToolIntelligence.plan()
  → ToolExecutionEngine.execute(plan)
    → ActionDispatcher.dispatch(tool_id, action_id)
      → PermissionManager.check_permission(...)
      → PythonTool.execute_action()
        → PythonRuntimeClient (isolated cwd + limits)
```

- **Tool Registry** — `ToolLoader` auto-discovers `PythonTool` from `core/tools/python/`
- **Action Framework** — each operation is an `Action` returning `ActionResult`
- **Permission Manager** — three permission IDs gate execute / format / syntax
- **Tool Execution Engine** — sole Brain-facing execution path (no Brain duplication)

Python Runtime V1 is separate from the legacy Phase 6 tool in `tools/python_exec_tool.py`. That stack remains for Tool Runtime V2 / orchestrator compatibility; this core tool is the Action Framework production path.

## Permission Model

| Permission ID | Level | Actions |
|---------------|-------|---------|
| `python.execute` | CONFIRMATION_REQUIRED | `run_snippet`, `run_script` |
| `python.format` | SAFE | `format_code` |
| `python.syntax_check` | SAFE | `syntax_check` |

Permissions are registered idempotently when `PythonTool` is instantiated.

`CONFIRMATION_REQUIRED` means `ActionDispatcher` denies execution until a higher-level confirmation flow grants a SAFE override (same pattern as Obsidian writes). There is **no autonomous execution**.

## Isolation & Safety

Each run:

1. Uses an isolated `workspace_root` as `cwd`
2. Builds a minimal environment (no API keys / Titan secrets forwarded)
3. Applies a hard timeout
4. Truncates oversized stdout/stderr
5. Diffs the workspace to report `files_created`
6. Rejects blocked imports/calls via static AST checks before launch

Script paths for `run_script` must resolve inside the workspace — `../` escapes are rejected.

## ActionResult Shape

Successful `run_snippet` / `run_script` data:

```json
{
  "action": "run_snippet",
  "success": true,
  "stdout": "hello\n",
  "stderr": "",
  "exit_code": 0,
  "duration": 0.042,
  "files_created": [],
  "timed_out": false,
  "truncated": false,
  "message": "Python action 'run_snippet' completed successfully.",
  "errors": []
}
```

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_PYTHON_RUNTIME_TIMEOUT_SECONDS` | `5` | Default per-run timeout |
| `TITAN_PYTHON_RUNTIME_MAX_EXECUTION_SECONDS` | same as timeout | Hard ceiling for requested timeouts |
| `TITAN_PYTHON_RUNTIME_MAX_OUTPUT_BYTES` | `65536` | Combined stdout/stderr budget |
| `TITAN_PYTHON_RUNTIME_MAX_FILE_COUNT` | `50` | Max files allowed in workspace |
| `TITAN_PYTHON_RUNTIME_WORKSPACE` | system temp `/titan_python_runtime` | Isolated working directory |
| `TITAN_TOOL_PYTHON_TIMEOUT` | `5` | Legacy fallback used when runtime timeout unset |

Programmatic configuration:

```python
from core.tools.python import PythonRuntimeConfig, PythonTool

config = PythonRuntimeConfig.for_workspace(
    "/tmp/titan_py",
    timeout_seconds=3.0,
    max_output_bytes=32_768,
)
tool = PythonTool(config=config)
result = tool.execute_action("run_snippet", code="print(1 + 1)")
```

## Action Dispatch Example

```python
from core.actions import ActionDispatcher, ActionRegistry
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools import ToolRegistry
from core.tools.python import PERMISSION_EXECUTE, PythonTool

permission_manager = PermissionManager()
permission_manager.register_permission(
    Permission(
        id=PERMISSION_EXECUTE,
        name="Execute Python",
        description="Allowed for this example.",
        level=PermissionLevel.SAFE,
    )
)
action_registry = ActionRegistry()
tool_registry = ToolRegistry()

tool = PythonTool(
    permission_manager=permission_manager,
    action_registry=action_registry,
)
tool_registry.register_tool(tool)

dispatcher = ActionDispatcher(
    tool_registry=tool_registry,
    action_registry=action_registry,
    permission_manager=permission_manager,
)

result = dispatcher.dispatch(
    "python",
    "run_snippet",
    {"code": "print('ok')"},
)
```

## Logging

Every execution logs:

- Start: timeout, workspace, code length (not full secrets)
- Completion: exit code, duration, files created, truncation / timeout flags
- Failures: error message and stderr size (never API keys)

## Tests

```bash
pytest tests/test_core_python_runtime_tool.py -v
```

Coverage includes: successful execution, syntax error, timeout, permission denied, confirmation required, output capture, file generation, path escape rejection, network/shell blocks, ToolLoader discovery, ToolExecutionEngine integration, and core runtime bootstrap.

## Related Documentation

- Tool Execution Engine: `docs/TOOL_EXECUTION.md`
- Tool Intelligence: `docs/TOOL_INTELLIGENCE.md`
- Legacy Python exec (Phase 6): `tools/python_exec_tool.py`
- Core tool loader: `core/tools/tool_loader.py`

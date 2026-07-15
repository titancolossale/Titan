# Titan Terminal Tool V1 — Controlled Workspace Shell

Terminal Tool V1 gives Titan **controlled access to the local development terminal**. It is a production tool in the `core/tools/` framework — **not** part of the Brain — and never grants unrestricted shell access.

## Scope (V1)

**Implemented actions:**

| Action | Permission | Description |
|--------|------------|-------------|
| `run_command` | `terminal.execute` | Run an allowlisted shell command in the workspace |
| `run_python` | `terminal.execute` | Run the Python interpreter with arguments |
| `run_git` | `terminal.git` | Run git in the project workspace |
| `run_pytest` | `terminal.testing` | Run pytest with optional args |
| `run_npm` | `terminal.execute` | Run npm with required args |
| `run_uv` | `terminal.execute` | Run uv with required args |

**Captured on every execution:**

- `stdout`
- `stderr`
- `exit_code`
- `duration`
- `command`
- `cwd`
- `success`

**Limits:**

| Limit | Default | Env var |
|-------|---------|---------|
| Execution timeout | 30s | `TITAN_TERMINAL_TIMEOUT_SECONDS` |
| Max execution ceiling | 120s | `TITAN_TERMINAL_MAX_EXECUTION_SECONDS` |
| Max output size | 64 KiB | `TITAN_TERMINAL_MAX_OUTPUT_BYTES` |
| Workspace | `PROJECT_ROOT` | `TITAN_TERMINAL_WORKSPACE` |

**Blocked by default (examples):**

- `rm -rf`, `del /f`, destructive deletes
- `shutdown`, `reboot`
- `mkfs`, `diskpart`, `format`
- `sudo` / `su`
- PowerShell execution-policy changes (`Set-ExecutionPolicy`, encoded payloads)
- Shell metacharacters (`|`, `&`, `;`, `>`, `` ` ``, …) — no chaining or redirection
- Commands outside the allowlist
- Working directories outside the configured workspace

**Deferred (future versions):**

- Interactive terminal sessions
- Background / long-running process management
- Arbitrary shell with user-approved elevated mode
- Streaming PTY output

## Architecture

```
core/tools/terminal/
├── terminal_tool.py      ← BaseTool facade (actions + permissions)
├── terminal_client.py    ← Subprocess runner + security gates
├── terminal_config.py    ← Workspace, timeout, allow/block lists
├── models.py             ← CommandResult
└── exceptions.py         ← Domain errors
```

### Integration with existing frameworks

```
ToolIntelligence.plan()
  → ToolExecutionEngine.execute(plan)
    → ActionDispatcher.dispatch(tool_id, action_id)
      → PermissionManager.check_permission(...)
      → TerminalTool.execute_action()
        → TerminalClient (workspace cwd + allowlist + limits)
```

- **Tool Registry** — `ToolLoader` auto-discovers `TerminalTool` from `core/tools/terminal/`
- **Action Framework** — each operation is an `Action` returning `ActionResult`
- **Permission Manager** — three permission IDs gate execute / git / testing
- **Tool Intelligence** — routes phrases like "Run pytest", "Show git status", "Run uv sync"
- **Tool Execution Engine** — sole Brain-facing execution path (no Brain duplication)
- **Mission Runtime** — unchanged; Terminal is invoked like any other core tool

## Permission Model

| Permission ID | Level | Actions |
|---------------|-------|---------|
| `terminal.execute` | CONFIRMATION_REQUIRED | `run_command`, `run_python`, `run_npm`, `run_uv` |
| `terminal.git` | CONFIRMATION_REQUIRED | `run_git` |
| `terminal.testing` | CONFIRMATION_REQUIRED | `run_pytest` |

Permissions are registered idempotently when `TerminalTool` is instantiated.

`CONFIRMATION_REQUIRED` means `ActionDispatcher` denies execution until a higher-level confirmation flow grants a SAFE override. There is **no autonomous unrestricted shell**.

## Security Model

Each run:

1. Uses the configured `workspace_root` as `cwd` (default: Titan project root)
2. Rejects `cwd` / path arguments that escape the workspace
3. Validates the first command token against an allowlist
4. Rejects blocked command names and dangerous substrings
5. Rejects shell metacharacters (no pipes, chaining, or redirection)
6. Runs with `shell=False` (argv list only)
7. Builds a minimal environment (no API keys / Titan secrets forwarded)
8. Applies a hard timeout
9. Truncates oversized stdout/stderr
10. Logs command, duration, exit code, and errors

### Default allowlist (first token)

`git`, `pytest`, `python`, `python3`, `py`, `npm`, `npx`, `uv`, `pip`, `pip3`, `node`, plus a few read-only helpers (`echo`, `dir`, `ls`, `type`, `cat`, `where`, `which`, `pwd`).

Override via `TITAN_TERMINAL_ALLOWED_COMMANDS` (comma-separated).

## ActionResult Shape

Successful `run_git` / `run_pytest` / `run_command` data:

```json
{
  "action": "run_git",
  "success": true,
  "stdout": "On branch main\nnothing to commit\n",
  "stderr": "",
  "exit_code": 0,
  "duration": 0.084,
  "command": "git status",
  "cwd": "C:/Users/.../Titan",
  "timed_out": false,
  "truncated": false,
  "message": "Terminal action 'run_git' completed successfully.",
  "errors": []
}
```

## Natural Language Examples

| User request | Tool | Action |
|--------------|------|--------|
| "Run pytest" | Terminal | `run_pytest` |
| "Show git status" | Terminal | `run_git` (`args=status`) |
| "Run uv sync" | Terminal | `run_uv` (`args=sync`) |
| "Run npm test" | Terminal | `run_npm` (`args=test`) |

Local git / pytest / npm / uv requests prefer Terminal over GitHub API or the sandboxed Python Runtime.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_TERMINAL_WORKSPACE` | Project root | Working directory root |
| `TITAN_TERMINAL_TIMEOUT_SECONDS` | `30` | Soft timeout |
| `TITAN_TERMINAL_MAX_EXECUTION_SECONDS` | `120` | Hard timeout ceiling |
| `TITAN_TERMINAL_MAX_OUTPUT_BYTES` | `65536` | stdout/stderr cap |
| `TITAN_TERMINAL_ALLOWED_COMMANDS` | (built-in) | Optional allowlist override |
| `TITAN_TERMINAL_BLOCKED_PATTERNS` | (built-in) | Optional blocked substring override |

## Logging

Every invocation logs:

- Command string
- Duration
- Exit code
- Timeout / truncation flags
- Errors (security blocks, non-zero exits)

Secrets are never forwarded into the subprocess environment.

## Testing

```bash
pytest tests/test_core_terminal_tool.py -v
```

Coverage includes:

- Allowed command
- Blocked command
- Git command
- Pytest
- Permission denied / confirmation required
- Timeout
- Output capture
- Brain integration via `ToolExecutionEngine` (no Brain architecture changes)
- Tool Intelligence routing for pytest / git status / uv sync

## Distinction: Terminal vs Python Runtime

| Concern | Python Runtime | Terminal Tool |
|---------|----------------|---------------|
| Purpose | Sandboxed snippets/scripts | Dev CLI (git, pytest, npm, uv) |
| Workspace | Isolated temp sandbox | Project workspace |
| `subprocess` in user code | Blocked | Used by the client |
| Category | `runtime` | `shell` |
| Confirmation | `python.execute` | `terminal.execute` / `.git` / `.testing` |

## Definition of Done

Titan can safely execute approved terminal commands through the Tool Runtime with permission enforcement and structured `ActionResult`s.

- No unrestricted shell access
- No Brain duplication
- Future versions may add interactive terminal sessions

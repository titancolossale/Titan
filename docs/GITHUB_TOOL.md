# Titan GitHub Tool V1 — Read-Only Repository Access

GitHub Tool V1 gives Titan **secure read-only access** to GitHub repositories through the core Tool Runtime. It is a **Tool**, not part of the Brain. Write operations (push, commit, pull request, issue creation) are intentionally unsupported and deferred to V2.

## Scope (V1)

**Implemented:**

| Action | Permission | Description |
|--------|------------|-------------|
| `list_repositories` | `github.list` | List repositories visible to the authenticated user |
| `repository_metadata` | `github.read` | Structured repository metadata |
| `list_branches` | `github.list` | List branches for a repository |
| `list_commits` | `github.read` | Recent commit history (optional branch) |
| `repository_tree` | `github.read` | File/directory tree for a ref |
| `read_file` | `github.read` | Decode and return file contents (e.g. README) |
| `search_repository` | `github.search` | Code search scoped to one repository |

**Deferred to V2:**

- Commits / pushes
- Pull request create / merge
- Issue create / update
- Branch create / delete
- Repository create / delete
- Any other write API

## Architecture

```
core/tools/github/
├── github_tool.py       ← BaseTool facade (actions + permissions)
├── github_client.py     ← Read-only GitHub REST client (httpx)
├── github_config.py     ← Token + timeout from environment
├── models.py            ← Structured ActionResult payloads
└── exceptions.py        ← Domain errors
```

### Integration with existing frameworks

```
ToolIntelligence.plan(request)
  → ToolExecutionEngine.execute(plan)
    → ActionDispatcher.dispatch(tool_id, action_id, params)
      → PermissionManager.check_permission(action.permission_id)
      → GitHubTool.execute_action()
        → GitHubClient (GET only)
```

- **Tool Registry / Tool Loader** — auto-discovers `GitHubTool` from `core/tools/github/`
- **Permission Manager** — `github.list`, `github.read`, `github.search`
- **Action Framework** — each operation returns structured `ActionResult` (never raw API payloads)
- **Tool Intelligence** — routes phrases like “Show recent commits”, “Read README”, “Find where X is implemented”

This core tool is separate from the legacy provider stack in `tools/providers/github_provider.py`. The production Action Framework path uses `core/tools/github/`.

## Permission Model

| Permission ID | Level | Actions |
|---------------|-------|---------|
| `github.list` | SAFE | `list_repositories`, `list_branches` |
| `github.read` | SAFE | `repository_metadata`, `list_commits`, `repository_tree`, `read_file` |
| `github.search` | SAFE | `search_repository` |

Permissions are registered idempotently when `GitHubTool` is instantiated. All V1 permissions are `SAFE` (read-only).

## Authentication

Uses a **Personal Access Token** loaded from configuration only:

```bash
TITAN_GITHUB_TOKEN=ghp_xxxxxxxx
```

Rules:

- Never hardcode credentials in source
- Token is sent as `Authorization: Bearer <token>`
- Missing or invalid token → `GitHubAuthenticationError` / failed `ActionResult`
- Token is never logged

Recommended classic PAT scopes for V1: `repo` (private repos) or `public_repo` (public only). Fine-grained tokens need Contents: Read and Metadata: Read.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TITAN_GITHUB_TOKEN` | _(empty)_ | Personal Access Token (required for API calls) |
| `TITAN_GITHUB_ENABLED` | `true` | Legacy provider enable flag (settings) |
| `TITAN_GITHUB_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `TITAN_GITHUB_RETRY_COUNT` | `2` | Retries for transient failures |
| `TITAN_GITHUB_PER_PAGE` | `30` | Default list page size |
| `TITAN_GITHUB_API_BASE_URL` | `https://api.github.com` | API base URL |
| `TITAN_GITHUB_USER_AGENT` | `TitanBot/1.0 (Read-Only GitHub Tool)` | User-Agent |

Programmatic example:

```python
from core.tools.github import GitHubConfig, GitHubTool

config = GitHubConfig.from_environment()
tool = GitHubTool(config=config)
result = tool.execute_action(
    "list_commits",
    owner="nolan",
    repo="titan",
    branch="main",
)
```

## ActionResult Shape

Success payloads are structured dataclasses converted via `to_dict()`. Example for `list_commits`:

```json
{
  "action": "list_commits",
  "repository": "nolan/titan",
  "branch": "main",
  "count": 1,
  "commits": [
    {
      "sha": "abc123",
      "message": "Add GitHub Tool V1",
      "author_name": "Nolan",
      "author_email": "nolan@example.com",
      "author_date": "2026-07-09T10:00:00Z",
      "html_url": "https://github.com/nolan/titan/commit/abc123"
    }
  ]
}
```

Raw GitHub API fields (e.g. `node_id`, nested `_links`) are not exposed.

## Logging

Every action logs:

- Repository (`owner/repo`)
- Branch / ref (when provided)
- Action id
- Duration
- Errors (message only — never the token)

## Tool Intelligence Examples

| Request | Selected tool / action |
|---------|------------------------|
| “Show recent commits” | GitHub → `list_commits` |
| “Read README” | GitHub → `read_file` (`path=README.md`) |
| “Find where MissionRuntime is implemented” | GitHub → `search_repository` |

## Security

- **GET-only** client — non-GET methods are rejected in `GitHubClient`
- No write actions registered in `list_actions()`
- Credentials from environment only
- Structured outputs only

## Definition of Done

Titan can securely inspect GitHub repositories using the Tool Runtime without any write capability. Future V2 will introduce commit and pull request support.

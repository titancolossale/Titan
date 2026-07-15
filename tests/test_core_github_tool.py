# =====================================
# Titan Core GitHub Tool V1 Tests
# =====================================

"""Tests for read-only GitHub integration in core/tools/github."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from brain.tool_execution_engine import ToolExecutionEngine, build_core_tool_runtime
from brain.tool_intelligence import (
    PlannedAction,
    SelectedTool,
    ToolExecutionPlan,
    ToolIntelligence,
    ToolIntent,
    build_default_tool_intelligence,
)
from core.actions import ActionDispatcher, ActionRegistry
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools import ToolLoader, ToolRegistry
from core.tools.github import (
    GitHubAuthenticationError,
    GitHubClient,
    GitHubConfig,
    GitHubPermissionDeniedError,
    GitHubTool,
    PERMISSION_LIST,
    PERMISSION_READ,
    PERMISSION_SEARCH,
)

CORE_TOOLS_DIR = Path(__file__).resolve().parents[1] / "core" / "tools"

SAMPLE_TOKEN = "ghp_test_token_abcdefghijklmnopqrstuvwxyz"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _json_response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _mock_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    auth = request.headers.get("Authorization", "")

    if not auth.startswith("Bearer "):
        return _json_response({"message": "Bad credentials"}, status=401)

    if path == "/user/repos":
        return _json_response(
            [
                {
                    "full_name": "nolan/titan",
                    "name": "titan",
                    "owner": {"login": "nolan"},
                    "private": True,
                    "description": "Personal agentic AI",
                    "default_branch": "main",
                    "html_url": "https://github.com/nolan/titan",
                    "language": "Python",
                    "updated_at": "2026-07-09T12:00:00Z",
                }
            ]
        )

    if path == "/repos/nolan/titan":
        return _json_response(
            {
                "full_name": "nolan/titan",
                "name": "titan",
                "owner": {"login": "nolan"},
                "private": True,
                "description": "Personal agentic AI",
                "default_branch": "main",
                "html_url": "https://github.com/nolan/titan",
                "clone_url": "https://github.com/nolan/titan.git",
                "language": "Python",
                "topics": ["ai", "agent"],
                "stargazers_count": 12,
                "forks_count": 2,
                "open_issues_count": 3,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-07-09T12:00:00Z",
                "pushed_at": "2026-07-09T11:00:00Z",
            }
        )

    if path == "/repos/nolan/titan/branches":
        return _json_response(
            [
                {
                    "name": "main",
                    "commit": {"sha": "abc123"},
                    "protected": True,
                },
                {
                    "name": "feature/github-tool",
                    "commit": {"sha": "def456"},
                    "protected": False,
                },
            ]
        )

    if path == "/repos/nolan/titan/commits":
        return _json_response(
            [
                {
                    "sha": "abc123",
                    "html_url": "https://github.com/nolan/titan/commit/abc123",
                    "commit": {
                        "message": "Add GitHub Tool V1",
                        "author": {
                            "name": "Nolan",
                            "email": "nolan@example.com",
                            "date": "2026-07-09T10:00:00Z",
                        },
                    },
                }
            ]
        )

    if path.startswith("/repos/nolan/titan/git/trees/"):
        return _json_response(
            {
                "sha": "tree1",
                "tree": [
                    {
                        "path": "README.md",
                        "type": "blob",
                        "sha": "file1",
                        "size": 42,
                    },
                    {
                        "path": "core",
                        "type": "tree",
                        "sha": "dir1",
                    },
                ],
            }
        )

    if path == "/repos/nolan/titan/contents/README.md":
        return _json_response(
            {
                "path": "README.md",
                "sha": "file1",
                "size": 20,
                "type": "file",
                "encoding": "base64",
                "content": _b64("# Titan\n"),
                "html_url": "https://github.com/nolan/titan/blob/main/README.md",
            }
        )

    if path == "/search/code":
        return _json_response(
            {
                "total_count": 1,
                "items": [
                    {
                        "name": "mission_runtime.py",
                        "path": "core/mission_runtime.py",
                        "sha": "search1",
                        "html_url": (
                            "https://github.com/nolan/titan/blob/main/"
                            "core/mission_runtime.py"
                        ),
                        "repository": {"full_name": "nolan/titan"},
                        "score": 1.0,
                        "text_matches": [
                            {"fragment": "class MissionRuntime:"},
                        ],
                    }
                ],
            }
        )

    return _json_response({"message": "Not Found"}, status=404)


@pytest.fixture
def github_config() -> GitHubConfig:
    return GitHubConfig(
        token=SAMPLE_TOKEN,
        timeout_seconds=5.0,
        retry_count=0,
        per_page=30,
    )


@pytest.fixture
def github_client(github_config: GitHubConfig) -> GitHubClient:
    client = GitHubClient(github_config, handler=_mock_handler)
    yield client
    client.close()


@pytest.fixture
def github_tool(github_config: GitHubConfig) -> GitHubTool:
    tool = GitHubTool(config=github_config, handler=_mock_handler)
    yield tool
    tool.close()


def test_authentication_requires_token() -> None:
    config = GitHubConfig(token="")
    client = GitHubClient(config, handler=_mock_handler)
    try:
        with pytest.raises(GitHubAuthenticationError):
            client.list_repositories()
    finally:
        client.close()


def test_authentication_rejects_invalid_token() -> None:
    def unauthorized_handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"message": "Bad credentials"}, status=401)

    config = GitHubConfig(token="invalid-token-value-1234567890")
    client = GitHubClient(config, handler=unauthorized_handler)
    try:
        with pytest.raises(GitHubAuthenticationError):
            client.list_repositories()
    finally:
        client.close()


def test_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_GITHUB_TOKEN", SAMPLE_TOKEN)
    monkeypatch.setenv("TITAN_GITHUB_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("TITAN_GITHUB_RETRY_COUNT", "1")
    monkeypatch.setenv("TITAN_GITHUB_API_BASE_URL", "https://api.github.com")

    config = GitHubConfig.from_environment()

    assert config.token == SAMPLE_TOKEN
    assert config.timeout_seconds == 15.0
    assert config.retry_count == 1
    assert config.has_token is True


def test_list_repositories(github_client: GitHubClient) -> None:
    repos = github_client.list_repositories()

    assert len(repos) == 1
    assert repos[0].full_name == "nolan/titan"
    assert repos[0].private is True
    assert repos[0].language == "Python"


def test_repository_listing_action(github_tool: GitHubTool) -> None:
    result = github_tool.execute_action("list_repositories")

    assert result.success is True
    assert result.data["count"] == 1
    assert result.data["repositories"][0]["full_name"] == "nolan/titan"
    assert "html_url" in result.data["repositories"][0]
    assert "node_id" not in result.data["repositories"][0]


def test_commit_history(github_tool: GitHubTool) -> None:
    result = github_tool.execute_action(
        "list_commits",
        owner="nolan",
        repo="titan",
        branch="main",
    )

    assert result.success is True
    assert result.data["count"] == 1
    commit = result.data["commits"][0]
    assert commit["sha"] == "abc123"
    assert "GitHub Tool V1" in commit["message"]
    assert commit["author_name"] == "Nolan"
    assert result.metadata["repository"] == "nolan/titan"
    assert result.metadata["branch"] == "main"


def test_read_file(github_tool: GitHubTool) -> None:
    result = github_tool.execute_action(
        "read_file",
        owner="nolan",
        repo="titan",
        path="README.md",
    )

    assert result.success is True
    file_payload = result.data["file"]
    assert file_payload["path"] == "README.md"
    assert file_payload["content"] == "# Titan\n"
    assert file_payload["encoding"] == "utf-8"


def test_repository_search(github_tool: GitHubTool) -> None:
    result = github_tool.execute_action(
        "search_repository",
        repository="nolan/titan",
        query="MissionRuntime",
    )

    assert result.success is True
    assert result.data["count"] == 1
    match = result.data["matches"][0]
    assert match["path"] == "core/mission_runtime.py"
    assert "MissionRuntime" in match["text_matches"][0]


def test_repository_metadata_and_tree(github_tool: GitHubTool) -> None:
    metadata = github_tool.execute_action(
        "repository_metadata",
        owner="nolan",
        repo="titan",
    )
    tree = github_tool.execute_action(
        "repository_tree",
        owner="nolan",
        repo="titan",
        ref="main",
    )

    assert metadata.success is True
    assert metadata.data["metadata"]["default_branch"] == "main"
    assert metadata.data["metadata"]["stars"] == 12

    assert tree.success is True
    paths = {entry["path"] for entry in tree.data["tree"]}
    assert "README.md" in paths
    assert "core" in paths


def test_list_branches(github_tool: GitHubTool) -> None:
    result = github_tool.execute_action(
        "list_branches",
        owner="nolan",
        repo="titan",
    )

    assert result.success is True
    names = {branch["name"] for branch in result.data["branches"]}
    assert names == {"main", "feature/github-tool"}


def test_permission_denied_for_read(github_config: GitHubConfig) -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_LIST,
            name="List",
            description="Allowed list.",
            level=PermissionLevel.SAFE,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_READ,
            name="Blocked Read",
            description="Blocked for test.",
            level=PermissionLevel.BLOCKED,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_SEARCH,
            name="Search",
            description="Allowed search.",
            level=PermissionLevel.SAFE,
        )
    )

    tool = GitHubTool(
        config=github_config,
        permission_manager=permission_manager,
        handler=_mock_handler,
    )
    try:
        with pytest.raises(GitHubPermissionDeniedError):
            tool.execute(action="list_commits", owner="nolan", repo="titan")
    finally:
        tool.close()


def test_permission_denied_via_dispatcher(github_config: GitHubConfig) -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_SEARCH,
            name="Blocked Search",
            description="Blocked for test.",
            level=PermissionLevel.BLOCKED,
        )
    )

    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = GitHubTool(
        config=github_config,
        permission_manager=permission_manager,
        action_registry=action_registry,
        handler=_mock_handler,
    )
    tool_registry.register_tool(tool)

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
    )

    try:
        result = dispatcher.dispatch(
            "github",
            "search_repository",
            {"owner": "nolan", "repo": "titan", "query": "MissionRuntime"},
        )
        assert result.success is False
        assert "permission" in result.message.lower()
    finally:
        tool.close()


def test_tool_registers_default_permissions(github_tool: GitHubTool) -> None:
    manager = github_tool.permission_manager

    assert manager.permission_exists(PERMISSION_LIST)
    assert manager.permission_exists(PERMISSION_READ)
    assert manager.permission_exists(PERMISSION_SEARCH)


def test_read_only_rejects_non_get(github_config: GitHubConfig) -> None:
    client = GitHubClient(github_config, handler=_mock_handler)
    try:
        with pytest.raises(Exception) as exc_info:
            client._request_json("POST", "/repos/nolan/titan")  # noqa: SLF001
        assert "read-only" in str(exc_info.value).lower()
    finally:
        client.close()


def test_tool_loader_discovers_github() -> None:
    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[CORE_TOOLS_DIR])
    result = loader.load()

    assert "github" in result.loaded
    loaded = registry.get_tool("github")
    assert loaded is not None
    assert loaded.id == "github"
    action_ids = {action.id for action in loaded.list_actions()}
    assert {
        "list_repositories",
        "repository_metadata",
        "list_branches",
        "list_commits",
        "repository_tree",
        "read_file",
        "search_repository",
    }.issubset(action_ids)


def test_brain_integration_via_tool_execution_engine(
    github_config: GitHubConfig,
) -> None:
    """GitHub runs only through ToolExecutionEngine + ActionDispatcher — not Brain logic."""
    permission_manager = PermissionManager()
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = GitHubTool(
        config=github_config,
        permission_manager=permission_manager,
        action_registry=action_registry,
        handler=_mock_handler,
    )
    tool_registry.register_tool(tool)

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
    )
    engine = ToolExecutionEngine(dispatcher)

    plan = ToolExecutionPlan(
        request="Show recent commits",
        intent=ToolIntent.READ,
        intent_summary="Inspect recent commits on GitHub.",
        selected_tools=(
            SelectedTool(
                tool_id="github",
                tool_name="GitHub",
                category="vcs",
                confidence=0.95,
                reason="Explicit GitHub commit request.",
                actions=(
                    PlannedAction(
                        tool_id="github",
                        action_id="list_commits",
                        reason="List recent commits.",
                        confidence=0.95,
                        parameters={
                            "owner": "nolan",
                            "repo": "titan",
                            "branch": "main",
                        },
                    ),
                ),
            ),
        ),
        execution_order=("github",),
        confidence=0.95,
        requires_tools=True,
        reasoning_summary="test",
    )

    result = engine.execute(plan)

    assert result.success is True
    assert len(result.completed_steps) == 1
    assert result.completed_steps[0].tool_id == "github"
    assert result.completed_steps[0].action_id == "list_commits"
    assert result.tool_outputs["github"]["count"] == 1


def test_core_runtime_discovers_github_tool() -> None:
    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])
    tool = runtime.tool_registry.get_tool("github")

    assert tool is not None
    assert tool.id == "github"
    assert runtime.action_registry.action_exists("github", "list_commits")
    assert runtime.permission_manager.permission_exists(PERMISSION_READ)


def test_tool_intelligence_routes_recent_commits() -> None:
    intelligence = build_default_tool_intelligence(scan_paths=[CORE_TOOLS_DIR])
    plan = intelligence.plan("Show recent commits on github for nolan/titan")

    assert plan.requires_tools is True
    assert "github" in [tool.tool_id for tool in plan.selected_tools]
    github = next(tool for tool in plan.selected_tools if tool.tool_id == "github")
    assert github.actions
    assert github.actions[0].action_id == "list_commits"
    assert github.actions[0].parameters.get("owner") == "nolan"
    assert github.actions[0].parameters.get("repo") == "titan"


def test_tool_intelligence_routes_readme() -> None:
    intelligence = build_default_tool_intelligence(scan_paths=[CORE_TOOLS_DIR])
    plan = intelligence.plan("Read README from nolan/titan on github")

    assert plan.requires_tools is True
    assert "github" in [tool.tool_id for tool in plan.selected_tools]
    github = next(tool for tool in plan.selected_tools if tool.tool_id == "github")
    assert github.actions[0].action_id == "read_file"
    assert github.actions[0].parameters.get("path") == "README.md"


def test_tool_intelligence_routes_code_search() -> None:
    intelligence = build_default_tool_intelligence(scan_paths=[CORE_TOOLS_DIR])
    plan = intelligence.plan(
        "Find where MissionRuntime is implemented in nolan/titan on github"
    )

    assert plan.requires_tools is True
    assert "github" in [tool.tool_id for tool in plan.selected_tools]
    github = next(tool for tool in plan.selected_tools if tool.tool_id == "github")
    assert github.actions[0].action_id == "search_repository"
    assert "MissionRuntime" in str(github.actions[0].parameters.get("query", ""))


def test_execute_action_records_execution_time(github_tool: GitHubTool) -> None:
    result = github_tool.execute_action(
        "repository_metadata",
        owner="nolan",
        repo="titan",
    )

    assert result.success is True
    assert result.execution_time >= 0.0

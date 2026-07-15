# =====================================
# Titan GitHub Tool
# =====================================

"""Read-only GitHub repository inspection tool for Titan's core tool layer."""

from __future__ import annotations

import logging
import time

import httpx

from core.actions.action import Action
from core.actions.action_registry import ActionRegistry
from core.actions.action_result import ActionResult
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.base_tool import BaseTool
from core.tools.github.exceptions import (
    GitHubAuthenticationError,
    GitHubConfigurationError,
    GitHubPermissionDeniedError,
)
from core.tools.github.github_client import GitHubClient, HttpHandler
from core.tools.github.github_config import GitHubConfig

logger = logging.getLogger(__name__)

PERMISSION_LIST = "github.list"
PERMISSION_READ = "github.read"
PERMISSION_SEARCH = "github.search"

CAPABILITY_LIST_REPOSITORIES = "list_repositories"
CAPABILITY_REPOSITORY_METADATA = "repository_metadata"
CAPABILITY_LIST_BRANCHES = "list_branches"
CAPABILITY_LIST_COMMITS = "list_commits"
CAPABILITY_REPOSITORY_TREE = "repository_tree"
CAPABILITY_READ_FILE = "read_file"
CAPABILITY_SEARCH_REPOSITORY = "search_repository"

_CAPABILITY_PERMISSIONS: dict[str, str] = {
    CAPABILITY_LIST_REPOSITORIES: PERMISSION_LIST,
    CAPABILITY_REPOSITORY_METADATA: PERMISSION_READ,
    CAPABILITY_LIST_BRANCHES: PERMISSION_LIST,
    CAPABILITY_LIST_COMMITS: PERMISSION_READ,
    CAPABILITY_REPOSITORY_TREE: PERMISSION_READ,
    CAPABILITY_READ_FILE: PERMISSION_READ,
    CAPABILITY_SEARCH_REPOSITORY: PERMISSION_SEARCH,
}

_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "list_repositories": CAPABILITY_LIST_REPOSITORIES,
    "repository_metadata": CAPABILITY_REPOSITORY_METADATA,
    "list_branches": CAPABILITY_LIST_BRANCHES,
    "list_commits": CAPABILITY_LIST_COMMITS,
    "repository_tree": CAPABILITY_REPOSITORY_TREE,
    "read_file": CAPABILITY_READ_FILE,
    "search_repository": CAPABILITY_SEARCH_REPOSITORY,
}

_DEFAULT_PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        id=PERMISSION_LIST,
        name="List GitHub Resources",
        description="List repositories and branches visible to the authenticated user.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_READ,
        name="Read GitHub Content",
        description="Read repository metadata, commits, trees, and file contents.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_SEARCH,
        name="Search GitHub Repositories",
        description="Search code within a GitHub repository.",
        level=PermissionLevel.SAFE,
    ),
)

_OWNER_REPO_PARAMETERS = {
    "owner": {
        "type": "string",
        "required": True,
        "description": "Repository owner (user or organization).",
    },
    "repo": {
        "type": "string",
        "required": True,
        "description": "Repository name.",
    },
    "repository": {
        "type": "string",
        "required": False,
        "description": "Optional owner/repo shorthand.",
    },
}


def _build_github_actions(tool_id: str) -> tuple[Action, ...]:
    """Return the canonical GitHub actions registered in the action framework."""
    return (
        Action(
            id="list_repositories",
            name="List Repositories",
            description=(
                "List GitHub repositories for the authenticated user. "
                "Useful for showing available repos."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_LIST,
            parameters={
                "visibility": {
                    "type": "string",
                    "required": False,
                    "description": "Filter: all, public, or private.",
                },
                "per_page": {
                    "type": "integer",
                    "required": False,
                    "description": "Page size (1-100).",
                },
            },
            metadata={"capability": CAPABILITY_LIST_REPOSITORIES},
        ),
        Action(
            id="repository_metadata",
            name="Repository Metadata",
            description=(
                "Return structured metadata for a GitHub repository "
                "(description, default branch, stars, language)."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_READ,
            parameters=dict(_OWNER_REPO_PARAMETERS),
            metadata={"capability": CAPABILITY_REPOSITORY_METADATA},
        ),
        Action(
            id="list_branches",
            name="List Branches",
            description="List branches in a GitHub repository.",
            tool_id=tool_id,
            permission_id=PERMISSION_LIST,
            parameters={
                **_OWNER_REPO_PARAMETERS,
                "per_page": {
                    "type": "integer",
                    "required": False,
                    "description": "Page size (1-100).",
                },
            },
            metadata={"capability": CAPABILITY_LIST_BRANCHES},
        ),
        Action(
            id="list_commits",
            name="List Commits",
            description=(
                "Show recent commits on a GitHub repository or branch. "
                "Use for commit history inspection."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_READ,
            parameters={
                **_OWNER_REPO_PARAMETERS,
                "branch": {
                    "type": "string",
                    "required": False,
                    "description": "Branch name, tag, or commit SHA.",
                },
                "per_page": {
                    "type": "integer",
                    "required": False,
                    "description": "Number of commits to return.",
                },
            },
            metadata={"capability": CAPABILITY_LIST_COMMITS},
        ),
        Action(
            id="repository_tree",
            name="Repository Tree",
            description="List the file and directory tree of a GitHub repository.",
            tool_id=tool_id,
            permission_id=PERMISSION_READ,
            parameters={
                **_OWNER_REPO_PARAMETERS,
                "ref": {
                    "type": "string",
                    "required": False,
                    "description": "Branch, tag, or commit SHA (defaults to default branch).",
                },
                "recursive": {
                    "type": "boolean",
                    "required": False,
                    "description": "Whether to expand the tree recursively (default true).",
                },
            },
            metadata={"capability": CAPABILITY_REPOSITORY_TREE},
        ),
        Action(
            id="read_file",
            name="Read File",
            description=(
                "Read a file from a GitHub repository (for example README.md). "
                "Returns decoded text content."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_READ,
            parameters={
                **_OWNER_REPO_PARAMETERS,
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "File path within the repository.",
                },
                "ref": {
                    "type": "string",
                    "required": False,
                    "description": "Branch, tag, or commit SHA.",
                },
            },
            metadata={"capability": CAPABILITY_READ_FILE},
        ),
        Action(
            id="search_repository",
            name="Search Repository",
            description=(
                "Search code inside a GitHub repository. "
                "Use to find where a symbol or class is implemented."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_SEARCH,
            parameters={
                **_OWNER_REPO_PARAMETERS,
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "Code search query (e.g. class or function name).",
                },
                "per_page": {
                    "type": "integer",
                    "required": False,
                    "description": "Number of matches to return.",
                },
            },
            metadata={"capability": CAPABILITY_SEARCH_REPOSITORY},
        ),
    )


class GitHubTool(BaseTool):
    """Read-only GitHub tool backed by the core permission and action systems.

    V1 supports repository inspection only. It never pushes, commits, opens
    pull requests, or creates issues. Write capabilities are deferred to V2.
    """

    def __init__(
        self,
        config: GitHubConfig | None = None,
        client: GitHubClient | None = None,
        permission_manager: PermissionManager | None = None,
        action_registry: ActionRegistry | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        handler: HttpHandler | None = None,
    ) -> None:
        super().__init__()
        self._permission_manager = permission_manager or PermissionManager()
        self._register_default_permissions()

        self._config = config or GitHubConfig.from_environment()
        self._client = client or GitHubClient(
            self._config,
            transport=transport,
            handler=handler,
        )
        self._actions = _build_github_actions(self.id)

        if action_registry is not None:
            self._register_actions(action_registry)

    @property
    def id(self) -> str:
        return "github"

    @property
    def name(self) -> str:
        return "GitHub"

    @property
    def description(self) -> str:
        return (
            "Read-only GitHub repository access. List repositories, inspect metadata, "
            "branches, recent commits, file trees, README and source files, and search "
            "code. Does not push, commit, open pull requests, or create issues."
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def category(self) -> str:
        return "vcs"

    @property
    def requires_confirmation(self) -> bool:
        return False

    @property
    def capabilities(self) -> list[str]:
        return list(_CAPABILITY_PERMISSIONS.keys())

    @property
    def client(self) -> GitHubClient:
        """Return the underlying GitHub API client."""
        return self._client

    @property
    def permission_manager(self) -> PermissionManager:
        """Return the permission manager used by this tool."""
        return self._permission_manager

    def list_actions(self) -> list[Action]:
        """Return the GitHub actions exposed by this tool."""
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        """Execute a registered GitHub action without performing permission checks.

        Permission verification is owned by ``ActionDispatcher``.
        """
        registered_ids = {action.id for action in self._actions}
        if action_id not in registered_ids:
            message = f"Unsupported GitHub action: {action_id}"
            logger.warning(message)
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"action_id": action_id},
            )

        owner, repo, branch = _resolve_repo_context(kwargs)
        started = time.perf_counter()
        try:
            data = self._dispatch_action(action_id, kwargs, owner=owner, repo=repo)
        except Exception as exc:
            elapsed = time.perf_counter() - started
            message = str(exc)
            logger.exception(
                "GitHub action failed: action=%s repository=%s branch=%s duration=%.3fs error=%s",
                action_id,
                f"{owner}/{repo}" if owner and repo else "",
                branch or "",
                elapsed,
                message,
            )
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                execution_time=elapsed,
                metadata={
                    "action_id": action_id,
                    "repository": f"{owner}/{repo}" if owner and repo else "",
                    "branch": branch or "",
                },
            )

        elapsed = time.perf_counter() - started
        repository = f"{owner}/{repo}" if owner and repo else ""
        logger.info(
            "GitHub action completed: action=%s repository=%s branch=%s duration=%.3fs",
            action_id,
            repository,
            branch or "",
            elapsed,
        )
        return ActionResult(
            success=True,
            data=data,
            message=f"GitHub action '{action_id}' completed successfully.",
            execution_time=elapsed,
            metadata={
                "action_id": action_id,
                "repository": repository,
                "branch": branch or "",
            },
        )

    def execute(self, **kwargs: object) -> object:
        """Dispatch a GitHub action after permission checks.

        Legacy callers pass ``action`` in kwargs.
        """
        action = str(kwargs.get("action", "")).strip().lower()
        if not action:
            raise GitHubConfigurationError("Missing required parameter: action")

        capability = _ACTION_CAPABILITY_MAP.get(action)
        if capability is None:
            raise GitHubConfigurationError(f"Unsupported GitHub action: {action}")

        self._require_permission(capability)

        result = self.execute_action(action, **kwargs)
        if not result.success:
            self._raise_for_failed_action(action, result)

        return result.data

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def _dispatch_action(
        self,
        action_id: str,
        kwargs: dict[str, object],
        *,
        owner: str,
        repo: str,
    ) -> dict[str, object]:
        if action_id == "list_repositories":
            visibility = str(kwargs.get("visibility") or "all").strip() or "all"
            per_page = _optional_int(kwargs.get("per_page"))
            repositories = self._client.list_repositories(
                visibility=visibility,
                per_page=per_page,
            )
            return {
                "action": action_id,
                "count": len(repositories),
                "repositories": [item.to_dict() for item in repositories],
            }

        if action_id == "repository_metadata":
            _require_owner_repo(owner, repo)
            metadata = self._client.get_repository(owner, repo)
            return {
                "action": action_id,
                "repository": metadata.full_name,
                "metadata": metadata.to_dict(),
            }

        if action_id == "list_branches":
            _require_owner_repo(owner, repo)
            per_page = _optional_int(kwargs.get("per_page"))
            branches = self._client.list_branches(owner, repo, per_page=per_page)
            return {
                "action": action_id,
                "repository": f"{owner}/{repo}",
                "count": len(branches),
                "branches": [item.to_dict() for item in branches],
            }

        if action_id == "list_commits":
            _require_owner_repo(owner, repo)
            branch = str(kwargs.get("branch") or kwargs.get("ref") or "").strip() or None
            per_page = _optional_int(kwargs.get("per_page"))
            commits = self._client.list_commits(
                owner,
                repo,
                branch=branch,
                per_page=per_page,
            )
            return {
                "action": action_id,
                "repository": f"{owner}/{repo}",
                "branch": branch or "",
                "count": len(commits),
                "commits": [item.to_dict() for item in commits],
            }

        if action_id == "repository_tree":
            _require_owner_repo(owner, repo)
            ref = str(kwargs.get("ref") or kwargs.get("branch") or "").strip() or None
            recursive = _optional_bool(kwargs.get("recursive"), default=True)
            entries = self._client.get_repository_tree(
                owner,
                repo,
                ref=ref,
                recursive=recursive,
            )
            return {
                "action": action_id,
                "repository": f"{owner}/{repo}",
                "ref": ref or "",
                "count": len(entries),
                "tree": [item.to_dict() for item in entries],
            }

        if action_id == "read_file":
            _require_owner_repo(owner, repo)
            path = str(kwargs.get("path") or "").strip()
            if not path:
                raise GitHubConfigurationError("Missing required parameter: path")
            ref = str(kwargs.get("ref") or kwargs.get("branch") or "").strip() or None
            file_content = self._client.read_file(owner, repo, path, ref=ref)
            return {
                "action": action_id,
                "repository": f"{owner}/{repo}",
                "ref": ref or "",
                "file": file_content.to_dict(),
            }

        if action_id == "search_repository":
            _require_owner_repo(owner, repo)
            query = str(kwargs.get("query") or "").strip()
            if not query:
                raise GitHubConfigurationError("Missing required parameter: query")
            per_page = _optional_int(kwargs.get("per_page"))
            matches = self._client.search_repository(
                owner,
                repo,
                query,
                per_page=per_page,
            )
            return {
                "action": action_id,
                "repository": f"{owner}/{repo}",
                "query": query,
                "count": len(matches),
                "matches": [item.to_dict() for item in matches],
            }

        raise GitHubConfigurationError(f"Unsupported GitHub action: {action_id}")

    def _register_actions(self, registry: ActionRegistry) -> None:
        for action in self._actions:
            if registry.action_exists(action.tool_id, action.id):
                continue
            registry.register_action(action)

    def _register_default_permissions(self) -> None:
        for permission in _DEFAULT_PERMISSIONS:
            if self._permission_manager.permission_exists(permission.id):
                continue
            self._permission_manager.register_permission(permission)
            logger.info("Registered GitHub permission: %s", permission.id)

    def _require_permission(self, capability: str) -> None:
        permission_id = _CAPABILITY_PERMISSIONS[capability]
        result = self._permission_manager.check_permission(permission_id)
        if not result.allowed:
            logger.warning(
                "GitHub permission denied: capability=%s permission=%s reason=%s",
                capability,
                permission_id,
                result.reason,
            )
            raise GitHubPermissionDeniedError(permission_id, result.reason)

    @staticmethod
    def _raise_for_failed_action(action: str, result: ActionResult) -> None:
        lowered = result.message.lower()
        if "permission" in lowered:
            permission_id = str(result.metadata.get("permission_id", "unknown"))
            raise GitHubPermissionDeniedError(permission_id, result.message)
        if "authentication" in lowered or "token" in lowered:
            raise GitHubAuthenticationError(result.message)
        raise GitHubConfigurationError(result.message or f"GitHub action failed: {action}")


def _resolve_repo_context(kwargs: dict[str, object]) -> tuple[str, str, str]:
    owner = str(kwargs.get("owner") or "").strip()
    repo = str(kwargs.get("repo") or "").strip()
    repository = str(kwargs.get("repository") or "").strip()
    if repository and ("/" in repository) and (not owner or not repo):
        parts = repository.split("/", 1)
        owner = owner or parts[0].strip()
        repo = repo or parts[1].strip()
    branch = str(kwargs.get("branch") or kwargs.get("ref") or "").strip()
    return owner, repo.removesuffix(".git"), branch


def _require_owner_repo(owner: str, repo: str) -> None:
    if not owner or not repo:
        raise GitHubConfigurationError("Missing required parameters: owner and repo")


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise GitHubConfigurationError(f"Invalid integer parameter: {value}") from exc


def _optional_bool(value: object, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise GitHubConfigurationError(f"Invalid boolean parameter: {value}")

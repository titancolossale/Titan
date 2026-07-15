# =====================================
# Titan GitHub Tool Package
# =====================================

"""Read-only GitHub repository integration for Titan's core tool layer."""

from core.tools.github.exceptions import (
    GitHubApiError,
    GitHubAuthenticationError,
    GitHubConfigurationError,
    GitHubError,
    GitHubNotFoundError,
    GitHubPermissionDeniedError,
)
from core.tools.github.github_client import GitHubClient
from core.tools.github.github_config import GitHubConfig
from core.tools.github.github_tool import (
    CAPABILITY_LIST_BRANCHES,
    CAPABILITY_LIST_COMMITS,
    CAPABILITY_LIST_REPOSITORIES,
    CAPABILITY_READ_FILE,
    CAPABILITY_REPOSITORY_METADATA,
    CAPABILITY_REPOSITORY_TREE,
    CAPABILITY_SEARCH_REPOSITORY,
    GitHubTool,
    PERMISSION_LIST,
    PERMISSION_READ,
    PERMISSION_SEARCH,
)
from core.tools.github.models import (
    BranchInfo,
    CommitInfo,
    FileContent,
    RepositoryMetadata,
    RepositorySummary,
    SearchMatch,
    TreeEntry,
)

__all__ = [
    "BranchInfo",
    "CAPABILITY_LIST_BRANCHES",
    "CAPABILITY_LIST_COMMITS",
    "CAPABILITY_LIST_REPOSITORIES",
    "CAPABILITY_READ_FILE",
    "CAPABILITY_REPOSITORY_METADATA",
    "CAPABILITY_REPOSITORY_TREE",
    "CAPABILITY_SEARCH_REPOSITORY",
    "CommitInfo",
    "FileContent",
    "GitHubApiError",
    "GitHubAuthenticationError",
    "GitHubClient",
    "GitHubConfig",
    "GitHubConfigurationError",
    "GitHubError",
    "GitHubNotFoundError",
    "GitHubPermissionDeniedError",
    "GitHubTool",
    "PERMISSION_LIST",
    "PERMISSION_READ",
    "PERMISSION_SEARCH",
    "RepositoryMetadata",
    "RepositorySummary",
    "SearchMatch",
    "TreeEntry",
]

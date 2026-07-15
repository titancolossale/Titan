# =====================================
# Titan GitHub Client
# =====================================

"""HTTP client for read-only GitHub REST API access."""

from __future__ import annotations

import base64
import logging
import time
from typing import Any, Callable
from urllib.parse import quote

import httpx

from core.exceptions import ToolTimeoutError
from core.tools.github.exceptions import (
    GitHubApiError,
    GitHubAuthenticationError,
    GitHubConfigurationError,
    GitHubNotFoundError,
)
from core.tools.github.github_config import GitHubConfig
from core.tools.github.models import (
    BranchInfo,
    CommitInfo,
    FileContent,
    RepositoryMetadata,
    RepositorySummary,
    SearchMatch,
    TreeEntry,
)

logger = logging.getLogger(__name__)

HttpHandler = Callable[[httpx.Request], httpx.Response]

_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class GitHubClient:
    """Read-only GitHub REST client authenticated via Personal Access Token.

    This client never performs write operations (push, commit, PR, issue create).
    """

    def __init__(
        self,
        config: GitHubConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        handler: HttpHandler | None = None,
    ) -> None:
        self._config = config or GitHubConfig.from_environment()
        if handler is not None and transport is not None:
            raise GitHubConfigurationError("Provide either transport or handler, not both")

        if handler is not None:
            transport = httpx.MockTransport(handler)

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self._config.user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._config.has_token:
            headers["Authorization"] = f"Bearer {self._config.token}"

        self._client = httpx.Client(
            base_url=self._config.api_base_url,
            transport=transport,
            timeout=httpx.Timeout(self._config.timeout_seconds),
            headers=headers,
            follow_redirects=True,
        )

    @property
    def config(self) -> GitHubConfig:
        """Return the active client configuration."""
        return self._config

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def require_token(self) -> None:
        """Raise when no Personal Access Token is configured."""
        if not self._config.has_token:
            raise GitHubAuthenticationError(
                "Missing TITAN_GITHUB_TOKEN. Configure a Personal Access Token."
            )

    def list_repositories(
        self,
        *,
        visibility: str = "all",
        per_page: int | None = None,
        page: int = 1,
    ) -> list[RepositorySummary]:
        """List repositories visible to the authenticated user."""
        self.require_token()
        params = {
            "visibility": visibility,
            "affiliation": "owner,collaborator,organization_member",
            "sort": "updated",
            "direction": "desc",
            "per_page": per_page or self._config.per_page,
            "page": max(1, page),
        }
        payload = self._request_json("GET", "/user/repos", params=params)
        if not isinstance(payload, list):
            raise GitHubApiError(500, "Unexpected response for repository list")
        return [_parse_repository_summary(item) for item in payload if isinstance(item, dict)]

    def get_repository(self, owner: str, repo: str) -> RepositoryMetadata:
        """Return metadata for a single repository."""
        self.require_token()
        owner, repo = _normalize_owner_repo(owner, repo)
        payload = self._request_json("GET", f"/repos/{owner}/{repo}")
        if not isinstance(payload, dict):
            raise GitHubApiError(500, "Unexpected response for repository metadata")
        return _parse_repository_metadata(payload)

    def list_branches(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int | None = None,
        page: int = 1,
    ) -> list[BranchInfo]:
        """List branches for a repository."""
        self.require_token()
        owner, repo = _normalize_owner_repo(owner, repo)
        params = {
            "per_page": per_page or self._config.per_page,
            "page": max(1, page),
        }
        payload = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/branches",
            params=params,
        )
        if not isinstance(payload, list):
            raise GitHubApiError(500, "Unexpected response for branch list")
        return [_parse_branch(item) for item in payload if isinstance(item, dict)]

    def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        branch: str | None = None,
        per_page: int | None = None,
        page: int = 1,
    ) -> list[CommitInfo]:
        """List recent commits for a repository (optionally on a branch)."""
        self.require_token()
        owner, repo = _normalize_owner_repo(owner, repo)
        params: dict[str, object] = {
            "per_page": per_page or self._config.per_page,
            "page": max(1, page),
        }
        if branch:
            params["sha"] = branch
        payload = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/commits",
            params=params,
        )
        if not isinstance(payload, list):
            raise GitHubApiError(500, "Unexpected response for commit list")
        return [_parse_commit(item) for item in payload if isinstance(item, dict)]

    def get_repository_tree(
        self,
        owner: str,
        repo: str,
        *,
        ref: str | None = None,
        recursive: bool = True,
    ) -> list[TreeEntry]:
        """Return the repository file tree for a ref (branch, tag, or SHA)."""
        self.require_token()
        owner, repo = _normalize_owner_repo(owner, repo)
        tree_ref = ref or self.get_repository(owner, repo).default_branch
        params: dict[str, object] = {}
        if recursive:
            params["recursive"] = "1"
        payload = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/git/trees/{quote(tree_ref, safe='')}",
            params=params,
        )
        if not isinstance(payload, dict):
            raise GitHubApiError(500, "Unexpected response for repository tree")
        entries = payload.get("tree", [])
        if not isinstance(entries, list):
            raise GitHubApiError(500, "Unexpected tree payload")
        return [_parse_tree_entry(item) for item in entries if isinstance(item, dict)]

    def read_file(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        ref: str | None = None,
    ) -> FileContent:
        """Read and decode a file from a repository."""
        self.require_token()
        owner, repo = _normalize_owner_repo(owner, repo)
        file_path = path.strip().lstrip("/")
        if not file_path:
            raise GitHubConfigurationError("Missing required parameter: path")

        params: dict[str, object] = {}
        if ref:
            params["ref"] = ref
        encoded_path = "/".join(quote(part, safe="") for part in file_path.split("/"))
        payload = self._request_json(
            "GET",
            f"/repos/{owner}/{repo}/contents/{encoded_path}",
            params=params,
        )
        if isinstance(payload, list):
            raise GitHubConfigurationError(
                f"Path '{file_path}' is a directory; provide a file path."
            )
        if not isinstance(payload, dict):
            raise GitHubApiError(500, "Unexpected response for file contents")
        if payload.get("type") != "file":
            raise GitHubConfigurationError(
                f"Path '{file_path}' is not a file (type={payload.get('type')})."
            )
        return _parse_file_content(payload)

    def search_repository(
        self,
        owner: str,
        repo: str,
        query: str,
        *,
        per_page: int | None = None,
        page: int = 1,
    ) -> list[SearchMatch]:
        """Search code within a single repository."""
        self.require_token()
        owner, repo = _normalize_owner_repo(owner, repo)
        cleaned_query = query.strip()
        if not cleaned_query:
            raise GitHubConfigurationError("Missing required parameter: query")

        scoped = f"{cleaned_query} repo:{owner}/{repo}"
        params = {
            "q": scoped,
            "per_page": per_page or self._config.per_page,
            "page": max(1, page),
        }
        headers = {"Accept": "application/vnd.github.text-match+json"}
        payload = self._request_json(
            "GET",
            "/search/code",
            params=params,
            headers=headers,
        )
        if not isinstance(payload, dict):
            raise GitHubApiError(500, "Unexpected response for code search")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise GitHubApiError(500, "Unexpected search items payload")
        return [_parse_search_match(item) for item in items if isinstance(item, dict)]

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Perform a GET request with retries and structured error mapping."""
        if method.upper() != "GET":
            raise GitHubConfigurationError(
                "GitHub Tool V1 is read-only; only GET requests are allowed."
            )

        attempts = self._config.retry_count + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                response = self._client.request(
                    method,
                    path,
                    params=params,
                    headers=headers,
                )
            except httpx.TimeoutException as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "GitHub request timed out: path=%s attempt=%d/%d duration=%.3fs",
                    path,
                    attempt,
                    attempts,
                    elapsed,
                )
                last_error = ToolTimeoutError(
                    f"GitHub request timed out after {self._config.timeout_seconds}s"
                )
                if attempt >= attempts:
                    raise last_error from exc
                continue
            except httpx.RequestError as exc:
                elapsed = time.perf_counter() - started
                reason = str(exc) or exc.__class__.__name__
                logger.warning(
                    "GitHub request failed: path=%s attempt=%d/%d duration=%.3fs error=%s",
                    path,
                    attempt,
                    attempts,
                    elapsed,
                    reason,
                )
                last_error = GitHubApiError(0, reason, path=path)
                if attempt >= attempts:
                    raise last_error from exc
                continue

            elapsed = time.perf_counter() - started
            if response.status_code in _TRANSIENT_STATUS_CODES and attempt < attempts:
                logger.warning(
                    "GitHub transient error: path=%s status=%d attempt=%d/%d duration=%.3fs",
                    path,
                    response.status_code,
                    attempt,
                    attempts,
                    elapsed,
                )
                continue

            return self._parse_response(response, path=path, duration=elapsed)

        if last_error is not None:
            raise last_error
        raise GitHubApiError(0, "GitHub request failed without response", path=path)

    def _parse_response(
        self,
        response: httpx.Response,
        *,
        path: str,
        duration: float,
    ) -> Any:
        status = response.status_code
        logger.info(
            "GitHub request completed: path=%s status=%d duration=%.3fs",
            path,
            status,
            duration,
        )

        if status == 401:
            raise GitHubAuthenticationError("Invalid or expired Personal Access Token.")
        if status == 403:
            message = _extract_error_message(response) or "Forbidden"
            if "rate limit" in message.lower():
                raise GitHubApiError(403, f"Rate limit exceeded: {message}", path=path)
            raise GitHubAuthenticationError(message)
        if status == 404:
            raise GitHubNotFoundError(path)
        if status >= 400:
            message = _extract_error_message(response) or response.reason_phrase or "API error"
            raise GitHubApiError(status, message, path=path)

        if response.status_code == 204 or not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            raise GitHubApiError(status, "Invalid JSON response", path=path) from exc


def _normalize_owner_repo(owner: str, repo: str) -> tuple[str, str]:
    owner_clean = owner.strip()
    repo_clean = repo.strip().removesuffix(".git")
    if "/" in owner_clean and not repo_clean:
        parts = owner_clean.split("/", 1)
        owner_clean, repo_clean = parts[0], parts[1]
    if not owner_clean or not repo_clean:
        raise GitHubConfigurationError("Missing required parameters: owner and repo")
    if "/" in repo_clean:
        raise GitHubConfigurationError("Invalid repo name; use owner and repo separately")
    return owner_clean, repo_clean


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "").strip()[:300]
    if isinstance(payload, dict):
        message = str(payload.get("message", "")).strip()
        if message:
            return message
    return (response.text or "").strip()[:300]


def _parse_repository_summary(item: dict[str, Any]) -> RepositorySummary:
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    return RepositorySummary(
        full_name=str(item.get("full_name", "")),
        name=str(item.get("name", "")),
        owner=str(owner.get("login", "")),
        private=bool(item.get("private", False)),
        description=str(item.get("description") or ""),
        default_branch=str(item.get("default_branch") or "main"),
        html_url=str(item.get("html_url", "")),
        language=str(item.get("language") or ""),
        updated_at=str(item.get("updated_at") or ""),
    )


def _parse_repository_metadata(item: dict[str, Any]) -> RepositoryMetadata:
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    topics = item.get("topics") if isinstance(item.get("topics"), list) else []
    return RepositoryMetadata(
        full_name=str(item.get("full_name", "")),
        name=str(item.get("name", "")),
        owner=str(owner.get("login", "")),
        private=bool(item.get("private", False)),
        description=str(item.get("description") or ""),
        default_branch=str(item.get("default_branch") or "main"),
        html_url=str(item.get("html_url", "")),
        clone_url=str(item.get("clone_url", "")),
        language=str(item.get("language") or ""),
        topics=tuple(str(topic) for topic in topics),
        stars=int(item.get("stargazers_count") or 0),
        forks=int(item.get("forks_count") or 0),
        open_issues=int(item.get("open_issues_count") or 0),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
        pushed_at=str(item.get("pushed_at") or ""),
    )


def _parse_branch(item: dict[str, Any]) -> BranchInfo:
    commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
    return BranchInfo(
        name=str(item.get("name", "")),
        sha=str(commit.get("sha", "")),
        protected=bool(item.get("protected", False)),
    )


def _parse_commit(item: dict[str, Any]) -> CommitInfo:
    commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    return CommitInfo(
        sha=str(item.get("sha", "")),
        message=str(commit.get("message") or "").strip(),
        author_name=str(author.get("name") or ""),
        author_email=str(author.get("email") or ""),
        author_date=str(author.get("date") or ""),
        html_url=str(item.get("html_url", "")),
    )


def _parse_tree_entry(item: dict[str, Any]) -> TreeEntry:
    size_raw = item.get("size")
    size = int(size_raw) if isinstance(size_raw, int) else None
    return TreeEntry(
        path=str(item.get("path", "")),
        type=str(item.get("type", "")),
        sha=str(item.get("sha", "")),
        size=size,
    )


def _parse_file_content(item: dict[str, Any]) -> FileContent:
    encoding = str(item.get("encoding") or "utf-8")
    raw_content = str(item.get("content") or "")
    if encoding == "base64":
        try:
            decoded = base64.b64decode(raw_content).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubApiError(500, f"Failed to decode file content: {exc}") from exc
        content = decoded
        encoding_label = "utf-8"
    else:
        content = raw_content
        encoding_label = encoding

    return FileContent(
        path=str(item.get("path", "")),
        sha=str(item.get("sha", "")),
        size=int(item.get("size") or len(content)),
        encoding=encoding_label,
        content=content,
        html_url=str(item.get("html_url", "")),
    )


def _parse_search_match(item: dict[str, Any]) -> SearchMatch:
    repository = item.get("repository") if isinstance(item.get("repository"), dict) else {}
    text_matches_raw = item.get("text_matches")
    snippets: list[str] = []
    if isinstance(text_matches_raw, list):
        for match in text_matches_raw:
            if isinstance(match, dict):
                fragment = str(match.get("fragment") or "").strip()
                if fragment:
                    snippets.append(fragment)

    return SearchMatch(
        path=str(item.get("path", "")),
        name=str(item.get("name", "")),
        sha=str(item.get("sha", "")),
        html_url=str(item.get("html_url", "")),
        repository=str(repository.get("full_name") or ""),
        score=float(item.get("score") or 0.0),
        text_matches=tuple(snippets),
    )

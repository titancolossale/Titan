# =====================================
# Titan GitHub Provider
# =====================================

"""GitHub REST API provider — read-only external integration (P10B-601–P10B-606)."""

from __future__ import annotations

import json
import socket
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Callable
from urllib.error import URLError

from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.providers.brave_http_client import (
    HttpTransport,
    UrllibHttpTransport,
    parse_json_body,
)
from tools.providers.credential_manager import CredentialStatus
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_failure import ProviderFailureReason, health_state_for_failure
from tools.providers.provider_health_resolver import resolve_provider_health
from tools.providers.base_provider import BaseProvider
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState

_GITHUB_API_BASE = "https://api.github.com"

_GITHUB_VERSION = ProviderVersionInfo(
    provider_id="github",
    version="1.0.0",
    min_runtime_version="0.10.0",
    api_version="2022-11-28",
    compatible_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
)

_READ_ACTIONS = frozenset({
    "get_authenticated_user",
    "list_repositories",
    "get_repository",
    "list_branches",
    "get_branch",
    "list_commits",
    "get_commit",
    "list_issues",
    "get_issue",
    "list_pull_requests",
    "get_pull_request",
    "get_file_contents",
})

HealthCallback = Callable[[ToolHealthState, str], None]


@dataclass
class GitHubResponse:
    """Structured GitHub operation response."""

    operation: str
    success: bool = True
    data: object = None
    error: str = ""
    provider: str = "github"
    repository: str = ""
    branch: str = ""
    target_path: str = ""
    failure_reason: str = ""
    latency_ms: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    confirmation_required: bool = False

    def format_for_agent(self) -> str:
        """Format response for agent and prompt consumption."""
        if not self.success:
            return f"Opération GitHub échouée ({self.operation}) : {self.error}"
        if isinstance(self.data, (dict, list)):
            return json.dumps(self.data, indent=2, ensure_ascii=False)
        return str(self.data) if self.data is not None else f"{self.operation} réussi."


class GitHubProvider(BaseProvider):
    """Contract for GitHub REST API backends."""

    @property
    def provider_id(self) -> str:
        return "github"

    def capabilities(self) -> frozenset[str]:
        return frozenset({"github"})

    def supported_actions(self) -> frozenset[str]:
        return _READ_ACTIONS

    @abstractmethod
    def execute(self, action: str, **params: object) -> GitHubResponse:
        """Run a read-only GitHub action and return structured results."""


class LiveGitHubProvider(GitHubProvider):
    """GitHub REST API backend — credentials via CredentialManager only (P10B-601)."""

    def __init__(
        self,
        *,
        context: ProviderContext | None = None,
        http_transport: HttpTransport | None = None,
        health_callback: HealthCallback | None = None,
    ) -> None:
        self.context = context
        self._http = http_transport or UrllibHttpTransport()
        self._health_callback = health_callback
        self._last_failure: ProviderFailureReason | None = None

    @property
    def version_info(self) -> ProviderVersionInfo:
        return _GITHUB_VERSION

    def health_check(self) -> ProviderHealth:
        default = ProviderHealth(
            state=ToolHealthState.ONLINE,
            message="GitHub API prêt.",
        )
        if self.context is None or self.context.credential_manager is None:
            return ProviderHealth(
                state=ToolHealthState.MISCONFIGURED,
                message="CredentialManager non injecté.",
            )

        validation = self.context.credential_manager.validate(self.provider_id)
        if validation.status == CredentialStatus.INVALID:
            return ProviderHealth(
                state=ToolHealthState.MISCONFIGURED,
                message=validation.message,
            )
        if validation.status == CredentialStatus.MISSING:
            return ProviderHealth(
                state=ToolHealthState.MISSING_CREDENTIALS,
                message=validation.message,
            )

        return resolve_provider_health(
            self.provider_id,
            context=self.context,
            default_health=default,
            require_credentials_in_live=True,
        )

    def execute(self, action: str, **params: object) -> GitHubResponse:
        """Dispatch a read-only GitHub action (P10B-602, P10B-603)."""
        operation = str(action or params.get("action", "")).strip()
        if operation not in _READ_ACTIONS:
            return self._failure_response(
                operation or "unknown",
                f"Action non autorisée ou inconnue : {operation!r}. "
                "Seules les opérations en lecture seule sont supportées.",
                ProviderFailureReason.UNKNOWN,
            )

        repo_label = self._resolve_repository_label(params)
        branch = str(params.get("branch", "") or "").strip()
        target_path = str(params.get("path", params.get("target_path", "")) or "").strip()

        handlers = {
            "get_authenticated_user": self._get_authenticated_user,
            "list_repositories": self._list_repositories,
            "get_repository": self._get_repository,
            "list_branches": self._list_branches,
            "get_branch": self._get_branch,
            "list_commits": self._list_commits,
            "get_commit": self._get_commit,
            "list_issues": self._list_issues,
            "get_issue": self._get_issue,
            "list_pull_requests": self._list_pull_requests,
            "get_pull_request": self._get_pull_request,
            "get_file_contents": self._get_file_contents,
        }
        handler = handlers[operation]
        response = handler(**params)
        if response.repository == "" and repo_label:
            response.repository = repo_label
        if response.branch == "" and branch:
            response.branch = branch
        if response.target_path == "" and target_path:
            response.target_path = target_path
        return response

    def _get_authenticated_user(self, **params: object) -> GitHubResponse:
        _ = params
        return self._api_get("get_authenticated_user", "/user")

    def _list_repositories(self, **params: object) -> GitHubResponse:
        username = str(params.get("username", "") or "").strip()
        query: dict[str, str] = {}
        per_page = params.get("per_page")
        if per_page is not None:
            query["per_page"] = str(int(per_page))
        if username:
            path = f"/users/{username}/repos"
        else:
            path = "/user/repos"
        return self._api_get("list_repositories", path, params=query)

    def _get_repository(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        return self._api_get(
            "get_repository",
            f"/repos/{owner}/{repo}",
            repository=f"{owner}/{repo}",
        )

    def _list_branches(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        return self._api_get(
            "list_branches",
            f"/repos/{owner}/{repo}/branches",
            repository=f"{owner}/{repo}",
        )

    def _get_branch(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        branch = str(params.get("branch", "") or "").strip()
        if not branch:
            return self._failure_response(
                "get_branch",
                "Paramètre branch requis.",
                ProviderFailureReason.UNKNOWN,
            )
        return self._api_get(
            "get_branch",
            f"/repos/{owner}/{repo}/branches/{branch}",
            repository=f"{owner}/{repo}",
            branch=branch,
        )

    def _list_commits(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        query: dict[str, str] = {}
        branch = str(params.get("branch", "") or "").strip()
        if branch:
            query["sha"] = branch
        return self._api_get(
            "list_commits",
            f"/repos/{owner}/{repo}/commits",
            params=query,
            repository=f"{owner}/{repo}",
            branch=branch,
        )

    def _get_commit(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        sha = str(params.get("sha", params.get("commit_sha", "")) or "").strip()
        if not sha:
            return self._failure_response(
                "get_commit",
                "Paramètre sha requis.",
                ProviderFailureReason.UNKNOWN,
            )
        return self._api_get(
            "get_commit",
            f"/repos/{owner}/{repo}/commits/{sha}",
            repository=f"{owner}/{repo}",
        )

    def _list_issues(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        query: dict[str, str] = {"state": str(params.get("state", "open"))}
        return self._api_get(
            "list_issues",
            f"/repos/{owner}/{repo}/issues",
            params=query,
            repository=f"{owner}/{repo}",
        )

    def _get_issue(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        issue_number = params.get("issue_number", params.get("number"))
        if issue_number is None:
            return self._failure_response(
                "get_issue",
                "Paramètre issue_number requis.",
                ProviderFailureReason.UNKNOWN,
            )
        return self._api_get(
            "get_issue",
            f"/repos/{owner}/{repo}/issues/{int(issue_number)}",
            repository=f"{owner}/{repo}",
        )

    def _list_pull_requests(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        query: dict[str, str] = {"state": str(params.get("state", "open"))}
        return self._api_get(
            "list_pull_requests",
            f"/repos/{owner}/{repo}/pulls",
            params=query,
            repository=f"{owner}/{repo}",
        )

    def _get_pull_request(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        pull_number = params.get("pull_number", params.get("number"))
        if pull_number is None:
            return self._failure_response(
                "get_pull_request",
                "Paramètre pull_number requis.",
                ProviderFailureReason.UNKNOWN,
            )
        return self._api_get(
            "get_pull_request",
            f"/repos/{owner}/{repo}/pulls/{int(pull_number)}",
            repository=f"{owner}/{repo}",
        )

    def _get_file_contents(self, **params: object) -> GitHubResponse:
        owner, repo, err = self._require_owner_repo(params)
        if err is not None:
            return err
        path = str(params.get("path", params.get("target_path", "")) or "").strip()
        if not path:
            return self._failure_response(
                "get_file_contents",
                "Paramètre path requis.",
                ProviderFailureReason.UNKNOWN,
            )
        query: dict[str, str] = {}
        ref = str(params.get("ref", params.get("branch", "")) or "").strip()
        if ref:
            query["ref"] = ref
        return self._api_get(
            "get_file_contents",
            f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}",
            params=query,
            repository=f"{owner}/{repo}",
            branch=ref,
            target_path=path,
        )

    def _api_get(
        self,
        operation: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        repository: str = "",
        branch: str = "",
        target_path: str = "",
    ) -> GitHubResponse:
        credential_error = self._validate_credentials_before_execution(operation)
        if credential_error is not None:
            return credential_error

        token = self._get_token()
        if not token:
            return self._failure_response(
                operation,
                "Token GitHub manquant.",
                ProviderFailureReason.INVALID_KEY,
                repository=repository,
                branch=branch,
                target_path=target_path,
            )

        url = f"{_GITHUB_API_BASE}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Titan-Agent",
        }
        request_timeout = self._resolve_timeout(None)

        start = time.perf_counter()
        try:
            http_response = self._http.get(
                url,
                headers=headers,
                params=params or {},
                timeout=request_timeout,
            )
        except TimeoutError:
            return self._failure_response(
                operation,
                "Délai dépassé lors de l'appel GitHub.",
                ProviderFailureReason.TIMEOUT,
                repository=repository,
                branch=branch,
                target_path=target_path,
            )
        except (URLError, socket.timeout, OSError) as exc:
            reason = self._classify_network_error(exc)
            return self._failure_response(
                operation,
                f"Erreur réseau GitHub : {exc}",
                reason,
                repository=repository,
                branch=branch,
                target_path=target_path,
            )

        latency_ms = (time.perf_counter() - start) * 1000.0
        failure = self._classify_http_failure(http_response.status_code, http_response.body)
        if failure is not None:
            message = self._extract_error_message(http_response.body) or failure.value
            return self._failure_response(
                operation,
                message,
                failure,
                latency_ms=latency_ms,
                repository=repository,
                branch=branch,
                target_path=target_path,
            )

        payload = parse_json_body(http_response.body)
        if not payload and http_response.body.strip():
            try:
                payload = json.loads(http_response.body)
            except json.JSONDecodeError:
                payload = http_response.body

        self._last_failure = None
        self._emit_health(ToolHealthState.ONLINE, "GitHub opérationnel.")

        return GitHubResponse(
            operation=operation,
            success=True,
            data=payload,
            provider=self.provider_id,
            repository=repository,
            branch=branch,
            target_path=target_path,
            latency_ms=latency_ms,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
        )

    def _validate_credentials_before_execution(self, operation: str) -> GitHubResponse | None:
        if self.context is None or self.context.credential_manager is None:
            return self._failure_response(
                operation,
                "CredentialManager non disponible.",
                ProviderFailureReason.INVALID_KEY,
            )
        validation = self.context.credential_manager.validate(self.provider_id)
        if validation.status == CredentialStatus.CONFIGURED:
            return None
        reason = ProviderFailureReason.INVALID_KEY
        if validation.status == CredentialStatus.MISSING:
            reason = ProviderFailureReason.INVALID_KEY
        return self._failure_response(operation, validation.message, reason)

    def _get_token(self) -> str | None:
        if self.context is None or self.context.credential_manager is None:
            return None
        return self.context.credential_manager.get_secret(self.provider_id, "token")

    def _resolve_timeout(self, timeout: float | None) -> float:
        if timeout is not None and timeout > 0:
            return float(timeout)
        if self.context is not None and self.context.configuration is not None:
            return float(self.context.configuration.timeout_seconds)
        return 30.0

    @staticmethod
    def _require_owner_repo(
        params: dict[str, object],
    ) -> tuple[str, str, GitHubResponse | None]:
        owner = str(params.get("owner", "") or "").strip()
        repo = str(params.get("repo", "") or "").strip()
        repository = str(params.get("repository", "") or "").strip()
        if repository and "/" in repository:
            parts = repository.split("/", 1)
            owner = owner or parts[0].strip()
            repo = repo or parts[1].strip()
        if not owner or not repo:
            return "", "", GitHubResponse(
                operation=str(params.get("action", "")),
                success=False,
                error="Paramètres owner et repo requis (ou repository='owner/repo').",
                provider="github",
                failure_reason=ProviderFailureReason.UNKNOWN.value,
            )
        return owner, repo, None

    @staticmethod
    def _resolve_repository_label(params: dict[str, object]) -> str:
        repository = str(params.get("repository", "") or "").strip()
        if repository:
            return repository
        owner = str(params.get("owner", "") or "").strip()
        repo = str(params.get("repo", "") or "").strip()
        if owner and repo:
            return f"{owner}/{repo}"
        return ""

    @staticmethod
    def _classify_http_failure(
        status_code: int,
        body: str,
    ) -> ProviderFailureReason | None:
        if 200 <= status_code < 300:
            return None
        lowered = body.lower()
        if status_code in (401, 403) or "bad credentials" in lowered or "invalid" in lowered:
            return ProviderFailureReason.INVALID_KEY
        if status_code == 429 or "rate limit" in lowered:
            return ProviderFailureReason.RATE_LIMIT
        if status_code in (502, 503, 504):
            return ProviderFailureReason.OFFLINE
        if status_code >= 500:
            return ProviderFailureReason.OFFLINE
        if status_code == 408:
            return ProviderFailureReason.TIMEOUT
        return ProviderFailureReason.UNKNOWN

    @staticmethod
    def _classify_network_error(exc: BaseException) -> ProviderFailureReason:
        if isinstance(exc, socket.timeout):
            return ProviderFailureReason.TIMEOUT
        if isinstance(exc, URLError):
            reason = getattr(exc, "reason", None)
            if isinstance(reason, socket.timeout):
                return ProviderFailureReason.TIMEOUT
            if reason is not None and "timed out" in str(reason).lower():
                return ProviderFailureReason.TIMEOUT
        message = str(exc).lower()
        if "timed out" in message or "timeout" in message:
            return ProviderFailureReason.TIMEOUT
        if "network" in message or "connection refused" in message:
            return ProviderFailureReason.NETWORK_ERROR
        if "offline" in message or "unreachable" in message:
            return ProviderFailureReason.OFFLINE
        return ProviderFailureReason.NETWORK_ERROR

    @staticmethod
    def _extract_error_message(body: str) -> str:
        payload = parse_json_body(body)
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _failure_response(
        self,
        operation: str,
        message: str,
        reason: ProviderFailureReason,
        *,
        latency_ms: float = 0.0,
        repository: str = "",
        branch: str = "",
        target_path: str = "",
    ) -> GitHubResponse:
        self._last_failure = reason
        health = health_state_for_failure(reason)
        self._emit_health(health, message)
        return GitHubResponse(
            operation=operation,
            success=False,
            error=message,
            provider=self.provider_id,
            repository=repository,
            branch=branch,
            target_path=target_path,
            failure_reason=reason.value,
            latency_ms=latency_ms,
            risk_level=RiskLevel.LOW,
            confirmation_required=False,
        )

    def _emit_health(self, state: ToolHealthState, message: str) -> None:
        if self._health_callback is not None:
            self._health_callback(state, message)

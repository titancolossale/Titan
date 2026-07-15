# =====================================
# Titan GitHub Provider Tests
# =====================================

"""Tests for Phase 10B Batch 6 — GitHub provider integration (P10B-601–P10B-606)."""

from __future__ import annotations

import json

import pytest

from tools.decision.execution_context import enrich_decision_report_from_result
from tools.decision.models import ToolDecisionReport, enrich_github_decision_context
from tools.decision.intent import Intent
from tools.github_tool import GitHubTool
from tools.health_monitor import HealthMonitor
from tools.providers.brave_http_client import HttpResponse, MockHttpTransport
from tools.providers.credential_manager import (
    CredentialManager,
    CredentialStatus,
    validate_github_token,
)
from tools.providers.github_provider import LiveGitHubProvider
from tools.providers.provider_configuration import ProviderConfigurationStore
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_failure import ProviderFailureReason
from tools.providers.provider_registry import ProviderRegistry
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState
from tools.tool_manager import ToolManager

_VALID_TOKEN = "ghp_test_github_token_abcdefghijklmnopqrstuvwxyz"
_GITHUB_BASE = "https://api.github.com"


def _github_env(token: str = _VALID_TOKEN) -> dict[str, str | None]:
    return {"TITAN_GITHUB_TOKEN": token}


def _user_body() -> str:
    return json.dumps({"login": "titan-user", "id": 1, "type": "User"})


def _repos_body() -> str:
    return json.dumps([{"name": "Titan", "full_name": "titan-org/Titan", "private": False}])


def _repo_body() -> str:
    return json.dumps(
        {
            "name": "Titan",
            "full_name": "titan-org/Titan",
            "default_branch": "main",
        },
    )


def _branches_body() -> str:
    return json.dumps([{"name": "main"}, {"name": "develop"}])


def _branch_body() -> str:
    return json.dumps({"name": "main", "commit": {"sha": "abc123"}})


def _commits_body() -> str:
    return json.dumps([{"sha": "abc123", "commit": {"message": "Initial commit"}}])


def _commit_body() -> str:
    return json.dumps({"sha": "abc123", "commit": {"message": "Initial commit"}})


def _issues_body() -> str:
    return json.dumps([{"number": 1, "title": "Bug report", "state": "open"}])


def _issue_body() -> str:
    return json.dumps({"number": 1, "title": "Bug report", "state": "open"})


def _pulls_body() -> str:
    return json.dumps([{"number": 42, "title": "Feature PR", "state": "open"}])


def _pull_body() -> str:
    return json.dumps({"number": 42, "title": "Feature PR", "state": "open"})


def _file_body() -> str:
    return json.dumps(
        {
            "name": "README.md",
            "path": "README.md",
            "content": "dGl0YW4=",
            "encoding": "base64",
        },
    )


def _mock_responses() -> dict[str, HttpResponse]:
    return {
        f"{_GITHUB_BASE}/repos/titan-org/Titan/contents/README.md": HttpResponse(
            status_code=200,
            body=_file_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan/pulls/42": HttpResponse(
            status_code=200,
            body=_pull_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan/pulls": HttpResponse(
            status_code=200,
            body=_pulls_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan/issues/1": HttpResponse(
            status_code=200,
            body=_issue_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan/issues": HttpResponse(
            status_code=200,
            body=_issues_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan/commits/abc123": HttpResponse(
            status_code=200,
            body=_commit_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan/commits": HttpResponse(
            status_code=200,
            body=_commits_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan/branches/main": HttpResponse(
            status_code=200,
            body=_branch_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan/branches": HttpResponse(
            status_code=200,
            body=_branches_body(),
        ),
        f"{_GITHUB_BASE}/repos/titan-org/Titan": HttpResponse(
            status_code=200,
            body=_repo_body(),
        ),
        f"{_GITHUB_BASE}/user/repos": HttpResponse(status_code=200, body=_repos_body()),
        f"{_GITHUB_BASE}/user": HttpResponse(status_code=200, body=_user_body()),
    }


@pytest.fixture
def github_registry() -> ProviderRegistry:
    credential_manager = CredentialManager(env=_github_env())
    configuration_store = ProviderConfigurationStore.from_defaults()
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(credential_manager, configuration_store)
    transport = MockHttpTransport(responses=_mock_responses())
    context = ProviderContext(
        credential_manager=credential_manager,
        configuration=configuration_store.get_or_default("github"),
    )
    registry.register(LiveGitHubProvider(context=context, http_transport=transport))
    return registry


def _repo_params() -> dict[str, str]:
    return {"owner": "titan-org", "repo": "Titan"}


def test_get_authenticated_user(github_registry: ProviderRegistry) -> None:
    """P10B-602: get_authenticated_user returns user profile."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("get_authenticated_user")
    assert response.success
    assert response.provider == "github"
    assert isinstance(response.data, dict)
    assert response.data["login"] == "titan-user"


def test_list_repositories(github_registry: ProviderRegistry) -> None:
    """P10B-602: list_repositories returns repository list."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("list_repositories")
    assert response.success
    assert isinstance(response.data, list)
    assert response.data[0]["name"] == "Titan"


def test_get_repository(github_registry: ProviderRegistry) -> None:
    """P10B-602: get_repository returns repository metadata."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("get_repository", **_repo_params())
    assert response.success
    assert response.repository == "titan-org/Titan"
    assert response.data["default_branch"] == "main"


def test_list_branches(github_registry: ProviderRegistry) -> None:
    """P10B-602: list_branches returns branch list."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("list_branches", **_repo_params())
    assert response.success
    assert response.repository == "titan-org/Titan"
    assert len(response.data) == 2


def test_get_branch(github_registry: ProviderRegistry) -> None:
    """P10B-602: get_branch returns branch metadata."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("get_branch", branch="main", **_repo_params())
    assert response.success
    assert response.branch == "main"
    assert response.data["name"] == "main"


def test_list_commits(github_registry: ProviderRegistry) -> None:
    """P10B-602: list_commits returns commit list."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("list_commits", **_repo_params())
    assert response.success
    assert isinstance(response.data, list)


def test_get_commit(github_registry: ProviderRegistry) -> None:
    """P10B-602: get_commit returns commit metadata."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("get_commit", sha="abc123", **_repo_params())
    assert response.success
    assert response.data["sha"] == "abc123"


def test_list_issues(github_registry: ProviderRegistry) -> None:
    """P10B-602: list_issues returns issue list."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("list_issues", **_repo_params())
    assert response.success
    assert response.data[0]["number"] == 1


def test_get_issue(github_registry: ProviderRegistry) -> None:
    """P10B-602: get_issue returns issue metadata."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("get_issue", issue_number=1, **_repo_params())
    assert response.success
    assert response.data["title"] == "Bug report"


def test_list_pull_requests(github_registry: ProviderRegistry) -> None:
    """P10B-602: list_pull_requests returns PR list."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("list_pull_requests", **_repo_params())
    assert response.success
    assert response.data[0]["number"] == 42


def test_get_pull_request(github_registry: ProviderRegistry) -> None:
    """P10B-602: get_pull_request returns PR metadata."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("get_pull_request", pull_number=42, **_repo_params())
    assert response.success
    assert response.data["title"] == "Feature PR"


def test_get_file_contents(github_registry: ProviderRegistry) -> None:
    """P10B-602: get_file_contents returns file metadata."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute(
        "get_file_contents",
        path="README.md",
        **_repo_params(),
    )
    assert response.success
    assert response.target_path == "README.md"
    assert response.data["name"] == "README.md"


def test_write_action_rejected() -> None:
    """P10B-603: Write/mutation operations are rejected."""
    manager = CredentialManager(env=_github_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("github"),
    )
    provider = LiveGitHubProvider(context=context, http_transport=MockHttpTransport())
    for forbidden in (
        "create_issue",
        "create_pull_request",
        "create_commit",
        "create_branch",
        "update_file",
        "delete_repository",
    ):
        response = provider.execute(forbidden, owner="a", repo="b")
        assert not response.success
        assert "non autorisée" in response.error.lower() or "inconnue" in response.error.lower()


def test_missing_credentials() -> None:
    """P10B-604: Missing credentials map to MISSING_CREDENTIALS without crash."""
    manager = CredentialManager(env={})
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("github"),
    )
    provider = LiveGitHubProvider(context=context, http_transport=MockHttpTransport())
    health = provider.health_check()
    assert health.state == ToolHealthState.MISSING_CREDENTIALS

    response = provider.execute("get_authenticated_user")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.INVALID_KEY.value


def test_invalid_token() -> None:
    """P10B-604: Invalid token maps to INVALID_KEY."""
    transport = MockHttpTransport(
        responses={
            f"{_GITHUB_BASE}/user": HttpResponse(
                status_code=401,
                body='{"message":"Bad credentials"}',
            ),
        },
    )
    manager = CredentialManager(env=_github_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("github"),
    )
    provider = LiveGitHubProvider(context=context, http_transport=transport)
    response = provider.execute("get_authenticated_user")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.INVALID_KEY.value


def test_rate_limit() -> None:
    """P10B-604: Rate limit maps to RATE_LIMIT."""
    transport = MockHttpTransport(
        responses={
            f"{_GITHUB_BASE}/user": HttpResponse(
                status_code=429,
                body='{"message":"API rate limit exceeded"}',
            ),
        },
    )
    manager = CredentialManager(env=_github_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("github"),
    )
    provider = LiveGitHubProvider(context=context, http_transport=transport)
    response = provider.execute("get_authenticated_user")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.RATE_LIMIT.value


def test_offline() -> None:
    """P10B-604: Service unavailable maps to OFFLINE."""
    transport = MockHttpTransport(
        responses={
            f"{_GITHUB_BASE}/user": HttpResponse(
                status_code=503,
                body='{"message":"service unavailable"}',
            ),
        },
    )
    manager = CredentialManager(env=_github_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("github"),
    )
    provider = LiveGitHubProvider(context=context, http_transport=transport)
    response = provider.execute("get_authenticated_user")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.OFFLINE.value


def test_network_error() -> None:
    """P10B-604: Network errors map to NETWORK_ERROR."""
    def _network_error(**kwargs: object) -> HttpResponse:
        raise OSError("network unreachable")

    transport = MockHttpTransport(side_effect=_network_error)
    manager = CredentialManager(env=_github_env())
    context = ProviderContext(
        credential_manager=manager,
        configuration=ProviderConfigurationStore.from_defaults().get_or_default("github"),
    )
    provider = LiveGitHubProvider(context=context, http_transport=transport)
    response = provider.execute("get_authenticated_user")
    assert not response.success
    assert response.failure_reason == ProviderFailureReason.NETWORK_ERROR.value


def test_provider_health_updates_on_failure(github_registry: ProviderRegistry) -> None:
    """P10B-604: ProviderExecutor updates health on failure without crashing runtime."""
    transport = MockHttpTransport(
        responses={
            f"{_GITHUB_BASE}/user": HttpResponse(
                status_code=429,
                body='{"message":"rate limit"}',
            ),
        },
    )
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    provider._http = transport  # noqa: SLF001 — test injection

    monitor = HealthMonitor()
    github_registry.sync_health(monitor)
    executor = ProviderExecutor(registry=github_registry, health_monitor=monitor)

    outcome = executor.execute("get_authenticated_user", {}, capability="github")
    assert not outcome.success
    assert monitor.get_provider_health("github") == ToolHealthState.DEGRADED


def test_provider_health_online_after_success(github_registry: ProviderRegistry) -> None:
    """P10B-604: Successful execution marks provider ONLINE."""
    monitor = HealthMonitor()
    github_registry.sync_health(monitor)
    executor = ProviderExecutor(registry=github_registry, health_monitor=monitor)

    outcome = executor.execute("get_authenticated_user", {}, capability="github")
    assert outcome.success
    assert outcome.provider_id == "github"
    assert monitor.get_provider_health("github") == ToolHealthState.ONLINE


def test_credential_validation_github() -> None:
    """P10B-601: CredentialManager validates GitHub token without exposing it."""
    manager = CredentialManager(env=_github_env())
    result = manager.validate("github")
    assert result.status == CredentialStatus.CONFIGURED
    assert _VALID_TOKEN not in str(result.to_public_dict().values())

    invalid = CredentialManager(env={"TITAN_GITHUB_TOKEN": "your_token_here"})
    invalid_result = invalid.validate("github")
    assert invalid_result.status == CredentialStatus.INVALID

    missing = CredentialManager(env={})
    missing_result = missing.validate("github")
    assert missing_result.status == CredentialStatus.MISSING


def test_validate_github_token_helper() -> None:
    """P10B-601: GitHub token validator rejects placeholders and short keys."""
    assert validate_github_token(_VALID_TOKEN)
    assert not validate_github_token("short")
    assert not validate_github_token("your_token_here")


def test_decision_report_github_fields() -> None:
    """P10B-605: DecisionReport includes GitHub metadata."""
    report = ToolDecisionReport(
        intent=Intent.CODING,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="github",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
    )
    enriched = enrich_github_decision_context(
        report,
        github_operation="get_repository",
        repository="titan-org/Titan",
        branch="main",
        target_path="README.md",
        execution_mode="live",
    )
    assert enriched.selected_provider == "github"
    assert enriched.github_operation == "get_repository"
    assert enriched.repository == "titan-org/Titan"
    assert enriched.branch == "main"
    assert enriched.target_path == "README.md"
    assert enriched.execution_mode == "live"
    assert enriched.risk_level == RiskLevel.LOW
    assert enriched.confirmation_required is False


def test_decision_report_enriched_from_tool_result(github_registry: ProviderRegistry) -> None:
    """P10B-605: Provider execution enriches GitHub fields on DecisionReport."""
    report = ToolDecisionReport(
        intent=Intent.CODING,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="github",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
    )
    executor = ProviderExecutor(registry=github_registry, health_monitor=HealthMonitor())
    outcome = executor.execute(
        "get_repository",
        _repo_params(),
        capability="github",
    )
    assert outcome.success

    enriched = enrich_decision_report_from_result(
        report,
        {
            "provider_id": outcome.provider_id,
            "provider_score": outcome.provider_score,
            "provider_health": outcome.provider_health.value,
            "provider_version": outcome.provider_version,
            "execution_path": list(outcome.execution_path),
            "duration_ms": outcome.duration_ms,
            "github_operation": "get_repository",
            "repository": "titan-org/Titan",
            "branch": "main",
            "target_path": "",
            "execution_mode": ExecutionMode.LIVE.value,
            "risk_level": RiskLevel.LOW.value,
            "confirmation_required": False,
        },
    )
    assert enriched is not None
    assert enriched.selected_provider == "github"
    assert enriched.github_operation == "get_repository"
    assert enriched.repository == "titan-org/Titan"
    assert enriched.provider_latency_ms is not None
    assert enriched.provider_health == "online"


def test_github_tool_via_executor(github_registry: ProviderRegistry) -> None:
    """P10B-601: GitHubTool executes provider through ProviderExecutor."""
    executor = ProviderExecutor(registry=github_registry, health_monitor=HealthMonitor())
    tool = GitHubTool(provider_executor=executor)
    result = tool.run(action="get_repository", owner="titan-org", repo="Titan")
    assert result.success
    assert result.metadata.get("provider_id") == "github"
    assert result.metadata.get("github_operation") == "get_repository"
    assert result.metadata.get("repository") == "titan-org/Titan"
    assert "Titan" in str(result.data)


def test_mock_http_records_calls(github_registry: ProviderRegistry) -> None:
    """P10B-606: Mock HTTP layer captures requests without real API calls."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    transport = provider._http  # noqa: SLF001
    assert isinstance(transport, MockHttpTransport)
    provider.execute("get_authenticated_user")
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert str(call["url"]).startswith(_GITHUB_BASE)
    auth_header = call["headers"]["Authorization"]
    assert auth_header == f"Bearer {_VALID_TOKEN}"
    assert _VALID_TOKEN not in str(call).replace(auth_header, "")


def test_missing_credentials_blocked_from_selection() -> None:
    """Regression: GitHub without credentials is blocked from selection."""
    credential_manager = CredentialManager(env={})
    configuration_store = ProviderConfigurationStore.from_defaults()
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.attach_bootstrap(credential_manager, configuration_store)
    context = ProviderContext(
        credential_manager=credential_manager,
        configuration=configuration_store.get_or_default("github"),
    )
    registry.register(LiveGitHubProvider(context=context, http_transport=MockHttpTransport()))

    health = registry.probe("github")
    assert health.state == ToolHealthState.MISSING_CREDENTIALS

    executor = ProviderExecutor(registry=registry, health_monitor=HealthMonitor())
    outcome = executor.execute("get_authenticated_user", {}, capability="github")
    assert not outcome.success
    assert outcome.no_capability or not outcome.success


def test_tool_manager_registers_github() -> None:
    """Legacy compatibility: ToolManager registers github tool by default."""
    manager = ToolManager()
    assert "github" in manager.list_tools()


def test_read_only_risk_metadata(github_registry: ProviderRegistry) -> None:
    """P10B-603: Read-only operations report LOW risk and no confirmation."""
    provider = github_registry.get("github")
    assert isinstance(provider, LiveGitHubProvider)
    response = provider.execute("get_repository", **_repo_params())
    assert response.risk_level == RiskLevel.LOW
    assert response.confirmation_required is False

# =====================================
# Titan GitHub Tool
# =====================================

"""GitHub tool via ProviderExecutor — read-only registry-authoritative (P10B-601)."""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.providers.github_provider import GitHubResponse
from tools.providers.provider_executor import (
    ProviderExecutionContext,
    ProviderExecutor,
    provider_outcome_metadata,
)
from tools.tool_enums import RiskLevel
from tools.tool_result import ToolResult


class GitHubTool(BaseTool):
    """GitHub REST access through ProviderRegistry-backed execution."""

    def __init__(
        self,
        *,
        provider_executor: ProviderExecutor | None = None,
    ) -> None:
        self._executor = provider_executor

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="github",
            description="Accès GitHub en lecture seule via provider abstrait.",
            parameters=[
                ToolParameter(
                    name="action",
                    param_type="string",
                    description=(
                        "Opération GitHub (get_authenticated_user, list_repositories, "
                        "get_repository, list_branches, get_branch, list_commits, "
                        "get_commit, list_issues, get_issue, list_pull_requests, "
                        "get_pull_request, get_file_contents)."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="owner",
                    param_type="string",
                    description="Propriétaire du dépôt.",
                    required=False,
                ),
                ToolParameter(
                    name="repo",
                    param_type="string",
                    description="Nom du dépôt.",
                    required=False,
                ),
                ToolParameter(
                    name="repository",
                    param_type="string",
                    description="Dépôt au format owner/repo.",
                    required=False,
                ),
                ToolParameter(
                    name="branch",
                    param_type="string",
                    description="Nom de branche.",
                    required=False,
                ),
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Chemin du fichier dans le dépôt.",
                    required=False,
                ),
                ToolParameter(
                    name="sha",
                    param_type="string",
                    description="SHA du commit.",
                    required=False,
                ),
                ToolParameter(
                    name="issue_number",
                    param_type="integer",
                    description="Numéro d'issue.",
                    required=False,
                ),
                ToolParameter(
                    name="pull_number",
                    param_type="integer",
                    description="Numéro de pull request.",
                    required=False,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        action = str(params.get("action", "")).strip()
        if not action:
            return self._result(success=False, error="Action GitHub requise.")

        if self._executor is None:
            return self._result(
                success=False,
                error="ProviderExecutor non configuré — exécution impossible.",
            )

        exec_params = dict(params)
        exec_params["action"] = action
        ctx_meta = exec_params.pop("_execution_context", {}) or {}
        if not isinstance(ctx_meta, dict):
            ctx_meta = {}

        ctx = ProviderExecutionContext.from_tool_metadata(
            action=action,
            params=exec_params,
            tool_name=self.name,
            ctx_meta=ctx_meta,
        )
        outcome = self._executor.execute(
            action,
            exec_params,
            capability="github",
            context=ctx,
            execution_mode=ctx.execution_mode,
        )

        if outcome.no_capability or outcome.provider_unavailable:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=outcome.error,
                source="provider_executor",
                metadata=provider_outcome_metadata(outcome),
            )

        if not outcome.success:
            return self._result(success=False, error=outcome.error)

        response = outcome.data
        if not isinstance(response, GitHubResponse):
            return self._result(success=False, error="Réponse provider GitHub invalide.")

        metadata = provider_outcome_metadata(outcome)
        metadata.update(
            {
                "github_operation": response.operation,
                "repository": response.repository,
                "branch": response.branch,
                "target_path": response.target_path,
                "execution_mode": ctx.execution_mode.value,
                "risk_level": RiskLevel.LOW.value,
                "confirmation_required": False,
            },
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=response.format_for_agent(),
            source=f"github/{outcome.provider_id}",
            metadata=metadata,
        )

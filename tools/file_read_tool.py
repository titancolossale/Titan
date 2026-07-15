# =====================================
# Titan File Read Tool
# =====================================

"""Filesystem operations via FileSystemProvider — registry-authoritative (P10B-501, P10B-1502)."""

from __future__ import annotations

from pathlib import Path

from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.path_guard import PathGuardError, resolve_allowed_path
from tools.providers.file_system_provider import FileSystemResponse
from tools.providers.provider_executor import (
    ProviderExecutionContext,
    ProviderExecutor,
    provider_outcome_metadata,
)
from tools.tool_enums import ExecutionMode
from tools.tool_result import ToolResult

_SUPPORTED_ACTIONS = frozenset({
    "read_file",
    "list_directory",
    "search_files",
    "get_metadata",
    "file_exists",
})


class FileReadTool(BaseTool):
    """Read and query project files through ProviderExecutor with legacy fallback."""

    def __init__(
        self,
        project_root: Path,
        *,
        provider_executor: ProviderExecutor | None = None,
    ) -> None:
        self._project_root = project_root
        self._executor = provider_executor

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="file_read",
            description="Lit, liste ou recherche des fichiers dans le projet.",
            parameters=[
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Chemin relatif ou absolu sous la racine du projet.",
                    required=False,
                ),
                ToolParameter(
                    name="action",
                    param_type="string",
                    description="Action filesystem: read_file, list_directory, search_files, get_metadata.",
                    required=False,
                ),
                ToolParameter(
                    name="directory",
                    param_type="string",
                    description="Répertoire racine pour search_files.",
                    required=False,
                ),
                ToolParameter(
                    name="pattern",
                    param_type="string",
                    description="Motif glob pour search_files.",
                    required=False,
                ),
                ToolParameter(
                    name="extension",
                    param_type="string",
                    description="Extension filtrée pour list_directory.",
                    required=False,
                ),
                ToolParameter(
                    name="keyword",
                    param_type="string",
                    description="Mot-clé à chercher dans le contenu des fichiers.",
                    required=False,
                ),
                ToolParameter(
                    name="recursive",
                    param_type="boolean",
                    description="Recherche récursive sous le répertoire.",
                    required=False,
                ),
                ToolParameter(
                    name="max_results",
                    param_type="integer",
                    description="Nombre maximal de résultats.",
                    required=False,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        action = str(params.get("action", "read_file")).strip() or "read_file"
        if action not in _SUPPORTED_ACTIONS:
            return self._result(
                success=False,
                error=f"Action non supportée : {action!r}",
            )
        if self._executor is None:
            if action != "read_file":
                return self._result(
                    success=False,
                    error="Opération disponible uniquement via ProviderExecutor.",
                )
            path = str(params.get("path", ""))
            return self._run_legacy(path)
        return self._run_via_provider(action, params)

    def _run_legacy(self, path: str) -> ToolResult:
        try:
            resolved = resolve_allowed_path(path, self._project_root, must_exist=True)
            content = resolved.read_text(encoding="utf-8")
        except PathGuardError as exc:
            return self._result(success=False, error=str(exc))
        except OSError as exc:
            return self._result(success=False, error=f"Lecture impossible : {exc}")
        return self._result(success=True, data=content)

    def _run_via_provider(self, action: str, params: dict) -> ToolResult:
        exec_params = dict(params)
        exec_params.pop("action", None)
        ctx_meta = exec_params.pop("_execution_context", {}) or {}
        if not isinstance(ctx_meta, dict):
            ctx_meta = {}

        ctx = ProviderExecutionContext.from_tool_metadata(
            action=action,
            params=exec_params,
            tool_name=self.name,
            ctx_meta=ctx_meta,
        )
        exec_params["execution_mode"] = ctx.execution_mode.value
        assert self._executor is not None
        outcome = self._executor.execute(
            action,
            exec_params,
            capability="file_system",
            context=ctx,
            execution_mode=ctx.execution_mode,
        )

        if outcome.no_capability or outcome.provider_unavailable:
            metadata = provider_outcome_metadata(outcome)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=outcome.error,
                source="provider_executor",
                metadata=metadata,
            )

        if not outcome.success:
            return self._result(success=False, error=outcome.error)

        response = outcome.data
        if not isinstance(response, FileSystemResponse):
            return self._result(success=False, error="Réponse provider invalide.")

        if not response.success:
            return self._result(success=False, error=response.error)

        metadata = provider_outcome_metadata(outcome)
        metadata.update(
            {
                "file_operation": response.operation,
                "target_path": response.target_path,
                "execution_mode": ctx.execution_mode.value,
                "confirmation_required": response.confirmation_required,
                "risk_level": response.risk_level.value,
            },
        )
        if response.operation == "search_files" and isinstance(response.data, list):
            metadata["search_results"] = [
                str(item).replace("\\", "/") for item in response.data
            ]
        formatted = self._format_response(response)
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=formatted,
            source=f"file_system/{outcome.provider_id}",
            metadata=metadata,
        )

    @staticmethod
    def _format_response(response: FileSystemResponse) -> str:
        """Format filesystem results for user-facing consumption (P10B-1506)."""
        if response.operation == "read_file":
            return str(response.data)
        if response.operation == "list_directory":
            entries = response.data if isinstance(response.data, list) else []
            if not entries:
                return (
                    f"Aucun fichier trouvé dans {response.target_path or '.'}."
                )
            lines = [f"Fichiers dans {response.target_path or '.'} ({len(entries)}) :"]
            lines.extend(f"  - {name}" for name in entries)
            return "\n".join(lines)
        if response.operation == "search_files":
            matches = response.data if isinstance(response.data, list) else []
            if not matches:
                return (
                    f"Aucun fichier correspondant trouvé sous "
                    f"{response.target_path or '.'}."
                )
            lines = [f"Résultats de recherche ({len(matches)}) :"]
            lines.extend(f"  - {match}" for match in matches)
            return "\n".join(lines)
        if response.operation == "get_metadata":
            return str(response.data)
        return response.format_for_agent()

    @staticmethod
    def _result(*, success: bool, data: str = "", error: str = "") -> ToolResult:
        return ToolResult(
            tool_name="file_read",
            success=success,
            data=data,
            error=error,
        )

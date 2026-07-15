# =====================================
# Titan File Write Tool
# =====================================

"""Write files via FileSystemProvider — confirmation in LIVE (P10B-504)."""

from __future__ import annotations

from pathlib import Path

from config.settings import TOOL_WRITE_DRY_RUN_DEFAULT
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


class FileWriteTool(BaseTool):
    """Write text to a file under the project root via FileSystemProvider."""

    def __init__(
        self,
        project_root: Path,
        *,
        dry_run_default: bool | None = None,
        provider_executor: ProviderExecutor | None = None,
    ) -> None:
        self._project_root = project_root
        self._dry_run_default = (
            TOOL_WRITE_DRY_RUN_DEFAULT if dry_run_default is None else dry_run_default
        )
        self._executor = provider_executor

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="file_write",
            description="Écrit du contenu dans un fichier du projet (dry-run par défaut).",
            parameters=[
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Chemin relatif ou absolu sous la racine du projet.",
                ),
                ToolParameter(
                    name="content",
                    param_type="string",
                    description="Contenu texte à écrire.",
                ),
                ToolParameter(
                    name="dry_run",
                    param_type="boolean",
                    description="Simuler l'écriture sans modifier le disque.",
                    required=False,
                    default=self._dry_run_default,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        path = str(params.get("path", ""))
        content = str(params.get("content", ""))
        dry_run = params.get("dry_run", self._dry_run_default)
        if not isinstance(dry_run, bool):
            dry_run = self._dry_run_default

        if self._executor is None:
            return self._run_legacy(path, content, dry_run)
        return self._run_via_provider(path, content, dry_run, params)

    def _run_legacy(self, path: str, content: str, dry_run: bool) -> ToolResult:
        try:
            resolved = resolve_allowed_path(path, self._project_root, must_exist=False)
        except PathGuardError as exc:
            return self._result(success=False, error=str(exc))

        if dry_run:
            return self._result(
                success=True,
                data=(
                    f"[dry-run] Écriture simulée : {len(content)} caractères "
                    f"→ {resolved.relative_to(self._project_root.resolve())}"
                ),
            )

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except OSError as exc:
            return self._result(success=False, error=f"Écriture impossible : {exc}")

        return self._result(
            success=True,
            data=f"Fichier écrit : {resolved.relative_to(self._project_root.resolve())}",
        )

    def _run_via_provider(
        self,
        path: str,
        content: str,
        dry_run: bool,
        params: dict,
    ) -> ToolResult:
        exec_params = dict(params)
        exec_params["path"] = path
        exec_params["content"] = content
        exec_params["dry_run"] = dry_run
        ctx_meta = exec_params.pop("_execution_context", {}) or {}
        if not isinstance(ctx_meta, dict):
            ctx_meta = {}

        ctx = ProviderExecutionContext.from_tool_metadata(
            action="write_file",
            params=exec_params,
            tool_name=self.name,
            ctx_meta=ctx_meta,
        )
        exec_params["execution_mode"] = ctx.execution_mode.value
        assert self._executor is not None
        outcome = self._executor.execute(
            "write_file",
            exec_params,
            capability="file_system",
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
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=response.data,
            source=f"file_system/{outcome.provider_id}",
            metadata=metadata,
        )

    @staticmethod
    def _provider_metadata(
        outcome,
        response: FileSystemResponse,
        execution_mode: ExecutionMode,
    ) -> dict:
        return {
            "provider_id": outcome.provider_id,
            "provider_version": outcome.provider_version,
            "provider_health": outcome.provider_health.value,
            "provider_score": outcome.provider_score,
            "execution_path": list(outcome.execution_path),
            "duration_ms": outcome.duration_ms,
            "file_operation": response.operation,
            "target_path": response.target_path,
            "execution_mode": execution_mode.value,
            "confirmation_required": response.confirmation_required,
            "risk_level": response.risk_level.value,
            "simulated": response.simulated,
        }

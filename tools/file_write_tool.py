# =====================================
# Titan File Write Tool
# =====================================

"""Write files within project bounds; dry-run by default (Phase 6 — P6-022)."""

from __future__ import annotations

from pathlib import Path

from config.settings import TOOL_WRITE_DRY_RUN_DEFAULT
from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.path_guard import PathGuardError, resolve_allowed_path
from tools.tool_result import ToolResult


class FileWriteTool(BaseTool):
    """Write text to a file under the project root.

    Defaults to dry-run mode until explicit confirmation is wired (Phase 6 v1).
    """

    def __init__(self, project_root: Path, *, dry_run_default: bool | None = None) -> None:
        self._project_root = project_root
        self._dry_run_default = (
            TOOL_WRITE_DRY_RUN_DEFAULT if dry_run_default is None else dry_run_default
        )

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

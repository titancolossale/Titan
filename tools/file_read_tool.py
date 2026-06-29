# =====================================
# Titan File Read Tool
# =====================================

"""Read files within the project directory allowlist (Phase 6 — P6-021)."""

from __future__ import annotations

from pathlib import Path

from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.path_guard import PathGuardError, resolve_allowed_path
from tools.tool_result import ToolResult


class FileReadTool(BaseTool):
    """Read text file contents from paths under the project root."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="file_read",
            description="Lit le contenu d'un fichier texte dans le projet.",
            parameters=[
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Chemin relatif ou absolu sous la racine du projet.",
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        path = str(params.get("path", ""))
        try:
            resolved = resolve_allowed_path(path, self._project_root, must_exist=True)
            content = resolved.read_text(encoding="utf-8")
        except PathGuardError as exc:
            return self._result(success=False, error=str(exc))
        except OSError as exc:
            return self._result(success=False, error=f"Lecture impossible : {exc}")
        return self._result(success=True, data=content)

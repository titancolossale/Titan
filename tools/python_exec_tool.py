# =====================================
# Titan Python Exec Tool
# =====================================

"""Sandboxed Python subprocess execution with timeout (Phase 6 — P6-023)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from config.settings import TOOL_PYTHON_EXEC_TIMEOUT
from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.tool_result import ToolResult


class PythonExecTool(BaseTool):
    """Execute Python code in an isolated subprocess with timeout and cwd restriction."""

    def __init__(
        self,
        project_root: Path,
        *,
        timeout_seconds: int | None = None,
    ) -> None:
        self._project_root = project_root.resolve()
        self._timeout = (
            TOOL_PYTHON_EXEC_TIMEOUT if timeout_seconds is None else timeout_seconds
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="python_exec",
            description="Exécute du code Python dans un sous-processus isolé.",
            parameters=[
                ToolParameter(
                    name="code",
                    param_type="string",
                    description="Code Python à exécuter.",
                ),
                ToolParameter(
                    name="timeout",
                    param_type="integer",
                    description="Délai maximum en secondes.",
                    required=False,
                    default=self._timeout,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        code = str(params.get("code", ""))
        if not code.strip():
            return self._result(success=False, error="Code Python vide.")

        timeout = params.get("timeout", self._timeout)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = self._timeout

        env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=float(timeout),
                cwd=str(self._project_root),
                env=env,
            )
        except subprocess.TimeoutExpired:
            return self._result(
                success=False,
                error=f"Exécution interrompue après {timeout}s (timeout).",
            )
        except OSError as exc:
            return self._result(success=False, error=f"Exécution impossible : {exc}")

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if completed.returncode != 0:
            detail = stderr or stdout or f"code de sortie {completed.returncode}"
            return self._result(success=False, error=detail)

        return self._result(success=True, data=stdout or "(aucune sortie)")

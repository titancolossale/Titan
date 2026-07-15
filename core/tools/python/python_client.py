# =====================================
# Titan Python Runtime Client
# =====================================

"""Sandboxed subprocess execution engine for the Python Runtime tool."""

from __future__ import annotations

import ast
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from core.tools.python.exceptions import (
    PythonConfigurationError,
    PythonOutputTooLargeError,
    PythonPathError,
    PythonSyntaxError,
    PythonWorkspaceLimitError,
)
from core.tools.python.models import (
    ExecutionResult,
    FormatResult,
    SyntaxCheckResult,
    WorkspaceSnapshot,
)
from core.tools.python.python_config import PythonRuntimeConfig

logger = logging.getLogger(__name__)

# Modules that imply network or shell escape — blocked at static analysis time.
_BLOCKED_IMPORT_MODULES = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "http.client",
        "http.server",
        "urllib",
        "urllib.request",
        "urllib.error",
        "urllib.parse",
        "requests",
        "aiohttp",
        "ftplib",
        "smtplib",
        "telnetlib",
        "subprocess",
        "multiprocessing",
        "ctypes",
        "cffi",
        "pty",
        "fcntl",
        "resource",
    }
)

# ``open`` is permitted for workspace files; shell/network helpers are not.
_BLOCKED_ATTRIBUTE_CALLS = frozenset(
    {
        "system",
        "popen",
        "call",
        "run",
        "Popen",
        "check_call",
        "check_output",
    }
)


class PythonRuntimeClient:
    """Execute Python code inside an isolated workspace with safety limits."""

    def __init__(self, config: PythonRuntimeConfig) -> None:
        self._config = config
        self._config.workspace_root.mkdir(parents=True, exist_ok=True)

    @property
    def config(self) -> PythonRuntimeConfig:
        """Return the active runtime configuration."""
        return self._config

    @property
    def workspace_root(self) -> Path:
        """Return the isolated working directory."""
        return self._config.workspace_root

    def run_snippet(
        self,
        code: str,
        *,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """Execute a Python source snippet in the isolated workspace."""
        source = code if isinstance(code, str) else str(code)
        if not source.strip():
            raise PythonConfigurationError("Missing required parameter: code")

        self._static_safety_check(source)
        timeout_seconds = self._config.resolve_timeout(timeout)
        return self._run_subprocess(
            [sys.executable, "-c", source],
            timeout_seconds=timeout_seconds,
            code_preview=source,
        )

    def run_script(
        self,
        path: str,
        *,
        timeout: float | None = None,
        args: list[str] | None = None,
    ) -> ExecutionResult:
        """Execute a Python script file relative to the workspace root."""
        script_path = self.resolve_script_path(path)
        if not script_path.is_file():
            raise PythonPathError(path, "script file does not exist")

        source = script_path.read_text(encoding="utf-8")
        self._static_safety_check(source)

        timeout_seconds = self._config.resolve_timeout(timeout)
        command = [sys.executable, str(script_path)]
        if args:
            command.extend(str(arg) for arg in args)

        return self._run_subprocess(
            command,
            timeout_seconds=timeout_seconds,
            code_preview=source,
        )

    def syntax_check(self, code: str) -> SyntaxCheckResult:
        """Validate Python syntax without executing the code."""
        source = code if isinstance(code, str) else str(code)
        if not source.strip():
            raise PythonConfigurationError("Missing required parameter: code")

        try:
            ast.parse(source, filename="<snippet>")
        except SyntaxError as exc:
            message = exc.msg or str(exc)
            return SyntaxCheckResult(
                valid=False,
                message=message,
                line=exc.lineno,
                offset=exc.offset,
            )

        return SyntaxCheckResult(valid=True, message="Syntax is valid.")

    def format_code(self, code: str) -> FormatResult:
        """Format Python source using a deterministic, dependency-free formatter.

        V1 uses ``ast`` round-trip via a conservative whitespace normalizer so
        Titan does not require an external formatter package. Invalid syntax
        raises ``PythonSyntaxError``.
        """
        source = code if isinstance(code, str) else str(code)
        if not source.strip():
            raise PythonConfigurationError("Missing required parameter: code")

        check = self.syntax_check(source)
        if not check.valid:
            raise PythonSyntaxError(check.message, line=check.line)

        formatted = self._normalize_source(source)
        return FormatResult(
            formatted_code=formatted,
            changed=formatted != source,
            message="Code formatted." if formatted != source else "Code already formatted.",
        )

    def resolve_script_path(self, raw_path: str) -> Path:
        """Resolve a script path and reject traversal outside the workspace."""
        if not raw_path or not str(raw_path).strip():
            raise PythonPathError(str(raw_path), "path is empty")

        candidate = Path(str(raw_path).strip())
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self._config.workspace_root / candidate).resolve()

        try:
            resolved.relative_to(self._config.workspace_root)
        except ValueError as exc:
            raise PythonPathError(
                str(raw_path),
                "path escapes the Python Runtime workspace",
            ) from exc

        return resolved

    def snapshot_workspace(self) -> WorkspaceSnapshot:
        """Return the set of relative file paths currently in the workspace."""
        root = self._config.workspace_root
        files: set[str] = set()
        if not root.exists():
            return WorkspaceSnapshot(files=frozenset())

        for path in root.rglob("*"):
            if path.is_file():
                files.add(path.relative_to(root).as_posix())
        return WorkspaceSnapshot(files=frozenset(files))

    def _run_subprocess(
        self,
        command: list[str],
        *,
        timeout_seconds: float,
        code_preview: str,
    ) -> ExecutionResult:
        before = self.snapshot_workspace()
        if len(before.files) > self._config.max_file_count:
            raise PythonWorkspaceLimitError(self._config.max_file_count)

        env = self._build_safe_env()
        logger.info(
            "Python Runtime starting: timeout=%.2fs workspace=%s code_chars=%d",
            timeout_seconds,
            self._config.workspace_root,
            len(code_preview),
        )

        started = time.perf_counter()
        timed_out = False
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(self._config.workspace_root),
                env=env,
                check=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            exit_code = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            raw_out = exc.stdout
            raw_err = exc.stderr
            stdout = raw_out if isinstance(raw_out, str) else (
                raw_out.decode("utf-8", errors="replace") if isinstance(raw_out, bytes) else ""
            )
            stderr = raw_err if isinstance(raw_err, str) else (
                raw_err.decode("utf-8", errors="replace") if isinstance(raw_err, bytes) else ""
            )
            if not stderr:
                stderr = f"Execution interrupted after {timeout_seconds}s (timeout)."
            exit_code = -1
        except OSError as exc:
            raise PythonConfigurationError(f"Execution impossible: {exc}") from exc

        duration = time.perf_counter() - started
        stdout, stderr, truncated = self._truncate_outputs(stdout, stderr)

        after = self.snapshot_workspace()
        if len(after.files) > self._config.max_file_count:
            raise PythonWorkspaceLimitError(self._config.max_file_count)

        created = tuple(sorted(after.files - before.files))
        logger.info(
            "Python Runtime finished: exit_code=%s duration=%.3fs "
            "files_created=%s truncated=%s timed_out=%s",
            exit_code,
            duration,
            created,
            truncated,
            timed_out,
        )
        if timed_out:
            logger.warning(
                "Python Runtime timeout: duration=%.3fs files_created=%s",
                duration,
                created,
            )
        elif exit_code != 0:
            logger.warning(
                "Python Runtime error output: stderr_chars=%d stdout_chars=%d",
                len(stderr),
                len(stdout),
            )

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration=duration,
            files_created=created,
            timed_out=timed_out,
            truncated=truncated,
        )

    def _truncate_outputs(self, stdout: str, stderr: str) -> tuple[str, str, bool]:
        max_bytes = self._config.max_output_bytes
        # Split budget evenly between streams while enforcing a combined cap.
        half = max(512, max_bytes // 2)
        truncated = False

        stdout_bytes = stdout.encode("utf-8", errors="replace")
        stderr_bytes = stderr.encode("utf-8", errors="replace")

        if len(stdout_bytes) > half:
            stdout = stdout_bytes[:half].decode("utf-8", errors="replace") + "\n...[truncated]"
            truncated = True
        if len(stderr_bytes) > half:
            stderr = stderr_bytes[:half].decode("utf-8", errors="replace") + "\n...[truncated]"
            truncated = True

        combined = len(stdout.encode("utf-8", errors="replace")) + len(
            stderr.encode("utf-8", errors="replace")
        )
        if combined > max_bytes:
            # Hard fail only when even truncated streams exceed the absolute cap.
            raise PythonOutputTooLargeError(max_bytes)

        return stdout, stderr, truncated

    def _build_safe_env(self) -> dict[str, str]:
        """Build a minimal environment — no inherited secrets, no network helpers."""
        env: dict[str, str] = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            # Discourage accidental network use by common libraries.
            "NO_PROXY": "*",
            "no_proxy": "*",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "http_proxy": "",
            "https_proxy": "",
            "all_proxy": "",
        }
        if sys.platform == "win32":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
            env["COMSPEC"] = os.environ.get("COMSPEC", "")
            env["PATHEXT"] = os.environ.get("PATHEXT", "")
        else:
            env["HOME"] = os.environ.get("HOME", "")
            env["LANG"] = os.environ.get("LANG", "C.UTF-8")

        # Never forward API keys or Titan secrets into the sandbox.
        return env

    def _static_safety_check(self, source: str) -> None:
        """Reject code that clearly attempts network or shell escape."""
        try:
            tree = ast.parse(source, filename="<snippet>")
        except SyntaxError:
            # Syntax errors are reported by the caller / syntax_check action.
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._reject_import(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self._reject_import(module)
            elif isinstance(node, ast.Call):
                self._reject_call(node)

    def _reject_import(self, module_name: str) -> None:
        root = module_name.split(".", 1)[0]
        if module_name in _BLOCKED_IMPORT_MODULES or root in _BLOCKED_IMPORT_MODULES:
            raise PythonConfigurationError(
                f"Import of '{module_name}' is blocked by Python Runtime V1 "
                "(no network or shell access)."
            )

    def _reject_call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"eval", "exec", "compile", "__import__"}:
            raise PythonConfigurationError(
                f"Call to '{func.id}()' is blocked by Python Runtime V1."
            )
        if isinstance(func, ast.Attribute) and func.attr in _BLOCKED_ATTRIBUTE_CALLS:
            # os.system / subprocess.run style escapes
            raise PythonConfigurationError(
                f"Call to '.{func.attr}()' is blocked by Python Runtime V1 "
                "(no arbitrary shell execution)."
            )

    @staticmethod
    def _normalize_source(source: str) -> str:
        """Conservative formatter: normalize newlines and trailing whitespace."""
        lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        normalized = [line.rstrip() for line in lines]
        # Ensure a single trailing newline for non-empty sources.
        text = "\n".join(normalized)
        if text and not text.endswith("\n"):
            text += "\n"
        return text

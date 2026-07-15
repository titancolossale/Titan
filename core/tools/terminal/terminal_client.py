# =====================================
# Titan Terminal Client
# =====================================

"""Workspace-bound subprocess execution engine for the Terminal tool."""

from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from core.tools.terminal.exceptions import (
    TerminalConfigurationError,
    TerminalOutputTooLargeError,
    TerminalPathError,
    TerminalSecurityError,
)
from core.tools.terminal.models import CommandResult
from core.tools.terminal.terminal_config import TerminalConfig

logger = logging.getLogger(__name__)

# Shell metacharacters that enable chaining / redirection escapes.
_SHELL_META_PATTERN = re.compile(r"[|&;<>`$]|&&|\|\||>>|<<")

# Windows drive / UNC absolute path markers in arguments.
_ABSOLUTE_PATH_PATTERN = re.compile(
    r"^(?:[A-Za-z]:[\\/]|\\\\|/)",
)


class TerminalClient:
    """Execute allowlisted commands inside the configured Titan workspace."""

    def __init__(self, config: TerminalConfig) -> None:
        self._config = config
        if not self._config.workspace_root.exists():
            raise TerminalConfigurationError(
                f"Terminal workspace does not exist: {self._config.workspace_root}"
            )

    @property
    def config(self) -> TerminalConfig:
        """Return the active Terminal configuration."""
        return self._config

    @property
    def workspace_root(self) -> Path:
        """Return the configured workspace root."""
        return self._config.workspace_root

    def run_command(
        self,
        command: str | list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Run an allowlisted command inside the workspace."""
        argv = self._normalize_command(command)
        self.validate_command(argv)
        workdir = self.resolve_cwd(cwd)
        timeout_seconds = self._config.resolve_timeout(timeout)
        return self._run_subprocess(argv, timeout_seconds=timeout_seconds, cwd=workdir)

    def run_python(
        self,
        args: str | list[str] = "",
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Run the Python interpreter with optional arguments."""
        argv = [sys.executable, *self._normalize_args(args)]
        self._reject_blocked_text(" ".join(argv))
        self._reject_path_escapes(argv[1:])
        workdir = self.resolve_cwd(cwd)
        timeout_seconds = self._config.resolve_timeout(timeout)
        return self._run_subprocess(argv, timeout_seconds=timeout_seconds, cwd=workdir)

    def run_git(
        self,
        args: str | list[str] = "status",
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Run a git subcommand inside the workspace."""
        argv = ["git", *self._normalize_args(args)]
        self._reject_blocked_text(" ".join(argv))
        self._reject_path_escapes(argv[1:])
        workdir = self.resolve_cwd(cwd)
        timeout_seconds = self._config.resolve_timeout(timeout)
        return self._run_subprocess(argv, timeout_seconds=timeout_seconds, cwd=workdir)

    def run_pytest(
        self,
        args: str | list[str] = "tests/",
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Run pytest with optional arguments."""
        argv = ["pytest", *self._normalize_args(args)]
        self._reject_blocked_text(" ".join(argv))
        self._reject_path_escapes(argv[1:])
        workdir = self.resolve_cwd(cwd)
        timeout_seconds = self._config.resolve_timeout(timeout)
        return self._run_subprocess(argv, timeout_seconds=timeout_seconds, cwd=workdir)

    def run_npm(
        self,
        args: str | list[str] = "",
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Run npm with optional arguments."""
        argv = ["npm", *self._normalize_args(args)]
        if len(argv) == 1:
            raise TerminalConfigurationError("Missing required npm arguments")
        self._reject_blocked_text(" ".join(argv))
        self._reject_path_escapes(argv[1:])
        workdir = self.resolve_cwd(cwd)
        timeout_seconds = self._config.resolve_timeout(timeout)
        return self._run_subprocess(argv, timeout_seconds=timeout_seconds, cwd=workdir)

    def run_uv(
        self,
        args: str | list[str] = "",
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Run uv with optional arguments."""
        argv = ["uv", *self._normalize_args(args)]
        if len(argv) == 1:
            raise TerminalConfigurationError("Missing required uv arguments")
        self._reject_blocked_text(" ".join(argv))
        self._reject_path_escapes(argv[1:])
        workdir = self.resolve_cwd(cwd)
        timeout_seconds = self._config.resolve_timeout(timeout)
        return self._run_subprocess(argv, timeout_seconds=timeout_seconds, cwd=workdir)

    def validate_command(self, command: list[str]) -> None:
        """Reject dangerous or non-allowlisted commands."""
        if not command:
            raise TerminalConfigurationError("Missing required parameter: command")

        joined = " ".join(command).strip()
        if not joined:
            raise TerminalConfigurationError("Missing required parameter: command")

        self._reject_blocked_text(joined)
        self._reject_shell_metacharacters(joined)

        first = Path(command[0]).name.lower()
        # Strip Windows extensions (.exe, .cmd, .bat)
        for suffix in (".exe", ".cmd", ".bat", ".ps1"):
            if first.endswith(suffix):
                first = first[: -len(suffix)]
                break

        if first in self._config.blocked_commands:
            raise TerminalSecurityError(
                joined,
                f"command '{first}' is blocked by Terminal security policy",
            )

        if first not in self._config.allowed_commands:
            raise TerminalSecurityError(
                joined,
                f"command '{first}' is not in the Terminal allowlist",
            )

        self._reject_path_escapes(command[1:])

    def resolve_cwd(self, raw: str | None = None) -> Path:
        """Resolve a working directory and reject escapes outside the workspace."""
        if raw is None or str(raw).strip() == "":
            return self._config.workspace_root

        candidate = Path(str(raw).strip())
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self._config.workspace_root / candidate).resolve()

        try:
            resolved.relative_to(self._config.workspace_root)
        except ValueError as exc:
            raise TerminalPathError(
                str(raw),
                "path escapes the Terminal workspace",
            ) from exc

        if not resolved.exists():
            raise TerminalPathError(str(raw), "working directory does not exist")
        if not resolved.is_dir():
            raise TerminalPathError(str(raw), "working directory is not a directory")

        return resolved

    def _run_subprocess(
        self,
        command: list[str],
        *,
        timeout_seconds: float,
        cwd: Path,
    ) -> CommandResult:
        display = " ".join(command)
        env = self._build_safe_env()
        logger.info(
            "Terminal starting: command=%r timeout=%.2fs cwd=%s",
            display,
            timeout_seconds,
            cwd,
        )

        started = time.perf_counter()
        timed_out = False
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(cwd),
                env=env,
                check=False,
                shell=False,
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
        except FileNotFoundError as exc:
            raise TerminalConfigurationError(
                f"Command not found: {command[0]}"
            ) from exc
        except OSError as exc:
            raise TerminalConfigurationError(f"Execution impossible: {exc}") from exc

        duration = time.perf_counter() - started
        stdout, stderr, truncated = self._truncate_outputs(stdout, stderr)

        logger.info(
            "Terminal finished: command=%r exit_code=%s duration=%.3fs "
            "truncated=%s timed_out=%s",
            display,
            exit_code,
            duration,
            truncated,
            timed_out,
        )
        if timed_out:
            logger.warning(
                "Terminal timeout: command=%r duration=%.3fs",
                display,
                duration,
            )
        elif exit_code != 0:
            logger.warning(
                "Terminal error: command=%r exit_code=%s stderr_chars=%d",
                display,
                exit_code,
                len(stderr),
            )

        return CommandResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration=duration,
            command=display,
            cwd=str(cwd),
            timed_out=timed_out,
            truncated=truncated,
        )

    def _truncate_outputs(self, stdout: str, stderr: str) -> tuple[str, str, bool]:
        max_bytes = self._config.max_output_bytes
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
            raise TerminalOutputTooLargeError(max_bytes)

        return stdout, stderr, truncated

    def _build_safe_env(self) -> dict[str, str]:
        """Build a minimal environment — no Titan secrets forwarded."""
        env: dict[str, str] = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TERM": os.environ.get("TERM", "dumb"),
        }
        if sys.platform == "win32":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
            env["COMSPEC"] = os.environ.get("COMSPEC", "")
            env["PATHEXT"] = os.environ.get("PATHEXT", "")
            env["TEMP"] = os.environ.get("TEMP", "")
            env["TMP"] = os.environ.get("TMP", "")
            # Git / Node often need USERPROFILE on Windows.
            env["USERPROFILE"] = os.environ.get("USERPROFILE", "")
            env["HOMEDRIVE"] = os.environ.get("HOMEDRIVE", "")
            env["HOMEPATH"] = os.environ.get("HOMEPATH", "")
        else:
            env["HOME"] = os.environ.get("HOME", "")
            env["LANG"] = os.environ.get("LANG", "C.UTF-8")
            env["USER"] = os.environ.get("USER", "")

        # Preserve git identity helpers without forwarding API keys.
        for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
                    "GIT_COMMITTER_EMAIL", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
            value = os.environ.get(key)
            if value:
                env[key] = value

        return env

    def _reject_blocked_text(self, text: str) -> None:
        lowered = text.lower()
        for pattern in self._config.blocked_patterns:
            if pattern and pattern in lowered:
                raise TerminalSecurityError(text, f"matches blocked pattern '{pattern}'")

        # Explicit standalone sudo token (covers "sudo" alone).
        tokens = {token.lower() for token in re.split(r"\s+", lowered) if token}
        if "sudo" in tokens:
            raise TerminalSecurityError(text, "sudo is blocked by Terminal security policy")

    def _reject_shell_metacharacters(self, text: str) -> None:
        if _SHELL_META_PATTERN.search(text):
            raise TerminalSecurityError(
                text,
                "shell metacharacters are not allowed (no chaining or redirection)",
            )

    def _reject_path_escapes(self, args: list[str]) -> None:
        """Reject absolute paths and ``..`` traversal outside the workspace."""
        for arg in args:
            if not arg or arg.startswith("-"):
                continue
            # Skip non-path-looking tokens (flags already skipped; URLs; plain words).
            if "://" in arg:
                continue
            if ".." in Path(arg).parts:
                # Resolve relative to workspace and ensure it stays inside.
                try:
                    resolved = (self._config.workspace_root / arg).resolve()
                    resolved.relative_to(self._config.workspace_root)
                except (ValueError, OSError) as exc:
                    raise TerminalPathError(
                        arg,
                        "argument path escapes the Terminal workspace",
                    ) from exc
            if _ABSOLUTE_PATH_PATTERN.match(arg):
                try:
                    resolved = Path(arg).resolve()
                    resolved.relative_to(self._config.workspace_root)
                except (ValueError, OSError) as exc:
                    raise TerminalPathError(
                        arg,
                        "absolute path is outside the Terminal workspace",
                    ) from exc

    @staticmethod
    def _normalize_command(command: str | list[str]) -> list[str]:
        if isinstance(command, (list, tuple)):
            argv = [str(item) for item in command if str(item).strip() != ""]
            if not argv:
                raise TerminalConfigurationError("Missing required parameter: command")
            return argv

        text = str(command).strip()
        if not text:
            raise TerminalConfigurationError("Missing required parameter: command")

        try:
            if sys.platform == "win32":
                argv = shlex.split(text, posix=False)
            else:
                argv = shlex.split(text)
        except ValueError as exc:
            raise TerminalConfigurationError(f"Invalid command syntax: {exc}") from exc

        if not argv:
            raise TerminalConfigurationError("Missing required parameter: command")
        return argv

    @staticmethod
    def _normalize_args(args: str | list[str]) -> list[str]:
        if isinstance(args, (list, tuple)):
            return [str(item) for item in args if str(item).strip() != ""]
        text = str(args).strip()
        if not text:
            return []
        try:
            if sys.platform == "win32":
                return shlex.split(text, posix=False)
            return shlex.split(text)
        except ValueError as exc:
            raise TerminalConfigurationError(f"Invalid arguments syntax: {exc}") from exc

# =====================================
# Titan Terminal Tool Configuration
# =====================================

"""Configuration for the core Terminal tool."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import PROJECT_ROOT

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_EXECUTION_SECONDS = 120.0
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KiB

DEFAULT_ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {
        "git",
        "pytest",
        "python",
        "python3",
        "py",
        "npm",
        "npx",
        "uv",
        "pip",
        "pip3",
        "node",
        "echo",
        "dir",
        "ls",
        "type",
        "cat",
        "where",
        "which",
        "pwd",
        "cd",
    }
)

DEFAULT_BLOCKED_PATTERNS: frozenset[str] = frozenset(
    {
        "rm -rf",
        "rm -r",
        "rmdir /s",
        "del /f",
        "del /s",
        "shutdown",
        "reboot",
        "mkfs",
        "diskpart",
        "format ",
        "format.c",
        "sudo ",
        "sudo\t",
        "set-executionpolicy",
        "executionpolicy",
        ":(){",
        "fork bomb",
        "dd if=",
        "mkfs.",
        "chmod 777",
        "chown ",
        "passwd",
        "useradd",
        "userdel",
        "net user",
        "reg delete",
        "reg add",
        "sc delete",
        "sc stop",
        "taskkill /f",
        "powershell -enc",
        "powershell -e ",
        "iex(",
        "invoke-expression",
        "curl | sh",
        "curl|sh",
        "wget | sh",
        "wget|sh",
        "> /dev/",
        ">/dev/",
        "\\\\.\\physicaldrive",
    }
)

# First-token denylist — always rejected even if somehow allowlisted.
DEFAULT_BLOCKED_COMMANDS: frozenset[str] = frozenset(
    {
        "rm",
        "rmdir",
        "del",
        "erase",
        "shutdown",
        "reboot",
        "mkfs",
        "diskpart",
        "format",
        "sudo",
        "su",
        "powershell",
        "pwsh",
        "cmd",
        "bash",
        "sh",
        "zsh",
        "fish",
        "dd",
        "mkfs.ext4",
        "mkfs.ntfs",
    }
)


@dataclass(frozen=True)
class TerminalConfig:
    """Runtime configuration for workspace-bound Terminal execution.

    Attributes:
        workspace_root: Project workspace used as the default cwd.
        timeout_seconds: Soft per-invocation timeout (seconds).
        max_execution_seconds: Hard ceiling applied to any requested timeout.
        max_output_bytes: Maximum combined stdout/stderr size retained.
        allowed_commands: First-token allowlist for ``run_command``.
        blocked_patterns: Substrings that always reject a command.
    """

    workspace_root: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_execution_seconds: float = DEFAULT_MAX_EXECUTION_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    allowed_commands: frozenset[str] = field(default_factory=lambda: DEFAULT_ALLOWED_COMMANDS)
    blocked_patterns: frozenset[str] = field(default_factory=lambda: DEFAULT_BLOCKED_PATTERNS)
    blocked_commands: frozenset[str] = field(default_factory=lambda: DEFAULT_BLOCKED_COMMANDS)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_root", Path(self.workspace_root).resolve())

    @classmethod
    def from_environment(
        cls,
        *,
        workspace_root: Path | str | None = None,
    ) -> TerminalConfig:
        """Load configuration from Titan environment variables."""
        timeout = float(
            os.getenv(
                "TITAN_TERMINAL_TIMEOUT_SECONDS",
                str(DEFAULT_TIMEOUT_SECONDS),
            )
        )
        max_execution = float(
            os.getenv(
                "TITAN_TERMINAL_MAX_EXECUTION_SECONDS",
                str(max(timeout, DEFAULT_MAX_EXECUTION_SECONDS)),
            )
        )
        max_output = int(
            os.getenv(
                "TITAN_TERMINAL_MAX_OUTPUT_BYTES",
                str(DEFAULT_MAX_OUTPUT_BYTES),
            )
        )

        root_env = os.getenv("TITAN_TERMINAL_WORKSPACE", "").strip()
        if workspace_root is not None:
            root = Path(workspace_root)
        elif root_env:
            root = Path(root_env).expanduser()
        else:
            root = PROJECT_ROOT

        allowed_env = os.getenv("TITAN_TERMINAL_ALLOWED_COMMANDS", "").strip()
        if allowed_env:
            allowed = frozenset(
                item.strip().lower() for item in allowed_env.split(",") if item.strip()
            )
        else:
            allowed = DEFAULT_ALLOWED_COMMANDS

        blocked_env = os.getenv("TITAN_TERMINAL_BLOCKED_PATTERNS", "").strip()
        if blocked_env:
            blocked = frozenset(
                item.strip().lower() for item in blocked_env.split(",") if item.strip()
            )
        else:
            blocked = DEFAULT_BLOCKED_PATTERNS

        return cls(
            workspace_root=root,
            timeout_seconds=max(0.1, timeout),
            max_execution_seconds=max(0.1, max_execution),
            max_output_bytes=max(1024, max_output),
            allowed_commands=allowed,
            blocked_patterns=blocked,
            blocked_commands=DEFAULT_BLOCKED_COMMANDS,
        )

    @classmethod
    def for_workspace(cls, workspace_root: Path | str, **overrides: object) -> TerminalConfig:
        """Build a config rooted at an explicit workspace directory."""
        root = Path(workspace_root)
        base = cls.from_environment(workspace_root=root)
        if not overrides:
            return base

        allowed = overrides.get("allowed_commands", base.allowed_commands)
        blocked = overrides.get("blocked_patterns", base.blocked_patterns)
        blocked_cmds = overrides.get("blocked_commands", base.blocked_commands)
        return cls(
            workspace_root=root,
            timeout_seconds=float(overrides.get("timeout_seconds", base.timeout_seconds)),
            max_execution_seconds=float(
                overrides.get("max_execution_seconds", base.max_execution_seconds)
            ),
            max_output_bytes=int(overrides.get("max_output_bytes", base.max_output_bytes)),
            allowed_commands=frozenset(allowed),  # type: ignore[arg-type]
            blocked_patterns=frozenset(blocked),  # type: ignore[arg-type]
            blocked_commands=frozenset(blocked_cmds),  # type: ignore[arg-type]
        )

    def resolve_timeout(self, requested: float | None) -> float:
        """Clamp a requested timeout to the configured hard ceiling."""
        if requested is None or requested <= 0:
            return min(self.timeout_seconds, self.max_execution_seconds)
        return min(float(requested), self.max_execution_seconds)

# =====================================
# Titan Terminal Tool Models
# =====================================

"""Structured data models for Terminal tool operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a workspace-bound Terminal subprocess run."""

    stdout: str
    stderr: str
    exit_code: int
    duration: float
    command: str
    cwd: str
    timed_out: bool = False
    truncated: bool = False

    @property
    def success(self) -> bool:
        """True when the process exited zero without timeout."""
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration": self.duration,
            "command": self.command,
            "cwd": self.cwd,
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "success": self.success,
        }

# =====================================
# Titan Python Runtime Models
# =====================================

"""Structured data models for Python Runtime operations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of a sandboxed Python subprocess run."""

    stdout: str
    stderr: str
    exit_code: int
    duration: float
    files_created: tuple[str, ...] = ()
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
            "files_created": list(self.files_created),
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "success": self.success,
        }


@dataclass(frozen=True)
class SyntaxCheckResult:
    """Outcome of a Python syntax validation pass."""

    valid: bool
    message: str
    line: int | None = None
    offset: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "valid": self.valid,
            "message": self.message,
            "line": self.line,
            "offset": self.offset,
        }


@dataclass(frozen=True)
class FormatResult:
    """Outcome of a Python format pass."""

    formatted_code: str
    changed: bool
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "formatted_code": self.formatted_code,
            "changed": self.changed,
            "message": self.message,
        }


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """File inventory used to detect artifacts created during execution."""

    files: frozenset[str] = field(default_factory=frozenset)

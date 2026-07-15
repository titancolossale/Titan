# =====================================
# Titan Python Runtime Configuration
# =====================================

"""Configuration for the core Python Runtime tool."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KiB
DEFAULT_MAX_FILE_COUNT = 50
DEFAULT_MAX_EXECUTION_SECONDS = 5.0


@dataclass(frozen=True)
class PythonRuntimeConfig:
    """Runtime configuration for sandboxed Python execution.

    Attributes:
        workspace_root: Isolated working directory for subprocess execution.
        timeout_seconds: Soft per-invocation timeout (seconds).
        max_execution_seconds: Hard ceiling applied to any requested timeout.
        max_output_bytes: Maximum combined stdout/stderr size retained.
        max_file_count: Maximum files allowed in the workspace after a run.
        allow_network: Always False in V1 — network is never enabled.
    """

    workspace_root: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_execution_seconds: float = DEFAULT_MAX_EXECUTION_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    max_file_count: int = DEFAULT_MAX_FILE_COUNT
    allow_network: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_root", Path(self.workspace_root).resolve())

    @classmethod
    def from_environment(
        cls,
        *,
        workspace_root: Path | str | None = None,
    ) -> PythonRuntimeConfig:
        """Load configuration from Titan environment variables."""
        timeout = float(
            os.getenv(
                "TITAN_PYTHON_RUNTIME_TIMEOUT_SECONDS",
                os.getenv("TITAN_TOOL_PYTHON_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)),
            )
        )
        max_execution = float(
            os.getenv(
                "TITAN_PYTHON_RUNTIME_MAX_EXECUTION_SECONDS",
                str(max(timeout, DEFAULT_MAX_EXECUTION_SECONDS)),
            )
        )
        max_output = int(
            os.getenv(
                "TITAN_PYTHON_RUNTIME_MAX_OUTPUT_BYTES",
                str(DEFAULT_MAX_OUTPUT_BYTES),
            )
        )
        max_files = int(
            os.getenv(
                "TITAN_PYTHON_RUNTIME_MAX_FILE_COUNT",
                str(DEFAULT_MAX_FILE_COUNT),
            )
        )

        root_env = os.getenv("TITAN_PYTHON_RUNTIME_WORKSPACE", "").strip()
        if workspace_root is not None:
            root = Path(workspace_root)
        elif root_env:
            root = Path(root_env).expanduser()
        else:
            root = Path(tempfile.gettempdir()) / "titan_python_runtime"

        root.mkdir(parents=True, exist_ok=True)

        return cls(
            workspace_root=root,
            timeout_seconds=max(0.1, timeout),
            max_execution_seconds=max(0.1, max_execution),
            max_output_bytes=max(1024, max_output),
            max_file_count=max(1, max_files),
            allow_network=False,
        )

    @classmethod
    def for_workspace(cls, workspace_root: Path | str, **overrides: object) -> PythonRuntimeConfig:
        """Build a config rooted at an explicit workspace directory."""
        root = Path(workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        base = cls.from_environment(workspace_root=root)
        if not overrides:
            return base
        return cls(
            workspace_root=root,
            timeout_seconds=float(overrides.get("timeout_seconds", base.timeout_seconds)),
            max_execution_seconds=float(
                overrides.get("max_execution_seconds", base.max_execution_seconds)
            ),
            max_output_bytes=int(overrides.get("max_output_bytes", base.max_output_bytes)),
            max_file_count=int(overrides.get("max_file_count", base.max_file_count)),
            allow_network=False,
        )

    def resolve_timeout(self, requested: float | None) -> float:
        """Clamp a requested timeout to the configured hard ceiling."""
        if requested is None or requested <= 0:
            return min(self.timeout_seconds, self.max_execution_seconds)
        return min(float(requested), self.max_execution_seconds)

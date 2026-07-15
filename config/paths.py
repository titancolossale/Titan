# =====================================
# Titan Path Resolution
# =====================================

"""Cross-platform path resolution for Titan runtime data and persistence."""

from __future__ import annotations

import os
from pathlib import Path

from config.settings import PROJECT_ROOT


def _resolve_directory(raw: str, *, default_relative: str) -> Path:
    """Resolve a directory path relative to PROJECT_ROOT when not absolute."""
    value = (raw or default_relative).strip()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def get_data_directory() -> Path:
    """Return the configured Titan data directory (must persist in cloud)."""
    raw = os.getenv("TITAN_DATA_DIR", "data").strip() or "data"
    return _resolve_directory(raw, default_relative="data")


def get_memory_directory() -> Path:
    """Return the directory used for durable memory JSON files."""
    raw = os.getenv("TITAN_MEMORY_DIR", "").strip()
    if raw:
        return _resolve_directory(raw, default_relative="data")
    return get_data_directory()


def get_logs_directory() -> Path:
    """Return the configured log directory."""
    raw = os.getenv("TITAN_LOG_DIR", "logs").strip() or "logs"
    return _resolve_directory(raw, default_relative="logs")


def resolve_under_data(relative: str | Path) -> Path:
    """Build a path under the configured data directory."""
    return get_data_directory() / Path(relative)


def resolve_under_memory(relative: str | Path) -> Path:
    """Build a path under the configured memory directory."""
    return get_memory_directory() / Path(relative)


def ensure_directory(path: Path) -> Path:
    """Create a directory if missing and return the resolved path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_directory_writable(path: Path) -> bool:
    """Return True when the directory exists and accepts a probe write."""
    if not path.is_dir():
        return False
    probe = path / ".titan_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False

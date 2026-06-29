# =====================================
# Titan Provider Version
# =====================================

"""Provider version and compatibility metadata (Phase 10A — P10A-007)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from tools.tool_enums import ExecutionMode, ToolHealthState


@dataclass(frozen=True)
class ProviderHealth:
    """Health probe result from a provider."""

    state: ToolHealthState
    message: str = ""


@dataclass(frozen=True)
class ProviderVersionInfo:
    """Version and compatibility metadata exposed by every provider."""

    provider_id: str
    version: str
    min_runtime_version: str
    api_version: str | None = None
    compatible_modes: frozenset[ExecutionMode] = frozenset({ExecutionMode.LIVE})
    changelog_url: str | None = None

    def to_dict(self) -> dict:
        """Serialize for audit logs and registration validation."""
        data = asdict(self)
        data["compatible_modes"] = sorted(m.value for m in self.compatible_modes)
        return data

    def is_compatible_with_runtime(self, runtime_version: str) -> bool:
        """Return True if provider min_runtime_version <= runtime_version."""
        return _compare_versions(runtime_version, self.min_runtime_version) >= 0

    def supports_mode(self, mode: ExecutionMode) -> bool:
        """Return True if provider supports the requested execution mode."""
        return mode in self.compatible_modes


def _compare_versions(left: str, right: str) -> int:
    """Compare semver-like strings; returns positive if left >= right."""

    def parse(version: str) -> tuple[int, ...]:
        parts: list[int] = []
        for segment in version.split("."):
            digits = "".join(ch for ch in segment if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts or (0,))

    left_parts = parse(left)
    right_parts = parse(right)
    length = max(len(left_parts), len(right_parts))
    left_padded = left_parts + (0,) * (length - len(left_parts))
    right_padded = right_parts + (0,) * (length - len(right_parts))
    if left_padded == right_padded:
        return 0
    return 1 if left_padded > right_padded else -1

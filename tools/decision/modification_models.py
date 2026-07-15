# =====================================
# Titan Tool Decision — Modification Models
# =====================================

"""Structured modification planning artifacts (Phase 11 — P11-302)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.tool_enums import RiskLevel


@dataclass(frozen=True)
class FileChangeSpec:
    """One planned file change with rationale."""

    path: str
    reason: str
    change_summary: str


@dataclass(frozen=True)
class PatchPreview:
    """Read-only unified diff or structured patch proposal (P11-303)."""

    path: str
    change_type: str
    unified_diff: str
    structured_proposal: str = ""


@dataclass(frozen=True)
class ModificationPlan:
    """Safe workspace modification plan — analysis only, no writes (P11-302)."""

    objective: str
    modification_type: str
    files_to_modify: tuple[FileChangeSpec, ...]
    files_to_create: tuple[FileChangeSpec, ...]
    files_to_delete: tuple[str, ...]
    dependency_graph: dict[str, tuple[str, ...]]
    implementation_steps: tuple[str, ...]
    estimated_risk: RiskLevel
    confidence: float
    patch_previews: tuple[PatchPreview, ...] = ()
    side_effects: tuple[str, ...] = ()
    ambiguous: bool = False
    ambiguity_reason: str = ""

    @property
    def affected_files(self) -> tuple[str, ...]:
        """All paths touched by the plan (modify + create)."""
        paths = [item.path for item in self.files_to_modify]
        paths.extend(item.path for item in self.files_to_create)
        return tuple(dict.fromkeys(paths))

    def to_dict(self) -> dict:
        """Serialize for DecisionReport and logging."""
        return {
            "objective": self.objective,
            "modification_type": self.modification_type,
            "files_to_modify": [
                {
                    "path": item.path,
                    "reason": item.reason,
                    "change_summary": item.change_summary,
                }
                for item in self.files_to_modify
            ],
            "files_to_create": [
                {
                    "path": item.path,
                    "reason": item.reason,
                    "change_summary": item.change_summary,
                }
                for item in self.files_to_create
            ],
            "files_to_delete": list(self.files_to_delete),
            "dependency_graph": {
                key: list(values) for key, values in self.dependency_graph.items()
            },
            "implementation_steps": list(self.implementation_steps),
            "estimated_risk": self.estimated_risk.value,
            "confidence": self.confidence,
            "patch_previews": [
                {
                    "path": item.path,
                    "change_type": item.change_type,
                    "unified_diff": item.unified_diff,
                    "structured_proposal": item.structured_proposal,
                }
                for item in self.patch_previews
            ],
            "side_effects": list(self.side_effects),
            "affected_files": list(self.affected_files),
            "ambiguous": self.ambiguous,
            "ambiguity_reason": self.ambiguity_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ModificationPlan:
        """Deserialize a stored modification plan."""
        return cls(
            objective=str(data.get("objective", "")),
            modification_type=str(data.get("modification_type", "unknown")),
            files_to_modify=tuple(
                FileChangeSpec(
                    path=item["path"],
                    reason=item.get("reason", ""),
                    change_summary=item.get("change_summary", ""),
                )
                for item in data.get("files_to_modify", [])
            ),
            files_to_create=tuple(
                FileChangeSpec(
                    path=item["path"],
                    reason=item.get("reason", ""),
                    change_summary=item.get("change_summary", ""),
                )
                for item in data.get("files_to_create", [])
            ),
            files_to_delete=tuple(data.get("files_to_delete", [])),
            dependency_graph={
                key: tuple(values)
                for key, values in (data.get("dependency_graph") or {}).items()
            },
            implementation_steps=tuple(data.get("implementation_steps", [])),
            estimated_risk=RiskLevel(data.get("estimated_risk", RiskLevel.MEDIUM.value)),
            confidence=float(data.get("confidence", 0.0)),
            patch_previews=tuple(
                PatchPreview(
                    path=item["path"],
                    change_type=item.get("change_type", "modify"),
                    unified_diff=item.get("unified_diff", ""),
                    structured_proposal=item.get("structured_proposal", ""),
                )
                for item in data.get("patch_previews", [])
            ),
            side_effects=tuple(data.get("side_effects", [])),
            ambiguous=bool(data.get("ambiguous", False)),
            ambiguity_reason=str(data.get("ambiguity_reason", "")),
        )


_CORE_RUNTIME_PATHS: frozenset[str] = frozenset({
    "brain/brain.py",
    "core/titan.py",
    "main.py",
    "tools/tool_runtime.py",
    "core/execution_coordinator.py",
    "tools/tool_manager.py",
})


def estimate_modification_risk(
    *,
    files_to_modify: tuple[FileChangeSpec, ...],
    files_to_create: tuple[FileChangeSpec, ...],
    modification_type: str,
) -> RiskLevel:
    """Map planned scope to modification risk (P11-305)."""
    all_paths = [item.path for item in files_to_modify] + [
        item.path for item in files_to_create
    ]
    if not all_paths:
        return RiskLevel.LOW

    if any(path in _CORE_RUNTIME_PATHS for path in all_paths):
        return RiskLevel.CRITICAL

    if modification_type == "add_comment":
        return RiskLevel.LOW

    total = len(all_paths)
    if total >= 3:
        return RiskLevel.HIGH
    if total == 1 and modification_type in {"fix_bug", "add_comment"}:
        return RiskLevel.MEDIUM
    if total <= 2:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH

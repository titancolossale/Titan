# =====================================
# Titan Capability Models
# =====================================

"""Serializable capability metadata for Titan's shared tool registry."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.tools.base_tool import BaseTool

_SEMVER_PATTERN = re.compile(
    r"^\d+\.\d+\.\d+(?:-[\w.]+)?(?:\+[\w.]+)?$"
)

STANDARD_CATEGORIES = frozenset(
    {
        "browser",
        "calendar",
        "demo",
        "editor",
        "email",
        "filesystem",
        "notes",
        "runtime",
        "shell",
        "trading",
        "vcs",
        "voice",
        "web",
    }
)

STANDARD_RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
STANDARD_EXECUTION_TRAITS = frozenset(
    {
        "read_only",
        "read_write",
        "network",
        "local",
        "interactive",
    }
)
STANDARD_STATUSES = frozenset({"active", "disabled", "error", "experimental", "deprecated"})


class CapabilityValidationError(ValueError):
    """Raised when tool capability metadata fails validation."""


@dataclass(frozen=True)
class ActionDescriptor:
    """Lightweight action metadata for registry export and UI."""

    id: str
    name: str
    description: str
    permission_id: str
    capability: str
    parameters: dict[str, object]
    requires_confirmation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "permission_id": self.permission_id,
            "capability": self.capability,
            "parameters": dict(self.parameters),
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass(frozen=True)
class CapabilityRecord:
    """Self-describing metadata for one installed Titan tool."""

    id: str
    display_name: str
    version: str
    description: str
    category: str
    author: str
    capabilities: tuple[str, ...]
    supported_actions: tuple[ActionDescriptor, ...]
    permissions_required: tuple[str, ...]
    requires_confirmation: bool
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    examples: tuple[dict[str, object], ...]
    configuration_requirements: tuple[str, ...]
    status: str
    enabled: bool
    experimental: bool
    deprecated: bool
    cost_estimate: str
    risk_level: str
    execution_traits: tuple[str, ...]
    streaming_support: bool
    tags: tuple[str, ...]

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(action.id for action in self.supported_actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "author": self.author,
            "capabilities": list(self.capabilities),
            "supported_actions": [action.to_dict() for action in self.supported_actions],
            "permissions_required": list(self.permissions_required),
            "requires_confirmation": self.requires_confirmation,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "examples": [dict(example) for example in self.examples],
            "configuration_requirements": list(self.configuration_requirements),
            "status": self.status,
            "enabled": self.enabled,
            "experimental": self.experimental,
            "deprecated": self.deprecated,
            "cost_estimate": self.cost_estimate,
            "risk_level": self.risk_level,
            "execution_traits": list(self.execution_traits),
            "streaming_support": self.streaming_support,
            "tags": list(self.tags),
        }

    @classmethod
    def from_tool(cls, tool: BaseTool) -> CapabilityRecord:
        """Build a capability record from a live tool instance."""
        actions = tool.list_actions()
        action_descriptors: list[ActionDescriptor] = []
        permissions: set[str] = set()
        duplicate_actions: set[str] = set()
        seen_action_ids: set[str] = set()

        for action in actions:
            if action.id in seen_action_ids:
                duplicate_actions.add(action.id)
            seen_action_ids.add(action.id)
            permissions.add(action.permission_id)
            capability = str(action.metadata.get("capability", action.id))
            requires_confirmation = bool(
                action.metadata.get(
                    "requires_confirmation",
                    tool.requires_confirmation,
                )
            )
            action_descriptors.append(
                ActionDescriptor(
                    id=action.id,
                    name=action.name,
                    description=action.description,
                    permission_id=action.permission_id,
                    capability=capability,
                    parameters=dict(action.parameters or {}),
                    requires_confirmation=requires_confirmation,
                )
            )

        if duplicate_actions:
            raise CapabilityValidationError(
                f"Tool '{tool.id}' declares duplicate actions: "
                f"{', '.join(sorted(duplicate_actions))}"
            )

        return cls(
            id=tool.id,
            display_name=tool.name,
            version=tool.version,
            description=tool.description,
            category=tool.category,
            author=tool.author,
            capabilities=tuple(tool.capabilities),
            supported_actions=tuple(action_descriptors),
            permissions_required=tuple(sorted(permissions)),
            requires_confirmation=tool.requires_confirmation,
            input_schema=dict(tool.input_schema),
            output_schema=dict(tool.output_schema),
            examples=tuple(dict(example) for example in tool.examples),
            configuration_requirements=tuple(tool.configuration_requirements),
            status=tool.status,
            enabled=tool.enabled,
            experimental=tool.experimental,
            deprecated=tool.deprecated,
            cost_estimate=tool.cost_estimate,
            risk_level=tool.risk_level,
            execution_traits=tuple(tool.execution_traits),
            streaming_support=tool.streaming_support,
            tags=tuple(tool.tags),
        )


def validate_capability_record(
    record: CapabilityRecord,
    *,
    known_permissions: frozenset[str] | None = None,
    strict_categories: bool = False,
) -> list[str]:
    """Validate a capability record and return human-friendly error messages."""
    errors: list[str] = []

    if not record.id or not record.id.strip():
        errors.append("Tool id is required.")
    if not record.display_name or not record.display_name.strip():
        errors.append(f"Tool '{record.id}': display name is required.")
    if not record.description or not record.description.strip():
        errors.append(f"Tool '{record.id}': description is required.")
    if not record.version or not _SEMVER_PATTERN.match(record.version):
        errors.append(
            f"Tool '{record.id}': version must be semver (e.g. 1.0.0), got {record.version!r}."
        )

    normalized_category = record.category.strip().lower()
    if not normalized_category:
        errors.append(f"Tool '{record.id}': category is required.")
    elif strict_categories and normalized_category not in STANDARD_CATEGORIES:
        errors.append(
            f"Tool '{record.id}': unknown category {record.category!r}. "
            f"Expected one of: {', '.join(sorted(STANDARD_CATEGORIES))}."
        )

    if record.risk_level not in STANDARD_RISK_LEVELS:
        errors.append(
            f"Tool '{record.id}': invalid risk level {record.risk_level!r}."
        )

    invalid_traits = [
        trait for trait in record.execution_traits if trait not in STANDARD_EXECUTION_TRAITS
    ]
    if invalid_traits:
        errors.append(
            f"Tool '{record.id}': invalid execution traits: {', '.join(invalid_traits)}."
        )

    if record.status not in STANDARD_STATUSES:
        errors.append(f"Tool '{record.id}': invalid status {record.status!r}.")

    action_ids = [action.id for action in record.supported_actions]
    if len(action_ids) != len(set(action_ids)):
        errors.append(f"Tool '{record.id}': duplicate action ids detected.")

    for action in record.supported_actions:
        if not action.id.strip():
            errors.append(f"Tool '{record.id}': action id is required.")
        if not isinstance(action.parameters, dict):
            errors.append(
                f"Tool '{record.id}' action '{action.id}': parameters schema must be a dict."
            )

    for permission_id in record.permissions_required:
        if known_permissions is not None and permission_id not in known_permissions:
            errors.append(
                f"Tool '{record.id}': unknown permission {permission_id!r}."
            )

    if not isinstance(record.input_schema, dict):
        errors.append(f"Tool '{record.id}': input_schema must be a dict.")
    if not isinstance(record.output_schema, dict):
        errors.append(f"Tool '{record.id}': output_schema must be a dict.")

    return errors

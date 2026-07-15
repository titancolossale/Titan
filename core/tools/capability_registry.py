# =====================================
# Titan Capability Registry
# =====================================

"""Shared registry of self-describing tool capabilities for discovery and Brain APIs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from core.tools.base_tool import BaseTool
from core.tools.capability_models import (
    CapabilityRecord,
    CapabilityValidationError,
    validate_capability_record,
)
from core.tools.exceptions import ToolAlreadyRegisteredError, ToolNotRegisteredError

logger = logging.getLogger(__name__)


@dataclass
class CapabilitySearchResult:
    """One tool matched by a registry search query."""

    record: CapabilityRecord
    score: float
    matched_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": self.record.to_dict(),
            "score": round(self.score, 3),
            "matched_fields": list(self.matched_fields),
        }


@dataclass
class CapabilityRegistrySummary:
    """Aggregate view of installed tools for Brain and future UI."""

    total_tools: int
    enabled_tools: int
    disabled_tools: int
    experimental_tools: int
    deprecated_tools: int
    confirmation_required_tools: int
    streaming_tools: int
    categories: dict[str, int]
    capabilities: dict[str, int]
    risk_levels: dict[str, int]
    tools: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tools": self.total_tools,
            "enabled_tools": self.enabled_tools,
            "disabled_tools": self.disabled_tools,
            "experimental_tools": self.experimental_tools,
            "deprecated_tools": self.deprecated_tools,
            "confirmation_required_tools": self.confirmation_required_tools,
            "streaming_tools": self.streaming_tools,
            "categories": dict(self.categories),
            "capabilities": dict(self.capabilities),
            "risk_levels": dict(self.risk_levels),
            "tools": list(self.tools),
        }


class CapabilityRegistry:
    """Single shared registry of installed tool metadata.

    Tools publish metadata through ``register_tool``; ``ToolLoader`` calls this
    automatically after ``ToolRegistry`` registration. Brain and Tool Intelligence
    consume this registry — never a hardcoded catalog.
    """

    def __init__(
        self,
        *,
        known_permissions: Iterable[str] | None = None,
        strict_categories: bool = False,
        strict_validation: bool = True,
    ) -> None:
        self._records: dict[str, CapabilityRecord] = {}
        self._registration_stack: set[str] = set()
        self._known_permissions = frozenset(known_permissions or ())
        self._strict_categories = strict_categories
        self._strict_validation = strict_validation

    def set_known_permissions(self, permission_ids: Iterable[str]) -> None:
        """Update the permission allowlist used during validation."""
        self._known_permissions = frozenset(permission_ids)

    def register_tool(self, tool: BaseTool) -> CapabilityRecord:
        """Register or refresh metadata for a tool instance."""
        tool_id = tool.id
        if tool_id in self._registration_stack:
            raise CapabilityValidationError(
                f"Circular registration detected for tool '{tool_id}'."
            )

        self._registration_stack.add(tool_id)
        try:
            record = CapabilityRecord.from_tool(tool)
            errors = validate_capability_record(
                record,
                known_permissions=self._known_permissions or None,
                strict_categories=self._strict_categories,
            )
            if errors and self._strict_validation:
                raise CapabilityValidationError("; ".join(errors))
            for error in errors:
                logger.warning("Capability validation warning: %s", error)

            if tool_id in self._records:
                raise ToolAlreadyRegisteredError(tool_id)

            self._records[tool_id] = record
            logger.debug("Registered capability metadata for tool %s", tool_id)
            return record
        finally:
            self._registration_stack.discard(tool_id)

    def refresh_tool(self, tool: BaseTool) -> CapabilityRecord:
        """Replace metadata for an already registered tool."""
        tool_id = tool.id
        if tool_id not in self._records:
            raise ToolNotRegisteredError(tool_id)
        record = CapabilityRecord.from_tool(tool)
        errors = validate_capability_record(
            record,
            known_permissions=self._known_permissions or None,
            strict_categories=self._strict_categories,
        )
        if errors and self._strict_validation:
            raise CapabilityValidationError("; ".join(errors))
        self._records[tool_id] = record
        return record

    def unregister_tool(self, tool_id: str) -> None:
        """Remove a tool from the capability registry."""
        if tool_id not in self._records:
            raise ToolNotRegisteredError(tool_id)
        del self._records[tool_id]

    def get_tool(self, tool_id: str) -> CapabilityRecord | None:
        """Return capability metadata for *tool_id*, or ``None``."""
        return self._records.get(tool_id)

    def list_tools(self) -> list[CapabilityRecord]:
        """Return all registered capability records sorted by id."""
        return [self._records[key] for key in sorted(self._records)]

    def find_by_category(self, category: str) -> list[CapabilityRecord]:
        """Return tools whose category matches *category* (case-insensitive)."""
        normalized = category.strip().lower()
        return [
            record
            for record in self.list_tools()
            if record.category.strip().lower() == normalized
        ]

    def find_by_capability(self, capability: str) -> list[CapabilityRecord]:
        """Return tools exposing *capability* (exact or suffix match)."""
        normalized = capability.strip().lower()
        matches: list[CapabilityRecord] = []
        for record in self.list_tools():
            tool_caps = {cap.lower() for cap in record.capabilities}
            action_caps = {action.capability.lower() for action in record.supported_actions}
            if normalized in tool_caps or normalized in action_caps:
                matches.append(record)
                continue
            if any(
                cap.endswith(normalized) or normalized.endswith(cap)
                for cap in tool_caps | action_caps
            ):
                matches.append(record)
        return matches

    def find_by_permission(self, permission_id: str) -> list[CapabilityRecord]:
        """Return tools requiring *permission_id*."""
        normalized = permission_id.strip().lower()
        return [
            record
            for record in self.list_tools()
            if any(perm.lower() == normalized for perm in record.permissions_required)
        ]

    def find_by_action(self, action_id: str) -> list[CapabilityRecord]:
        """Return tools that expose *action_id*."""
        normalized = action_id.strip().lower()
        return [
            record
            for record in self.list_tools()
            if any(action.id.lower() == normalized for action in record.supported_actions)
        ]

    def find_requiring_confirmation(self) -> list[CapabilityRecord]:
        """Return tools that require user confirmation."""
        return [
            record
            for record in self.list_tools()
            if record.requires_confirmation
            or any(action.requires_confirmation for action in record.supported_actions)
        ]

    def find_experimental(self) -> list[CapabilityRecord]:
        """Return tools marked experimental."""
        return [record for record in self.list_tools() if record.experimental]

    def find_streaming(self) -> list[CapabilityRecord]:
        """Return tools that support streaming."""
        return [record for record in self.list_tools() if record.streaming_support]

    def search(
        self,
        query: str,
        *,
        exact: bool = False,
    ) -> list[CapabilitySearchResult]:
        """Search tools by id, name, description, tags, capabilities, and actions."""
        normalized = query.strip().lower()
        if not normalized:
            return []

        results: list[CapabilitySearchResult] = []
        for record in self.list_tools():
            score, fields = self._score_record(record, normalized, exact=exact)
            if score > 0.0:
                results.append(
                    CapabilitySearchResult(
                        record=record,
                        score=score,
                        matched_fields=tuple(fields),
                    )
                )

        results.sort(key=lambda item: (-item.score, item.record.id))
        return results

    def summarize(self) -> CapabilityRegistrySummary:
        """Return an aggregate summary suitable for Brain and future UI."""
        records = self.list_tools()
        categories: dict[str, int] = {}
        capabilities: dict[str, int] = {}
        risk_levels: dict[str, int] = {}

        for record in records:
            categories[record.category] = categories.get(record.category, 0) + 1
            risk_levels[record.risk_level] = risk_levels.get(record.risk_level, 0) + 1
            for capability in record.capabilities:
                capabilities[capability] = capabilities.get(capability, 0) + 1

        tool_rows = [
            {
                "id": record.id,
                "display_name": record.display_name,
                "version": record.version,
                "category": record.category,
                "enabled": record.enabled,
                "status": record.status,
                "risk_level": record.risk_level,
                "requires_confirmation": record.requires_confirmation,
                "capabilities": list(record.capabilities),
                "permissions_required": list(record.permissions_required),
                "experimental": record.experimental,
                "deprecated": record.deprecated,
                "streaming_support": record.streaming_support,
            }
            for record in records
        ]

        return CapabilityRegistrySummary(
            total_tools=len(records),
            enabled_tools=sum(1 for record in records if record.enabled),
            disabled_tools=sum(1 for record in records if not record.enabled),
            experimental_tools=sum(1 for record in records if record.experimental),
            deprecated_tools=sum(1 for record in records if record.deprecated),
            confirmation_required_tools=len(self.find_requiring_confirmation()),
            streaming_tools=len(self.find_streaming()),
            categories=categories,
            capabilities=capabilities,
            risk_levels=risk_levels,
            tools=tool_rows,
        )

    def export(self) -> dict[str, Any]:
        """Serialize the full registry for API and future Settings UI."""
        summary = self.summarize()
        return {
            "summary": summary.to_dict(),
            "tools": [record.to_dict() for record in self.list_tools()],
        }

    def _score_record(
        self,
        record: CapabilityRecord,
        query: str,
        *,
        exact: bool,
    ) -> tuple[float, list[str]]:
        score = 0.0
        fields: list[str] = []

        def _match(value: str, field_name: str, weight: float) -> None:
            nonlocal score
            lowered = value.lower()
            if exact:
                if lowered == query:
                    score += weight
                    fields.append(field_name)
            elif query in lowered:
                score += weight
                fields.append(field_name)
            elif lowered.startswith(query):
                score += weight * 0.85
                fields.append(field_name)

        _match(record.id, "id", 1.0)
        _match(record.display_name, "display_name", 0.95)
        _match(record.description, "description", 0.6)
        _match(record.category, "category", 0.7)

        for tag in record.tags:
            _match(tag, "tag", 0.75)
        for capability in record.capabilities:
            _match(capability, "capability", 0.8)
        for action in record.supported_actions:
            _match(action.id, "action", 0.65)
            _match(action.name, "action", 0.55)
            _match(action.capability, "capability", 0.7)
        for permission in record.permissions_required:
            _match(permission, "permission", 0.5)

        if not exact:
            tokens = re.findall(r"[a-z0-9_]+", query)
            if len(tokens) > 1:
                haystack = " ".join(
                    [
                        record.id,
                        record.display_name,
                        record.description,
                        record.category,
                        " ".join(record.tags),
                        " ".join(record.capabilities),
                    ]
                ).lower()
                if all(token in haystack for token in tokens):
                    score = max(score, 0.5)
                    fields.append("multi_token")

        return score, fields

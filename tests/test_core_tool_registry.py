# =====================================
# Titan Core Tool Registry Tests
# =====================================

"""Tests and demo for the core tool registry foundation."""

from __future__ import annotations

import pytest

from core.actions import Action, ActionResult
from core.tools import (
    BaseTool,
    ToolAlreadyRegisteredError,
    ToolNotRegisteredError,
    ToolRegistry,
)


class FakeTool(BaseTool):
    """Minimal concrete tool used to exercise the registry."""

    @property
    def id(self) -> str:
        return "fake_tool"

    @property
    def name(self) -> str:
        return "Fake Tool"

    @property
    def description(self) -> str:
        return "A placeholder tool for registry validation."

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def category(self) -> str:
        return "demo"

    @property
    def requires_confirmation(self) -> bool:
        return False

    @property
    def capabilities(self) -> list[str]:
        return ["fake.echo"]

    def list_actions(self) -> list[Action]:
        return [
            Action(
                id="echo",
                name="Echo",
                description="Echo a message.",
                tool_id=self.id,
                permission_id="fake_tool.echo",
                parameters={"message": {"type": "string", "required": False}},
            )
        ]

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        message = kwargs.get("message", "hello")
        return ActionResult(success=True, data={"echo": message})

    def execute(self, **kwargs: object) -> object:
        message = kwargs.get("message", "hello")
        return {"echo": message}


def _format_registry(registry: ToolRegistry) -> str:
    """Render registry contents for demo output."""
    lines = ["Tool Registry:"]
    for metadata in registry.list_tool_metadata():
        status = "enabled" if metadata.enabled else "disabled"
        caps = ", ".join(metadata.capabilities) or "(none)"
        lines.append(
            f"  - {metadata.id} ({metadata.name}) "
            f"[{metadata.category} v{metadata.version}] "
            f"status={status} caps=[{caps}]"
        )
    if not lines[1:]:
        lines.append("  (empty)")
    return "\n".join(lines)


def test_core_tool_registry_demo(capsys: pytest.CaptureFixture[str]) -> None:
    """End-to-end demo: register, list, disable, enable, remove."""
    registry = ToolRegistry()
    tool = FakeTool()

    registry.register_tool(tool)
    print(_format_registry(registry))
    assert registry.tool_exists("fake_tool")
    assert len(registry.list_tools()) == 1
    assert len(registry.list_enabled_tools()) == 1
    assert len(registry.list_tools_by_category("demo")) == 1

    registry.disable_tool("fake_tool")
    print("\nAfter disable:")
    print(_format_registry(registry))
    assert registry.get_tool("fake_tool") is not None
    assert registry.get_tool("fake_tool").enabled is False
    assert registry.list_enabled_tools() == []

    registry.enable_tool("fake_tool")
    print("\nAfter enable:")
    print(_format_registry(registry))
    assert registry.list_enabled_tools()[0].id == "fake_tool"

    result = registry.get_tool("fake_tool").execute(message="titan")
    assert result == {"echo": "titan"}

    registry.unregister_tool("fake_tool")
    print("\nAfter unregister:")
    print(_format_registry(registry))
    assert not registry.tool_exists("fake_tool")
    assert registry.get_tool("fake_tool") is None

    captured = capsys.readouterr()
    assert "fake_tool" in captured.out
    assert "status=disabled" in captured.out
    assert "(empty)" in captured.out


def test_register_duplicate_raises() -> None:
    registry = ToolRegistry()
    registry.register_tool(FakeTool())
    with pytest.raises(ToolAlreadyRegisteredError, match="fake_tool"):
        registry.register_tool(FakeTool())


def test_unregister_missing_raises() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotRegisteredError, match="missing"):
        registry.unregister_tool("missing")


def test_enable_disable_missing_raises() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotRegisteredError):
        registry.enable_tool("missing")
    with pytest.raises(ToolNotRegisteredError):
        registry.disable_tool("missing")


def test_list_tools_by_category_is_case_insensitive() -> None:
    registry = ToolRegistry()
    registry.register_tool(FakeTool())
    assert len(registry.list_tools_by_category("DEMO")) == 1
    assert registry.list_tools_by_category("other") == []

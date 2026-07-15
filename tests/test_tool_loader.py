# =====================================
# Titan Core Tool Loader Tests
# =====================================

"""Tests for automatic BaseTool discovery and registration."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

from core.tools import BaseTool, ToolLoader, ToolRegistry


CORE_TOOLS_DIR = Path(__file__).resolve().parents[1] / "core" / "tools"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

_PLUGIN_ACTION_METHODS = """
            def list_actions(self):
                return []
            def execute_action(self, action_id, **kwargs):
                from core.actions.action_result import ActionResult
                return ActionResult(success=True, data=None)
"""


def _write_plugin(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).strip() + "\n", encoding="utf-8")


def test_successful_loading_from_core_tools() -> None:
    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[CORE_TOOLS_DIR])

    result = loader.load()

    assert "code_editor" in result.loaded
    assert "fake_search" in result.loaded
    assert "fake_calculator" in result.loaded
    assert "obsidian" in result.loaded
    assert "browser" in result.loaded
    assert "python" in result.loaded
    assert "github" in result.loaded
    assert "terminal" in result.loaded
    assert registry.tool_exists("fake_search")
    assert registry.tool_exists("fake_calculator")
    assert registry.tool_exists("obsidian")
    assert registry.tool_exists("browser")
    assert registry.tool_exists("python")
    assert registry.tool_exists("github")
    assert registry.tool_exists("terminal")
    assert registry.tool_exists("code_editor")
    assert len(registry.list_tools()) == 8

    search_tool = registry.get_tool("fake_search")
    assert search_tool is not None
    assert search_tool.execute(query="titan") == {"query": "titan", "results": []}

    calculator_tool = registry.get_tool("fake_calculator")
    assert calculator_tool is not None
    assert calculator_tool.execute(left=3, right=2) == {"result": 5.0}


def test_demo_tools_are_not_manually_registered() -> None:
    """FakeSearchTool and FakeCalculatorTool must be discovered, not pre-registered."""
    registry = ToolRegistry()
    assert registry.list_tools() == []

    loader = ToolLoader(registry, scan_paths=[CORE_TOOLS_DIR])
    loader.load()

    tool_ids = {tool.id for tool in registry.list_tools()}
    assert tool_ids == {
        "fake_search",
        "fake_calculator",
        "obsidian",
        "browser",
        "python",
        "github",
        "terminal",
        "code_editor",
    }


def test_duplicate_ids_are_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    plugins = tmp_path / "plugins"
    _write_plugin(
        plugins / "first_tool.py",
        """
        from core.tools.base_tool import BaseTool

        class FirstTool(BaseTool):
            @property
            def id(self) -> str:
                return "duplicate_id"
            @property
            def name(self) -> str:
                return "First"
            @property
            def description(self) -> str:
                return "first"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "first"
        """,
    )
    _write_plugin(
        plugins / "second_tool.py",
        """
        from core.tools.base_tool import BaseTool

        class SecondTool(BaseTool):
            @property
            def id(self) -> str:
                return "duplicate_id"
            @property
            def name(self) -> str:
                return "Second"
            @property
            def description(self) -> str:
                return "second"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "second"
        """,
    )

    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[plugins])
    result = loader.load()

    assert result.duplicates == ["duplicate_id"]
    assert len(registry.list_tools()) == 1
    assert registry.get_tool("duplicate_id").execute() == "first"
    assert "Duplicate tool id" in caplog.text


def test_invalid_plugins_do_not_stop_loading(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    plugins = tmp_path / "plugins"
    _write_plugin(plugins / "broken.py", "raise SyntaxError('nope'")
    _write_plugin(
        plugins / "good_tool.py",
        """
        from core.tools.base_tool import BaseTool

        class GoodTool(BaseTool):
            @property
            def id(self) -> str:
                return "good_tool"
            @property
            def name(self) -> str:
                return "Good"
            @property
            def description(self) -> str:
                return "works"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "ok"
        """,
    )
    _write_plugin(
        plugins / "bad_instance.py",
        """
        from core.tools.base_tool import BaseTool

        class BadInstanceTool(BaseTool):
            def __init__(self) -> None:
                raise RuntimeError("boom")
            @property
            def id(self) -> str:
                return "bad_instance"
            @property
            def name(self) -> str:
                return "Bad"
            @property
            def description(self) -> str:
                return "bad"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return None
        """,
    )

    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[plugins])
    result = loader.load()

    assert registry.tool_exists("good_tool")
    assert len(result.failed) >= 2
    assert "good_tool" in result.loaded
    assert "Failed" in caplog.text or "Failed to" in caplog.text


def test_abstract_tools_are_ignored(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    _write_plugin(
        plugins / "abstract_tool.py",
        """
        from abc import abstractmethod
        from core.tools.base_tool import BaseTool

        class AbstractDemoTool(BaseTool):
            @property
            def id(self) -> str:
                return "abstract_demo"
            @property
            def name(self) -> str:
                return "Abstract"
            @property
            def description(self) -> str:
                return "abstract"
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
                return []
            @abstractmethod
            def execute(self, **kwargs: object) -> object:
                ...
        """,
    )
    _write_plugin(
        plugins / "concrete_tool.py",
        """
        from core.tools.base_tool import BaseTool

        class ConcreteTool(BaseTool):
            @property
            def id(self) -> str:
                return "concrete_tool"
            @property
            def name(self) -> str:
                return "Concrete"
            @property
            def description(self) -> str:
                return "concrete"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "done"
        """,
    )

    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[plugins])
    result = loader.load()

    assert registry.tool_exists("concrete_tool")
    assert not registry.tool_exists("abstract_demo")
    assert "AbstractDemoTool" in result.skipped


def test_disabled_tools_are_registered_and_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    plugins = tmp_path / "plugins"
    _write_plugin(
        plugins / "disabled_tool.py",
        """
        from core.tools.base_tool import BaseTool

        class DisabledTool(BaseTool):
            def __init__(self) -> None:
                super().__init__()
                self.enabled = False
            @property
            def id(self) -> str:
                return "disabled_tool"
            @property
            def name(self) -> str:
                return "Disabled"
            @property
            def description(self) -> str:
                return "disabled"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return None
        """,
    )

    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[plugins])
    result = loader.load()

    assert "disabled_tool" in result.disabled
    assert registry.tool_exists("disabled_tool")
    assert registry.get_tool("disabled_tool").enabled is False
    assert registry.list_enabled_tools() == []
    assert "Disabled tool" in caplog.text


def test_reload_clears_and_rediscovers_tools(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    tool_file = plugins / "reload_tool.py"
    _write_plugin(
        tool_file,
        """
        from core.tools.base_tool import BaseTool

        class ReloadTool(BaseTool):
            @property
            def id(self) -> str:
                return "reload_tool"
            @property
            def name(self) -> str:
                return "Reload"
            @property
            def description(self) -> str:
                return "reload"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "v1"
        """,
    )

    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[plugins])
    first = loader.load()
    assert "reload_tool" in first.loaded
    assert registry.get_tool("reload_tool").execute() == "v1"

    tool_file.write_text(
        textwrap.dedent(
            """
            from core.tools.base_tool import BaseTool

            class ReloadTool(BaseTool):
                @property
                def id(self) -> str:
                    return "reload_tool"
                @property
                def name(self) -> str:
                    return "Reload"
                @property
                def description(self) -> str:
                    return "reload"
                @property
                def version(self) -> str:
                    return "0.2.0"
                @property
                def category(self) -> str:
                    return "demo"
                @property
                def requires_confirmation(self) -> bool:
                    return False
                @property
                def capabilities(self) -> list[str]:
                    return []
                def list_actions(self):
                    return []
                def execute_action(self, action_id, **kwargs):
                    from core.actions.action_result import ActionResult
                    return ActionResult(success=True, data=None)
                def execute(self, **kwargs: object) -> object:
                    return "v2"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    second = loader.reload()
    assert "reload_tool" in second.loaded
    assert registry.tool_exists("reload_tool")
    assert registry.get_tool("reload_tool").version == "0.2.0"
    assert registry.get_tool("reload_tool").execute() == "v2"
    assert loader.loaded_tool_ids == ("reload_tool",)


def test_multiple_folders_are_scanned(tmp_path: Path) -> None:
    folder_a = tmp_path / "folder_a"
    folder_b = tmp_path / "folder_b"
    _write_plugin(
        folder_a / "tool_a.py",
        """
        from core.tools.base_tool import BaseTool

        class ToolA(BaseTool):
            @property
            def id(self) -> str:
                return "tool_a"
            @property
            def name(self) -> str:
                return "A"
            @property
            def description(self) -> str:
                return "a"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "a"
        """,
    )
    _write_plugin(
        folder_b / "nested" / "tool_b.py",
        """
        from core.tools.base_tool import BaseTool

        class ToolB(BaseTool):
            @property
            def id(self) -> str:
                return "tool_b"
            @property
            def name(self) -> str:
                return "B"
            @property
            def description(self) -> str:
                return "b"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "b"
        """,
    )

    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[folder_a, folder_b])
    result = loader.load()

    assert set(result.loaded) == {"tool_a", "tool_b"}
    assert registry.tool_exists("tool_a")
    assert registry.tool_exists("tool_b")


def test_add_scan_path_before_load(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    _write_plugin(
        plugins / "added_tool.py",
        """
        from core.tools.base_tool import BaseTool

        class AddedTool(BaseTool):
            @property
            def id(self) -> str:
                return "added_tool"
            @property
            def name(self) -> str:
                return "Added"
            @property
            def description(self) -> str:
                return "added"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "added"
        """,
    )

    registry = ToolRegistry()
    loader = ToolLoader(registry)
    loader.add_scan_path(plugins)
    result = loader.load()

    assert "added_tool" in result.loaded


def test_missing_scan_path_is_skipped(tmp_path: Path) -> None:
    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[tmp_path / "missing"])
    result = loader.load()

    assert str((tmp_path / "missing").resolve()) in result.skipped
    assert registry.list_tools() == []


def test_loader_tracks_only_its_registrations(tmp_path: Path) -> None:
    class ManualTool(BaseTool):
        @property
        def id(self) -> str:
            return "manual_tool"

        @property
        def name(self) -> str:
            return "Manual"

        @property
        def description(self) -> str:
            return "manual"

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
            return []

        def list_actions(self) -> list:
            return []

        def execute_action(self, action_id: str, **kwargs: object) -> object:
            from core.actions.action_result import ActionResult

            return ActionResult(success=True, data=None)

        def execute(self, **kwargs: object) -> object:
            return "manual"

    plugins = tmp_path / "plugins"
    _write_plugin(
        plugins / "loaded_tool.py",
        """
        from core.tools.base_tool import BaseTool

        class LoadedTool(BaseTool):
            @property
            def id(self) -> str:
                return "loaded_tool"
            @property
            def name(self) -> str:
                return "Loaded"
            @property
            def description(self) -> str:
                return "loaded"
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
                return []
""" + _PLUGIN_ACTION_METHODS + """
            def execute(self, **kwargs: object) -> object:
                return "loaded"
        """,
    )

    registry = ToolRegistry()
    registry.register_tool(ManualTool())
    loader = ToolLoader(registry, scan_paths=[plugins])
    loader.load()
    loader.reload()

    assert registry.tool_exists("manual_tool")
    assert registry.tool_exists("loaded_tool")
    assert "manual_tool" not in loader.loaded_tool_ids
    assert "loaded_tool" in loader.loaded_tool_ids

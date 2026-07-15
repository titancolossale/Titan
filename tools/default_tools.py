# =====================================
# Titan Default Tool Registration
# =====================================

"""Central registration for built-in tools (Phase 12.8 — P128-004)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tools.calendar_tool import CalendarTool
from tools.email_tool import EmailTool
from tools.file_read_tool import FileReadTool
from tools.file_write_tool import FileWriteTool
from tools.github_tool import GitHubTool
from tools.browser_tool import BrowserTool
from tools.obsidian_tool import ObsidianTool
from tools.python_exec_tool import PythonExecTool
from tools.time_tool import TimeTool
from tools.tool_registry import ToolRegistry
from tools.providers.provider_executor import ProviderExecutor
from tools.trading_tool import TradingTool
from tools.web_search_tool import WebSearchTool


def build_default_tools(
    project_root: Path,
    *,
    provider_executor: ProviderExecutor | None = None,
) -> list:
    """Return default tool instances for registration."""
    return [
        TimeTool(),
        FileReadTool(project_root, provider_executor=provider_executor),
        FileWriteTool(project_root, provider_executor=provider_executor),
        PythonExecTool(project_root),
        WebSearchTool(provider_executor=provider_executor),
        CalendarTool(),
        EmailTool(),
        TradingTool(),
        GitHubTool(provider_executor=provider_executor),
        ObsidianTool(),
        BrowserTool(),
    ]


def register_default_tools(
    registry: ToolRegistry,
    project_root: Path,
    *,
    provider_executor: ProviderExecutor | None = None,
    refresh_catalog: Callable[[], None] | None = None,
) -> None:
    """Register all built-in tools if not already present."""
    for tool in build_default_tools(
        project_root,
        provider_executor=provider_executor,
    ):
        if registry.get(tool.name) is None:
            registry.register(tool)

    browser_tool = registry.get("browser")
    if browser_tool is not None and hasattr(browser_tool, "wire_search_from_manager"):
        browser_tool.wire_search_from_manager(registry)

    if refresh_catalog is not None:
        refresh_catalog()

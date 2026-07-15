# =====================================
# Titan Capability Registry Tests
# =====================================

"""Tests for dynamic tool discovery and the shared capability registry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from brain.tool_execution_engine import build_core_tool_runtime
from brain.tool_intelligence import ToolIntelligence, build_default_tool_intelligence
from core.actions.action import Action
from core.actions.action_result import ActionResult
from core.tools import BaseTool, CapabilityRegistry, ToolLoader, ToolRegistry
from core.tools.capability_models import (
    CapabilityRecord,
    CapabilityValidationError,
    validate_capability_record,
)
from core.tools.capability_registry import CapabilitySearchResult
from core.tools.exceptions import ToolAlreadyRegisteredError

CORE_TOOLS_DIR = Path(__file__).resolve().parents[1] / "core" / "tools"


def _write_plugin(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).strip() + "\n", encoding="utf-8")


class _RegistryDemoTool(BaseTool):
    """Minimal tool for registry unit tests."""

    def __init__(self, tool_id: str = "registry_demo") -> None:
        super().__init__()
        self._tool_id = tool_id
        self._actions = (
            Action(
                id="ping",
                name="Ping",
                description="Return a pong response.",
                tool_id=tool_id,
                permission_id=f"{tool_id}.ping",
                parameters={"message": {"type": "string"}},
                metadata={"capability": "demo.ping"},
            ),
        )

    @property
    def id(self) -> str:
        return self._tool_id

    @property
    def name(self) -> str:
        return "Registry Demo"

    @property
    def description(self) -> str:
        return "Demo tool for capability registry tests."

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def category(self) -> str:
        return "demo"

    @property
    def requires_confirmation(self) -> bool:
        return False

    @property
    def capabilities(self) -> list[str]:
        return ["demo.ping"]

    @property
    def tags(self) -> list[str]:
        return ["demo", "registry"]

    def list_actions(self) -> list[Action]:
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        return ActionResult(success=True, data={"pong": kwargs.get("message", "")})

    def execute(self, **kwargs: object) -> object:
        return {"pong": kwargs.get("message", "")}


def test_tool_loader_auto_registers_capability_metadata(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    _write_plugin(
        plugin_dir / "demo_tool.py",
        """
        from core.actions.action import Action
        from core.actions.action_result import ActionResult
        from core.tools.base_tool import BaseTool

        class AutoRegistryTool(BaseTool):
            @property
            def id(self):
                return "auto_registry"

            @property
            def name(self):
                return "Auto Registry"

            @property
            def description(self):
                return "Discovered automatically."

            @property
            def version(self):
                return "1.0.0"

            @property
            def category(self):
                return "demo"

            @property
            def requires_confirmation(self):
                return False

            @property
            def capabilities(self):
                return ["auto.discover"]

            def list_actions(self):
                return [
                    Action(
                        id="run",
                        name="Run",
                        description="Run demo action.",
                        tool_id=self.id,
                        permission_id="auto_registry.run",
                    )
                ]

            def execute_action(self, action_id, **kwargs):
                return ActionResult(success=True, data=None)

            def execute(self, **kwargs):
                return None
        """,
    )

    cap_registry = CapabilityRegistry()
    tool_registry = ToolRegistry(capability_registry=cap_registry)
    loader = ToolLoader(tool_registry, scan_paths=[plugin_dir])
    result = loader.load()

    assert "auto_registry" in result.loaded
    record = cap_registry.get_tool("auto_registry")
    assert record is not None
    assert record.display_name == "Auto Registry"
    assert "auto.discover" in record.capabilities
    assert record.supported_actions[0].id == "run"


def test_duplicate_tool_id_rejected_by_registry() -> None:
    cap_registry = CapabilityRegistry()
    tool_registry = ToolRegistry(capability_registry=cap_registry)
    tool_registry.register_tool(_RegistryDemoTool())

    with pytest.raises(ToolAlreadyRegisteredError):
        tool_registry.register_tool(_RegistryDemoTool())


def test_metadata_validation_rejects_invalid_version() -> None:
    tool = _RegistryDemoTool()
    record = CapabilityRecord.from_tool(tool)
    invalid = CapabilityRecord(
        **{
            **record.__dict__,
            "version": "not-a-version",
        }
    )
    errors = validate_capability_record(invalid)
    assert any("semver" in error for error in errors)


def test_metadata_validation_rejects_duplicate_actions() -> None:
    class DuplicateActionTool(_RegistryDemoTool):
        def list_actions(self) -> list[Action]:
            action = Action(
                id="ping",
                name="Ping",
                description="Duplicate id.",
                tool_id=self.id,
                permission_id="registry_demo.ping",
            )
            return [action, action]

    with pytest.raises(CapabilityValidationError):
        CapabilityRecord.from_tool(DuplicateActionTool())


def test_capability_registry_search_and_filters() -> None:
    cap_registry = CapabilityRegistry()
    tool_registry = ToolRegistry(capability_registry=cap_registry)
    tool_registry.register_tool(_RegistryDemoTool())

    by_category = cap_registry.find_by_category("demo")
    assert len(by_category) == 1

    by_capability = cap_registry.find_by_capability("demo.ping")
    assert len(by_capability) == 1

    by_action = cap_registry.find_by_action("ping")
    assert len(by_action) == 1

    by_permission = cap_registry.find_by_permission("registry_demo.ping")
    assert len(by_permission) == 1

    search_hits = cap_registry.search("registry demo")
    assert search_hits
    assert isinstance(search_hits[0], CapabilitySearchResult)

    exact_hits = cap_registry.search("registry_demo", exact=True)
    assert exact_hits
    assert exact_hits[0].record.id == "registry_demo"


def test_capability_registry_summarize_and_serialize() -> None:
    cap_registry = CapabilityRegistry()
    tool_registry = ToolRegistry(capability_registry=cap_registry)
    tool_registry.register_tool(_RegistryDemoTool())

    summary = cap_registry.summarize()
    assert summary.total_tools == 1
    assert summary.enabled_tools == 1
    assert summary.categories["demo"] == 1

    exported = cap_registry.export()
    assert exported["summary"]["total_tools"] == 1
    assert exported["tools"][0]["id"] == "registry_demo"


def test_tool_intelligence_uses_capability_registry() -> None:
    intelligence = build_default_tool_intelligence(scan_paths=[CORE_TOOLS_DIR])

    records = intelligence.list_capabilities()
    assert len(records) >= 7
    assert any(record.id == "browser" for record in records)
    assert any(record.id == "github" for record in records)

    web_hits = intelligence.search_capabilities("web")
    assert web_hits

    github_hits = intelligence.search_capabilities("github")
    assert any(hit.record.id == "github" for hit in github_hits)

    confirmation_tools = intelligence.capability_registry.find_requiring_confirmation()
    assert isinstance(confirmation_tools, list)

    summary = intelligence.summarize_installed_tools()
    assert summary.total_tools >= 7


def test_tool_intelligence_find_tools_for_task() -> None:
    intelligence = build_default_tool_intelligence(scan_paths=[CORE_TOOLS_DIR])

    hits = intelligence.find_tools_for_task("search the internet")
    assert hits
    assert any(
        "web" in hit.record.category or "browser" in hit.record.id.lower()
        for hit in hits
    )

    code_hits = intelligence.find_tools_for_task("execute python code")
    assert any(hit.record.id == "python" for hit in code_hits)


def test_brain_capability_apis(tmp_path: Path) -> None:
    from agents.agent_manager import AgentManager
    from context.context_manager import ContextManager
    from core.state_manager import StateManager
    from core.mission_manager import MissionManager
    from memory.memory_service import MemoryService
    from memory.memory_manager import MemoryManager
    from memory.long_term_memory import LongTermMemory
    from tools.tool_manager import ToolManager
    from brain.brain import Brain

    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory_service = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])
    brain = Brain(
        agent_manager=AgentManager(),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory_service,
        tool_manager=ToolManager(project_root=tmp_path),
        core_tool_runtime=runtime,
    )

    capabilities = brain.list_capabilities()
    assert len(capabilities) >= 7

    search_hits = brain.search_capabilities("obsidian")
    assert search_hits

    described = brain.describe_tool("browser")
    assert described is not None
    assert described.id == "browser"

    task_hits = brain.find_tools_for_task("modify files in the codebase")
    assert task_hits

    summary = brain.summarize_installed_tools()
    assert summary.total_tools >= 7
    assert summary.tools


def test_core_runtime_includes_capability_registry() -> None:
    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])
    assert runtime.capability_registry is not None
    assert runtime.capability_registry.list_tools()
    assert runtime.intelligence.capability_registry is runtime.capability_registry


def test_dynamic_plugin_discovery_without_brain_changes(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "slack"
    _write_plugin(
        plugin_dir / "slack_tool.py",
        """
        from core.actions.action import Action
        from core.actions.action_result import ActionResult
        from core.tools.base_tool import BaseTool

        class SlackTool(BaseTool):
            @property
            def id(self):
                return "slack"

            @property
            def name(self):
                return "Slack"

            @property
            def description(self):
                return "Send Slack messages."

            @property
            def version(self):
                return "0.1.0"

            @property
            def category(self):
                return "web"

            @property
            def requires_confirmation(self):
                return True

            @property
            def capabilities(self):
                return ["messaging.send"]

            @property
            def tags(self):
                return ["slack", "chat"]

            def list_actions(self):
                return [
                    Action(
                        id="send_message",
                        name="Send Message",
                        description="Send a Slack message.",
                        tool_id=self.id,
                        permission_id="slack.send_message",
                    )
                ]

            def execute_action(self, action_id, **kwargs):
                return ActionResult(success=True, data=None)

            def execute(self, **kwargs):
                return None
        """,
    )

    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR, plugin_dir])
    record = runtime.capability_registry.get_tool("slack")
    assert record is not None
    assert record.requires_confirmation is True
    assert "messaging.send" in record.capabilities

    hits = runtime.intelligence.search_capabilities("slack")
    assert any(hit.record.id == "slack" for hit in hits)


def test_streaming_and_experimental_filters() -> None:
    class StreamingTool(_RegistryDemoTool):
        @property
        def streaming_support(self) -> bool:
            return True

        @property
        def experimental(self) -> bool:
            return True

    cap_registry = CapabilityRegistry()
    tool_registry = ToolRegistry(capability_registry=cap_registry)
    tool_registry.register_tool(StreamingTool())

    assert cap_registry.find_streaming()
    assert cap_registry.find_experimental()


def test_future_compatible_export_shape() -> None:
    cap_registry = CapabilityRegistry()
    tool_registry = ToolRegistry(capability_registry=cap_registry)
    tool_registry.register_tool(_RegistryDemoTool())
    payload = cap_registry.export()

    required_tool_keys = {
        "id",
        "display_name",
        "version",
        "enabled",
        "capabilities",
        "permissions_required",
        "risk_level",
        "status",
    }
    assert required_tool_keys.issubset(payload["tools"][0].keys())

    required_summary_keys = {
        "total_tools",
        "enabled_tools",
        "categories",
        "capabilities",
        "risk_levels",
    }
    assert required_summary_keys.issubset(payload["summary"].keys())

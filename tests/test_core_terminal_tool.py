# =====================================
# Titan Core Terminal Tool V1 Tests
# =====================================

"""Tests for controlled Terminal integration in core/tools/terminal."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from brain.tool_execution_engine import ToolExecutionEngine, build_core_tool_runtime
from brain.tool_intelligence import (
    PlannedAction,
    SelectedTool,
    ToolExecutionPlan,
    ToolIntent,
    ToolIntelligence,
)
from core.actions import ActionDispatcher, ActionRegistry
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools import ToolLoader, ToolRegistry
from core.tools.terminal import (
    PERMISSION_EXECUTE,
    PERMISSION_GIT,
    PERMISSION_TESTING,
    TerminalConfig,
    TerminalPermissionDeniedError,
    TerminalTool,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_TOOLS_DIR = PROJECT_ROOT / "core" / "tools"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "terminal_workspace"
    root.mkdir()
    return root


@pytest.fixture
def terminal_config(workspace: Path) -> TerminalConfig:
    # Ensure the active interpreter basename is allowlisted (e.g. python.exe).
    from core.tools.terminal.terminal_config import DEFAULT_ALLOWED_COMMANDS

    interpreter = Path(sys.executable).name.lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if interpreter.endswith(suffix):
            interpreter = interpreter[: -len(suffix)]
            break
    allowed = frozenset(DEFAULT_ALLOWED_COMMANDS | {interpreter})
    return TerminalConfig.for_workspace(
        workspace,
        timeout_seconds=5.0,
        max_execution_seconds=5.0,
        max_output_bytes=16 * 1024,
        allowed_commands=allowed,
    )


@pytest.fixture
def terminal_tool(terminal_config: TerminalConfig) -> TerminalTool:
    return TerminalTool(config=terminal_config)


def _allow_all_permissions() -> PermissionManager:
    manager = PermissionManager()
    for permission_id, name in (
        (PERMISSION_EXECUTE, "Execute Terminal"),
        (PERMISSION_GIT, "Terminal Git"),
        (PERMISSION_TESTING, "Terminal Testing"),
    ):
        manager.register_permission(
            Permission(
                id=permission_id,
                name=name,
                description="Allowed for test.",
                level=PermissionLevel.SAFE,
            )
        )
    return manager


def test_allowed_command(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action(
        "run_command",
        command=[sys.executable, "-c", "print('hello-terminal')"],
    )

    assert result.success is True
    assert "hello-terminal" in result.data["stdout"]
    assert result.data["stderr"] == ""
    assert result.data["exit_code"] == 0
    assert result.data["duration"] >= 0.0
    assert result.execution_time >= 0.0


def test_blocked_command_rm_rf(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action("run_command", command="rm -rf /")

    assert result.success is False
    assert "blocked" in result.message.lower() or "allowlist" in result.message.lower()


def test_blocked_command_shutdown(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action("run_command", command="shutdown /s")

    assert result.success is False
    assert "blocked" in result.message.lower()


def test_blocked_command_sudo(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action("run_command", command="sudo apt update")

    assert result.success is False
    assert "blocked" in result.message.lower() or "sudo" in result.message.lower()


def test_blocked_shell_metacharacters(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action(
        "run_command",
        command=f"{sys.executable} -c \"print(1)\" && {sys.executable} -c \"print(2)\"",
    )

    assert result.success is False
    assert "blocked" in result.message.lower() or "metacharacter" in result.message.lower()


def test_blocked_powershell_execution_policy(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action(
        "run_command",
        command="powershell Set-ExecutionPolicy Bypass",
    )

    assert result.success is False
    assert "blocked" in result.message.lower()


def test_cwd_escape_rejected(terminal_tool: TerminalTool, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()

    result = terminal_tool.execute_action(
        "run_command",
        command=[sys.executable, "-c", "print(1)"],
        cwd=str(outside),
    )

    assert result.success is False
    assert "escape" in result.message.lower() or "path" in result.message.lower()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_command(terminal_tool: TerminalTool, workspace: Path) -> None:
    # Initialize a local repo so git status succeeds without relying on PROJECT_ROOT.
    init = terminal_tool.execute_action("run_git", args="init")
    assert init.success is True

    result = terminal_tool.execute_action("run_git", args="status")

    assert result.success is True
    assert result.data["exit_code"] == 0
    assert "git" in result.data["command"].lower()
    assert "status" in result.data["command"].lower()
    assert result.data["stdout"] or result.data["stderr"] == ""


@pytest.mark.skipif(shutil.which("pytest") is None, reason="pytest not on PATH")
def test_pytest_action(terminal_tool: TerminalTool, workspace: Path) -> None:
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    result = terminal_tool.execute_action(
        "run_pytest",
        args="tests/test_sample.py -q",
        timeout=30.0,
    )

    assert result.data["exit_code"] == 0
    assert result.success is True
    assert "pytest" in result.data["command"].lower()


def test_permission_denied_via_dispatcher(terminal_config: TerminalConfig) -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_EXECUTE,
            name="Blocked Execute",
            description="Blocked for test.",
            level=PermissionLevel.BLOCKED,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_GIT,
            name="Git",
            description="Allowed.",
            level=PermissionLevel.SAFE,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_TESTING,
            name="Testing",
            description="Allowed.",
            level=PermissionLevel.SAFE,
        )
    )

    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = TerminalTool(
        config=terminal_config,
        permission_manager=permission_manager,
        action_registry=action_registry,
    )
    tool_registry.register_tool(tool)

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
    )

    result = dispatcher.dispatch(
        "terminal",
        "run_command",
        {"command": [sys.executable, "-c", "print(1)"]},
    )

    assert result.success is False
    assert "permission" in result.message.lower() or "blocked" in result.message.lower()
    assert result.metadata["permission_id"] == PERMISSION_EXECUTE


def test_confirmation_required_blocks_execute(terminal_tool: TerminalTool) -> None:
    """Default terminal.* permissions are CONFIRMATION_REQUIRED — dispatcher must deny."""
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = TerminalTool(
        config=terminal_tool.client.config,
        permission_manager=terminal_tool.permission_manager,
        action_registry=action_registry,
    )
    tool_registry.register_tool(tool)

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=tool.permission_manager,
    )

    result = dispatcher.dispatch(
        "terminal",
        "run_command",
        {"command": [sys.executable, "-c", "print(1)"]},
    )

    assert result.success is False
    assert "confirmation" in result.message.lower()


def test_timeout(terminal_config: TerminalConfig) -> None:
    config = TerminalConfig.for_workspace(
        terminal_config.workspace_root,
        timeout_seconds=0.3,
        max_execution_seconds=0.3,
    )
    tool = TerminalTool(config=config)

    result = tool.execute_action(
        "run_python",
        args=["-c", "import time; time.sleep(5)"],
        timeout=0.3,
    )

    assert result.success is False
    assert result.data["timed_out"] is True
    assert result.data["exit_code"] == -1
    assert "timeout" in result.data["stderr"].lower() or result.errors


def test_output_capture(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action(
        "run_python",
        args=["-c", "import sys; print('out'); print('err', file=sys.stderr)"],
    )

    assert result.success is True
    assert "out" in result.data["stdout"]
    assert "err" in result.data["stderr"]
    assert result.data["exit_code"] == 0
    assert "duration" in result.data


def test_run_python_action(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action(
        "run_python",
        args=["-c", "print(2+2)"],
    )

    assert result.success is True
    assert result.data["stdout"].strip() == "4"


def test_legacy_execute_requires_permission(terminal_config: TerminalConfig) -> None:
    tool = TerminalTool(config=terminal_config)

    with pytest.raises(TerminalPermissionDeniedError):
        tool.execute(
            action="run_command",
            command=[sys.executable, "-c", "print(1)"],
        )


def test_legacy_execute_with_safe_permission(terminal_config: TerminalConfig) -> None:
    tool = TerminalTool(
        config=terminal_config,
        permission_manager=_allow_all_permissions(),
    )

    data = tool.execute(
        action="run_command",
        command=[sys.executable, "-c", "print(99)"],
    )
    assert data["stdout"].strip() == "99"


def test_tool_registers_default_permissions(terminal_tool: TerminalTool) -> None:
    manager = terminal_tool.permission_manager

    assert manager.permission_exists(PERMISSION_EXECUTE)
    assert manager.permission_exists(PERMISSION_GIT)
    assert manager.permission_exists(PERMISSION_TESTING)
    assert manager.get_permission(PERMISSION_EXECUTE).level == PermissionLevel.CONFIRMATION_REQUIRED
    assert manager.get_permission(PERMISSION_GIT).level == PermissionLevel.CONFIRMATION_REQUIRED
    assert manager.get_permission(PERMISSION_TESTING).level == PermissionLevel.CONFIRMATION_REQUIRED


def test_tool_loader_discovers_terminal() -> None:
    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[CORE_TOOLS_DIR])
    result = loader.load()

    assert "terminal" in result.loaded
    loaded = registry.get_tool("terminal")
    assert loaded is not None
    assert loaded.id == "terminal"
    assert {action.id for action in loaded.list_actions()} == {
        "run_command",
        "run_python",
        "run_git",
        "run_pytest",
        "run_npm",
        "run_uv",
    }


def test_brain_integration_via_tool_execution_engine(
    terminal_config: TerminalConfig,
) -> None:
    """Terminal runs only through ToolExecutionEngine + ActionDispatcher — not Brain logic."""
    permission_manager = _allow_all_permissions()
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = TerminalTool(
        config=terminal_config,
        permission_manager=permission_manager,
        action_registry=action_registry,
    )
    tool_registry.register_tool(tool)

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
    )
    engine = ToolExecutionEngine(dispatcher)

    plan = ToolExecutionPlan(
        request="Run a terminal command",
        intent=ToolIntent.WRITE,
        intent_summary="Execute terminal command.",
        selected_tools=(
            SelectedTool(
                tool_id="terminal",
                tool_name="Terminal",
                category="shell",
                confidence=0.95,
                reason="Explicit terminal request.",
                actions=(
                    PlannedAction(
                        tool_id="terminal",
                        action_id="run_command",
                        reason="Run command.",
                        confidence=0.95,
                        parameters={
                            "command": [sys.executable, "-c", "print('engine-ok')"],
                        },
                    ),
                ),
            ),
        ),
        execution_order=("terminal",),
        confidence=0.95,
        requires_tools=True,
        reasoning_summary="test",
    )

    result = engine.execute(plan)

    assert result.success is True
    assert len(result.completed_steps) == 1
    assert result.completed_steps[0].tool_id == "terminal"
    assert result.completed_steps[0].action_id == "run_command"
    assert result.tool_outputs["terminal"]["stdout"].strip() == "engine-ok"


def test_core_runtime_discovers_terminal_tool() -> None:
    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])
    tool = runtime.tool_registry.get_tool("terminal")

    assert tool is not None
    assert tool.id == "terminal"
    assert runtime.action_registry.action_exists("terminal", "run_command")
    assert runtime.action_registry.action_exists("terminal", "run_git")
    assert runtime.action_registry.action_exists("terminal", "run_pytest")
    assert runtime.permission_manager.permission_exists(PERMISSION_EXECUTE)
    assert runtime.permission_manager.permission_exists(PERMISSION_GIT)
    assert runtime.permission_manager.permission_exists(PERMISSION_TESTING)


def test_tool_intelligence_routes_pytest() -> None:
    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])
    intelligence = ToolIntelligence(runtime.tool_registry)

    plan = intelligence.plan("Run pytest")

    assert plan.requires_tools is True
    assert any(tool.tool_id == "terminal" for tool in plan.selected_tools)
    terminal = next(tool for tool in plan.selected_tools if tool.tool_id == "terminal")
    assert terminal.actions[0].action_id == "run_pytest"


def test_tool_intelligence_routes_git_status() -> None:
    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])
    intelligence = ToolIntelligence(runtime.tool_registry)

    plan = intelligence.plan("Show git status")

    assert plan.requires_tools is True
    assert any(tool.tool_id == "terminal" for tool in plan.selected_tools)
    terminal = next(tool for tool in plan.selected_tools if tool.tool_id == "terminal")
    assert terminal.actions[0].action_id == "run_git"
    assert terminal.actions[0].parameters.get("args") == "status"


def test_tool_intelligence_routes_uv_sync() -> None:
    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])
    intelligence = ToolIntelligence(runtime.tool_registry)

    plan = intelligence.plan("Run uv sync")

    assert plan.requires_tools is True
    assert any(tool.tool_id == "terminal" for tool in plan.selected_tools)
    terminal = next(tool for tool in plan.selected_tools if tool.tool_id == "terminal")
    assert terminal.actions[0].action_id == "run_uv"
    assert terminal.actions[0].parameters.get("args") == "sync"


def test_missing_command_returns_failure(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action("run_command", command="   ")

    assert result.success is False
    assert "command" in result.message.lower()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_run_uv_version(terminal_tool: TerminalTool) -> None:
    result = terminal_tool.execute_action("run_uv", args="--version")

    assert result.success is True
    assert result.data["exit_code"] == 0
    assert "uv" in result.data["stdout"].lower() or "uv" in result.data["command"].lower()

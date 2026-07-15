# =====================================
# Titan Core Python Runtime V1 Tests
# =====================================

"""Tests for sandboxed Python Runtime integration in core/tools/python."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.tool_execution_engine import ToolExecutionEngine, build_core_tool_runtime
from brain.tool_intelligence import (
    PlannedAction,
    SelectedTool,
    ToolExecutionPlan,
    ToolIntent,
)
from core.actions import ActionDispatcher, ActionRegistry
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools import ToolLoader, ToolRegistry
from core.tools.python import (
    PERMISSION_EXECUTE,
    PERMISSION_FORMAT,
    PERMISSION_SYNTAX_CHECK,
    PythonConfigurationError,
    PythonPermissionDeniedError,
    PythonRuntimeConfig,
    PythonTool,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_TOOLS_DIR = PROJECT_ROOT / "core" / "tools"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "python_workspace"
    root.mkdir()
    return root


@pytest.fixture
def python_config(workspace: Path) -> PythonRuntimeConfig:
    return PythonRuntimeConfig.for_workspace(
        workspace,
        timeout_seconds=2.0,
        max_execution_seconds=2.0,
        max_output_bytes=16 * 1024,
        max_file_count=20,
    )


@pytest.fixture
def python_tool(python_config: PythonRuntimeConfig) -> PythonTool:
    return PythonTool(config=python_config)


def _allow_all_permissions() -> PermissionManager:
    manager = PermissionManager()
    for permission_id, name in (
        (PERMISSION_EXECUTE, "Execute Python"),
        (PERMISSION_FORMAT, "Format Python"),
        (PERMISSION_SYNTAX_CHECK, "Syntax Check Python"),
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


def test_successful_snippet_execution(python_tool: PythonTool) -> None:
    result = python_tool.execute_action("run_snippet", code="print('hello-titan')")

    assert result.success is True
    assert result.data["stdout"].strip() == "hello-titan"
    assert result.data["stderr"] == ""
    assert result.data["exit_code"] == 0
    assert result.data["duration"] >= 0.0
    assert result.data["files_created"] == []
    assert result.execution_time >= 0.0


def test_syntax_error_on_snippet(python_tool: PythonTool) -> None:
    result = python_tool.execute_action("run_snippet", code="def broken(:\n    pass\n")

    assert result.success is False
    assert result.data["exit_code"] != 0
    assert result.data["stderr"]
    assert result.errors


def test_timeout(python_config: PythonRuntimeConfig) -> None:
    config = PythonRuntimeConfig.for_workspace(
        python_config.workspace_root,
        timeout_seconds=0.3,
        max_execution_seconds=0.3,
    )
    tool = PythonTool(config=config)

    result = tool.execute_action(
        "run_snippet",
        code="import time\ntime.sleep(5)",
        timeout=0.3,
    )

    assert result.success is False
    assert result.data["timed_out"] is True
    assert result.data["exit_code"] == -1
    assert "timeout" in result.data["stderr"].lower() or result.errors


def test_permission_denied_via_dispatcher(python_config: PythonRuntimeConfig) -> None:
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
            id=PERMISSION_SYNTAX_CHECK,
            name="Syntax",
            description="Allowed.",
            level=PermissionLevel.SAFE,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_FORMAT,
            name="Format",
            description="Allowed.",
            level=PermissionLevel.SAFE,
        )
    )

    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = PythonTool(
        config=python_config,
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
        "python",
        "run_snippet",
        {"code": "print(1)"},
    )

    assert result.success is False
    assert "permission" in result.message.lower() or "blocked" in result.message.lower()
    assert result.metadata["permission_id"] == PERMISSION_EXECUTE


def test_confirmation_required_blocks_execute(python_tool: PythonTool) -> None:
    """Default python.execute is CONFIRMATION_REQUIRED — dispatcher must deny."""
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = PythonTool(
        config=python_tool.client.config,
        permission_manager=python_tool.permission_manager,
        action_registry=action_registry,
    )
    tool_registry.register_tool(tool)

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=tool.permission_manager,
    )

    result = dispatcher.dispatch("python", "run_snippet", {"code": "print(1)"})

    assert result.success is False
    assert "confirmation" in result.message.lower()


def test_output_capture(python_tool: PythonTool) -> None:
    result = python_tool.execute_action(
        "run_snippet",
        code="import sys\nprint('out')\nprint('err', file=sys.stderr)",
    )

    assert result.success is True
    assert "out" in result.data["stdout"]
    assert "err" in result.data["stderr"]


def test_file_generation(python_tool: PythonTool, workspace: Path) -> None:
    result = python_tool.execute_action(
        "run_snippet",
        code=(
            "from pathlib import Path\n"
            "Path('artifact.txt').write_text('created', encoding='utf-8')\n"
            "print('done')\n"
        ),
    )

    assert result.success is True
    assert "artifact.txt" in result.data["files_created"]
    assert (workspace / "artifact.txt").read_text(encoding="utf-8") == "created"


def test_run_script(python_tool: PythonTool, workspace: Path) -> None:
    script = workspace / "hello.py"
    script.write_text("print('from-script')\n", encoding="utf-8")

    result = python_tool.execute_action("run_script", path="hello.py")

    assert result.success is True
    assert result.data["stdout"].strip() == "from-script"
    assert result.data["path"] == "hello.py"


def test_run_script_rejects_path_escape(
    python_tool: PythonTool,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("print('nope')\n", encoding="utf-8")

    result = python_tool.execute_action(
        "run_script",
        path="../outside.py",
    )

    assert result.success is False
    assert "escape" in result.message.lower() or "path" in result.message.lower()


def test_syntax_check_valid(python_tool: PythonTool) -> None:
    result = python_tool.execute_action(
        "syntax_check",
        code="x = 1 + 2\nprint(x)\n",
    )

    assert result.success is True
    assert result.data["valid"] is True


def test_syntax_check_invalid(python_tool: PythonTool) -> None:
    result = python_tool.execute_action(
        "syntax_check",
        code="def broken(:\n",
    )

    assert result.success is False
    assert result.data["valid"] is False
    assert result.data["line"] is not None


def test_format_code(python_tool: PythonTool) -> None:
    result = python_tool.execute_action(
        "format_code",
        code="x = 1  \n",
    )

    assert result.success is True
    assert result.data["formatted_code"] == "x = 1\n"
    assert result.data["changed"] is True


def test_blocks_network_import(python_tool: PythonTool) -> None:
    result = python_tool.execute_action(
        "run_snippet",
        code="import socket\nprint(socket.gethostname())",
    )

    assert result.success is False
    assert "blocked" in result.message.lower()


def test_blocks_subprocess_import(python_tool: PythonTool) -> None:
    result = python_tool.execute_action(
        "run_snippet",
        code="import subprocess\nsubprocess.run(['echo', 'hi'])",
    )

    assert result.success is False
    assert "blocked" in result.message.lower()


def test_blocks_os_system(python_tool: PythonTool) -> None:
    result = python_tool.execute_action(
        "run_snippet",
        code="import os\nos.system('echo hi')",
    )

    assert result.success is False
    assert "blocked" in result.message.lower()


def test_legacy_execute_requires_permission(python_config: PythonRuntimeConfig) -> None:
    tool = PythonTool(config=python_config)

    with pytest.raises(PythonPermissionDeniedError):
        tool.execute(action="run_snippet", code="print(1)")


def test_legacy_execute_with_safe_permission(python_config: PythonRuntimeConfig) -> None:
    tool = PythonTool(
        config=python_config,
        permission_manager=_allow_all_permissions(),
    )

    data = tool.execute(action="run_snippet", code="print(42)")
    assert data["stdout"].strip() == "42"


def test_missing_code_returns_failure(python_tool: PythonTool) -> None:
    result = python_tool.execute_action("run_snippet", code="   ")

    assert result.success is False
    assert "code" in result.message.lower()


def test_tool_registers_default_permissions(python_tool: PythonTool) -> None:
    manager = python_tool.permission_manager

    assert manager.permission_exists(PERMISSION_EXECUTE)
    assert manager.permission_exists(PERMISSION_FORMAT)
    assert manager.permission_exists(PERMISSION_SYNTAX_CHECK)
    assert manager.get_permission(PERMISSION_EXECUTE).level == PermissionLevel.CONFIRMATION_REQUIRED
    assert manager.get_permission(PERMISSION_FORMAT).level == PermissionLevel.SAFE


def test_tool_loader_discovers_python() -> None:
    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[CORE_TOOLS_DIR])
    result = loader.load()

    assert "python" in result.loaded
    loaded = registry.get_tool("python")
    assert loaded is not None
    assert loaded.id == "python"
    assert {action.id for action in loaded.list_actions()} == {
        "run_snippet",
        "run_script",
        "syntax_check",
        "format_code",
    }


def test_dispatcher_end_to_end_syntax_check(python_config: PythonRuntimeConfig) -> None:
    permission_manager = _allow_all_permissions()
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = PythonTool(
        config=python_config,
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
        "python",
        "syntax_check",
        {"code": "print(1)"},
    )

    assert result.success is True
    assert result.metadata["tool_id"] == "python"
    assert result.data["valid"] is True


def test_brain_integration_via_tool_execution_engine(
    python_config: PythonRuntimeConfig,
) -> None:
    """Python runs only through ToolExecutionEngine + ActionDispatcher — not Brain logic."""
    permission_manager = _allow_all_permissions()
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = PythonTool(
        config=python_config,
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
        request="Run this python snippet",
        intent=ToolIntent.WRITE,
        intent_summary="Execute python snippet.",
        selected_tools=(
            SelectedTool(
                tool_id="python",
                tool_name="Python Runtime",
                category="runtime",
                confidence=0.95,
                reason="Explicit python request.",
                actions=(
                    PlannedAction(
                        tool_id="python",
                        action_id="run_snippet",
                        reason="Run snippet.",
                        confidence=0.95,
                        parameters={"code": "print('engine-ok')"},
                    ),
                ),
            ),
        ),
        execution_order=("python",),
        confidence=0.95,
        requires_tools=True,
        reasoning_summary="test",
    )

    result = engine.execute(plan)

    assert result.success is True
    assert len(result.completed_steps) == 1
    assert result.completed_steps[0].tool_id == "python"
    assert result.completed_steps[0].action_id == "run_snippet"
    assert result.tool_outputs["python"]["stdout"].strip() == "engine-ok"


def test_core_runtime_discovers_python_tool() -> None:
    runtime = build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])
    tool = runtime.tool_registry.get_tool("python")

    assert tool is not None
    assert tool.id == "python"
    assert runtime.action_registry.action_exists("python", "run_snippet")
    assert runtime.permission_manager.permission_exists(PERMISSION_EXECUTE)


def test_empty_action_raises(python_tool: PythonTool) -> None:
    with pytest.raises(PythonConfigurationError, match="action"):
        python_tool.execute(code="print(1)")

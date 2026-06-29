# =====================================
# Titan Tool Framework Tests
# =====================================

"""Security and integration tests for Phase 6 tool framework (P6-040–P6-060)."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.brain import Brain
from brain.executor import Executor
from brain.pipeline.stages import STAGE_ORDER
from brain.prompt_builder import PromptBuilder
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from config.settings import TOOL_WRITE_DRY_RUN_DEFAULT
from tools.file_read_tool import FileReadTool
from tools.file_write_tool import FileWriteTool
from tools.path_guard import PathGuardError, resolve_allowed_path
from tools.python_exec_tool import PythonExecTool
from tools.time_tool import TimeTool
from tools.tool_manager import ToolManager
from tools.tool_policy import ToolPolicy
from tools.tool_registry import ToolRegistry
from tools.tool_result import ToolRequest, ToolResult


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Isolated project root for file and exec tools."""
    (tmp_path / "subdir").mkdir()
    sample = tmp_path / "sample.txt"
    sample.write_text("hello titan", encoding="utf-8")
    return tmp_path


@pytest.fixture
def tool_manager(project_root: Path) -> ToolManager:
    return ToolManager(project_root=project_root)


def test_tool_result_format_includes_source_attribution() -> None:
    """P6-010: ToolResult prompt formatting labels data source."""
    result = ToolResult(
        tool_name="time",
        success=True,
        data="2026-06-27 12:00:00",
        source="time",
    )
    text = result.format_for_prompt()
    assert "[Source: time]" in text
    assert "2026-06-27" in text


def test_tool_registry_registers_and_lists_tools(tool_manager: ToolManager) -> None:
    """P6-011: registry exposes all core Phase 6 tools."""
    names = tool_manager.list_tools()
    assert "time" in names
    assert "file_read" in names
    assert "file_write" in names
    assert "python_exec" in names
    assert "web_search" in names
    assert "calendar" in names


def test_time_tool_returns_formatted_datetime(tool_manager: ToolManager) -> None:
    """P6-012: TimeTool returns non-empty datetime string."""
    result = tool_manager.run("time", caller="brain")
    assert result.success
    assert len(result.data) >= 10


def test_time_tool_backward_compatible_get_current_time(tool_manager: ToolManager) -> None:
    """Regression: get_current_time facade still works."""
    assert tool_manager.get_current_time()


def test_path_guard_blocks_traversal(project_root: Path) -> None:
    """P6-020: path traversal outside project root is rejected."""
    with pytest.raises(PathGuardError):
        resolve_allowed_path("../../etc/passwd", project_root)


def test_path_guard_allows_relative_file(project_root: Path) -> None:
    """P6-020: valid relative paths resolve under project root."""
    resolved = resolve_allowed_path("sample.txt", project_root, must_exist=True)
    assert resolved.name == "sample.txt"
    assert resolved.read_text(encoding="utf-8") == "hello titan"


def test_file_read_tool_reads_project_file(project_root: Path) -> None:
    """P6-021: file_read returns content for allowed paths."""
    tool = FileReadTool(project_root)
    result = tool.run(path="sample.txt")
    assert result.success
    assert result.data == "hello titan"


def test_file_read_tool_rejects_missing_file(project_root: Path) -> None:
    """P6-021: missing files return structured error."""
    tool = FileReadTool(project_root)
    result = tool.run(path="missing.txt")
    assert not result.success
    assert "introuvable" in result.error.lower()


def test_file_write_tool_dry_run_by_default(project_root: Path) -> None:
    """P6-022: file_write defaults to dry-run without touching disk."""
    assert TOOL_WRITE_DRY_RUN_DEFAULT is True
    tool = FileWriteTool(project_root)
    target = project_root / "new.txt"
    result = tool.run(path="new.txt", content="secret")
    assert result.success
    assert "[dry-run]" in result.data
    assert not target.exists()


def test_file_write_tool_writes_when_dry_run_false(project_root: Path) -> None:
    """P6-022: explicit dry_run=False persists content."""
    tool = FileWriteTool(project_root, dry_run_default=False)
    result = tool.run(path="out.txt", content="written", dry_run=False)
    assert result.success
    assert (project_root / "out.txt").read_text(encoding="utf-8") == "written"


def test_file_write_tool_blocks_escape(project_root: Path) -> None:
    """P6-022: write outside project root is rejected."""
    tool = FileWriteTool(project_root)
    result = tool.run(path="../escape.txt", content="bad")
    assert not result.success


def test_python_exec_tool_runs_simple_code(project_root: Path) -> None:
    """P6-023: python_exec captures stdout."""
    tool = PythonExecTool(project_root, timeout_seconds=5)
    result = tool.run(code="print('ok')")
    assert result.success
    assert result.data == "ok"


def test_python_exec_tool_timeout(project_root: Path) -> None:
    """P6-023: infinite loop is killed by timeout."""
    tool = PythonExecTool(project_root, timeout_seconds=1)
    result = tool.run(code="while True: pass")
    assert not result.success
    assert "timeout" in result.error.lower()


def test_python_exec_tool_reports_runtime_error(project_root: Path) -> None:
    """P6-023: failing code returns stderr/error."""
    tool = PythonExecTool(project_root)
    result = tool.run(code="raise ValueError('boom')")
    assert not result.success


def test_web_search_stub_returns_not_available(tool_manager: ToolManager) -> None:
    """P9-080 / P10A-029: web_search stub succeeds in MOCK mode (no external API)."""
    from tools.tool_enums import ExecutionMode
    from tools.tool_run_models import ToolExecutionContext

    ctx = ToolExecutionContext(
        caller="brain",
        user="Nolan",
        session_id="default",
        turn_id="default",
        execution_mode=ExecutionMode.MOCK,
        metadata={"execution_mode_override": True},
    )
    outcome = tool_manager.invoke("web_search", {"query": "titan ai"}, ctx)
    assert outcome.is_terminal()
    result = tool_manager.runtime.outcome_to_result(outcome)
    assert result.success
    assert "web_search" in result.source


def test_tool_policy_blocks_research_file_write(tool_manager: ToolManager) -> None:
    """P6-030: research agent cannot write files."""
    result = tool_manager.run(
        "file_write",
        {"path": "x.txt", "content": "nope"},
        caller="research",
    )
    assert not result.success
    assert "Politique" in result.error or "politique" in result.error.lower()


def test_tool_policy_allows_coding_file_read(tool_manager: ToolManager) -> None:
    """P6-030: coding agent may read files."""
    result = tool_manager.run("file_read", {"path": "sample.txt"}, caller="coding")
    assert result.success


def test_reasoning_detects_time_request() -> None:
    """P6-032: time keywords produce time ToolRequest."""
    analysis = Reasoning().analyze("Quelle heure est-il ?")
    assert analysis["needs_tool"] is True
    assert any(req.tool_name == "time" for req in analysis["tool_requests"])


def test_reasoning_detects_file_read_with_path() -> None:
    """P6-032: read keywords + path produce file_read request."""
    analysis = Reasoning().analyze("Lire le fichier config/settings.py")
    assert analysis["needs_tool"] is True
    names = [req.tool_name for req in analysis["tool_requests"]]
    assert "file_read" in names


def test_executor_plan_tools_returns_requests() -> None:
    """P6-033: executor surfaces reasoning tool requests."""
    analysis = Reasoning().analyze("Quelle heure est-il ?")
    requests = Executor().plan_tools(analysis)
    assert len(requests) == 1
    assert requests[0].tool_name == "time"


def test_tool_dispatcher_formats_results_with_attribution(
    tool_manager: ToolManager,
) -> None:
    """P6-031: dispatcher output includes source labels."""
    dispatcher = ToolDispatcher(tool_manager)
    results = dispatcher.dispatch([ToolRequest("time", {})])
    text = dispatcher.format_results(results)
    assert "[Source: time]" in text


def test_pipeline_includes_execution_coordinate_stage() -> None:
    """P8-063: execution_coordinate runs agents+tools before assemble_prompt."""
    assert "execution_coordinate" in STAGE_ORDER
    assert STAGE_ORDER.index("execution_coordinate") < STAGE_ORDER.index("assemble_prompt")
    assert STAGE_ORDER.index("execution_coordinate") > STAGE_ORDER.index("create_plan")


def test_brain_think_injects_tool_results_in_prompt(brain: Brain) -> None:
    """P6-034: time request surfaces RÉSULTATS OUTILS in LLM prompt."""
    brain.think("Quelle heure est-il ?")
    prompt_sent = brain.llm.ask.call_args[0][0]
    assert "RÉSULTATS OUTILS" in prompt_sent
    assert "[Source: time]" in prompt_sent


def test_prompt_builder_includes_tool_section() -> None:
    """P6-035: PromptBuilder renders RÉSULTATS OUTILS when present."""
    from brain.pipeline.context_bundle import ThinkContext

    ctx = ThinkContext(
        user_message="test",
        tool_results_text="[Source: time]\n2026-01-01 00:00:00",
    )
    prompt = PromptBuilder().build(ctx)
    assert "RÉSULTATS OUTILS" in prompt
    assert "[Source: time]" in prompt


def test_registry_rejects_duplicate_registration() -> None:
    """P6-011: duplicate tool name raises on register."""
    registry = ToolRegistry()
    registry.register(TimeTool())
    with pytest.raises(ValueError):
        registry.register(TimeTool())


def test_registry_unknown_tool_returns_error() -> None:
    """P6-011: unknown tool name returns structured failure."""
    registry = ToolRegistry()
    result = registry.run("missing", {})
    assert not result.success
    assert "inconnu" in result.error.lower()


def test_tool_manager_custom_registry(project_root: Path) -> None:
    """P6-013: ToolManager accepts injected registry."""
    registry = ToolRegistry()
    registry.register(TimeTool())
    manager = ToolManager(
        project_root=project_root,
        registry=registry,
        register_defaults=False,
    )
    assert manager.list_tools() == ["time"]

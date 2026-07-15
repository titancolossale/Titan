# =====================================
# Titan Controlled Patch Application V1 Tests
# =====================================

"""Tests for core/tools/code_editor Controlled Patch Application."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.code_generation_engine import (
    GeneratedEdit,
    GeneratedFile,
    GeneratedPatch,
    GenerationSummary,
)
from brain.development_session import DevelopmentSessionRuntime
from core.actions import ActionDispatcher, ActionRegistry
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.code_editor import (
    PERMISSION_APPLY,
    PERMISSION_PREVIEW,
    PERMISSION_ROLLBACK,
    PERMISSION_VALIDATE,
    CodeEditorTool,
    PatchApplier,
    TransactionStatus,
)
from core.tools.code_editor.exceptions import (
    CodeEditorApprovalError,
    CodeEditorConfirmationError,
    CodeEditorPermissionDeniedError,
)
from core.tools.tool_loader import ToolLoader
from core.tools.tool_registry import ToolRegistry
from tools.decision.patch_preview import generate_unified_diff

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_TOOLS_DIR = PROJECT_ROOT / "core" / "tools"


def _summary(**overrides) -> GenerationSummary:
    base = dict(
        request="test",
        change_type="add_feature",
        files_created=0,
        files_edited=0,
        review_count=0,
        confidence=0.8,
        complexity="low",
        risk="low",
        requires_manual_review=True,
    )
    base.update(overrides)
    return GenerationSummary(**base)


def _make_edit(path: str, original: str, proposed: str) -> GeneratedEdit:
    preview = generate_unified_diff(path, original=original, proposed=proposed)
    return GeneratedEdit(
        path=path,
        original_content=original,
        proposed_content=proposed,
        unified_diff=preview.unified_diff,
        rationale="test edit",
        confidence=0.9,
    )


def _make_patch(
    *,
    workspace: Path,
    files: tuple[GeneratedFile, ...] = (),
    edits: tuple[GeneratedEdit, ...] = (),
    approved: bool = True,
    plan_approved: bool = True,
) -> GeneratedPatch:
    return GeneratedPatch(
        plan_request="test patch",
        files=files,
        edits=edits,
        review_items=(),
        summary=_summary(
            files_created=len(files),
            files_edited=len(edits),
        ),
        unified_diff_bundle="\n".join(e.unified_diff for e in edits),
        confidence=0.9,
        rationale="test",
        sources={"workspace_root": str(workspace.resolve())},
        plan_approved=plan_approved,
        approved=approved,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pkg").mkdir()
    (root / "pkg" / "hello.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    (root / "pkg" / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


@pytest.fixture
def editor(repo: Path) -> CodeEditorTool:
    return CodeEditorTool(workspace_root=repo)


def _allow_mutating_permissions() -> PermissionManager:
    manager = PermissionManager()
    for permission_id, name, level in (
        (PERMISSION_VALIDATE, "Validate", PermissionLevel.SAFE),
        (PERMISSION_PREVIEW, "Preview", PermissionLevel.SAFE),
        (PERMISSION_APPLY, "Apply", PermissionLevel.SAFE),
        (PERMISSION_ROLLBACK, "Rollback", PermissionLevel.SAFE),
    ):
        manager.register_permission(
            Permission(
                id=permission_id,
                name=name,
                description="test",
                level=level,
            )
        )
    return manager


def test_valid_patch_validation(editor: CodeEditorTool, repo: Path) -> None:
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    proposed = "def hello():\n    return 2\n"
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, proposed),),
    )
    result = editor.validate_patch(patch)
    assert result.valid is True
    assert result.files_to_modify == ("pkg/hello.py",)
    assert not result.errors
    assert not result.conflicts


def test_malformed_patch_rejection(editor: CodeEditorTool, repo: Path) -> None:
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    edit = GeneratedEdit(
        path="pkg/hello.py",
        original_content=original,
        proposed_content="x",
        unified_diff="this is not a diff",
        rationale="bad",
    )
    # Force empty-looking ops — validator checks syntax
    edit = GeneratedEdit(
        path="pkg/hello.py",
        original_content=original,
        proposed_content="x",
        unified_diff="",
        rationale="bad",
    )
    patch = _make_patch(workspace=repo, edits=(edit,))
    result = editor.validate_patch(patch)
    assert result.valid is False
    assert any("empty unified diff" in err.lower() or "malformed" in err.lower() for err in result.errors)


def test_unapproved_patch_rejection(editor: CodeEditorTool, repo: Path) -> None:
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, "def hello():\n    return 9\n"),),
        approved=False,
    )
    with pytest.raises(CodeEditorApprovalError):
        editor.apply_patch(patch, confirmed=True)
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8") == original


def test_missing_confirmation(repo: Path) -> None:
    # Keep default CONFIRMATION_REQUIRED so confirmed=False is the gate under test.
    editor = CodeEditorTool(workspace_root=repo)
    # Override apply to SAFE so permission denial does not mask confirmation check.
    # Instead, call apply_patch after temporarily treating permission as allowed
    # via confirmed path — we want CodeEditorConfirmationError specifically.
    manager = PermissionManager()
    manager.register_permission(
        Permission(
            id=PERMISSION_APPLY,
            name="Apply",
            description="safe for confirmation test",
            level=PermissionLevel.SAFE,
        )
    )
    editor = CodeEditorTool(workspace_root=repo, permission_manager=manager)
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, "def hello():\n    return 3\n"),),
    )
    with pytest.raises(CodeEditorConfirmationError):
        editor.apply_patch(patch, confirmed=False)
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8") == original


def test_permission_denied(repo: Path) -> None:
    manager = PermissionManager()
    manager.register_permission(
        Permission(
            id=PERMISSION_APPLY,
            name="Apply",
            description="blocked",
            level=PermissionLevel.BLOCKED,
        )
    )
    editor = CodeEditorTool(workspace_root=repo, permission_manager=manager)
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, "def hello():\n    return 4\n"),),
    )
    with pytest.raises(CodeEditorPermissionDeniedError):
        editor.apply_patch(patch, confirmed=True)


def test_path_traversal_rejection(editor: CodeEditorTool, repo: Path) -> None:
    patch = _make_patch(
        workspace=repo,
        files=(
            GeneratedFile(
                path="../outside.py",
                content="print('no')\n",
                rationale="escape",
            ),
        ),
    )
    result = editor.validate_patch(patch)
    assert result.valid is False
    assert result.errors


def test_stale_baseline_hash_mismatch(editor: CodeEditorTool, repo: Path) -> None:
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, "def hello():\n    return 5\n"),),
    )
    (repo / "pkg" / "hello.py").write_text(
        "def hello():\n    return 'changed'\n",
        encoding="utf-8",
    )
    result = editor.validate_patch(patch)
    assert result.valid is False
    assert any("hash mismatch" in c.lower() or "stale" in c.lower() for c in result.conflicts)


def test_preview_additions_and_deletions(editor: CodeEditorTool, repo: Path) -> None:
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    proposed = "def hello():\n    return 2\n    # extra\n"
    patch = _make_patch(
        workspace=repo,
        files=(
            GeneratedFile(
                path="pkg/new_mod.py",
                content="X = 1\n",
                rationale="new",
            ),
        ),
        edits=(_make_edit("pkg/hello.py", original, proposed),),
    )
    preview = editor.preview_patch(patch)
    assert "pkg/hello.py" in preview.affected_files
    assert "pkg/new_mod.py" in preview.new_files
    assert preview.additions > 0
    assert preview.deletions >= 0
    assert preview.change_summary
    assert (repo / "pkg" / "new_mod.py").exists() is False


def test_successful_single_file_application(repo: Path) -> None:
    editor = CodeEditorTool(
        workspace_root=repo,
        permission_manager=_allow_mutating_permissions(),
    )
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    proposed = "def hello():\n    return 42\n"
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, proposed),),
    )
    result = editor.apply_patch(patch, confirmed=True)
    assert result.success is True
    assert result.transaction_id
    assert result.files_modified == ("pkg/hello.py",)
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8") == proposed
    backup = repo / ".titan" / "backups" / result.transaction_id / "manifest.json"
    assert backup.is_file()


def test_successful_multi_file_application(repo: Path) -> None:
    editor = CodeEditorTool(
        workspace_root=repo,
        permission_manager=_allow_mutating_permissions(),
    )
    hello = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    util = (repo / "pkg" / "util.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(
            _make_edit("pkg/hello.py", hello, "def hello():\n    return 7\n"),
            _make_edit("pkg/util.py", util, "VALUE = 7\n"),
        ),
    )
    result = editor.apply_patch(patch, confirmed=True)
    assert result.success is True
    assert set(result.files_modified) == {"pkg/hello.py", "pkg/util.py"}
    assert "return 7" in (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    assert (repo / "pkg" / "util.py").read_text(encoding="utf-8") == "VALUE = 7\n"


def test_new_file_creation(repo: Path) -> None:
    editor = CodeEditorTool(
        workspace_root=repo,
        permission_manager=_allow_mutating_permissions(),
    )
    patch = _make_patch(
        workspace=repo,
        files=(
            GeneratedFile(
                path="pkg/created.py",
                content="CREATED = True\n",
                rationale="create",
            ),
        ),
    )
    result = editor.apply_patch(patch, confirmed=True)
    assert result.success is True
    assert result.files_created == ("pkg/created.py",)
    assert (repo / "pkg" / "created.py").read_text(encoding="utf-8") == "CREATED = True\n"


def test_rollback_restoration(repo: Path) -> None:
    editor = CodeEditorTool(
        workspace_root=repo,
        permission_manager=_allow_mutating_permissions(),
    )
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, "def hello():\n    return 99\n"),),
    )
    applied = editor.apply_patch(patch, confirmed=True)
    assert applied.success is True
    rolled = editor.rollback_patch(applied.transaction_id or "", confirmed=True)
    assert rolled.success is True
    assert rolled.status == TransactionStatus.ROLLED_BACK
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8") == original


def test_automatic_rollback_after_partial_failure(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = CodeEditorTool(
        workspace_root=repo,
        permission_manager=_allow_mutating_permissions(),
    )
    hello = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    util = (repo / "pkg" / "util.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(
            _make_edit("pkg/hello.py", hello, "def hello():\n    return 11\n"),
            _make_edit("pkg/util.py", util, "VALUE = 11\n"),
        ),
    )

    applier = editor._applier
    original_write = Path.write_text
    repo_writes = {"n": 0}

    def flaky_write(self: Path, data: str, encoding: str = "utf-8", **kwargs):
        if ".titan" in str(self):
            return original_write(self, data, encoding=encoding, **kwargs)
        repo_writes["n"] += 1
        if repo_writes["n"] >= 2:
            raise OSError("simulated write failure")
        return original_write(self, data, encoding=encoding, **kwargs)

    monkeypatch.setattr(Path, "write_text", flaky_write)
    result = applier.apply(patch, validation=editor.validate_patch(patch))
    assert result.success is False
    assert result.rollback_performed is True
    monkeypatch.undo()
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8") == hello
    assert (repo / "pkg" / "util.py").read_text(encoding="utf-8") == util


def test_repository_unchanged_after_failed_validation(
    editor: CodeEditorTool,
    repo: Path,
) -> None:
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    fingerprint = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file()
    }
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", "stale baseline", "def hello():\n    return 0\n"),),
    )
    validation = editor.validate_patch(patch)
    assert validation.valid is False
    result = editor._applier.apply(patch, validation=validation)
    assert result.success is False
    assert result.transaction_id is None
    after = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file()
    }
    assert after == fingerprint
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8") == original


def test_development_session_recording(repo: Path, tmp_path: Path) -> None:
    editor = CodeEditorTool(
        workspace_root=repo,
        permission_manager=_allow_mutating_permissions(),
    )
    session_runtime = DevelopmentSessionRuntime(
        file_path=tmp_path / "sessions.json",
    )
    session_runtime.start("controlled-patch")
    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, "def hello():\n    return 12\n"),),
    )
    validation = editor.validate_patch(patch)
    session_runtime.update(
        application_record={
            "kind": "validation",
            "valid": validation.valid,
        },
        patch=patch,
    )
    applied = editor.apply_patch(patch, confirmed=True)
    session_runtime.update(
        application_record={
            "kind": "application",
            "success": applied.success,
            "transaction_id": applied.transaction_id,
            "status": applied.status.value,
            "files_modified": list(applied.files_modified),
        },
        mark_patch_applied=True,
        complete_task="Apply generated patch",
        add_pending=["Review applied changes"],
        decision=f"Applied {applied.transaction_id}",
    )
    active = session_runtime.get_active()
    assert active is not None
    assert active.application_records
    assert active.patches[-1].get("_applied") is True
    if applied.success:
        assert active.patches[-1].get("_transaction_id") == applied.transaction_id
    assert any(t.description == "Apply generated patch" for t in active.completed_tasks)
    assert any("Review applied changes" in t.description for t in active.pending_tasks)

    assert applied.success is True
    rolled = editor.rollback_patch(applied.transaction_id or "", confirmed=True)
    session_runtime.update(
        application_record={
            "kind": "rollback",
            "success": rolled.success,
            "transaction_id": rolled.transaction_id,
            "status": rolled.status.value,
        },
        complete_task="Rollback patch transaction",
    )
    active = session_runtime.get_active()
    assert active is not None
    assert active.state.value == "active"
    assert any(r.get("kind") == "rollback" for r in active.application_records)


def test_brain_facade_integration(repo: Path, tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from agents.agent_manager import AgentManager
    from brain.brain import Brain
    from brain.llm import LLM
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from core.state_manager import StateManager
    from memory.long_term_memory import LongTermMemory
    from memory.memory_manager import MemoryManager
    from memory.memory_service import MemoryService
    from tools.tool_manager import ToolManager

    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    brain = Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=repo),
        llm=mock_llm,
    )
    brain.code_editor = CodeEditorTool(
        workspace_root=repo,
        permission_manager=_allow_mutating_permissions(),
    )
    brain.development_session = DevelopmentSessionRuntime(
        file_path=tmp_path / "dev_sessions.json",
        workspace_awareness=brain.workspace_awareness,
        executive_function=brain.executive_function,
        mission_manager=brain.mission_manager,
        memory_service=brain.memory_service,
        context_manager=brain.context_manager,
    )
    brain.start_development_session("brain-patch-facade")

    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, "def hello():\n    return 13\n"),),
    )

    validation = brain.validate_generated_patch(patch, record_to_session=True)
    assert validation.valid is True
    preview = brain.preview_generated_patch(patch, record_to_session=True)
    assert preview.additions >= 0
    denied = brain.apply_generated_patch(patch, confirmed=False, record_to_session=True)
    assert denied.success is False
    applied = brain.apply_generated_patch(patch, confirmed=True, record_to_session=True)
    assert applied.success is True
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8").endswith("return 13\n")
    rolled = brain.rollback_patch(
        applied.transaction_id or "",
        confirmed=True,
        record_to_session=True,
    )
    assert rolled.success is True
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8") == original
    session = brain.get_development_session()
    assert session is not None
    assert session.state.value == "active"
    assert len(session.application_records) >= 3


def test_tool_loader_discovers_code_editor() -> None:
    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[CORE_TOOLS_DIR])
    result = loader.load()
    assert "code_editor" in result.loaded or registry.get_tool("code_editor") is not None


def test_dispatcher_blocks_apply_without_safe_override(repo: Path) -> None:
    permission_manager = PermissionManager()
    tool = CodeEditorTool(
        workspace_root=repo,
        permission_manager=permission_manager,
    )
    action_registry = ActionRegistry()
    for action in tool.list_actions():
        action_registry.register_action(action)
    tool_registry = ToolRegistry()
    tool_registry.register_tool(tool)
    dispatcher = ActionDispatcher(tool_registry, action_registry, permission_manager)

    original = (repo / "pkg" / "hello.py").read_text(encoding="utf-8")
    patch = _make_patch(
        workspace=repo,
        edits=(_make_edit("pkg/hello.py", original, "def hello():\n    return 14\n"),),
    )
    result = dispatcher.dispatch(
        "code_editor",
        "apply_patch",
        {"patch": patch, "confirmed": True},
    )
    assert result.success is False
    assert (repo / "pkg" / "hello.py").read_text(encoding="utf-8") == original

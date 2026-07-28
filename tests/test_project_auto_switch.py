# =====================================
# Titan Automatic Project Switching Tests
# =====================================

"""Phase 15.3 — automatic project matching and switching before Brain.think()."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from brain.brain import Brain
from brain.pipeline.context_bundle import ProjectContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.project_manager import ProjectManager
from core.project_matcher import HIGH_CONFIDENCE, match_project
from core.project_models import Project, ProjectPriority, ProjectState
from core.state_manager import WorkspaceState
from datetime import datetime, timezone


def _seed_two_projects(brain: Brain) -> tuple[Any, Any]:
    """Create Titan (active) and Trading Bot (paused) with matching signals."""
    titan = brain.project_manager.create_project(
        "Titan OS",
        "Personal agentic AI system",
        aliases=["titan"],
        keywords=["brain", "agent"],
    )
    trading = brain.project_manager.create_project(
        "Trading Bot",
        "Automated market strategy runner",
        aliases=["trader", "trading"],
        keywords=["market", "backtest", "ninjatrader"],
    )
    # create_project makes Trading Bot ACTIVE — resume Titan so Trading is paused.
    brain.project_manager.resume_project(titan.id)
    brain.mission_manager.create_mission(
        "Wire brain pipeline",
        "Ship awareness",
        ["A", "B"],
        project_id=titan.id,
    )
    brain.mission_manager.create_mission(
        "Backtest momentum strategy",
        "Validate edges",
        ["Collect", "Run"],
        project_id=trading.id,
    )
    return titan, trading


def test_auto_switches_to_matching_project(brain: Brain, caplog) -> None:
    """High-confidence mention of another project must switch ACTIVE focus."""
    titan, trading = _seed_two_projects(brain)
    assert brain.project_manager.get_active_project().id == titan.id
    # Seeding may log PROJECT_SWITCHED — clear so think() capture is clean.
    caplog.clear()

    with caplog.at_level(logging.INFO):
        brain.think("Continue work on Trading Bot please")

    active = brain.project_manager.get_active_project()
    assert active is not None
    assert active.id == trading.id
    assert active.name == "Trading Bot"

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.project_context is not None
    assert ctx.project_context.project_id == trading.id
    assert ctx.project_context.name == "Trading Bot"
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.active_project_id == trading.id

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PROJECT_MATCH_STARTED") for msg in messages)
    assert any(msg.startswith("PROJECT_MATCH_FOUND") for msg in messages)
    assert any(msg.startswith("PROJECT_SWITCHED") for msg in messages)


def test_stays_on_current_project_when_confidence_low(brain: Brain, caplog) -> None:
    """Vague messages must not switch projects."""
    titan, trading = _seed_two_projects(brain)
    # Seeding may log PROJECT_SWITCHED (resume Titan) — clear before think() capture.
    caplog.clear()

    with caplog.at_level(logging.INFO):
        brain.think("Quelle heure est-il ?")

    active = brain.project_manager.get_active_project()
    assert active is not None
    assert active.id == titan.id
    paused = brain.project_manager.get_project(trading.id)
    assert paused is not None
    assert paused.status == ProjectState.PAUSED.value

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.project_context is not None
    assert ctx.project_context.project_id == titan.id

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("PROJECT_MATCH_STARTED") for msg in messages)
    assert any(msg.startswith("PROJECT_MATCH_FAILED") for msg in messages)
    assert not any(
        msg.startswith("PROJECT_SWITCHED") and trading.id in msg for msg in messages
    )


def test_prompt_receives_only_selected_project(brain: Brain) -> None:
    """PromptBuilder must attach only the post-switch active project."""
    titan, trading = _seed_two_projects(brain)

    brain.think("Reprendre Trading Bot")

    ctx = brain.last_think_context
    assert ctx is not None
    assert "CONTEXTE PROJET" in ctx.prompt
    assert "Trading Bot" in ctx.prompt
    assert "Current Project:\nTrading Bot" in ctx.prompt
    assert "Current Project:\nTitan OS" not in ctx.prompt
    assert ctx.project_context is not None
    assert ctx.project_context.name == "Trading Bot"
    assert ctx.project_context.project_id == trading.id
    assert titan.id != trading.id


def test_prompt_builder_only_uses_active_project_context() -> None:
    """PromptBuilder ignores all projects except the injected active context."""
    project_context = ProjectContext(
        name="Selected Only",
        status="ACTIVE",
        progress=10.0,
        project_id="proj-selected",
    )
    ctx = ThinkContext(
        user_message="Go.",
        project_context=project_context,
        state={},
        mission={},
    )
    prompt = PromptBuilder().build(ctx)
    assert "CONTEXTE PROJET" in prompt
    assert "Selected Only" in prompt
    assert "Other Project" not in prompt


def test_match_by_alias_and_keywords() -> None:
    """Matcher must score aliases and keywords as high-confidence signals."""
    now = datetime.now(timezone.utc)
    projects = [
        Project(
            id="a",
            name="Titan OS",
            description="Agent system",
            status=ProjectState.ACTIVE.value,
            created_at=now,
            updated_at=now,
            progress=0.0,
            active_mission_id=None,
            mission_ids=[],
            completed_mission_ids=[],
            priority=ProjectPriority.NORMAL,
            aliases=["titan"],
            keywords=["brain"],
        ),
        Project(
            id="b",
            name="Trading Bot",
            description="Market automation",
            status=ProjectState.PAUSED.value,
            created_at=now,
            updated_at=now,
            progress=0.0,
            active_mission_id=None,
            mission_ids=[],
            completed_mission_ids=[],
            priority=ProjectPriority.NORMAL,
            aliases=["trader"],
            keywords=["ninjatrader", "backtest"],
        ),
    ]
    outcome = match_project(
        "Open the trader workspace",
        projects,
        active_project_id="a",
    )
    assert outcome.matched is True
    assert outcome.should_switch is True
    assert outcome.project_id == "b"
    assert outcome.confidence >= HIGH_CONFIDENCE


def test_match_by_recent_mission_title() -> None:
    """Recent mission titles belonging to a project must drive a match."""
    now = datetime.now(timezone.utc)
    projects = [
        Project(
            id="a",
            name="Alpha",
            description="",
            status=ProjectState.ACTIVE.value,
            created_at=now,
            updated_at=now,
            progress=0.0,
            active_mission_id=None,
            mission_ids=[],
            completed_mission_ids=[],
            priority=ProjectPriority.NORMAL,
            aliases=[],
            keywords=[],
        ),
        Project(
            id="b",
            name="Beta",
            description="",
            status=ProjectState.PAUSED.value,
            created_at=now,
            updated_at=now,
            progress=0.0,
            active_mission_id=None,
            mission_ids=[],
            completed_mission_ids=[],
            priority=ProjectPriority.NORMAL,
            aliases=[],
            keywords=[],
        ),
    ]
    outcome = match_project(
        "Continue Backtest momentum strategy",
        projects,
        missions_by_project={
            "b": [{"title": "Backtest momentum strategy"}],
        },
        active_project_id="a",
    )
    assert outcome.matched is True
    assert outcome.project_id == "b"
    assert "mission_titles" in outcome.signals


def test_never_creates_project_on_match(brain: Brain) -> None:
    """Matching must never invent a new project."""
    titan, _trading = _seed_two_projects(brain)
    before = {item.id for item in brain.project_manager.list_projects()}

    brain.think("Continue work on Trading Bot")

    after = {item.id for item in brain.project_manager.list_projects()}
    assert after == before
    assert brain.project_manager.get_active_project().id != titan.id


def test_single_workspace_state_read_with_auto_switch(brain: Brain) -> None:
    """Auto-switch must keep a single request-scoped WorkspaceState load()."""
    _seed_two_projects(brain)
    load_calls = {"count": 0}
    original_load = brain.state_manager.load

    def counting_load() -> WorkspaceState:
        load_calls["count"] += 1
        return original_load()

    brain.state_manager.load = counting_load  # type: ignore[method-assign]
    brain.think("Continue work on Trading Bot")

    assert load_calls["count"] == 1
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.project_context is not None
    assert ctx.project_context.name == "Trading Bot"


def test_aliases_keywords_persist(tmp_path: Path) -> None:
    """Aliases and keywords round-trip through ProjectManager persistence."""
    path = tmp_path / "titan_projects.json"
    manager = ProjectManager(file_path=path)
    created = manager.create_project(
        "Persist Signals",
        "desc",
        aliases=["ps", "persist"],
        keywords=["signal", "match"],
    )
    reloaded = ProjectManager(file_path=path)
    loaded = reloaded.get_project(created.id)
    assert loaded is not None
    assert loaded.aliases == ["ps", "persist"]
    assert loaded.keywords == ["signal", "match"]

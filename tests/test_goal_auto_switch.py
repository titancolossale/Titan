# =====================================
# Titan Automatic Goal Switching Tests
# =====================================

"""Phase 16.3 — automatic goal matching and switching before Brain.think()."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain.brain import Brain
from brain.pipeline.context_bundle import GoalContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.goal_manager import GoalManager
from core.goal_matcher import HIGH_CONFIDENCE, match_goal
from core.goal_models import Goal, GoalPriority, GoalState
from core.state_manager import WorkspaceState


def _seed_two_goals(brain: Brain) -> tuple[Any, Any]:
    """Create Ship Titan (active) and Automate Trading (paused) with signals."""
    titan_goal = brain.goal_manager.create_goal(
        "Ship Titan OS",
        "Personal agentic AI platform with brain and agents",
        aliases=["titan-goal", "ship titan"],
        keywords=["brain", "agent", "orchestrator"],
    )
    trading_goal = brain.goal_manager.create_goal(
        "Automate Trading",
        "Automated market strategy runner with backtesting",
        aliases=["trading-goal", "trader goal"],
        keywords=["market", "backtest", "ninjatrader"],
    )
    # Second create_goal makes Trading ACTIVE — resume Titan so Trading is paused.
    titan_proj = brain.project_manager.create_project(
        "Titan Core",
        "Core agent runtime",
        goal_id=titan_goal.id,
    )
    trading_proj = brain.project_manager.create_project(
        "Trading Bot",
        "Strategy executor",
        goal_id=trading_goal.id,
    )
    brain.mission_manager.create_mission(
        "Wire brain pipeline",
        "Ship awareness",
        ["A", "B"],
        project_id=titan_proj.id,
    )
    brain.mission_manager.create_mission(
        "Backtest momentum strategy",
        "Validate edges",
        ["Collect", "Run"],
        project_id=trading_proj.id,
    )
    brain.goal_manager.resume_goal(titan_goal.id)
    return titan_goal, trading_goal


def test_goal_matching_works() -> None:
    """Exact goal name must match at high confidence."""
    now = datetime.now(timezone.utc)
    goals = [
        Goal(
            id="a",
            name="Ship Titan OS",
            description="Agent platform",
            status=GoalState.ACTIVE.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=[],
            keywords=[],
        ),
        Goal(
            id="b",
            name="Automate Trading",
            description="Market automation",
            status=GoalState.PAUSED.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=[],
            keywords=[],
        ),
    ]
    outcome = match_goal(
        "Continue Automate Trading",
        goals,
        active_goal_id="a",
    )
    assert outcome.matched is True
    assert outcome.should_switch is True
    assert outcome.goal_id == "b"
    assert outcome.confidence >= HIGH_CONFIDENCE
    assert "exact_name" in outcome.signals


def test_aliases_work() -> None:
    """Matcher must score aliases as high-confidence signals."""
    now = datetime.now(timezone.utc)
    goals = [
        Goal(
            id="a",
            name="Ship Titan OS",
            description="Agent platform",
            status=GoalState.ACTIVE.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=["titan-goal"],
            keywords=["brain"],
        ),
        Goal(
            id="b",
            name="Automate Trading",
            description="Market automation",
            status=GoalState.PAUSED.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=["trading-goal"],
            keywords=["ninjatrader"],
        ),
    ]
    outcome = match_goal(
        "Open the trading-goal workspace",
        goals,
        active_goal_id="a",
    )
    assert outcome.matched is True
    assert outcome.should_switch is True
    assert outcome.goal_id == "b"
    assert outcome.confidence >= HIGH_CONFIDENCE
    assert "exact_alias" in outcome.signals


def test_keywords_work() -> None:
    """Matcher must score keywords as high-confidence signals."""
    now = datetime.now(timezone.utc)
    goals = [
        Goal(
            id="a",
            name="Alpha Goal",
            description="",
            status=GoalState.ACTIVE.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=[],
            keywords=["orchestrator"],
        ),
        Goal(
            id="b",
            name="Beta Goal",
            description="",
            status=GoalState.PAUSED.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=[],
            keywords=["ninjatrader", "backtest", "market"],
        ),
    ]
    outcome = match_goal(
        "Need ninjatrader backtest market work",
        goals,
        active_goal_id="a",
    )
    assert outcome.matched is True
    assert outcome.goal_id == "b"
    assert outcome.confidence >= HIGH_CONFIDENCE
    assert "keywords" in outcome.signals


def test_semantic_match_works() -> None:
    """Description token overlap must drive a semantic match."""
    now = datetime.now(timezone.utc)
    goals = [
        Goal(
            id="a",
            name="Alpha",
            description="Routine housekeeping chores",
            status=GoalState.ACTIVE.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=[],
            keywords=[],
        ),
        Goal(
            id="b",
            name="Beta",
            description="cryptocurrency arbitrage volatility hedging derivatives",
            status=GoalState.PAUSED.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=[],
            keywords=[],
        ),
    ]
    outcome = match_goal(
        "cryptocurrency arbitrage volatility hedging derivatives research",
        goals,
        active_goal_id="a",
    )
    assert outcome.matched is True
    assert outcome.goal_id == "b"
    assert outcome.confidence >= HIGH_CONFIDENCE
    assert "semantic" in outcome.signals


def test_wrong_goal_is_rejected() -> None:
    """Vague messages must not match / switch goals."""
    now = datetime.now(timezone.utc)
    goals = [
        Goal(
            id="a",
            name="Ship Titan OS",
            description="Agent platform",
            status=GoalState.ACTIVE.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=["titan-goal"],
            keywords=["brain"],
        ),
        Goal(
            id="b",
            name="Automate Trading",
            description="Market automation",
            status=GoalState.PAUSED.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=[],
            active_project_id=None,
            aliases=["trading-goal"],
            keywords=["market"],
        ),
    ]
    outcome = match_goal(
        "Quelle heure est-il ?",
        goals,
        active_goal_id="a",
    )
    assert outcome.matched is False
    assert outcome.should_switch is False
    assert outcome.confidence < HIGH_CONFIDENCE or outcome.reason in {
        "no_signal",
        "low_confidence",
        "ambiguous",
        "empty_message",
    }


def test_automatic_switch_works(brain: Brain, caplog) -> None:
    """High-confidence mention of another goal must switch ACTIVE focus."""
    titan_goal, trading_goal = _seed_two_goals(brain)
    assert brain.goal_manager.get_active_goal().id == titan_goal.id

    with caplog.at_level(logging.INFO):
        brain.think("Continue work on Automate Trading please")

    active = brain.goal_manager.get_active_goal()
    assert active is not None
    assert active.id == trading_goal.id
    assert active.name == "Automate Trading"

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.goal_context is not None
    assert ctx.goal_context.goal_id == trading_goal.id
    assert ctx.goal_context.name == "Automate Trading"
    assert ctx.goal_context.match_confidence is not None
    assert ctx.goal_context.match_confidence >= HIGH_CONFIDENCE
    assert ctx.goal_context.selection_reason == "auto_switched"
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.active_goal_id == trading_goal.id

    # resume_goal restores nested project + mission into WorkspaceState.
    assert ctx.workspace_state.active_project_id is not None
    assert ctx.project_context is not None

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("GOAL_MATCH_FOUND") for msg in messages)
    assert any(msg.startswith("GOAL_AUTO_SWITCH") for msg in messages)
    assert any(msg.startswith("GOAL_CONFIDENCE") for msg in messages)


def test_stays_on_current_goal_when_confidence_low(brain: Brain, caplog) -> None:
    """Vague messages must not switch goals."""
    titan_goal, trading_goal = _seed_two_goals(brain)

    with caplog.at_level(logging.INFO):
        brain.think("Quelle heure est-il ?")

    active = brain.goal_manager.get_active_goal()
    assert active is not None
    assert active.id == titan_goal.id
    paused = brain.goal_manager.get_goal(trading_goal.id)
    assert paused is not None
    assert paused.status == GoalState.PAUSED.value

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.goal_context is not None
    assert ctx.goal_context.goal_id == titan_goal.id
    assert ctx.goal_context.selection_reason is not None
    assert "retained_current" in ctx.goal_context.selection_reason

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("GOAL_MATCH_STARTED") for msg in messages)
    assert any(msg.startswith("GOAL_MATCH_FAILED") for msg in messages)
    assert any(msg.startswith("GOAL_CONFIDENCE") for msg in messages)
    assert not any(
        msg.startswith("GOAL_AUTO_SWITCH") and trading_goal.id in msg
        for msg in messages
    )


def test_prompt_receives_goal_confidence_and_reason(brain: Brain) -> None:
    """PromptBuilder must inject Current Goal, Confidence, and Reason."""
    _titan, trading_goal = _seed_two_goals(brain)

    brain.think("Reprendre Automate Trading")

    ctx = brain.last_think_context
    assert ctx is not None
    assert "CONTEXTE GOAL" in ctx.prompt
    assert "Current Goal:\nAutomate Trading" in ctx.prompt
    assert "Confidence:" in ctx.prompt
    assert "Reason for selection:\nauto_switched" in ctx.prompt
    assert "Current Goal:\nShip Titan OS" not in ctx.prompt
    assert ctx.goal_context is not None
    assert ctx.goal_context.goal_id == trading_goal.id


def test_prompt_builder_injects_confidence_reason_fields() -> None:
    """PromptBuilder includes confidence and reason from GoalContext."""
    goal_context = GoalContext(
        name="Selected Goal",
        status="ACTIVE",
        progress=25.0,
        goal_id="goal-selected",
        match_confidence=0.97,
        selection_reason="auto_switched",
    )
    ctx = ThinkContext(
        user_message="Go.",
        goal_context=goal_context,
        state={},
        mission={},
    )
    prompt = PromptBuilder().build(ctx)
    assert "CONTEXTE GOAL" in prompt
    assert "Current Goal:\nSelected Goal" in prompt
    assert "Confidence:\n0.97" in prompt
    assert "Reason for selection:\nauto_switched" in prompt


def test_never_creates_goal_on_match(brain: Brain) -> None:
    """Matching must never invent a new goal."""
    titan_goal, _trading = _seed_two_goals(brain)
    before = {item.id for item in brain.goal_manager.list_goals()}

    brain.think("Continue work on Automate Trading")

    after = {item.id for item in brain.goal_manager.list_goals()}
    assert after == before
    assert brain.goal_manager.get_active_goal().id != titan_goal.id


def test_single_workspace_state_read_with_goal_auto_switch(brain: Brain) -> None:
    """Auto-switch must keep a single request-scoped WorkspaceState load()."""
    _seed_two_goals(brain)
    load_calls = {"count": 0}
    original_load = brain.state_manager.load

    def counting_load() -> WorkspaceState:
        load_calls["count"] += 1
        return original_load()

    brain.state_manager.load = counting_load  # type: ignore[method-assign]
    brain.think("Continue work on Automate Trading")

    assert load_calls["count"] == 1
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.goal_context is not None
    assert ctx.goal_context.name == "Automate Trading"


def test_aliases_keywords_persist(tmp_path: Path) -> None:
    """Aliases and keywords round-trip through GoalManager persistence."""
    path = tmp_path / "titan_goals.json"
    manager = GoalManager(file_path=path)
    created = manager.create_goal(
        "Persist Signals",
        "desc",
        aliases=["ps", "persist"],
        keywords=["signal", "match"],
    )
    reloaded = GoalManager(file_path=path)
    loaded = reloaded.get_goal(created.id)
    assert loaded is not None
    assert loaded.aliases == ["ps", "persist"]
    assert loaded.keywords == ["signal", "match"]


def test_match_by_contained_project_name() -> None:
    """Contained project names belonging to a goal must drive a match."""
    now = datetime.now(timezone.utc)
    goals = [
        Goal(
            id="a",
            name="Alpha",
            description="",
            status=GoalState.ACTIVE.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=["pa"],
            active_project_id="pa",
            aliases=[],
            keywords=[],
        ),
        Goal(
            id="b",
            name="Beta",
            description="",
            status=GoalState.PAUSED.value,
            priority=GoalPriority.NORMAL,
            created_at=now,
            updated_at=now,
            progress=0.0,
            project_ids=["pb"],
            active_project_id="pb",
            aliases=[],
            keywords=[],
        ),
    ]
    outcome = match_goal(
        "Continue Trading Bot workspace",
        goals,
        projects_by_goal={
            "b": [{"name": "Trading Bot"}],
        },
        active_goal_id="a",
    )
    assert outcome.matched is True
    assert outcome.goal_id == "b"
    assert "project_names" in outcome.signals

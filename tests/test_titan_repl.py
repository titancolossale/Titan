# =====================================
# Titan REPL Static Guard Tests
# =====================================

"""Static guards against REPL orchestration regressions."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_titan_repl_does_not_call_auto_execute() -> None:
    """P1-073: REPL must not invoke AgentManager.auto_execute (Brain orchestrator only)."""
    source = (PROJECT_ROOT / "core" / "titan.py").read_text(encoding="utf-8")

    assert "auto_execute" not in source

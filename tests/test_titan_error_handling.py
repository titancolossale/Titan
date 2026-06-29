# =====================================
# Titan REPL Error Handling Tests
# =====================================

"""Tests for REPL graceful recovery when Brain.think() raises (P1-110 / P1-111)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.titan import Titan

BRAIN_FAILURE_MESSAGE = (
    "Désolé, une erreur interne s'est produite. On peut réessayer."
)


@pytest.fixture
def titan_with_mock_brain(monkeypatch: pytest.MonkeyPatch) -> Titan:
    """Titan instance whose Brain.think is replaced after construction."""
    inputs = iter(["test question", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    instance = Titan()
    instance.brain.think = MagicMock(side_effect=RuntimeError("simulated brain failure"))
    return instance


def test_repl_survives_brain_exception(
    titan_with_mock_brain: Titan,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """P1-111: one loop iteration with Brain failure returns French message and exits cleanly."""
    titan_with_mock_brain.start()

    captured = capsys.readouterr()
    assert BRAIN_FAILURE_MESSAGE in captured.out
    titan_with_mock_brain.brain.think.assert_called_once_with("test question")
    assert titan_with_mock_brain.conversation.history[-1]["message"] == BRAIN_FAILURE_MESSAGE


def test_repl_brain_exception_is_logged(
    titan_with_mock_brain: Titan,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """P1-110: Brain failure must log stack trace at ERROR level."""
    with caplog.at_level("ERROR", logger="core.titan"):
        titan_with_mock_brain.start()

    assert any("Brain failure" in record.message for record in caplog.records)
    assert any(record.exc_info is not None for record in caplog.records)

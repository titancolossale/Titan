# =====================================
# Titan Calendar Validator Tests
# =====================================

"""Tests for Calendar connector configuration validation (Phase 14.1)."""

from __future__ import annotations

from tools.connectors.calendar_validator import (
    CalendarValidationCode,
    validate_calendar_config,
)


def test_validate_calendar_enabled() -> None:
    # Explicit mock provider — isolate from process .env (e.g. google OAuth).
    result = validate_calendar_config(
        enabled=True,
        timeout_seconds=30.0,
        provider="mock",
    )
    assert result.ok
    assert result.code == CalendarValidationCode.OK
    assert result.provider == "mock"


def test_validate_calendar_disabled() -> None:
    result = validate_calendar_config(enabled=False)
    assert not result.ok
    assert result.code == CalendarValidationCode.CALENDAR_DISABLED


def test_validate_calendar_invalid_timeout() -> None:
    result = validate_calendar_config(enabled=True, timeout_seconds=0)
    assert not result.ok
    assert result.code == CalendarValidationCode.INVALID_TIMEOUT

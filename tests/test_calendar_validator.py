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
    result = validate_calendar_config(enabled=True, timeout_seconds=30.0)
    assert result.ok
    assert result.code == CalendarValidationCode.OK


def test_validate_calendar_disabled() -> None:
    result = validate_calendar_config(enabled=False)
    assert not result.ok
    assert result.code == CalendarValidationCode.CALENDAR_DISABLED


def test_validate_calendar_invalid_timeout() -> None:
    result = validate_calendar_config(enabled=True, timeout_seconds=0)
    assert not result.ok
    assert result.code == CalendarValidationCode.INVALID_TIMEOUT

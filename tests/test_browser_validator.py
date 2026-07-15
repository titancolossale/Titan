# =====================================
# Titan Browser Validator Tests
# =====================================

"""Tests for Phase 13.2 — Browser validator."""

from __future__ import annotations

from unittest.mock import patch

from tools.connectors.browser_validator import (
    BrowserValidationCode,
    validate_browser_config,
)


def test_browser_disabled_by_default() -> None:
    result = validate_browser_config(enabled=False)
    assert not result.ok
    assert result.code == BrowserValidationCode.BROWSER_DISABLED


def test_browser_enabled_with_valid_timeout() -> None:
    result = validate_browser_config(
        enabled=True,
        timeout_seconds=15.0,
        require_playwright=False,
    )
    assert result.ok
    assert result.code == BrowserValidationCode.OK
    assert result.timeout_seconds == 15.0


def test_browser_rejects_invalid_timeout() -> None:
    result = validate_browser_config(
        enabled=True,
        timeout_seconds=0,
        require_playwright=False,
    )
    assert not result.ok
    assert result.code == BrowserValidationCode.INVALID_TIMEOUT


def test_browser_requires_playwright_when_enabled() -> None:
    with patch(
        "tools.connectors.browser_validator._playwright_importable",
        return_value=False,
    ):
        result = validate_browser_config(enabled=True, timeout_seconds=15.0)
    assert not result.ok
    assert result.code == BrowserValidationCode.PLAYWRIGHT_MISSING

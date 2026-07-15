# =====================================
# Titan Browser Interaction Tests
# =====================================

"""Tests for Phase 13.3 — Browser controlled interaction."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools.connectors.browser_backend import FetchBrowserBackend, PlaywrightBrowserBackend
from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.browser_permissions import (
    BrowserPermissionLevel,
    evaluate_browser_permission,
)
from tools.connectors.browser_session import BrowserSession
from tools.permission_manager import PermissionLevel, PermissionManager

_SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Interaction Test</title></head>
<body>
  <button id="submit">Submit</button>
  <input id="query" type="text" />
  <select id="country"><option value="fr">France</option></select>
</body>
</html>
"""


def _mock_fetch(url: str, timeout: float) -> tuple[str, str, tuple[str, ...]]:
    return _SAMPLE_HTML, "text/html; charset=utf-8", ()


@pytest.fixture
def connector() -> BrowserConnector:
    backend = FetchBrowserBackend(_mock_fetch, timeout_seconds=5.0)
    conn = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    conn.execute("open_page", {"url": "https://example.com/page"})
    return conn


@pytest.fixture
def backend() -> FetchBrowserBackend:
    backend = FetchBrowserBackend(_mock_fetch, timeout_seconds=5.0)
    backend.navigate("https://example.com/page", timeout_seconds=5.0)
    return backend


def test_action_routing_supported_actions() -> None:
    connector = BrowserConnector(enabled=True, fetcher=_mock_fetch)
    actions = connector.supported_actions()
    assert "click_element" in actions
    assert "scroll_page" in actions
    assert "take_screenshot" in actions
    assert "go_back" in actions


def test_permissions_auto_allowed_scroll() -> None:
    result = evaluate_browser_permission("scroll_page", {})
    assert result.level == BrowserPermissionLevel.AUTO_ALLOWED


def test_permissions_confirmation_required_click() -> None:
    result = evaluate_browser_permission("click_element", {"selector": "#submit"})
    assert result.level == BrowserPermissionLevel.CONFIRMATION_REQUIRED
    assert result.confirmation_required


def test_permissions_blocked_unsafe_click_params() -> None:
    result = evaluate_browser_permission(
        "click_element",
        {"selector": "#submit", "force": True},
    )
    assert result.level == BrowserPermissionLevel.BLOCKED


def test_permissions_blocked_credential_type() -> None:
    result = evaluate_browser_permission(
        "type_text",
        {"selector": "#password", "input_type": "password"},
    )
    assert result.level == BrowserPermissionLevel.BLOCKED


def test_permissions_credential_allowed_with_flag() -> None:
    result = evaluate_browser_permission(
        "type_text",
        {
            "selector": "#password",
            "input_type": "password",
            "credential_approved": True,
            "confirmed": True,
        },
        confirmed=True,
    )
    assert result.level == BrowserPermissionLevel.AUTO_ALLOWED


def test_click_without_confirmation_does_not_execute(connector: BrowserConnector) -> None:
    outcome = connector.execute(
        "click_element",
        {"selector": "#submit"},
    )
    assert not outcome.success
    payload = json.loads(outcome.data)
    assert payload["executed"] is False
    assert payload["confirmation_required"] is True
    backend = connector._backend
    assert isinstance(backend, FetchBrowserBackend)
    assert not any(entry[0] == "click_element" for entry in backend.interaction_log)


def test_click_with_confirmation_executes(connector: BrowserConnector) -> None:
    outcome = connector.execute(
        "click_element",
        {"selector": "#submit", "confirmed": True},
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["executed"] is True
    assert payload["action"] == "click_element"
    backend = connector._backend
    assert isinstance(backend, FetchBrowserBackend)
    assert ("click_element", {"selector": "#submit"}) in backend.interaction_log


def test_type_text_with_confirmation(backend: FetchBrowserBackend) -> None:
    connector = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    outcome = connector.execute(
        "type_text",
        {"selector": "#query", "text": "Titan", "confirmed": True},
    )
    assert outcome.success
    assert ("type_text", {"selector": "#query", "text": "Titan", "clear": True}) in (
        backend.interaction_log
    )


def test_select_option_with_confirmation(backend: FetchBrowserBackend) -> None:
    connector = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    outcome = connector.execute(
        "select_option",
        {"selector": "#country", "value": "fr", "confirmed": True},
    )
    assert outcome.success
    assert (
        "select_option",
        {"selector": "#country", "value": "fr"},
    ) in backend.interaction_log


def test_scroll_auto_allowed(backend: FetchBrowserBackend) -> None:
    connector = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    outcome = connector.execute("scroll_page", {"direction": "down", "pixels": 200})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["permission_level"] == BrowserPermissionLevel.AUTO_ALLOWED.value
    assert ("scroll_page", {"direction": "down", "pixels": 200}) in backend.interaction_log


def test_go_back_auto_allowed(backend: FetchBrowserBackend) -> None:
    connector = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    outcome = connector.execute("go_back", {})
    assert outcome.success
    assert ("go_back", {}) in backend.interaction_log


def test_open_tab_requires_confirmation(backend: FetchBrowserBackend) -> None:
    connector = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    pending = connector.execute("open_new_tab", {})
    assert not pending.success
    assert not any(entry[0] == "open_new_tab" for entry in backend.interaction_log)

    confirmed = connector.execute("open_new_tab", {"confirmed": True})
    assert confirmed.success
    assert ("open_new_tab", {}) in backend.interaction_log


def test_close_tab_requires_confirmation(backend: FetchBrowserBackend) -> None:
    connector = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    pending = connector.execute("close_tab", {})
    assert not pending.success

    confirmed = connector.execute("close_tab", {"confirmed": True})
    assert confirmed.success


def test_wait_for_element_auto_allowed(backend: FetchBrowserBackend) -> None:
    connector = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    outcome = connector.execute("wait_for_element", {"selector": "#submit"})
    assert outcome.success
    assert ("wait_for_element", {"selector": "#submit"}) in backend.interaction_log


def test_take_screenshot_auto_allowed(backend: FetchBrowserBackend, tmp_path) -> None:
    connector = BrowserConnector(enabled=True, timeout_seconds=5.0, backend=backend)
    screenshot_path = str(tmp_path / "shot.png")
    outcome = connector.execute("take_screenshot", {"path": screenshot_path})
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["screenshot_path"] == screenshot_path


def test_blocked_bypass_security_action(connector: BrowserConnector) -> None:
    outcome = connector.execute("bypass_security", {})
    assert not outcome.success
    assert "bloqu" in outcome.error.lower() or "supportée" in outcome.error.lower()


def test_permission_manager_scroll_auto_allowed() -> None:
    manager = PermissionManager()
    result = manager.evaluate("browser", "scroll_page", {"action": "scroll_page"})
    assert result.level == PermissionLevel.AUTO_ALLOWED


def test_permission_manager_click_confirmation() -> None:
    manager = PermissionManager()
    result = manager.evaluate(
        "browser",
        "click_element",
        {"action": "click_element", "selector": "#submit"},
    )
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_playwright_backend_click_delegates_to_session() -> None:
    mock_session = MagicMock(spec=BrowserSession)
    mock_session.is_launched = True
    mock_session.launch.return_value = (True, "ok")
    mock_session.click_element.return_value = (True, None)
    mock_session.get_current_url.return_value = "https://example.com"
    mock_session.get_page_title.return_value = "Example"
    mock_session.get_page_html.return_value = _SAMPLE_HTML
    mock_session.get_visible_text.return_value = "Submit"
    mock_session.wait_for_page_load.return_value = (True, None)

    backend = PlaywrightBrowserBackend(session=mock_session)
    ok, error = backend.click_element("#submit", timeout_seconds=5.0)
    assert ok
    assert error is None
    mock_session.click_element.assert_called_once_with("#submit")

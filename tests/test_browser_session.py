# =====================================
# Titan Browser Session Tests
# =====================================

"""Unit tests for Phase 13.2 — BrowserSession and Playwright backend."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.connectors.browser_backend import FetchBrowserBackend, PlaywrightBrowserBackend
from tools.connectors.browser_session import BrowserSession

_SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Session Test</title></head>
<body><p>Playwright body text</p></body>
</html>
"""


def _mock_fetch(url: str, timeout: float) -> tuple[str, str, tuple[str, ...]]:
    return _SAMPLE_HTML, "text/html; charset=utf-8", ()


def test_browser_session_launch_and_close() -> None:
    session = BrowserSession(headless=True, timeout_seconds=5.0)
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_playwright.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context

    with patch("playwright.sync_api.sync_playwright") as sync_pw:
        sync_pw.return_value.start.return_value = mock_playwright
        launched, message = session.launch()
        assert launched
        assert "Playwright" in message
        assert session.is_launched

        session.close()
        assert not session.is_launched
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()


def test_browser_session_new_page_and_read() -> None:
    session = BrowserSession(headless=True, timeout_seconds=5.0)
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.title.return_value = "Example"
    mock_page.content.return_value = _SAMPLE_HTML
    mock_page.locator.return_value.inner_text.return_value = "Playwright body text"

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    session._launched = True
    session._context = mock_context

    page_id, error = session.new_page("tab-1")
    assert page_id == "tab-1"
    assert error is None
    assert session.page_count == 1

    ok, nav_error = session.open_url("https://example.com")
    assert ok
    assert nav_error is None
    mock_page.goto.assert_called_once()

    assert session.get_current_url() == "https://example.com"
    assert session.get_page_title() == "Example"
    assert "Playwright body text" in session.get_visible_text()
    assert "Session Test" in session.get_page_html()


def test_playwright_backend_navigate_with_mock_session() -> None:
    mock_session = MagicMock(spec=BrowserSession)
    mock_session.is_launched = False
    mock_session.launch.return_value = (True, "ok")
    mock_session.open_url.return_value = (True, None)
    mock_session.get_current_url.return_value = "https://example.com"
    mock_session.get_page_title.return_value = "Example"
    mock_session.get_page_html.return_value = _SAMPLE_HTML
    mock_session.get_visible_text.return_value = "Playwright body text"

    backend = PlaywrightBrowserBackend(session=mock_session)
    snapshot, error = backend.navigate("https://example.com", timeout_seconds=5.0)

    assert error is None
    assert snapshot is not None
    assert snapshot.url == "https://example.com"
    assert snapshot.title == "Example"
    assert "Playwright body text" in snapshot.visible_text


def test_fetch_backend_preserves_test_injection() -> None:
    backend = FetchBrowserBackend(_mock_fetch, timeout_seconds=5.0)
    snapshot, error = backend.navigate("https://example.com/page", timeout_seconds=5.0)

    assert error is None
    assert snapshot is not None
    assert snapshot.title == "Session Test"
    assert backend.is_started

    read_snapshot, read_error = backend.read_current(timeout_seconds=5.0)
    assert read_error is None
    assert read_snapshot is not None
    assert read_snapshot.url == "https://example.com/page"

    backend.stop()
    assert not backend.is_started

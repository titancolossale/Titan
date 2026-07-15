# =====================================
# Titan Browser Tool Tests
# =====================================

"""Tests for Phase 13.2 — Browser connector with Playwright backend."""

from __future__ import annotations

import json

import pytest

from tools.browser_tool import BrowserTool
from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.browser_models import BrowserResult
from tools.connectors.browser_parser import parse_html_page
from tools.tool_manager import ToolManager

_SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Titan Test Page</title></head>
<body>
  <h1>Hello Titan</h1>
  <p>Visible paragraph.</p>
  <a href="/docs">Documentation</a>
  <form action="/search" method="get">
    <input type="text" name="q" />
    <input type="submit" value="Search" />
  </form>
  <button type="button">Dismiss</button>
  <script>ignored();</script>
</body>
</html>
"""


def _mock_fetch(url: str, timeout: float) -> tuple[str, str, tuple[str, ...]]:
    return _SAMPLE_HTML, "text/html; charset=utf-8", ()


@pytest.fixture
def connector() -> BrowserConnector:
    return BrowserConnector(enabled=True, timeout_seconds=5.0, fetcher=_mock_fetch)


@pytest.fixture
def browser_tool(connector: BrowserConnector) -> BrowserTool:
    return BrowserTool(enabled=True, connector=connector)


def test_parser_extracts_title_text_links_forms_buttons() -> None:
    result = parse_html_page(_SAMPLE_HTML, url="https://example.com/page")
    assert result.page_title == "Titan Test Page"
    assert "Hello Titan" in result.page_text
    assert "ignored" not in result.page_text
    assert len(result.detected_links) == 1
    assert result.detected_links[0].href == "https://example.com/docs"
    assert len(result.detected_forms) == 1
    assert result.detected_forms[0].method == "get"
    assert "q" in result.detected_forms[0].fields
    assert any(btn.label == "Search" for btn in result.detected_buttons)
    assert any(btn.label == "Dismiss" for btn in result.detected_buttons)


def test_connector_open_page_returns_browser_result_json(connector: BrowserConnector) -> None:
    outcome = connector.execute(
        "open_page",
        {"url": "https://example.com/page"},
    )
    assert outcome.success
    payload = json.loads(outcome.data)
    assert payload["page_title"] == "Titan Test Page"
    assert payload["url"] == "https://example.com/page"
    assert connector.session.current_url == "https://example.com/page"


def test_connector_read_page_uses_session_cache(connector: BrowserConnector) -> None:
    connector.execute("open_page", {"url": "https://example.com/page"})
    outcome = connector.execute("read_page", {})
    assert outcome.success
    assert connector.session.last_result is not None


def test_connector_blocks_unsafe_url_scheme(connector: BrowserConnector) -> None:
    outcome = connector.execute("open_page", {"url": "javascript:alert(1)"})
    assert not outcome.success
    assert "autorisées" in outcome.error.lower() or "bloqué" in outcome.error.lower()


def test_connector_start_and_health(connector: BrowserConnector) -> None:
    started, message = connector.start()
    assert started
    assert "démarrée" in message.lower()
    ok, health_message = connector.health_check()
    assert ok
    assert health_message


def test_browser_tool_run_open_page(browser_tool: BrowserTool) -> None:
    result = browser_tool.run(
        action="open_page",
        url="https://example.com/page",
    )
    assert result.success
    assert result.source == "browser"
    assert result.metadata["connector"] == "browser"


def test_browser_tool_registered_in_tool_manager() -> None:
    manager = ToolManager()
    assert manager.registry.get("browser") is not None
    schema = manager.registry.get("browser").schema
    assert schema.name == "browser"

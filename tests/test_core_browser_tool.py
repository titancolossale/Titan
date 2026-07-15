# =====================================
# Titan Core Browser Tool V1 Tests
# =====================================

"""Tests for read-only Browser integration in core/tools/browser."""

from __future__ import annotations

import httpx
import pytest

from core.actions import ActionDispatcher, ActionRegistry
from core.exceptions import ToolTimeoutError
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools import ToolRegistry
from core.tools.browser import (
    BrowserClient,
    BrowserConfig,
    BrowserInvalidUrlError,
    BrowserPermissionDeniedError,
    BrowserTool,
    PERMISSION_EXTRACT,
    PERMISSION_FETCH,
    PERMISSION_OPEN_URL,
)
from core.tools.browser.html_parser import extract_links, extract_text
from core.tools.browser.url_validator import validate_url

SAMPLE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <title>Test Page</title>
  <style>body { display: none; }</style>
  <script>window.secret = "hidden";</script>
  <noscript>Enable JS</noscript>
</head>
<body>
  <p>Hello World</p>
  <a href="/about">About Us</a>
  <a href="https://example.org/external">External</a>
</body>
</html>
"""


def _mock_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)

    if "redirect-source.example.com" in url:
        return httpx.Response(
            302,
            headers={"Location": "https://example.com/final"},
        )

    if "example.com/final" in url or url.endswith("example.com/valid"):
        return httpx.Response(
            200,
            text=SAMPLE_HTML,
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-language": "fr-CA",
            },
        )

    if "example.com/notfound" in url:
        return httpx.Response(404, text="Not Found")

    if "example.com/timeout" in url:
        raise httpx.ReadTimeout("Simulated timeout", request=request)

    return httpx.Response(404, text="Unexpected URL in mock handler")


@pytest.fixture
def browser_config() -> BrowserConfig:
    return BrowserConfig(timeout=5.0, max_download_size=1024 * 1024)


@pytest.fixture
def browser_client(browser_config: BrowserConfig) -> BrowserClient:
    client = BrowserClient(browser_config, handler=_mock_handler)
    yield client
    client.close()


@pytest.fixture
def browser_tool(browser_config: BrowserConfig) -> BrowserTool:
    tool = BrowserTool(config=browser_config, handler=_mock_handler)
    yield tool
    tool.close()


def test_valid_url_fetch(browser_client: BrowserClient) -> None:
    page = browser_client.fetch_page("https://example.com/valid")

    assert page.status_code == 200
    assert page.title == "Test Page"
    assert page.language == "fr"
    assert page.response_size > 0
    assert "Hello World" in page.html


def test_404_response(browser_client: BrowserClient) -> None:
    page = browser_client.fetch_page("https://example.com/notfound")

    assert page.status_code == 404


def test_redirect_followed(browser_client: BrowserClient) -> None:
    page = browser_client.fetch_page("https://redirect-source.example.com/start")

    assert page.status_code == 200
    assert page.url == "https://example.com/final"
    assert page.title == "Test Page"


def test_timeout(browser_config: BrowserConfig) -> None:
    config = BrowserConfig(
        timeout=0.001,
        max_download_size=browser_config.max_download_size,
        user_agent=browser_config.user_agent,
        follow_redirects=browser_config.follow_redirects,
        allowed_schemes=browser_config.allowed_schemes,
    )

    def slow_handler(request: httpx.Request) -> httpx.Response:
        if "example.com/timeout" in str(request.url):
            raise httpx.ReadTimeout("Simulated timeout", request=request)
        return _mock_handler(request)

    client = BrowserClient(config, handler=slow_handler)
    try:
        with pytest.raises(ToolTimeoutError):
            client.fetch_page("https://example.com/timeout")
    finally:
        client.close()


def test_invalid_url_scheme() -> None:
    config = BrowserConfig()

    with pytest.raises(BrowserInvalidUrlError):
        validate_url("file:///etc/passwd", config)

    with pytest.raises(BrowserInvalidUrlError):
        validate_url("ftp://files.example.com/data", config)

    with pytest.raises(BrowserInvalidUrlError):
        validate_url("not-a-url", config)


def test_private_ip_blocked() -> None:
    config = BrowserConfig()

    for blocked in (
        "http://127.0.0.1/",
        "http://localhost/admin",
        "http://192.168.1.1/",
        "http://10.0.0.5/page",
        "http://172.16.0.1/",
    ):
        with pytest.raises(BrowserInvalidUrlError):
            validate_url(blocked, config)


def test_extract_text_ignores_script_style() -> None:
    text = extract_text(SAMPLE_HTML)

    assert "Hello World" in text
    assert "window.secret" not in text
    assert "display: none" not in text
    assert "Enable JS" not in text


def test_extract_links_resolves_relative_urls() -> None:
    links = extract_links(SAMPLE_HTML, base_url="https://example.com/page")

    hrefs = {link.href for link in links}
    assert "https://example.com/about" in hrefs
    assert "https://example.org/external" in hrefs


def test_page_metadata_action(browser_tool: BrowserTool) -> None:
    result = browser_tool.execute_action(
        "page_metadata",
        url="https://example.com/valid",
    )

    assert result.success is True
    metadata = result.data["metadata"]
    assert metadata["title"] == "Test Page"
    assert metadata["status_code"] == 200
    assert metadata["content_type"] == "text/html"
    assert metadata["language"] == "fr"
    assert metadata["response_size"] > 0
    assert metadata["url"] == "https://example.com/valid"


def test_open_url_action(browser_tool: BrowserTool) -> None:
    result = browser_tool.execute_action(
        "open_url",
        url="https://example.com/valid",
    )

    assert result.success is True
    assert "Hello World" in result.data["text_preview"]
    assert result.data["metadata"]["title"] == "Test Page"


def test_fetch_html_action(browser_tool: BrowserTool) -> None:
    result = browser_tool.execute_action(
        "fetch_html",
        url="https://example.com/valid",
    )

    assert result.success is True
    assert "<title>Test Page</title>" in result.data["html"]


def test_extract_text_action(browser_tool: BrowserTool) -> None:
    result = browser_tool.execute_action(
        "extract_text",
        url="https://example.com/valid",
    )

    assert result.success is True
    assert result.data["text"] == "Hello World"
    assert result.data["title"] == "Test Page"


def test_extract_links_action(browser_tool: BrowserTool) -> None:
    result = browser_tool.execute_action(
        "extract_links",
        url="https://example.com/valid",
    )

    assert result.success is True
    assert result.data["count"] == 2
    hrefs = {link["href"] for link in result.data["links"]}
    assert "https://example.com/about" in hrefs


def test_permission_denied_for_open_url(browser_config: BrowserConfig) -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_OPEN_URL,
            name="Blocked Open",
            description="Blocked for test.",
            level=PermissionLevel.BLOCKED,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_FETCH,
            name="Fetch",
            description="Allowed fetch.",
            level=PermissionLevel.SAFE,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_EXTRACT,
            name="Extract",
            description="Allowed extract.",
            level=PermissionLevel.SAFE,
        )
    )

    tool = BrowserTool(
        config=browser_config,
        permission_manager=permission_manager,
        handler=_mock_handler,
    )
    try:
        with pytest.raises(BrowserPermissionDeniedError):
            tool.execute(action="open_url", url="https://example.com/valid")
    finally:
        tool.close()


def test_permission_denied_via_dispatcher(browser_config: BrowserConfig) -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_FETCH,
            name="Blocked Fetch",
            description="Blocked for test.",
            level=PermissionLevel.BLOCKED,
        )
    )

    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = BrowserTool(
        config=browser_config,
        permission_manager=permission_manager,
        action_registry=action_registry,
        handler=_mock_handler,
    )
    tool_registry.register_tool(tool)

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
    )

    try:
        result = dispatcher.dispatch(
            "browser",
            "page_metadata",
            {"url": "https://example.com/valid"},
        )
        assert result.success is False
        assert "permission" in result.message.lower()
    finally:
        tool.close()


def test_tool_registers_default_permissions(browser_tool: BrowserTool) -> None:
    manager = browser_tool.permission_manager

    assert manager.permission_exists(PERMISSION_OPEN_URL)
    assert manager.permission_exists(PERMISSION_FETCH)
    assert manager.permission_exists(PERMISSION_EXTRACT)


def test_execute_action_records_execution_time(browser_tool: BrowserTool) -> None:
    result = browser_tool.execute_action(
        "page_metadata",
        url="https://example.com/valid",
    )

    assert result.success is True
    assert result.execution_time >= 0.0


def test_tool_loader_discovers_browser() -> None:
    from core.tools import ToolLoader, ToolRegistry

    registry = ToolRegistry()
    loader = ToolLoader(
        registry,
        scan_paths=[__import__("pathlib").Path(__file__).resolve().parents[1] / "core" / "tools"],
    )
    result = loader.load()

    assert "browser" in result.loaded
    assert registry.tool_exists("browser")

    loaded = registry.get_tool("browser")
    assert loaded is not None
    assert loaded.id == "browser"
    assert "open_url" in {action.id for action in loaded.list_actions()}

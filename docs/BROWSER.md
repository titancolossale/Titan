# Titan Browser Tool V1 — Read-Only HTTP (Core Tools)

Browser Tool V1 is Titan's first **production read-only web retrieval tool** in the `core/tools/` framework. It fetches public HTTP/HTTPS pages and returns structured content — it is **not** Titan's reasoning engine and does not execute JavaScript, authenticate, or automate browsers.

## Scope (V1)

**Implemented:**

| Action | Permission | Description |
|--------|------------|-------------|
| `open_url` | `browser.open_url` | Fetch URL; return metadata + text preview |
| `fetch_html` | `browser.fetch` | Return raw HTML body |
| `extract_text` | `browser.extract` | Visible text (script/style/noscript ignored) |
| `extract_links` | `browser.extract` | Hyperlinks with absolute URLs |
| `page_metadata` | `browser.fetch` | Title, URL, status, content type, language, size |

**Supported HTTP features:**

- `http` and `https` schemes
- Redirect following (configurable)
- Request timeouts
- Custom User-Agent
- Response size limits

**Deferred to future versions:**

- JavaScript execution
- Authentication, cookies, login
- Screenshots and downloads
- File uploads
- Playwright browser automation

## Architecture

```
core/tools/browser/
├── browser_tool.py      ← BaseTool facade (actions + permissions)
├── browser_client.py    ← HTTP fetch via httpx
├── browser_config.py    ← Timeout, size limits, user-agent
├── url_validator.py       ← Safe URL validation (SSRF protection)
├── html_parser.py         ← Text and link extraction
├── models.py              ← PageResponse, PageMetadata, ExtractedLink
└── exceptions.py          ← Domain errors
```

### Integration with existing frameworks

```
ActionDispatcher
  → PermissionManager.check_permission(action.permission_id)
  → BrowserTool.execute_action()
  → BrowserClient.fetch_page()
  → url_validator + html_parser
```

- **Tool Registry** — `ToolLoader` auto-discovers `BrowserTool` from `core/tools/browser/`
- **Action Framework** — each operation is an `Action` returning `ActionResult`
- **Permission Manager** — three permission IDs gate read operations

Browser Tool V1 is separate from the legacy Playwright stack in `tools/browser_tool.py` (Phase 13). That stack provides session-based Chromium automation; this core tool provides lightweight HTTP retrieval aligned with the Action Framework.

## Permission Model

| Permission ID | Level | Actions |
|---------------|-------|---------|
| `browser.open_url` | SAFE | `open_url` |
| `browser.fetch` | SAFE | `fetch_html`, `page_metadata` |
| `browser.extract` | SAFE | `extract_text`, `extract_links` |

Permissions are registered idempotently when `BrowserTool` is instantiated.

## URL Safety

The validator rejects:

- Non-HTTP schemes (`file://`, `ftp://`, `javascript:`, `data:`)
- `localhost`, `127.0.0.1`, `::1`
- Private, link-local, loopback, and reserved IP ranges
- Malformed URLs

This prevents SSRF against internal networks.

## Page Metadata

`page_metadata` and `open_url` return:

```json
{
  "title": "Example Page",
  "url": "https://example.com/page",
  "status_code": 200,
  "content_type": "text/html",
  "language": "en",
  "response_size": 4096
}
```

Language is detected from the `Content-Language` header or `<html lang="...">`.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_BROWSER_TIMEOUT_SECONDS` | `30` | Request timeout (seconds) |
| `TITAN_BROWSER_MAX_DOWNLOAD_SIZE` | `5242880` | Max response body (5 MiB) |
| `TITAN_BROWSER_USER_AGENT` | `TitanBot/1.0 (Read-Only Browser Tool)` | HTTP User-Agent |
| `TITAN_BROWSER_FOLLOW_REDIRECTS` | `true` | Follow HTTP redirects |
| `TITAN_BROWSER_ALLOWED_SCHEMES` | `http,https` | Permitted URL schemes |

Programmatic configuration via `BrowserConfig`:

```python
from core.tools.browser import BrowserConfig, BrowserTool

config = BrowserConfig(timeout=15.0, max_download_size=1_048_576)
tool = BrowserTool(config=config)
result = tool.execute_action("extract_text", url="https://example.com")
```

## Action Dispatch Example

```python
from core.actions import ActionDispatcher, ActionRegistry
from core.permissions import PermissionManager
from core.tools import ToolRegistry
from core.tools.browser import BrowserTool

permission_manager = PermissionManager()
action_registry = ActionRegistry()
tool_registry = ToolRegistry()

tool = BrowserTool(
    permission_manager=permission_manager,
    action_registry=action_registry,
)
tool_registry.register_tool(tool)

dispatcher = ActionDispatcher(
    tool_registry=tool_registry,
    action_registry=action_registry,
    permission_manager=permission_manager,
)

result = dispatcher.dispatch(
    "browser",
    "extract_text",
    {"url": "https://example.com"},
)
```

## Logging

Every request logs:

- Start: URL (credentials redacted)
- Completion: final URL, status code, response size
- Failures: error class and message (never full response bodies or secrets)

## Tests

```bash
pytest tests/test_core_browser_tool.py -v
```

Coverage includes: valid URL, 404, redirect, timeout, invalid URL, private IP blocked, extract text, extract links, metadata, permission denied, and ToolLoader discovery.

## Related Documentation

- Legacy Playwright browser connector: `tools/connectors/browser_connector.py` (Phase 13+)
- Browser intelligence layer: `tools/browser_intelligence.py` (Phase 23)
- Core tool loader: `core/tools/tool_loader.py`

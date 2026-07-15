# =====================================
# Titan Browser Tool
# =====================================

"""Read-only HTTP browser tool for Titan's core tool layer."""

from __future__ import annotations

import logging
import time

import httpx

from core.actions.action import Action
from core.actions.action_registry import ActionRegistry
from core.actions.action_result import ActionResult
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.base_tool import BaseTool
from core.tools.browser.browser_client import BrowserClient, HttpHandler
from core.tools.browser.browser_config import BrowserConfig
from core.tools.browser.exceptions import (
    BrowserConfigurationError,
    BrowserInvalidUrlError,
    BrowserPermissionDeniedError,
)
from core.tools.browser.html_parser import extract_links, extract_text
from core.tools.browser.models import PageMetadata

logger = logging.getLogger(__name__)

PERMISSION_OPEN_URL = "browser.open_url"
PERMISSION_FETCH = "browser.fetch"
PERMISSION_EXTRACT = "browser.extract"

CAPABILITY_OPEN_URL = "open_url"
CAPABILITY_FETCH_HTML = "fetch_html"
CAPABILITY_EXTRACT_TEXT = "extract_text"
CAPABILITY_EXTRACT_LINKS = "extract_links"
CAPABILITY_PAGE_METADATA = "page_metadata"

_CAPABILITY_PERMISSIONS: dict[str, str] = {
    CAPABILITY_OPEN_URL: PERMISSION_OPEN_URL,
    CAPABILITY_FETCH_HTML: PERMISSION_FETCH,
    CAPABILITY_EXTRACT_TEXT: PERMISSION_EXTRACT,
    CAPABILITY_EXTRACT_LINKS: PERMISSION_EXTRACT,
    CAPABILITY_PAGE_METADATA: PERMISSION_FETCH,
}

_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "open_url": CAPABILITY_OPEN_URL,
    "fetch_html": CAPABILITY_FETCH_HTML,
    "extract_text": CAPABILITY_EXTRACT_TEXT,
    "extract_links": CAPABILITY_EXTRACT_LINKS,
    "page_metadata": CAPABILITY_PAGE_METADATA,
}

_DEFAULT_PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        id=PERMISSION_OPEN_URL,
        name="Open URL",
        description="Open and inspect a public web page URL.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_FETCH,
        name="Fetch HTML",
        description="Retrieve raw HTML content from a public web page.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_EXTRACT,
        name="Extract Page Content",
        description="Extract visible text or links from a web page.",
        level=PermissionLevel.SAFE,
    ),
)

_URL_PARAMETER = {
    "url": {
        "type": "string",
        "required": True,
        "description": "Target HTTP or HTTPS URL.",
    },
}


def _build_browser_actions(tool_id: str) -> tuple[Action, ...]:
    """Return the canonical Browser actions registered in the action framework."""
    return (
        Action(
            id="open_url",
            name="Open URL",
            description="Fetch a URL and return page metadata with a text preview.",
            tool_id=tool_id,
            permission_id=PERMISSION_OPEN_URL,
            parameters=_URL_PARAMETER,
            metadata={"capability": CAPABILITY_OPEN_URL},
        ),
        Action(
            id="fetch_html",
            name="Fetch HTML",
            description="Retrieve the raw HTML body for a URL.",
            tool_id=tool_id,
            permission_id=PERMISSION_FETCH,
            parameters=_URL_PARAMETER,
            metadata={"capability": CAPABILITY_FETCH_HTML},
        ),
        Action(
            id="extract_text",
            name="Extract Text",
            description="Extract visible text from a URL, ignoring script and style.",
            tool_id=tool_id,
            permission_id=PERMISSION_EXTRACT,
            parameters=_URL_PARAMETER,
            metadata={"capability": CAPABILITY_EXTRACT_TEXT},
        ),
        Action(
            id="extract_links",
            name="Extract Links",
            description="Extract hyperlinks from a URL.",
            tool_id=tool_id,
            permission_id=PERMISSION_EXTRACT,
            parameters=_URL_PARAMETER,
            metadata={"capability": CAPABILITY_EXTRACT_LINKS},
        ),
        Action(
            id="page_metadata",
            name="Page Metadata",
            description="Return HTTP and document metadata for a URL.",
            tool_id=tool_id,
            permission_id=PERMISSION_FETCH,
            parameters=_URL_PARAMETER,
            metadata={"capability": CAPABILITY_PAGE_METADATA},
        ),
    )


class BrowserTool(BaseTool):
    """Read-only HTTP browser tool backed by the core permission and action systems.

    This tool retrieves public web content only. It does not execute JavaScript,
    authenticate, or perform browser automation.
    """

    def __init__(
        self,
        config: BrowserConfig | None = None,
        client: BrowserClient | None = None,
        permission_manager: PermissionManager | None = None,
        action_registry: ActionRegistry | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        handler: HttpHandler | None = None,
    ) -> None:
        super().__init__()
        self._permission_manager = permission_manager or PermissionManager()
        self._register_default_permissions()

        self._config = config or BrowserConfig.from_environment()
        self._client = client or BrowserClient(
            self._config,
            transport=transport,
            handler=handler,
        )
        self._actions = _build_browser_actions(self.id)

        if action_registry is not None:
            self._register_actions(action_registry)

    @property
    def id(self) -> str:
        return "browser"

    @property
    def name(self) -> str:
        return "Browser"

    @property
    def description(self) -> str:
        return (
            "Read-only HTTP access to public web pages. Retrieves HTML, visible text, "
            "links, and page metadata. Does not execute JavaScript or perform automation."
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def category(self) -> str:
        return "web"

    @property
    def requires_confirmation(self) -> bool:
        return False

    @property
    def capabilities(self) -> list[str]:
        return list(_CAPABILITY_PERMISSIONS.keys())

    @property
    def client(self) -> BrowserClient:
        """Return the underlying HTTP client."""
        return self._client

    @property
    def permission_manager(self) -> PermissionManager:
        """Return the permission manager used by this tool."""
        return self._permission_manager

    def list_actions(self) -> list[Action]:
        """Return the Browser actions exposed by this tool."""
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        """Execute a registered Browser action without performing permission checks.

        Permission verification is owned by ``ActionDispatcher``.
        """
        registered_ids = {action.id for action in self._actions}
        if action_id not in registered_ids:
            message = f"Unsupported Browser action: {action_id}"
            logger.warning(message)
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"action_id": action_id},
            )

        url = str(kwargs.get("url", "")).strip()
        if not url:
            message = "Missing required parameter: url"
            logger.warning("Browser action blocked: %s", message)
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"action_id": action_id},
            )

        started = time.perf_counter()
        try:
            data = self._dispatch_action(action_id, url)
        except BrowserInvalidUrlError as exc:
            message = str(exc)
            logger.warning(
                "Browser URL rejected: action=%s url=%s reason=%s",
                action_id,
                url,
                exc.reason,
            )
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                execution_time=time.perf_counter() - started,
                metadata={"action_id": action_id},
            )
        except Exception as exc:
            message = str(exc)
            logger.exception(
                "Browser action failed: action=%s error=%s",
                action_id,
                message,
            )
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                execution_time=time.perf_counter() - started,
                metadata={"action_id": action_id},
            )

        elapsed = time.perf_counter() - started
        logger.info("Browser action completed: action=%s url=%s", action_id, url)
        return ActionResult(
            success=True,
            data=data,
            message=f"Browser action '{action_id}' completed successfully.",
            execution_time=elapsed,
            metadata={"action_id": action_id},
        )

    def execute(self, **kwargs: object) -> object:
        """Dispatch a Browser action after permission checks.

        Legacy callers pass ``action`` in kwargs.
        """
        action = str(kwargs.get("action", "")).strip().lower()
        if not action:
            raise BrowserConfigurationError("Missing required parameter: action")

        capability = _ACTION_CAPABILITY_MAP.get(action)
        if capability is None:
            raise BrowserConfigurationError(f"Unsupported Browser action: {action}")

        self._require_permission(capability)

        result = self.execute_action(action, **kwargs)
        if not result.success:
            self._raise_for_failed_action(action, result)

        return result.data

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def _dispatch_action(self, action_id: str, url: str) -> dict[str, object]:
        page = self._client.fetch_page(url)

        if action_id == "open_url":
            preview = extract_text(page.html)[:500]
            metadata = page.to_metadata()
            return {
                "action": action_id,
                "metadata": metadata.to_dict(),
                "text_preview": preview,
            }

        if action_id == "fetch_html":
            return {
                "action": action_id,
                "url": page.url,
                "status_code": page.status_code,
                "html": page.html,
            }

        if action_id == "extract_text":
            text = extract_text(page.html)
            return {
                "action": action_id,
                "url": page.url,
                "text": text,
                "title": page.title,
            }

        if action_id == "extract_links":
            links = extract_links(page.html, base_url=page.url)
            return {
                "action": action_id,
                "url": page.url,
                "links": [link.to_dict() for link in links],
                "count": len(links),
            }

        if action_id == "page_metadata":
            metadata: PageMetadata = page.to_metadata()
            return {
                "action": action_id,
                "metadata": metadata.to_dict(),
            }

        raise BrowserConfigurationError(f"Unsupported Browser action: {action_id}")

    def _register_actions(self, registry: ActionRegistry) -> None:
        for action in self._actions:
            if registry.action_exists(action.tool_id, action.id):
                continue
            registry.register_action(action)

    def _register_default_permissions(self) -> None:
        for permission in _DEFAULT_PERMISSIONS:
            if self._permission_manager.permission_exists(permission.id):
                continue
            self._permission_manager.register_permission(permission)
            logger.info("Registered Browser permission: %s", permission.id)

    def _require_permission(self, capability: str) -> None:
        permission_id = _CAPABILITY_PERMISSIONS[capability]
        result = self._permission_manager.check_permission(permission_id)
        if not result.allowed:
            logger.warning(
                "Browser permission denied: capability=%s permission=%s reason=%s",
                capability,
                permission_id,
                result.reason,
            )
            raise BrowserPermissionDeniedError(permission_id, result.reason)

    @staticmethod
    def _raise_for_failed_action(action: str, result: ActionResult) -> None:
        if "permission" in result.message.lower():
            permission_id = str(result.metadata.get("permission_id", "unknown"))
            raise BrowserPermissionDeniedError(permission_id, result.message)
        raise BrowserConfigurationError(result.message or f"Browser action failed: {action}")

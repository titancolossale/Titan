# =====================================
# Titan Browser Connector
# =====================================

"""Browser web interaction connector — read and controlled interaction (Phase 13.3).

Playwright-backed foundation for long-term autonomous interaction.
BrowserConnector is the only public browser interface; Playwright stays internal.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from config.settings import PROJECT_ROOT, TITAN_BROWSER_HEADLESS
from tools.connectors.base_connector import ConnectorResult
from tools.connectors.browser_backend import (
    BrowserBackend,
    FetchBrowserBackend,
    PageSnapshot,
    PlaywrightBrowserBackend,
)
from tools.connectors.browser_models import (
    BrowserActionResult,
    BrowserResult,
    BrowserSessionState,
)
from tools.connectors.browser_parser import parse_html_page
from tools.connectors.browser_permissions import (
    BrowserPermissionLevel,
    evaluate_browser_permission,
    is_confirmed,
    normalize_browser_action,
)
from tools.connectors.browser_validator import validate_browser_config

_READ_ACTIONS = frozenset({
    "open_page",
    "navigate",
    "read_page",
    "extract_text",
})

_INTERACTION_ACTIONS = frozenset({
    "click_element",
    "click",
    "click_button",
    "type_text",
    "type",
    "type_into_input",
    "select_option",
    "select",
    "select_dropdown",
    "scroll_page",
    "scroll",
    "go_back",
    "open_new_tab",
    "new_tab",
    "close_tab",
    "wait_for_element",
    "take_screenshot",
    "screenshot",
})

_SUPPORTED_ACTIONS = _READ_ACTIONS | _INTERACTION_ACTIONS

_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+",
    re.IGNORECASE,
)

_BLOCKED_SCHEMES = frozenset({"javascript", "data", "file", "vbscript"})

_SCREENSHOT_DIR = PROJECT_ROOT / "data" / "browser_screenshots"


class BrowserConnector:
    """Operate on web pages via a bounded browser session with permission gating."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 30.0,
        fetcher: Callable[[str, float], tuple[str, str, tuple[str, ...]]] | None = None,
        backend: BrowserBackend | None = None,
        headless: bool | None = None,
    ) -> None:
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._headless = TITAN_BROWSER_HEADLESS if headless is None else headless
        if backend is not None:
            self._backend = backend
        elif fetcher is not None:
            self._backend = FetchBrowserBackend(
                fetcher,
                timeout_seconds=timeout_seconds,
            )
        else:
            self._backend = PlaywrightBrowserBackend(
                headless=self._headless,
                timeout_seconds=timeout_seconds,
            )
        self._session = BrowserSessionState()

    @property
    def connector_id(self) -> str:
        return "browser"

    @property
    def is_configured(self) -> bool:
        return self._enabled

    @property
    def session(self) -> BrowserSessionState:
        return self._session

    def configuration_error(self) -> str:
        """Return a French error when the connector is not ready."""
        result = validate_browser_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
        )
        return result.message

    def health_check(self) -> tuple[bool, str]:
        """Probe connector readiness without mutating external state."""
        validation = validate_browser_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
        )
        if not validation.ok:
            return False, validation.message
        started, message = self.start()
        if not started:
            return False, message
        return True, f"{validation.message} Session : {message}"

    def start(self) -> tuple[bool, str]:
        """Start the browser session (Playwright Chromium)."""
        if not self._enabled:
            return False, self.configuration_error()
        if self._session.started and self._backend.is_started:
            return True, "Session navigateur déjà active."
        started, message = self._backend.start()
        if started:
            self._session.started = True
        return started, message

    def stop(self) -> None:
        """Stop the browser session and clear in-memory state."""
        self._backend.stop()
        self._session.started = False
        self._session.current_url = None
        self._session.last_result = None
        self._session.warnings.clear()

    def supported_actions(self) -> frozenset[str]:
        return _SUPPORTED_ACTIONS

    def execute(self, action: str, params: dict) -> ConnectorResult:
        """Dispatch *action* to the connector implementation."""
        normalized = normalize_browser_action(action)
        if normalized not in self.supported_actions():
            return ConnectorResult(
                success=False,
                action=action,
                error=f"Action non supportée : {action!r}",
            )
        if not self.is_configured:
            return ConnectorResult(
                success=False,
                action=action,
                error=self.configuration_error(),
            )
        started, start_error = self.start()
        if not started:
            return ConnectorResult(success=False, action=action, error=start_error)
        return self._execute_action(normalized, params)

    def _execute_action(self, action: str, params: dict) -> ConnectorResult:
        if action in _READ_ACTIONS:
            dispatch = {
                "open_page": self._open_page,
                "navigate": self._navigate,
                "read_page": self._read_page,
                "extract_text": self._extract_text,
            }
            return dispatch[action](params)

        permission = evaluate_browser_permission(
            action,
            params,
            confirmed=is_confirmed(params),
        )
        if permission.level == BrowserPermissionLevel.BLOCKED:
            return self._action_blocked(action, params, permission.reason)
        if permission.confirmation_required:
            return self._action_pending_confirmation(action, params, permission.reason)

        dispatch = {
            "click_element": self._click_element,
            "click": self._click_element,
            "click_button": self._click_element,
            "type_text": self._type_text,
            "type": self._type_text,
            "type_into_input": self._type_text,
            "select_option": self._select_option,
            "select": self._select_option,
            "select_dropdown": self._select_option,
            "scroll_page": self._scroll_page,
            "scroll": self._scroll_page,
            "go_back": self._go_back,
            "open_new_tab": self._open_new_tab,
            "new_tab": self._open_new_tab,
            "close_tab": self._close_tab,
            "wait_for_element": self._wait_for_element,
            "take_screenshot": self._take_screenshot,
            "screenshot": self._take_screenshot,
        }
        return dispatch[action](params)

    def _open_page(self, params: dict) -> ConnectorResult:
        url = self._resolve_url(params)
        if url is None:
            return self._error("open_page", "URL requise pour open_page.")
        return self._navigate_and_store("open_page", url)

    def _navigate(self, params: dict) -> ConnectorResult:
        url = self._resolve_url(params)
        if url is None:
            return self._error("navigate", "URL requise pour navigate.")
        return self._navigate_and_store("navigate", url)

    def _read_page(self, params: dict) -> ConnectorResult:
        url = self._resolve_url(params, allow_session=True)
        if url is None:
            return self._error(
                "read_page",
                "Aucune page active. Fournissez une URL ou appelez open_page d'abord.",
            )
        if self._session.last_result is not None and self._session.current_url == url:
            return self._success("read_page", self._session.last_result)
        snapshot, error = self._backend.read_current(self._timeout)
        if snapshot is None:
            return self._error("read_page", error or "Lecture de page impossible.")
        if snapshot.url != url:
            return self._navigate_and_store("read_page", url)
        return self._store_snapshot("read_page", snapshot)

    def _extract_text(self, params: dict) -> ConnectorResult:
        url = self._resolve_url(params, allow_session=True)
        if url is None:
            return self._error(
                "extract_text",
                "Aucune page active. Fournissez une URL ou appelez open_page d'abord.",
            )
        if self._session.last_result is None or self._session.current_url != url:
            fetch_result = self._navigate_and_store("extract_text", url)
            if not fetch_result.success:
                return fetch_result
        assert self._session.last_result is not None
        text_only = BrowserResult(
            url=self._session.last_result.url,
            page_title=self._session.last_result.page_title,
            page_text=self._session.last_result.page_text,
            status=self._session.last_result.status,
            warnings=self._session.last_result.warnings,
        )
        return self._success("extract_text", text_only)

    def _click_element(self, params: dict) -> ConnectorResult:
        selector = self._require_selector(params)
        if selector is None:
            return self._error("click_element", "Paramètre selector requis pour click_element.")
        ok, error = self._backend.click_element(selector, self._timeout)
        return self._interaction_result(
            "click_element",
            selector,
            ok,
            error or "Clic effectué.",
        )

    def _type_text(self, params: dict) -> ConnectorResult:
        selector = self._require_selector(params)
        if selector is None:
            return self._error("type_text", "Paramètre selector requis pour type_text.")
        text = str(params.get("text", ""))
        clear = params.get("clear", True) is not False
        ok, error = self._backend.type_text(selector, text, self._timeout, clear=clear)
        return self._interaction_result(
            "type_text",
            selector,
            ok,
            error or "Texte saisi.",
        )

    def _select_option(self, params: dict) -> ConnectorResult:
        selector = self._require_selector(params)
        if selector is None:
            return self._error("select_option", "Paramètre selector requis pour select_option.")
        value = str(params.get("value", "")).strip()
        if not value:
            return self._error("select_option", "Paramètre value requis pour select_option.")
        ok, error = self._backend.select_option(selector, value, self._timeout)
        return self._interaction_result(
            "select_option",
            selector,
            ok,
            error or f"Option {value!r} sélectionnée.",
        )

    def _scroll_page(self, params: dict) -> ConnectorResult:
        direction = str(params.get("direction", "down")).strip() or "down"
        pixels = int(params.get("pixels", 400))
        ok, error = self._backend.scroll_page(
            self._timeout,
            direction=direction,
            pixels=pixels,
        )
        return self._interaction_result(
            "scroll_page",
            "",
            ok,
            error or f"Défilement {direction} de {pixels}px effectué.",
            permission_level=BrowserPermissionLevel.AUTO_ALLOWED.value,
        )

    def _go_back(self, params: dict) -> ConnectorResult:
        ok, error = self._backend.go_back(self._timeout)
        result = self._interaction_result(
            "go_back",
            "",
            ok,
            error or "Retour arrière effectué.",
            permission_level=BrowserPermissionLevel.AUTO_ALLOWED.value,
        )
        if ok:
            self._refresh_session_from_backend()
        return result

    def _open_new_tab(self, params: dict) -> ConnectorResult:
        page_id, error = self._backend.open_new_tab(self._timeout)
        ok = page_id is not None
        return self._interaction_result(
            "open_new_tab",
            page_id or "",
            ok,
            error or f"Nouvel onglet ouvert : {page_id}.",
        )

    def _close_tab(self, params: dict) -> ConnectorResult:
        page_id = str(params.get("page_id", "")).strip() or None
        ok, error = self._backend.close_tab(self._timeout, page_id=page_id)
        return self._interaction_result(
            "close_tab",
            page_id or "",
            ok,
            error or "Onglet fermé.",
        )

    def _wait_for_element(self, params: dict) -> ConnectorResult:
        selector = self._require_selector(params)
        if selector is None:
            return self._error(
                "wait_for_element",
                "Paramètre selector requis pour wait_for_element.",
            )
        ok, error = self._backend.wait_for_element(selector, self._timeout)
        return self._interaction_result(
            "wait_for_element",
            selector,
            ok,
            error or f"Élément {selector!r} visible.",
            permission_level=BrowserPermissionLevel.AUTO_ALLOWED.value,
        )

    def _take_screenshot(self, params: dict) -> ConnectorResult:
        path = self._resolve_screenshot_path(params)
        ok, error = self._backend.take_screenshot(path, self._timeout)
        result = self._interaction_result(
            "take_screenshot",
            "",
            ok,
            error or f"Capture enregistrée : {path}",
            permission_level=BrowserPermissionLevel.AUTO_ALLOWED.value,
            screenshot_path=path if ok else "",
        )
        return result

    def _navigate_and_store(self, action: str, url: str) -> ConnectorResult:
        safe_url, url_error = self._validate_url(url)
        if safe_url is None:
            return self._error(action, url_error or "URL invalide.")

        snapshot, error = self._backend.navigate(safe_url, self._timeout)
        if snapshot is None:
            return self._error(action, error or "Navigation impossible.")
        return self._store_snapshot(action, snapshot)

    def _store_snapshot(self, action: str, snapshot: PageSnapshot) -> ConnectorResult:
        warnings = list(snapshot.warnings)
        if snapshot.content_type and "html" not in snapshot.content_type.lower():
            warnings.append(
                f"Type de contenu non HTML : {snapshot.content_type}. "
                "Extraction textuelle limitée.",
            )

        if snapshot.html:
            page_result = parse_html_page(
                snapshot.html,
                url=snapshot.url,
                warnings=tuple(warnings),
            )
            if snapshot.title:
                page_result = BrowserResult(
                    url=page_result.url,
                    page_title=snapshot.title,
                    page_text=snapshot.visible_text or page_result.page_text,
                    detected_links=page_result.detected_links,
                    detected_forms=page_result.detected_forms,
                    detected_buttons=page_result.detected_buttons,
                    status=page_result.status,
                    warnings=page_result.warnings,
                )
            elif snapshot.visible_text:
                page_result = BrowserResult(
                    url=page_result.url,
                    page_title=page_result.page_title,
                    page_text=snapshot.visible_text,
                    detected_links=page_result.detected_links,
                    detected_forms=page_result.detected_forms,
                    detected_buttons=page_result.detected_buttons,
                    status=page_result.status,
                    warnings=page_result.warnings,
                )
        else:
            page_result = BrowserResult(
                url=snapshot.url,
                page_title=snapshot.title,
                page_text=snapshot.visible_text,
                warnings=tuple(warnings),
            )

        self._session.current_url = snapshot.url
        self._session.last_result = page_result
        return self._success(action, page_result)

    def _interaction_result(
        self,
        action: str,
        selector: str,
        ok: bool,
        message: str,
        *,
        permission_level: str = BrowserPermissionLevel.CONFIRMATION_REQUIRED.value,
        screenshot_path: str = "",
    ) -> ConnectorResult:
        current_url, page_title = self._backend.get_page_context(self._timeout)
        if ok and current_url:
            self._session.current_url = current_url
        action_result = BrowserActionResult(
            action=action,
            selector=selector,
            status="ok" if ok else "error",
            permission_level=permission_level,
            executed=ok,
            confirmation_required=False,
            message=message if ok else (message or "Action échouée."),
            current_url=current_url,
            page_title=page_title,
            warnings=tuple(self._session.warnings),
            screenshot_path=screenshot_path,
        )
        if ok:
            self._refresh_session_from_backend()
        return ConnectorResult(
            success=ok,
            action=action,
            data=action_result.to_json(),
            error="" if ok else action_result.message,
            target_path=current_url,
        )

    def _action_blocked(
        self,
        action: str,
        params: dict,
        reason: str,
    ) -> ConnectorResult:
        selector = self._require_selector(params) or ""
        current_url, page_title = self._backend.get_page_context(self._timeout)
        action_result = BrowserActionResult(
            action=action,
            selector=selector,
            status="blocked",
            permission_level=BrowserPermissionLevel.BLOCKED.value,
            executed=False,
            confirmation_required=False,
            message=reason,
            current_url=current_url,
            page_title=page_title,
        )
        return ConnectorResult(
            success=False,
            action=action,
            data=action_result.to_json(),
            error=reason,
        )

    def _action_pending_confirmation(
        self,
        action: str,
        params: dict,
        reason: str,
    ) -> ConnectorResult:
        selector = self._require_selector(params) or ""
        current_url, page_title = self._backend.get_page_context(self._timeout)
        action_result = BrowserActionResult(
            action=action,
            selector=selector,
            status="pending_confirmation",
            permission_level=BrowserPermissionLevel.CONFIRMATION_REQUIRED.value,
            executed=False,
            confirmation_required=True,
            message=reason,
            current_url=current_url,
            page_title=page_title,
        )
        return ConnectorResult(
            success=False,
            action=action,
            data=action_result.to_json(),
            error=reason,
        )

    def _refresh_session_from_backend(self) -> None:
        snapshot, _ = self._backend.read_current(self._timeout)
        if snapshot is not None:
            self._session.current_url = snapshot.url
            if snapshot.html:
                self._session.last_result = parse_html_page(
                    snapshot.html,
                    url=snapshot.url,
                    warnings=snapshot.warnings,
                )

    def _resolve_screenshot_path(self, params: dict) -> str:
        custom = str(params.get("path", "")).strip()
        if custom:
            return custom
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return str(_SCREENSHOT_DIR / f"screenshot_{stamp}.png")

    def _require_selector(self, params: dict) -> str | None:
        selector = str(params.get("selector", "")).strip()
        return selector or None

    def _resolve_url(self, params: dict, *, allow_session: bool = False) -> str | None:
        raw = str(params.get("url", "")).strip()
        if raw:
            return raw
        if allow_session and self._session.current_url:
            return self._session.current_url
        return None

    def _validate_url(self, url: str) -> tuple[str | None, str | None]:
        candidate = url.strip()
        if not candidate:
            return None, "URL vide."
        if not _URL_PATTERN.match(candidate):
            return None, "Seules les URL http:// et https:// sont autorisées."
        scheme = candidate.split(":", 1)[0].lower()
        if scheme in _BLOCKED_SCHEMES:
            return None, f"Schéma URL bloqué : {scheme!r}."
        return candidate, None

    def _success(self, action: str, result: BrowserResult) -> ConnectorResult:
        return ConnectorResult(
            success=True,
            action=action,
            data=result.to_json(),
            target_path=result.url,
        )

    def _error(self, action: str, message: str) -> ConnectorResult:
        return ConnectorResult(success=False, action=action, error=message)

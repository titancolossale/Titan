# =====================================
# Titan Browser Backend
# =====================================

"""Browser backend abstraction — Playwright production path (Phase 13.2–13.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from tools.connectors.browser_session import BrowserSession


@dataclass(frozen=True)
class PageSnapshot:
    """Read-only page state returned by a browser backend."""

    url: str
    title: str
    html: str
    visible_text: str
    content_type: str = "text/html"
    warnings: tuple[str, ...] = ()


class BrowserBackend(Protocol):
    """Contract for browser engines used internally by BrowserConnector."""

    def start(self) -> tuple[bool, str]:
        """Start the backend session."""
        ...

    def stop(self) -> None:
        """Stop the backend and release resources."""
        ...

    @property
    def is_started(self) -> bool:
        """Return True when the backend session is active."""
        ...

    def navigate(self, url: str, timeout_seconds: float) -> tuple[PageSnapshot | None, str | None]:
        """Open *url* and return a page snapshot, or an error message."""
        ...

    def read_current(
        self,
        timeout_seconds: float,
    ) -> tuple[PageSnapshot | None, str | None]:
        """Read the current page without navigation."""
        ...

    def click_element(
        self,
        selector: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        """Click an element on the active page."""
        ...

    def type_text(
        self,
        selector: str,
        text: str,
        timeout_seconds: float,
        *,
        clear: bool = True,
    ) -> tuple[bool, str | None]:
        """Type text into an input on the active page."""
        ...

    def select_option(
        self,
        selector: str,
        value: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        """Select a dropdown option on the active page."""
        ...

    def scroll_page(
        self,
        timeout_seconds: float,
        *,
        direction: str = "down",
        pixels: int = 400,
    ) -> tuple[bool, str | None]:
        """Scroll the active page."""
        ...

    def go_back(self, timeout_seconds: float) -> tuple[bool, str | None]:
        """Navigate back in browser history."""
        ...

    def open_new_tab(self, timeout_seconds: float) -> tuple[str | None, str | None]:
        """Open a new tab and return its page id."""
        ...

    def close_tab(
        self,
        timeout_seconds: float,
        page_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Close a tab by id or the active tab."""
        ...

    def wait_for_element(
        self,
        selector: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        """Wait for an element to become visible."""
        ...

    def take_screenshot(
        self,
        path: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        """Capture a screenshot of the active page."""
        ...

    def get_page_context(self, timeout_seconds: float) -> tuple[str, str]:
        """Return current URL and page title."""
        ...


class PlaywrightBrowserBackend:
    """Production browser backend backed by Playwright Chromium."""

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_seconds: float = 30.0,
        session: BrowserSession | None = None,
    ) -> None:
        self._session = session or BrowserSession(
            headless=headless,
            timeout_seconds=timeout_seconds,
        )
        self._started = False

    @property
    def session(self) -> BrowserSession:
        """Expose the underlying Playwright session for health checks."""
        return self._session

    @property
    def is_started(self) -> bool:
        return self._started and self._session.is_launched

    def start(self) -> tuple[bool, str]:
        if self._started and self._session.is_launched:
            return True, "Session navigateur déjà active."
        launched, message = self._session.launch()
        if launched:
            self._started = True
        return launched, message

    def stop(self) -> None:
        self._session.close()
        self._started = False

    def navigate(
        self,
        url: str,
        timeout_seconds: float,
    ) -> tuple[PageSnapshot | None, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return None, start_error

        ok, nav_error = self._session.open_url(url)
        if not ok:
            return None, nav_error

        return self._capture_snapshot(timeout_seconds)

    def read_current(
        self,
        timeout_seconds: float,
    ) -> tuple[PageSnapshot | None, str | None]:
        if not self.is_started:
            return None, "Session navigateur non démarrée."

        self._session.timeout_seconds = timeout_seconds
        ok, load_error = self._session.wait_for_page_load()
        if not ok and load_error:
            return None, load_error
        return self._capture_snapshot(timeout_seconds)

    def _capture_snapshot(
        self,
        timeout_seconds: float,
    ) -> tuple[PageSnapshot | None, str | None]:
        self._session.timeout_seconds = timeout_seconds
        current_url = self._session.get_current_url()
        if not current_url:
            return None, "Aucune page active."

        return (
            PageSnapshot(
                url=current_url,
                title=self._session.get_page_title(),
                html=self._session.get_page_html(),
                visible_text=self._session.get_visible_text(),
            ),
            None,
        )

    def click_element(
        self,
        selector: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return False, start_error
        return self._session.click_element(selector)

    def type_text(
        self,
        selector: str,
        text: str,
        timeout_seconds: float,
        *,
        clear: bool = True,
    ) -> tuple[bool, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return False, start_error
        return self._session.type_text(selector, text, clear=clear)

    def select_option(
        self,
        selector: str,
        value: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return False, start_error
        return self._session.select_option(selector, value)

    def scroll_page(
        self,
        timeout_seconds: float,
        *,
        direction: str = "down",
        pixels: int = 400,
    ) -> tuple[bool, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return False, start_error
        return self._session.scroll_page(direction=direction, pixels=pixels)

    def go_back(self, timeout_seconds: float) -> tuple[bool, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return False, start_error
        return self._session.go_back()

    def open_new_tab(self, timeout_seconds: float) -> tuple[str | None, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return None, start_error
        return self._session.new_page()

    def close_tab(
        self,
        timeout_seconds: float,
        page_id: str | None = None,
    ) -> tuple[bool, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return False, start_error
        return self._session.close_tab(page_id)

    def wait_for_element(
        self,
        selector: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return False, start_error
        return self._session.wait_for_element(selector)

    def take_screenshot(
        self,
        path: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        self._session.timeout_seconds = timeout_seconds
        started, start_error = self.start()
        if not started:
            return False, start_error
        return self._session.take_screenshot(path)

    def get_page_context(self, timeout_seconds: float) -> tuple[str, str]:
        self._session.timeout_seconds = timeout_seconds
        if not self.is_started:
            return "", ""
        return self._session.get_current_url() or "", self._session.get_page_title()


class FetchBrowserBackend:
    """Test-oriented backend that simulates page loads via an injectable fetcher.

    Preserves Phase 13.1 test hooks without requiring a live Playwright browser.
    """

    def __init__(
        self,
        fetcher: Callable[[str, float], tuple[str, str, tuple[str, ...]]],
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._fetcher = fetcher
        self._timeout_seconds = timeout_seconds
        self._started = False
        self._current_url: str | None = None
        self._last_html: str = ""
        self._last_content_type: str = ""
        self._last_warnings: tuple[str, ...] = ()
        self._interaction_log: list[tuple[str, dict]] = []

    @property
    def interaction_log(self) -> list[tuple[str, dict]]:
        """Return recorded interaction calls (test helper)."""
        return list(self._interaction_log)

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self) -> tuple[bool, str]:
        if self._started:
            return True, "Session navigateur déjà active."
        self._started = True
        return True, "Session navigateur démarrée."

    def stop(self) -> None:
        self._started = False
        self._current_url = None
        self._last_html = ""
        self._last_content_type = ""
        self._last_warnings = ()

    def navigate(
        self,
        url: str,
        timeout_seconds: float,
    ) -> tuple[PageSnapshot | None, str | None]:
        started, start_error = self.start()
        if not started:
            return None, start_error

        try:
            html, content_type, warnings = self._fetcher(url, timeout_seconds)
        except Exception as exc:
            return None, f"Erreur réseau : {exc}"

        self._current_url = url
        self._last_html = html
        self._last_content_type = content_type
        self._last_warnings = warnings
        return self._build_snapshot(url, html, content_type, warnings), None

    def read_current(
        self,
        timeout_seconds: float,
    ) -> tuple[PageSnapshot | None, str | None]:
        if not self._started or not self._current_url:
            return None, "Aucune page active."
        return (
            self._build_snapshot(
                self._current_url,
                self._last_html,
                self._last_content_type,
                self._last_warnings,
            ),
            None,
        )

    def click_element(
        self,
        selector: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        self._interaction_log.append(("click_element", {"selector": selector}))
        if not self._started:
            return False, "Session navigateur non démarrée."
        return True, None

    def type_text(
        self,
        selector: str,
        text: str,
        timeout_seconds: float,
        *,
        clear: bool = True,
    ) -> tuple[bool, str | None]:
        self._interaction_log.append(
            ("type_text", {"selector": selector, "text": text, "clear": clear}),
        )
        if not self._started:
            return False, "Session navigateur non démarrée."
        return True, None

    def select_option(
        self,
        selector: str,
        value: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        self._interaction_log.append(
            ("select_option", {"selector": selector, "value": value}),
        )
        if not self._started:
            return False, "Session navigateur non démarrée."
        return True, None

    def scroll_page(
        self,
        timeout_seconds: float,
        *,
        direction: str = "down",
        pixels: int = 400,
    ) -> tuple[bool, str | None]:
        self._interaction_log.append(
            ("scroll_page", {"direction": direction, "pixels": pixels}),
        )
        if not self._started:
            return False, "Session navigateur non démarrée."
        return True, None

    def go_back(self, timeout_seconds: float) -> tuple[bool, str | None]:
        self._interaction_log.append(("go_back", {}))
        if not self._started:
            return False, "Session navigateur non démarrée."
        return True, None

    def open_new_tab(self, timeout_seconds: float) -> tuple[str | None, str | None]:
        self._interaction_log.append(("open_new_tab", {}))
        if not self._started:
            return None, "Session navigateur non démarrée."
        return "mock-tab-2", None

    def close_tab(
        self,
        timeout_seconds: float,
        page_id: str | None = None,
    ) -> tuple[bool, str | None]:
        self._interaction_log.append(("close_tab", {"page_id": page_id}))
        if not self._started:
            return False, "Session navigateur non démarrée."
        return True, None

    def wait_for_element(
        self,
        selector: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        self._interaction_log.append(("wait_for_element", {"selector": selector}))
        if not self._started:
            return False, "Session navigateur non démarrée."
        return True, None

    def take_screenshot(
        self,
        path: str,
        timeout_seconds: float,
    ) -> tuple[bool, str | None]:
        self._interaction_log.append(("take_screenshot", {"path": path}))
        if not self._started:
            return False, "Session navigateur non démarrée."
        return True, None

    def get_page_context(self, timeout_seconds: float) -> tuple[str, str]:
        return self._current_url or "", "Session Test"

    def _build_snapshot(
        self,
        url: str,
        html: str,
        content_type: str,
        warnings: tuple[str, ...],
    ) -> PageSnapshot:
        from tools.connectors.browser_parser import parse_html_page

        parsed = parse_html_page(html, url=url, warnings=warnings)
        return PageSnapshot(
            url=url,
            title=parsed.page_title,
            html=html,
            visible_text=parsed.page_text,
            content_type=content_type,
            warnings=warnings,
        )

# =====================================
# Titan Browser Session
# =====================================

"""Playwright-backed browser session for long-term autonomous interaction (Phase 13.2–13.3)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserSession:
    """Manage Playwright browser lifecycle, pages, and read-only page inspection.

    Designed for future expansion: multiple tabs, cookies, authentication,
    downloads, and uploads. Phase 13.3 adds controlled interaction (click, type, scroll,
    tabs, wait, screenshot) on top of read-only inspection from 13.2.
    """

    headless: bool = True
    timeout_seconds: float = 30.0
    _playwright: Any | None = field(default=None, repr=False)
    _browser: Any | None = field(default=None, repr=False)
    _context: Any | None = field(default=None, repr=False)
    _pages: dict[str, Any] = field(default_factory=dict, repr=False)
    _active_page_id: str | None = field(default=None, repr=False)
    _launched: bool = field(default=False, repr=False)

    @property
    def is_launched(self) -> bool:
        """Return True when the Playwright browser is running."""
        return self._launched

    @property
    def active_page_id(self) -> str | None:
        """Return the identifier of the currently active tab."""
        return self._active_page_id

    @property
    def page_count(self) -> int:
        """Return the number of open pages in this session."""
        return len(self._pages)

    def launch(self) -> tuple[bool, str]:
        """Launch the Playwright browser and create a default browsing context."""
        if self._launched:
            return True, "Navigateur Playwright déjà lancé."

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return (
                False,
                "Playwright n'est pas installé. Exécutez : pip install playwright "
                "&& playwright install chromium",
            )

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context()
            self._launched = True
            return True, "Navigateur Playwright lancé."
        except Exception as exc:
            self._cleanup_playwright()
            return False, f"Impossible de lancer Playwright : {exc}"

    def close(self) -> None:
        """Close all pages, context, browser, and stop Playwright."""
        for page in self._pages.values():
            try:
                page.close()
            except Exception:
                pass
        self._pages.clear()
        self._active_page_id = None

        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        self._cleanup_playwright()
        self._launched = False

    def new_page(self, page_id: str | None = None) -> tuple[str | None, str | None]:
        """Create a new browser tab and make it active.

        Returns:
            Tuple of (page_id, error_message). page_id is None on failure.
        """
        if not self._launched or self._context is None:
            return None, "Session navigateur non démarrée."

        try:
            page = self._context.new_page()
            resolved_id = page_id or str(uuid.uuid4())
            self._pages[resolved_id] = page
            self._active_page_id = resolved_id
            page.set_default_timeout(int(self.timeout_seconds * 1000))
            return resolved_id, None
        except Exception as exc:
            return None, f"Impossible de créer une page : {exc}"

    def _active_page(self) -> Any | None:
        if self._active_page_id is None:
            return None
        return self._pages.get(self._active_page_id)

    def open_url(self, url: str) -> tuple[bool, str | None]:
        """Navigate the active page to *url* and wait for load."""
        page = self._active_page()
        if page is None:
            page_id, error = self.new_page()
            if page_id is None:
                return False, error
            page = self._active_page()
        assert page is not None

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(self.timeout_seconds * 1000),
            )
            self.wait_for_page_load()
            return True, None
        except Exception as exc:
            return False, f"Navigation impossible : {exc}"

    def wait_for_page_load(self) -> tuple[bool, str | None]:
        """Wait for the active page to reach a stable loaded state."""
        page = self._active_page()
        if page is None:
            return False, "Aucune page active."

        try:
            page.wait_for_load_state(
                "load",
                timeout=int(self.timeout_seconds * 1000),
            )
            return True, None
        except Exception as exc:
            return False, f"Chargement de page interrompu : {exc}"

    def get_current_url(self) -> str | None:
        """Return the active page URL, or None when no page is open."""
        page = self._active_page()
        if page is None:
            return None
        try:
            return page.url
        except Exception:
            return None

    def get_page_title(self) -> str:
        """Return the active page document title."""
        page = self._active_page()
        if page is None:
            return ""
        try:
            return page.title()
        except Exception:
            return ""

    def get_visible_text(self) -> str:
        """Return human-visible text from the active page body."""
        page = self._active_page()
        if page is None:
            return ""
        try:
            return page.locator("body").inner_text(timeout=int(self.timeout_seconds * 1000))
        except Exception:
            return ""

    def get_page_html(self) -> str:
        """Return full HTML content of the active page."""
        page = self._active_page()
        if page is None:
            return ""
        try:
            return page.content()
        except Exception:
            return ""

    def click_element(self, selector: str) -> tuple[bool, str | None]:
        """Click the element matching *selector* on the active page."""
        page = self._active_page()
        if page is None:
            return False, "Aucune page active."
        try:
            page.locator(selector).click(timeout=int(self.timeout_seconds * 1000))
            return True, None
        except Exception as exc:
            return False, f"Clic impossible : {exc}"

    def type_text(self, selector: str, text: str, *, clear: bool = True) -> tuple[bool, str | None]:
        """Type *text* into the element matching *selector*."""
        page = self._active_page()
        if page is None:
            return False, "Aucune page active."
        try:
            locator = page.locator(selector)
            if clear:
                locator.fill(text, timeout=int(self.timeout_seconds * 1000))
            else:
                locator.type(text, timeout=int(self.timeout_seconds * 1000))
            return True, None
        except Exception as exc:
            return False, f"Saisie impossible : {exc}"

    def select_option(
        self,
        selector: str,
        value: str,
    ) -> tuple[bool, str | None]:
        """Select *value* in a dropdown matching *selector*."""
        page = self._active_page()
        if page is None:
            return False, "Aucune page active."
        try:
            page.locator(selector).select_option(
                value,
                timeout=int(self.timeout_seconds * 1000),
            )
            return True, None
        except Exception as exc:
            return False, f"Sélection impossible : {exc}"

    def scroll_page(
        self,
        *,
        direction: str = "down",
        pixels: int = 400,
    ) -> tuple[bool, str | None]:
        """Scroll the active page in *direction* by *pixels*."""
        page = self._active_page()
        if page is None:
            return False, "Aucune page active."
        delta_y = pixels if direction.lower() in {"down", "bottom"} else -pixels
        try:
            page.evaluate(f"window.scrollBy(0, {delta_y})")
            return True, None
        except Exception as exc:
            return False, f"Défilement impossible : {exc}"

    def go_back(self) -> tuple[bool, str | None]:
        """Navigate back in the active page history."""
        page = self._active_page()
        if page is None:
            return False, "Aucune page active."
        try:
            page.go_back(timeout=int(self.timeout_seconds * 1000))
            self.wait_for_page_load()
            return True, None
        except Exception as exc:
            return False, f"Retour arrière impossible : {exc}"

    def close_tab(self, page_id: str | None = None) -> tuple[bool, str | None]:
        """Close a tab by *page_id* or the active tab."""
        target_id = page_id or self._active_page_id
        if target_id is None or target_id not in self._pages:
            return False, "Onglet introuvable."

        page = self._pages.pop(target_id)
        try:
            page.close()
        except Exception:
            pass

        if self._active_page_id == target_id:
            remaining = next(iter(self._pages), None)
            self._active_page_id = remaining
        return True, None

    def switch_tab(self, page_id: str) -> tuple[bool, str | None]:
        """Make *page_id* the active tab."""
        if page_id not in self._pages:
            return False, f"Onglet introuvable : {page_id!r}."
        self._active_page_id = page_id
        return True, None

    def wait_for_element(self, selector: str) -> tuple[bool, str | None]:
        """Wait until *selector* is visible on the active page."""
        page = self._active_page()
        if page is None:
            return False, "Aucune page active."
        try:
            page.locator(selector).wait_for(
                state="visible",
                timeout=int(self.timeout_seconds * 1000),
            )
            return True, None
        except Exception as exc:
            return False, f"Élément introuvable : {exc}"

    def take_screenshot(self, path: str) -> tuple[bool, str | None]:
        """Capture a screenshot of the active page to *path*."""
        page = self._active_page()
        if page is None:
            return False, "Aucune page active."
        try:
            page.screenshot(path=path, full_page=False)
            return True, None
        except Exception as exc:
            return False, f"Capture d'écran impossible : {exc}"

    def _cleanup_playwright(self) -> None:
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

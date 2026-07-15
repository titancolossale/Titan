# =====================================
# Titan Browser HTML Parser
# =====================================

"""HTML parsing helpers for read-only text and link extraction."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

from core.tools.browser.models import ExtractedLink


class _ReadOnlyHTMLParser(HTMLParser):
    """Extract visible text and links while ignoring script, style, and noscript."""

    _SKIP_TAGS = frozenset({"script", "style", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[ExtractedLink] = []
        self.language: str = ""
        self._skip_depth = 0
        self._in_title = False
        self._current_link_href: str | None = None
        self._current_link_text: list[str] = []
        self._pending_space = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attr_map = {key: (value or "") for key, value in attrs}

        if lowered in self._SKIP_TAGS:
            self._skip_depth += 1
            return

        if lowered == "html" and not self.language:
            lang = attr_map.get("lang", "").strip()
            if lang:
                self.language = lang.split("-")[0].lower()

        if lowered == "title":
            self._in_title = True
            return

        if lowered == "a":
            self._flush_link()
            self._current_link_href = attr_map.get("href", "").strip()
            self._current_link_text = []
            return

        if lowered in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._pending_space = True

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return

        if lowered == "title":
            self._in_title = False
            return

        if lowered == "a":
            self._flush_link()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return

        text = data.strip()
        if not text:
            return

        if self._in_title:
            self.title_parts.append(text)
            return

        if self._current_link_href is not None:
            self._current_link_text.append(text)
            return

        if self._pending_space and self.text_parts:
            self.text_parts.append(" ")
            self._pending_space = False
        self.text_parts.append(text)

    def _flush_link(self) -> None:
        if self._current_link_href is None:
            return
        link_text = " ".join(self._current_link_text).strip()
        if self._current_link_href:
            self.links.append(
                ExtractedLink(href=self._current_link_href, text=link_text),
            )
        self._current_link_href = None
        self._current_link_text = []

    def finalize(self) -> None:
        """Flush any open elements at end of document."""
        self._flush_link()


def extract_title(html: str) -> str:
    """Extract the document title from HTML."""
    parser = _ReadOnlyHTMLParser()
    parser.feed(html)
    parser.finalize()
    return " ".join(parser.title_parts).strip()


def extract_language(html: str, content_language: str = "") -> str:
    """Detect page language from Content-Language header or html lang attribute."""
    header_lang = content_language.strip().split(",")[0].split(";")[0].strip()
    if header_lang:
        return header_lang.split("-")[0].lower()

    parser = _ReadOnlyHTMLParser()
    parser.feed(html)
    parser.finalize()
    return parser.language


def extract_text(html: str) -> str:
    """Extract visible text from HTML, ignoring script, style, and noscript."""
    parser = _ReadOnlyHTMLParser()
    parser.feed(html)
    parser.finalize()

    page_text = " ".join(parser.text_parts)
    while "  " in page_text:
        page_text = page_text.replace("  ", " ")
    return page_text.strip()


def extract_links(html: str, *, base_url: str) -> list[ExtractedLink]:
    """Extract hyperlinks from HTML with absolute href values."""
    parser = _ReadOnlyHTMLParser()
    parser.feed(html)
    parser.finalize()

    resolved: list[ExtractedLink] = []
    for link in parser.links:
        if not link.href or link.href.startswith("#"):
            continue
        if link.href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        href = urljoin(base_url, link.href)
        resolved.append(ExtractedLink(href=href, text=link.text))
    return resolved

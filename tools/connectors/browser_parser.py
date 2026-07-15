# =====================================
# Titan Browser HTML Parser
# =====================================

"""HTML inspection helpers for the Browser connector (Phase 13.1)."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

from tools.connectors.browser_models import (
    BrowserResult,
    DetectedButton,
    DetectedForm,
    DetectedLink,
)


class _PageHTMLParser(HTMLParser):
    """Extract visible text and interactive elements without executing scripts."""

    _SKIP_TAGS = frozenset({"script", "style", "noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[DetectedLink] = []
        self.forms: list[DetectedForm] = []
        self.buttons: list[DetectedButton] = []
        self._skip_depth = 0
        self._in_title = False
        self._current_form: dict[str, object] | None = None
        self._current_link_href: str | None = None
        self._current_link_text: list[str] = []
        self._current_button: dict[str, str] | None = None
        self._pending_space = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attr_map = {key: (value or "") for key, value in attrs}

        if lowered in self._SKIP_TAGS:
            self._skip_depth += 1
            return

        if lowered == "title":
            self._in_title = True
            return

        if lowered == "a":
            self._flush_link_text()
            self._current_link_href = attr_map.get("href", "").strip()
            self._current_link_text = []
            return

        if lowered == "button":
            self._flush_button()
            self._current_button = {
                "label": attr_map.get("value", "").strip() or attr_map.get("aria-label", "").strip(),
                "button_type": attr_map.get("type", "button").lower(),
                "name": attr_map.get("name", "").strip(),
            }
            return

        if lowered == "form":
            self._close_form()
            fields: list[str] = []
            self._current_form = {
                "action": attr_map.get("action", "").strip(),
                "method": (attr_map.get("method", "get") or "get").lower(),
                "fields": fields,
            }
            return

        if self._current_form is not None and lowered in {"input", "textarea", "select"}:
            name = attr_map.get("name", "").strip() or attr_map.get("id", "").strip()
            if name:
                fields = self._current_form["fields"]
                assert isinstance(fields, list)
                fields.append(name)

        if lowered == "input":
            input_type = (attr_map.get("type", "text") or "text").lower()
            if input_type in {"submit", "button", "reset"}:
                label = attr_map.get("value", "").strip() or input_type
                self.buttons.append(
                    DetectedButton(
                        label=label,
                        button_type=input_type,
                        name=attr_map.get("name", "").strip(),
                    ),
                )

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
            self._flush_link_text()
            return

        if lowered == "button":
            self._flush_button()
            return

        if lowered == "form":
            self._close_form()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._current_button is not None:
            if not self._current_button.get("label"):
                self._current_button["label"] = text
            else:
                self._current_button["label"] = f"{self._current_button['label']} {text}".strip()
            return
        if self._current_link_href is not None:
            self._current_link_text.append(text)
            return
        if self._pending_space and self.text_parts:
            self.text_parts.append(" ")
            self._pending_space = False
        self.text_parts.append(text)

    def _flush_link_text(self) -> None:
        if self._current_link_href is None:
            return
        link_text = " ".join(self._current_link_text).strip()
        if self._current_link_href:
            self.links.append(
                DetectedLink(href=self._current_link_href, text=link_text),
            )
        self._current_link_href = None
        self._current_link_text = []

    def _close_form(self) -> None:
        if self._current_form is None:
            return
        fields = self._current_form["fields"]
        assert isinstance(fields, list)
        self.forms.append(
            DetectedForm(
                action=str(self._current_form.get("action", "")),
                method=str(self._current_form.get("method", "get")),
                fields=tuple(fields),
            ),
        )
        self._current_form = None

    def _flush_button(self) -> None:
        if self._current_button is None:
            return
        self.buttons.append(
            DetectedButton(
                label=self._current_button.get("label", ""),
                button_type=self._current_button.get("button_type", "button"),
                name=self._current_button.get("name", ""),
            ),
        )
        self._current_button = None

    def finalize(self) -> None:
        """Flush any open elements at end of document."""
        self._flush_link_text()
        self._flush_button()
        self._close_form()


def parse_html_page(
    html: str,
    *,
    url: str,
    warnings: tuple[str, ...] = (),
) -> BrowserResult:
    """Parse HTML and return structured page information."""
    parser = _PageHTMLParser()
    parser.feed(html)
    parser.finalize()

    resolved_links: list[DetectedLink] = []
    for link in parser.links:
        href = urljoin(url, link.href) if link.href else url
        resolved_links.append(DetectedLink(href=href, text=link.text))

    resolved_forms: list[DetectedForm] = []
    for form in parser.forms:
        action = urljoin(url, form.action) if form.action else url
        resolved_forms.append(
            DetectedForm(action=action, method=form.method, fields=form.fields),
        )

    page_text = " ".join(parser.text_parts)
    while "  " in page_text:
        page_text = page_text.replace("  ", " ")

    return BrowserResult(
        url=url,
        page_title=" ".join(parser.title_parts).strip(),
        page_text=page_text.strip(),
        detected_links=tuple(resolved_links),
        detected_forms=tuple(resolved_forms),
        detected_buttons=tuple(parser.buttons),
        status="ok",
        warnings=warnings,
    )

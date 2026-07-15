# =====================================
# Titan Browser Models
# =====================================

"""Structured page and interaction results for the Browser connector (Phase 13.1–13.3)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DetectedLink:
    """A hyperlink found on the page."""

    href: str
    text: str


@dataclass(frozen=True)
class DetectedForm:
    """A form element found on the page (inspection only — never submitted in V1)."""

    action: str
    method: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class DetectedButton:
    """A button or submit input found on the page (inspection only — never clicked in V1)."""

    label: str
    button_type: str
    name: str = ""


@dataclass(frozen=True)
class BrowserResult:
    """Structured outcome from a Browser connector read operation."""

    url: str
    page_title: str
    page_text: str
    detected_links: tuple[DetectedLink, ...] = ()
    detected_forms: tuple[DetectedForm, ...] = ()
    detected_buttons: tuple[DetectedButton, ...] = ()
    status: str = "ok"
    warnings: tuple[str, ...] = ()

    def to_json(self) -> str:
        """Serialize for ToolResult.data and logging."""
        payload = asdict(self)
        payload["detected_links"] = [asdict(link) for link in self.detected_links]
        payload["detected_forms"] = [asdict(form) for form in self.detected_forms]
        payload["detected_buttons"] = [asdict(btn) for btn in self.detected_buttons]
        payload["warnings"] = list(self.warnings)
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def format_summary(self) -> str:
        """Return a concise French summary for tool output."""
        lines = [
            f"URL : {self.url}",
            f"Titre : {self.page_title or '(sans titre)'}",
            f"Statut : {self.status}",
            f"Liens détectés : {len(self.detected_links)}",
            f"Formulaires détectés : {len(self.detected_forms)}",
            f"Boutons détectés : {len(self.detected_buttons)}",
        ]
        if self.warnings:
            lines.append(f"Avertissements : {', '.join(self.warnings)}")
        preview = self.page_text[:500].strip()
        if preview:
            lines.append("")
            lines.append("Texte visible (aperçu) :")
            lines.append(preview)
            if len(self.page_text) > 500:
                lines.append("…")
        return "\n".join(lines)


@dataclass(frozen=True)
class BrowserActionResult:
    """Structured outcome from a Browser connector interaction (Phase 13.3)."""

    action: str
    selector: str
    status: str
    permission_level: str
    executed: bool
    confirmation_required: bool
    message: str
    current_url: str = ""
    page_title: str = ""
    warnings: tuple[str, ...] = ()
    screenshot_path: str = ""

    def to_json(self) -> str:
        """Serialize for ToolResult.data and logging."""
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def format_summary(self) -> str:
        """Return a concise French summary for tool output."""
        lines = [
            f"Action : {self.action}",
            f"Sélecteur : {self.selector or '(aucun)'}",
            f"Statut : {self.status}",
            f"Permission : {self.permission_level}",
            f"Exécutée : {'oui' if self.executed else 'non'}",
        ]
        if self.confirmation_required:
            lines.append("Confirmation requise : oui")
        if self.current_url:
            lines.append(f"URL : {self.current_url}")
        if self.page_title:
            lines.append(f"Titre : {self.page_title}")
        if self.screenshot_path:
            lines.append(f"Capture : {self.screenshot_path}")
        if self.message:
            lines.append(f"Message : {self.message}")
        if self.warnings:
            lines.append(f"Avertissements : {', '.join(self.warnings)}")
        return "\n".join(lines)


@dataclass(frozen=True)
class BrowserSource:
    """One web source consulted during Browser Intelligence research (Phase 23.0)."""

    title: str
    url: str
    excerpt: str
    index: int = 1

    def citation_label(self) -> str:
        """Return a user-facing citation label — title only, no URL path internals."""
        label = (self.title or "Source").strip()
        if len(label) > 64:
            label = label[:61] + "…"
        return label

    def to_dict(self) -> dict[str, str | int]:
        """Serialize for ToolResult metadata and API payloads."""
        return {
            "index": self.index,
            "title": self.citation_label(),
            "url": self.url,
            "excerpt": self.excerpt[:240].strip(),
        }


@dataclass(frozen=True)
class BrowserResearchResult:
    """Structured multi-source browser research outcome (Phase 23.0)."""

    query: str
    sources: tuple[BrowserSource, ...] = ()
    status: str = "ok"
    warnings: tuple[str, ...] = ()

    def format_for_tool(self) -> str:
        """Return French research summary with numbered citations for Brain synthesis."""
        lines = [f"Exploration web — requête : « {self.query} »"]
        if not self.sources:
            lines.append("Aucune source consultée.")
            if self.warnings:
                lines.append(f"Avertissements : {', '.join(self.warnings)}")
            return "\n".join(lines)

        lines.append("")
        lines.append("Sources consultées :")
        for source in self.sources:
            lines.append(f"[{source.index}] {source.citation_label()}")
            if source.excerpt:
                preview = source.excerpt[:400].strip()
                lines.append(f"    Extrait : {preview}")
                if len(source.excerpt) > 400:
                    lines.append("    …")
        lines.append("")
        lines.append(self.citations_block())
        if self.warnings:
            lines.append("")
            lines.append(f"Avertissements : {', '.join(self.warnings)}")
        return "\n".join(lines)

    def citations_block(self) -> str:
        """Return a compact citation list for prompt injection."""
        if not self.sources:
            return "Références : aucune."
        refs = [f"[{s.index}] {s.citation_label()}" for s in self.sources]
        return "Références : " + " · ".join(refs)

    def to_json(self) -> str:
        """Serialize for ToolResult.data."""
        payload = {
            "query": self.query,
            "status": self.status,
            "sources": [source.to_dict() for source in self.sources],
            "warnings": list(self.warnings),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


@dataclass
class BrowserSessionState:
    """In-memory connector session tracking for multi-step navigation.

    Tracks cached read results and the active URL. The Playwright ``BrowserSession``
    object lives inside ``PlaywrightBrowserBackend`` and is not exposed to callers.
    """

    started: bool = False
    current_url: str | None = None
    last_result: BrowserResult | None = None
    warnings: list[str] = field(default_factory=list)

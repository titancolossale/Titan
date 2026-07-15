# =====================================
# Titan Browser Tool Models
# =====================================

"""Structured data models for read-only browser operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedLink:
    """Hyperlink extracted from an HTML page."""

    href: str
    text: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable representation."""
        return {"href": self.href, "text": self.text}


@dataclass(frozen=True)
class PageMetadata:
    """HTTP and document metadata for a fetched page."""

    title: str
    url: str
    status_code: int
    content_type: str
    language: str
    response_size: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "title": self.title,
            "url": self.url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "language": self.language,
            "response_size": self.response_size,
        }


@dataclass(frozen=True)
class PageResponse:
    """Raw HTTP response returned by the browser client."""

    url: str
    status_code: int
    content_type: str
    language: str
    response_size: int
    html: str
    title: str

    def to_metadata(self) -> PageMetadata:
        """Return page metadata without the HTML body."""
        return PageMetadata(
            title=self.title,
            url=self.url,
            status_code=self.status_code,
            content_type=self.content_type,
            language=self.language,
            response_size=self.response_size,
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "url": self.url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "language": self.language,
            "response_size": self.response_size,
            "html": self.html,
            "title": self.title,
        }

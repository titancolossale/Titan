# =====================================
# Titan GitHub Tool Models
# =====================================

"""Structured data models for read-only GitHub operations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RepositorySummary:
    """Lightweight repository listing entry."""

    full_name: str
    name: str
    owner: str
    private: bool
    description: str
    default_branch: str
    html_url: str
    language: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "full_name": self.full_name,
            "name": self.name,
            "owner": self.owner,
            "private": self.private,
            "description": self.description,
            "default_branch": self.default_branch,
            "html_url": self.html_url,
            "language": self.language,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RepositoryMetadata:
    """Detailed repository metadata."""

    full_name: str
    name: str
    owner: str
    private: bool
    description: str
    default_branch: str
    html_url: str
    clone_url: str
    language: str
    topics: tuple[str, ...]
    stars: int
    forks: int
    open_issues: int
    created_at: str
    updated_at: str
    pushed_at: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "full_name": self.full_name,
            "name": self.name,
            "owner": self.owner,
            "private": self.private,
            "description": self.description,
            "default_branch": self.default_branch,
            "html_url": self.html_url,
            "clone_url": self.clone_url,
            "language": self.language,
            "topics": list(self.topics),
            "stars": self.stars,
            "forks": self.forks,
            "open_issues": self.open_issues,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "pushed_at": self.pushed_at,
        }


@dataclass(frozen=True)
class BranchInfo:
    """Branch listing entry."""

    name: str
    sha: str
    protected: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "name": self.name,
            "sha": self.sha,
            "protected": self.protected,
        }


@dataclass(frozen=True)
class CommitInfo:
    """Commit history entry."""

    sha: str
    message: str
    author_name: str
    author_email: str
    author_date: str
    html_url: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "sha": self.sha,
            "message": self.message,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "author_date": self.author_date,
            "html_url": self.html_url,
        }


@dataclass(frozen=True)
class TreeEntry:
    """Single entry in a repository tree."""

    path: str
    type: str
    sha: str
    size: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        payload: dict[str, object] = {
            "path": self.path,
            "type": self.type,
            "sha": self.sha,
        }
        if self.size is not None:
            payload["size"] = self.size
        return payload


@dataclass(frozen=True)
class FileContent:
    """Decoded file content from a repository."""

    path: str
    sha: str
    size: int
    encoding: str
    content: str
    html_url: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "path": self.path,
            "sha": self.sha,
            "size": self.size,
            "encoding": self.encoding,
            "content": self.content,
            "html_url": self.html_url,
        }


@dataclass(frozen=True)
class SearchMatch:
    """Code search match within a repository."""

    path: str
    name: str
    sha: str
    html_url: str
    repository: str
    score: float
    text_matches: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "path": self.path,
            "name": self.name,
            "sha": self.sha,
            "html_url": self.html_url,
            "repository": self.repository,
            "score": self.score,
            "text_matches": list(self.text_matches),
        }

# =====================================
# Titan File System Provider
# =====================================

"""Local filesystem provider — first local capability backend (P10B-501–P10B-504)."""

from __future__ import annotations

import fnmatch
import os
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from tools.path_guard import PathGuardError, resolve_allowed_path
from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.providers.base_provider import BaseProvider
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_health_resolver import resolve_provider_health
from tools.tool_enums import ExecutionMode, RiskLevel, ToolHealthState

_FILE_SYSTEM_VERSION = ProviderVersionInfo(
    provider_id="file_system",
    version="1.0.0",
    min_runtime_version="0.10.0",
    api_version=None,
    compatible_modes=frozenset({
        ExecutionMode.LIVE,
        ExecutionMode.PAPER,
        ExecutionMode.MOCK,
        ExecutionMode.SIMULATION,
    }),
)

_WRITE_BLOCKED_MODES = frozenset({
    ExecutionMode.MOCK,
    ExecutionMode.SIMULATION,
    ExecutionMode.PAPER,
})

_READ_ACTIONS = frozenset({
    "read_file",
    "list_directory",
    "file_exists",
    "search_files",
    "get_metadata",
})

_WRITE_ACTIONS = frozenset({"write_file"})


@dataclass(frozen=True)
class FileMetadata:
    """Structured metadata for a filesystem path."""

    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size_bytes: int = 0
    modified_at: float | None = None

    def to_dict(self) -> dict:
        """Serialize for tool and decision metadata."""
        return {
            "path": self.path,
            "exists": self.exists,
            "is_file": self.is_file,
            "is_dir": self.is_dir,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
        }


@dataclass
class FileSystemResponse:
    """Structured filesystem operation response."""

    operation: str
    success: bool = True
    data: object = None
    error: str = ""
    provider: str = "file_system"
    target_path: str = ""
    simulated: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    confirmation_required: bool = False

    def format_for_agent(self) -> str:
        """Format response for agent and prompt consumption."""
        if not self.success:
            return f"Opération fichier échouée ({self.operation}) : {self.error}"
        if self.simulated:
            return f"[simulation] {self.operation} → {self.target_path} : {self.data}"
        if isinstance(self.data, str):
            return self.data
        if isinstance(self.data, dict):
            return str(self.data)
        if isinstance(self.data, list):
            return "\n".join(str(item) for item in self.data)
        return str(self.data) if self.data is not None else f"{self.operation} réussi."


class FileSystemProvider(BaseProvider):
    """Contract for local filesystem backends."""

    @property
    def provider_id(self) -> str:
        return "file_system"

    def capabilities(self) -> frozenset[str]:
        return frozenset({"file_system"})

    def supported_actions(self) -> frozenset[str]:
        return frozenset({
            "read_file",
            "write_file",
            "list_directory",
            "file_exists",
            "search_files",
            "get_metadata",
        })

    @staticmethod
    def risk_for_action(action: str) -> RiskLevel:
        """Return risk classification for a filesystem action (P10B-503)."""
        if action in _WRITE_ACTIONS:
            return RiskLevel.HIGH
        return RiskLevel.LOW

    @staticmethod
    def requires_confirmation_for_action(action: str) -> bool:
        """Return True when the action requires LIVE-mode confirmation."""
        return action in _WRITE_ACTIONS

    @abstractmethod
    def execute(self, action: str, **params: object) -> FileSystemResponse:
        """Run a filesystem action and return structured results."""


class LocalFileSystemProvider(FileSystemProvider):
    """Production local filesystem provider scoped to allowed project roots."""

    def __init__(
        self,
        project_root: Path,
        *,
        context: ProviderContext | None = None,
        allowed_roots: tuple[Path, ...] | None = None,
    ) -> None:
        self._project_root = project_root.resolve()
        roots = allowed_roots or (self._project_root,)
        self._allowed_roots = tuple(root.resolve() for root in roots)
        self.context = context

    @property
    def version_info(self) -> ProviderVersionInfo:
        return _FILE_SYSTEM_VERSION

    def health_check(self) -> ProviderHealth:
        default = ProviderHealth(
            state=ToolHealthState.ONLINE,
            message="Filesystem local opérationnel.",
        )
        for root in self._allowed_roots:
            if not root.exists() or not root.is_dir():
                return ProviderHealth(
                    state=ToolHealthState.MISCONFIGURED,
                    message=f"Racine projet inaccessible : {root}",
                )
        return resolve_provider_health(
            self.provider_id,
            context=self.context,
            default_health=default,
        )

    def execute(self, action: str, **params: object) -> FileSystemResponse:
        """Dispatch filesystem action with path guard and mode safety."""
        normalized = action.strip()
        if normalized not in self.supported_actions():
            return self._failure(
                normalized,
                f"Action non supportée : {action!r}",
                target_path=str(params.get("path", "")),
            )

        execution_mode = self._parse_execution_mode(params.get("execution_mode"))
        dry_run = bool(params.get("dry_run", False))
        target_path = str(params.get("path", "")).strip()
        risk = self.risk_for_action(normalized)
        confirmation = self.requires_confirmation_for_action(normalized)

        handlers = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_directory": self._list_directory,
            "file_exists": self._file_exists,
            "search_files": self._search_files,
            "get_metadata": self._get_metadata,
        }
        handler = handlers[normalized]
        try:
            response = handler(
                params,
                execution_mode=execution_mode,
                dry_run=dry_run,
            )
        except PathGuardError as exc:
            return self._failure(normalized, str(exc), target_path=target_path, risk=risk)

        response.risk_level = risk
        response.confirmation_required = confirmation
        if not response.target_path:
            response.target_path = target_path
        return response

    def _read_file(
        self,
        params: dict,
        *,
        execution_mode: ExecutionMode,
        dry_run: bool,
    ) -> FileSystemResponse:
        _ = execution_mode, dry_run
        path = str(params.get("path", ""))
        resolved = self._resolve_path(path, must_exist=True)
        try:
            content = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            return self._failure("read_file", f"Lecture impossible : {exc}", target_path=path)
        return FileSystemResponse(
            operation="read_file",
            success=True,
            data=content,
            target_path=self._relative_display(resolved),
            provider=self.provider_id,
        )

    def _write_file(
        self,
        params: dict,
        *,
        execution_mode: ExecutionMode,
        dry_run: bool,
    ) -> FileSystemResponse:
        path = str(params.get("path", ""))
        content = str(params.get("content", ""))
        resolved = self._resolve_path(path, must_exist=False)
        display = self._relative_display(resolved)

        if dry_run or execution_mode in _WRITE_BLOCKED_MODES:
            return FileSystemResponse(
                operation="write_file",
                success=True,
                data=(
                    f"[simulation] Écriture simulée : {len(content)} caractères → {display}"
                ),
                target_path=display,
                provider=self.provider_id,
                simulated=True,
            )

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except OSError as exc:
            return self._failure("write_file", f"Écriture impossible : {exc}", target_path=path)

        return FileSystemResponse(
            operation="write_file",
            success=True,
            data=f"Fichier écrit : {display}",
            target_path=display,
            provider=self.provider_id,
        )

    def _list_directory(
        self,
        params: dict,
        *,
        execution_mode: ExecutionMode,
        dry_run: bool,
    ) -> FileSystemResponse:
        _ = execution_mode, dry_run
        path = str(params.get("path", ".")).strip() or "."
        extension = str(params.get("extension", "")).strip().lstrip(".")
        resolved = self._resolve_path(path, must_exist=False)
        if not resolved.exists():
            return self._failure(
                "list_directory",
                f"Répertoire introuvable : {resolved.name}",
                target_path=path,
            )
        if not resolved.is_dir():
            return self._failure(
                "list_directory",
                f"N'est pas un répertoire : {resolved.name}",
                target_path=path,
            )
        entries = sorted(entry.name for entry in resolved.iterdir())
        if extension:
            entries = [
                name for name in entries
                if name.endswith(f".{extension}") or fnmatch.fnmatch(name, f"*.{extension}")
            ]
        return FileSystemResponse(
            operation="list_directory",
            success=True,
            data=entries,
            target_path=self._relative_display(resolved),
            provider=self.provider_id,
        )

    def _file_exists(
        self,
        params: dict,
        *,
        execution_mode: ExecutionMode,
        dry_run: bool,
    ) -> FileSystemResponse:
        _ = execution_mode, dry_run
        path = str(params.get("path", ""))
        try:
            resolved = self._resolve_path(path, must_exist=False)
            exists = resolved.exists()
        except PathGuardError as exc:
            return self._failure("file_exists", str(exc), target_path=path)
        return FileSystemResponse(
            operation="file_exists",
            success=True,
            data={"exists": exists, "path": self._relative_display(resolved)},
            target_path=self._relative_display(resolved),
            provider=self.provider_id,
        )

    def _search_files(
        self,
        params: dict,
        *,
        execution_mode: ExecutionMode,
        dry_run: bool,
    ) -> FileSystemResponse:
        _ = execution_mode, dry_run
        directory = str(params.get("directory", params.get("path", "."))).strip() or "."
        pattern = str(params.get("pattern", "*")).strip() or "*"
        keyword = str(params.get("keyword", "")).strip()
        recursive = bool(params.get("recursive", True))
        max_results = int(params.get("max_results", 50))
        max_results = min(max(max_results, 1), 200)

        resolved = self._resolve_path(directory, must_exist=False)
        if not resolved.exists() or not resolved.is_dir():
            return self._failure(
                "search_files",
                f"Répertoire introuvable : {directory}",
                target_path=directory,
            )

        matches: list[str] = []
        if keyword:
            matches = self._search_by_keyword(
                resolved,
                keyword=keyword,
                pattern=pattern,
                recursive=recursive,
                max_results=max_results,
            )
        else:
            walker = os.walk(resolved) if recursive else [(str(resolved), [], os.listdir(resolved))]
            for root, _dirs, files in walker:
                root_path = Path(root)
                for name in files:
                    if fnmatch.fnmatch(name, pattern):
                        rel = root_path / name
                        matches.append(str(rel.relative_to(self._project_root)))
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break

        return FileSystemResponse(
            operation="search_files",
            success=True,
            data=matches,
            target_path=self._relative_display(resolved),
            provider=self.provider_id,
        )

    def _search_by_keyword(
        self,
        root_dir: Path,
        *,
        keyword: str,
        pattern: str,
        recursive: bool,
        max_results: int,
    ) -> list[str]:
        """Search file contents for a keyword within allowed project roots."""
        matches: list[str] = []
        keyword_lower = keyword.lower()
        walker = os.walk(root_dir) if recursive else [(str(root_dir), [], os.listdir(root_dir))]

        for root, _dirs, files in walker:
            root_path = Path(root)
            for name in files:
                if pattern != "*" and not fnmatch.fnmatch(name, pattern):
                    continue
                file_path = root_path / name
                if not file_path.is_file():
                    continue
                try:
                    if file_path.stat().st_size > 512_000:
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if keyword_lower in content.lower():
                    matches.append(str(file_path.relative_to(self._project_root)))
                    if len(matches) >= max_results:
                        return matches
        return matches

    def _get_metadata(
        self,
        params: dict,
        *,
        execution_mode: ExecutionMode,
        dry_run: bool,
    ) -> FileSystemResponse:
        _ = execution_mode, dry_run
        path = str(params.get("path", ""))
        try:
            resolved = self._resolve_path(path, must_exist=False)
        except PathGuardError as exc:
            return self._failure("get_metadata", str(exc), target_path=path)

        exists = resolved.exists()
        metadata = FileMetadata(
            path=self._relative_display(resolved),
            exists=exists,
            is_file=resolved.is_file() if exists else False,
            is_dir=resolved.is_dir() if exists else False,
            size_bytes=resolved.stat().st_size if exists and resolved.is_file() else 0,
            modified_at=resolved.stat().st_mtime if exists else None,
        )
        return FileSystemResponse(
            operation="get_metadata",
            success=True,
            data=metadata.to_dict(),
            target_path=metadata.path,
            provider=self.provider_id,
        )

    def _resolve_path(self, raw_path: str, *, must_exist: bool) -> Path:
        """Resolve path against allowed roots; primary root is project_root."""
        return resolve_allowed_path(raw_path, self._project_root, must_exist=must_exist)

    def _relative_display(self, resolved: Path) -> str:
        try:
            return str(resolved.relative_to(self._project_root))
        except ValueError:
            return str(resolved)

    @staticmethod
    def _parse_execution_mode(value: object) -> ExecutionMode:
        if isinstance(value, ExecutionMode):
            return value
        if isinstance(value, str):
            try:
                return ExecutionMode(value.lower())
            except ValueError:
                pass
        return ExecutionMode.LIVE

    @staticmethod
    def _failure(
        operation: str,
        error: str,
        *,
        target_path: str = "",
        risk: RiskLevel = RiskLevel.LOW,
    ) -> FileSystemResponse:
        return FileSystemResponse(
            operation=operation,
            success=False,
            error=error,
            target_path=target_path,
            provider="file_system",
            risk_level=risk,
        )

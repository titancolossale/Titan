# =====================================
# Titan Core Tool Loader
# =====================================

"""Automatic discovery and loading of BaseTool implementations from filesystem paths."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Iterable

from core.tools.base_tool import BaseTool
from core.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_SKIP_DIR_NAMES = frozenset({"__pycache__", ".git", ".mypy_cache", ".pytest_cache"})
_SKIP_FILE_PREFIXES = ("_",)
_INFRASTRUCTURE_MODULES = frozenset(
    {
        "base_tool",
        "tool_registry",
        "tool_loader",
        "tool_metadata",
        "capability_models",
        "capability_registry",
        "exceptions",
        "__init__",
    }
)


@dataclass
class ToolLoadResult:
    """Summary of a tool loading or reload pass."""

    loaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)

    @property
    def total_discovered(self) -> int:
        """Count of tools successfully registered (enabled and disabled)."""
        return len(self.loaded) + len(self.disabled)


class ToolLoader:
    """Discover, import, instantiate, and register BaseTool subclasses from folders.

    The loader scans one or more directories recursively, uses Python introspection
    to find concrete ``BaseTool`` implementations, and registers them into a
    ``ToolRegistry``. It tolerates individual plugin failures and duplicate tool ids.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        scan_paths: Iterable[Path | str] | None = None,
    ) -> None:
        """Initialize the loader.

        Args:
            registry: Registry that discovered tools are registered into.
            scan_paths: Optional directories to scan. Paths may be added later via
                ``add_scan_path`` before calling ``load`` or ``reload``.
        """
        self._registry = registry
        self._scan_paths: list[Path] = [
            Path(path).resolve() for path in (scan_paths or [])
        ]
        self._loaded_tool_ids: list[str] = []
        self._loaded_module_names: list[str] = []
        self._load_generation: int = 0

    @property
    def scan_paths(self) -> tuple[Path, ...]:
        """Return the configured scan directories."""
        return tuple(self._scan_paths)

    @property
    def loaded_tool_ids(self) -> tuple[str, ...]:
        """Return tool ids registered by this loader instance."""
        return tuple(self._loaded_tool_ids)

    def add_scan_path(self, path: Path | str) -> None:
        """Append a directory to the scan list if not already present."""
        resolved = Path(path).resolve()
        if resolved not in self._scan_paths:
            self._scan_paths.append(resolved)

    def load(self) -> ToolLoadResult:
        """Scan configured folders and register all discoverable tools.

        Returns:
            Structured summary of loaded, skipped, failed, duplicate, and disabled tools.
        """
        result = ToolLoadResult()

        for scan_path in self._scan_paths:
            if not scan_path.exists():
                logger.warning("Skipped missing scan path: %s", scan_path)
                result.skipped.append(str(scan_path))
                continue
            if not scan_path.is_dir():
                logger.warning("Skipped non-directory scan path: %s", scan_path)
                result.skipped.append(str(scan_path))
                continue

            for file_path in self._iter_python_files(scan_path):
                self._load_module_tools(file_path, result)

        return result

    def reload(self) -> ToolLoadResult:
        """Unregister tools loaded by this instance and run discovery again.

        Returns:
            Structured summary of the reload pass.
        """
        self._unregister_loaded_tools()
        self._load_generation += 1
        return self.load()

    def _unregister_loaded_tools(self) -> None:
        """Remove all tool ids previously registered by this loader."""
        for tool_id in list(self._loaded_tool_ids):
            if self._registry.tool_exists(tool_id):
                self._registry.unregister_tool(tool_id)
        self._loaded_tool_ids.clear()
        for module_name in self._loaded_module_names:
            sys.modules.pop(module_name, None)
        self._loaded_module_names.clear()

    def _iter_python_files(self, root: Path) -> Iterable[Path]:
        """Yield importable ``.py`` files under ``root``, skipping cache dirs."""
        for path in sorted(root.rglob("*.py")):
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.name.startswith(_SKIP_FILE_PREFIXES):
                continue
            if path.stem in _INFRASTRUCTURE_MODULES and self._is_infrastructure_root(
                path.parent, root
            ):
                continue
            yield path

    @staticmethod
    def _is_infrastructure_root(parent: Path, scan_root: Path) -> bool:
        """Return True when ``parent`` is the direct scan root for core/tools infra."""
        return parent.resolve() == scan_root.resolve()

    def _load_module_tools(self, file_path: Path, result: ToolLoadResult) -> None:
        """Import a module file and register every concrete BaseTool subclass."""
        module_name = self._module_name_for_path(file_path)
        try:
            module = self._import_module_from_path(file_path, module_name)
            if module_name not in self._loaded_module_names:
                self._loaded_module_names.append(module_name)
        except Exception as exc:
            message = f"{file_path.name}: {exc}"
            logger.warning("Failed to import module %s: %s", file_path, exc)
            result.failed.append((file_path.stem, message))
            return

        for _name, candidate in inspect.getmembers(module, inspect.isclass):
            if not self._is_concrete_tool_class(candidate):
                if self._is_tool_subclass(candidate):
                    logger.debug(
                        "Skipped abstract tool class %s in %s",
                        candidate.__name__,
                        file_path,
                    )
                    result.skipped.append(candidate.__name__)
                continue

            self._register_discovered_tool(candidate, file_path, result)

    def _register_discovered_tool(
        self,
        tool_cls: type[BaseTool],
        file_path: Path,
        result: ToolLoadResult,
    ) -> None:
        """Instantiate and register a discovered tool class."""
        class_name = tool_cls.__name__
        logger.info("Loading tool %s from %s", class_name, file_path)

        try:
            tool = tool_cls()
        except Exception as exc:
            message = f"{class_name}: {exc}"
            logger.warning("Failed to instantiate tool %s: %s", class_name, exc)
            result.failed.append((class_name, message))
            return

        try:
            tool_id = tool.id
        except Exception as exc:
            message = f"{class_name}.id: {exc}"
            logger.warning("Failed to read tool id for %s: %s", class_name, exc)
            result.failed.append((class_name, message))
            return

        if not tool_id or not isinstance(tool_id, str):
            message = f"{class_name}: invalid tool id {tool_id!r}"
            logger.warning(message)
            result.failed.append((class_name, message))
            return

        if self._registry.tool_exists(tool_id):
            logger.warning(
                "Duplicate tool id '%s' from %s — skipping",
                tool_id,
                class_name,
            )
            result.duplicates.append(tool_id)
            return

        try:
            self._registry.register_tool(tool)
        except Exception as exc:
            message = f"{tool_id}: {exc}"
            logger.warning("Failed to register tool %s: %s", tool_id, exc)
            result.failed.append((class_name, message))
            return

        self._loaded_tool_ids.append(tool_id)

        if tool.enabled:
            logger.info("Loaded tool %s (id=%s)", class_name, tool_id)
            result.loaded.append(tool_id)
        else:
            logger.info("Disabled tool %s (id=%s)", class_name, tool_id)
            result.disabled.append(tool_id)

    @staticmethod
    def _is_tool_subclass(candidate: type[object]) -> bool:
        """Return True when ``candidate`` is a BaseTool subclass (not BaseTool itself)."""
        return inspect.isclass(candidate) and issubclass(candidate, BaseTool) and candidate is not BaseTool

    @staticmethod
    def _is_concrete_tool_class(candidate: type[object]) -> bool:
        """Return True for non-abstract BaseTool subclasses."""
        return (
            inspect.isclass(candidate)
            and issubclass(candidate, BaseTool)
            and candidate is not BaseTool
            and not inspect.isabstract(candidate)
        )

    def _module_name_for_path(self, file_path: Path) -> str:
        """Build a unique module name for dynamic import."""
        sanitized = (
            str(file_path.resolve())
            .replace("\\", "_")
            .replace("/", "_")
            .replace(":", "_")
            .replace(".", "_")
        )
        return f"titan_discovered_tool_{self._load_generation}_{sanitized}"

    def _import_module_from_path(self, file_path: Path, module_name: str) -> ModuleType:
        """Dynamically import a Python file as a module."""
        self._clear_bytecode_cache(file_path)
        importlib.invalidate_caches()

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules.pop(module_name, None)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _clear_bytecode_cache(file_path: Path) -> None:
        """Remove cached bytecode for ``file_path`` so reloads pick up source changes."""
        pycache_dir = file_path.parent / "__pycache__"
        if not pycache_dir.is_dir():
            return
        for cached in pycache_dir.glob(f"{file_path.stem}.*.pyc"):
            cached.unlink(missing_ok=True)

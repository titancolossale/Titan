# =====================================
# Titan Path Guard
# =====================================

"""Project-root path validation for file tools (Phase 6 — P6-020)."""

from __future__ import annotations

from pathlib import Path


class PathGuardError(ValueError):
    """Raised when a path fails allowlist or traversal checks."""


def resolve_allowed_path(
    raw_path: str,
    project_root: Path,
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve *raw_path* relative to *project_root*; reject traversal escapes.

    Args:
        raw_path: User-supplied path (relative or absolute within project).
        project_root: Allowed root directory.
        must_exist: When True, the resolved path must exist on disk.

    Returns:
        Resolved absolute path guaranteed to be under *project_root*.

    Raises:
        PathGuardError: On empty path, traversal escape, or missing file.
    """
    if not raw_path or not str(raw_path).strip():
        raise PathGuardError("Chemin de fichier vide.")

    root = project_root.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathGuardError(
            f"Accès refusé : le chemin sort du répertoire autorisé ({root})."
        ) from exc

    if must_exist and not resolved.is_file():
        raise PathGuardError(f"Fichier introuvable : {resolved.name}")

    return resolved

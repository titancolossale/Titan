# =====================================
# Titan Vault Path Guard
# =====================================

"""Path validation for external vault connectors (Phase 12.5 — P125-003)."""

from __future__ import annotations

from pathlib import Path


class VaultPathGuardError(ValueError):
    """Raised when a vault path fails allowlist or traversal checks."""


def resolve_vault_path(
    raw_path: str,
    vault_root: Path,
    *,
    must_exist: bool = False,
    expect_file: bool = False,
    expect_dir: bool = False,
) -> Path:
    """Resolve *raw_path* relative to *vault_root*; reject traversal escapes.

    Args:
        raw_path: User-supplied path (relative or absolute within vault).
        vault_root: Allowed vault root directory.
        must_exist: When True, the resolved path must exist on disk.
        expect_file: When True, require a file (not a directory).
        expect_dir: When True, require a directory (not a file).

    Returns:
        Resolved absolute path guaranteed to be under *vault_root*.

    Raises:
        VaultPathGuardError: On empty path, traversal escape, or type mismatch.
    """
    if not raw_path or not str(raw_path).strip():
        raise VaultPathGuardError("Chemin vide.")

    root = vault_root.resolve()
    if not root.is_dir():
        raise VaultPathGuardError(f"Racine du vault introuvable : {root}")

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise VaultPathGuardError(
            f"Accès refusé : le chemin sort du vault autorisé ({root})."
        ) from exc

    if must_exist and not resolved.exists():
        raise VaultPathGuardError(f"Chemin introuvable dans le vault : {resolved.name}")

    if expect_file and resolved.exists() and not resolved.is_file():
        raise VaultPathGuardError(f"Un fichier est attendu, pas un dossier : {resolved.name}")

    if expect_dir and resolved.exists() and not resolved.is_dir():
        raise VaultPathGuardError(f"Un dossier est attendu, pas un fichier : {resolved.name}")

    return resolved


def relative_vault_path(resolved: Path, vault_root: Path) -> str:
    """Return a vault-relative POSIX path for display and metadata."""
    rel = resolved.resolve().relative_to(vault_root.resolve())
    return rel.as_posix()

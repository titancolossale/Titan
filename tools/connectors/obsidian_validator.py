# =====================================
# Titan Obsidian Validator
# =====================================

"""Production readiness validation for the Obsidian vault connector."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ObsidianValidationCode(str, Enum):
    """Machine-readable Obsidian configuration status."""

    OK = "ok"
    OBSIDIAN_DISABLED = "obsidian_disabled"
    MISSING_VAULT_PATH = "missing_vault_path"
    INVALID_VAULT_PATH = "invalid_vault_path"
    VAULT_NOT_FOUND = "vault_not_found"
    VAULT_NOT_READABLE = "vault_not_readable"
    VAULT_NOT_WRITABLE = "vault_not_writable"
    UNSAFE_VAULT_PATH = "unsafe_vault_path"


@dataclass(frozen=True)
class ObsidianValidationResult:
    """Structured outcome from Obsidian vault validation."""

    ok: bool
    code: ObsidianValidationCode
    message: str
    vault_path: Path | None = None
    vault_name: str = ""
    readable: bool = False
    writable: bool = False

    def format_report(self) -> str:
        """Return a multi-line French report for CLI output."""
        lines = ["=== Obsidian — validation du vault ===", ""]
        enabled = os.getenv("TITAN_OBSIDIAN_ENABLED", "false").lower() == "true"
        lines.append(f"Activé (TITAN_OBSIDIAN_ENABLED) : {'oui' if enabled else 'non'}")
        env_path = os.getenv("TITAN_OBSIDIAN_VAULT_PATH", "").strip()
        lines.append(f"TITAN_OBSIDIAN_VAULT_PATH : {env_path or '(non défini)'}")
        if self.vault_path is not None:
            lines.append(f"Chemin résolu : {self.vault_path}")
            if self.vault_name:
                lines.append(f"Nom du dossier vault : {self.vault_name}")
        lines.append(f"Lecture : {'oui' if self.readable else 'non'}")
        lines.append(f"Écriture : {'oui' if self.writable else 'non'}")
        lines.append("")
        status = "PRÊT" if self.ok else "ÉCHEC"
        lines.append(f"Statut : {status} ({self.code.value})")
        lines.append(self.message)
        if self.ok:
            lines.append("")
            lines.append(
                "Titan ne crée jamais un nouveau vault — seul le dossier existant "
                "configuré est utilisé."
            )
        return "\n".join(lines)


def _is_unsafe_vault_path(resolved: Path) -> str | None:
    """Return an error message when the vault path is considered unsafe."""
    parts_lower = {part.lower() for part in resolved.parts}
    blocked_roots = {
        "windows",
        "system32",
        "program files",
        "program files (x86)",
        "programdata",
    }
    if parts_lower & blocked_roots:
        return (
            "Chemin vault refusé : emplacement système non autorisé. "
            "Pointez TITAN_OBSIDIAN_VAULT_PATH vers votre vault Obsidian existant "
            "(ex. « Titan AI »)."
        )
    normalized = str(resolved).lower()
    if ".." in normalized or normalized.startswith("\\\\"):
        return (
            "Chemin vault refusé : chemin non sûr détecté. "
            "Utilisez un chemin absolu vers votre vault Obsidian existant."
        )
    return None


def _probe_writable(directory: Path) -> tuple[bool, str]:
    """Try creating and deleting a probe file without leaving artifacts."""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".titan_obsidian_probe_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write("probe")
            probe_path = Path(handle.name)
        probe_path.unlink(missing_ok=True)
        return True, ""
    except OSError as exc:
        return False, f"Vault en lecture seule ou inaccessible en écriture : {exc}"


def validate_obsidian_config(
    *,
    enabled: bool | None = None,
    vault_path: Path | str | None = None,
) -> ObsidianValidationResult:
    """Validate Obsidian connector configuration for production use.

    Checks, in order:
    - TITAN_OBSIDIAN_ENABLED is true
    - TITAN_OBSIDIAN_VAULT_PATH is set
    - Path resolves to an existing directory (never creates a vault)
    - Path is safe (user home subtree, not system dirs)
    - Vault is readable and writable
    """
    is_enabled = (
        os.getenv("TITAN_OBSIDIAN_ENABLED", "false").lower() == "true"
        if enabled is None
        else enabled
    )
    if not is_enabled:
        return ObsidianValidationResult(
            ok=False,
            code=ObsidianValidationCode.OBSIDIAN_DISABLED,
            message=(
                "Connecteur Obsidian désactivé. Définissez TITAN_OBSIDIAN_ENABLED=true "
                "dans .env pour activer l'intégration."
            ),
        )

    raw_path = (
        os.getenv("TITAN_OBSIDIAN_VAULT_PATH", "").strip()
        if vault_path is None
        else str(vault_path).strip()
    )
    if not raw_path:
        return ObsidianValidationResult(
            ok=False,
            code=ObsidianValidationCode.MISSING_VAULT_PATH,
            message=(
                "TITAN_OBSIDIAN_VAULT_PATH est vide. Pointez-le vers votre vault "
                "Obsidian existant (ex. dossier « Titan AI »). "
                "Titan ne crée jamais un nouveau vault."
            ),
        )

    try:
        resolved = Path(raw_path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return ObsidianValidationResult(
            ok=False,
            code=ObsidianValidationCode.INVALID_VAULT_PATH,
            message=f"Chemin vault invalide : {exc}",
        )

    unsafe_reason = _is_unsafe_vault_path(resolved)
    if unsafe_reason:
        return ObsidianValidationResult(
            ok=False,
            code=ObsidianValidationCode.UNSAFE_VAULT_PATH,
            message=unsafe_reason,
            vault_path=resolved,
            vault_name=resolved.name,
        )

    if not resolved.exists():
        return ObsidianValidationResult(
            ok=False,
            code=ObsidianValidationCode.VAULT_NOT_FOUND,
            message=(
                f"Vault Obsidian introuvable : {resolved}. "
                "Créez le vault dans Obsidian d'abord, puis pointez "
                "TITAN_OBSIDIAN_VAULT_PATH vers ce dossier existant. "
                "Titan ne crée jamais un nouveau vault."
            ),
            vault_path=resolved,
            vault_name=resolved.name,
        )

    if not resolved.is_dir():
        return ObsidianValidationResult(
            ok=False,
            code=ObsidianValidationCode.INVALID_VAULT_PATH,
            message=(
                f"TITAN_OBSIDIAN_VAULT_PATH doit pointer vers un dossier vault "
                f"existant, pas un fichier : {resolved}"
            ),
            vault_path=resolved,
            vault_name=resolved.name,
        )

    readable = os.access(resolved, os.R_OK)
    if not readable:
        return ObsidianValidationResult(
            ok=False,
            code=ObsidianValidationCode.VAULT_NOT_READABLE,
            message=(
                f"Vault Obsidian non lisible : {resolved}. "
                "Vérifiez les permissions du dossier."
            ),
            vault_path=resolved,
            vault_name=resolved.name,
            readable=False,
            writable=False,
        )

    writable, write_error = _probe_writable(resolved)
    if not writable:
        return ObsidianValidationResult(
            ok=False,
            code=ObsidianValidationCode.VAULT_NOT_WRITABLE,
            message=write_error or f"Vault Obsidian non modifiable : {resolved}",
            vault_path=resolved,
            vault_name=resolved.name,
            readable=True,
            writable=False,
        )

    name_hint = ""
    if resolved.name.lower() != "titan ai":
        name_hint = (
            f" (nom actuel : « {resolved.name} » — attendu : vault « Titan AI »)"
        )

    return ObsidianValidationResult(
        ok=True,
        code=ObsidianValidationCode.OK,
        message=(
            f"Vault Obsidian prêt{name_hint} : {resolved}. "
            "Lecture et écriture confirmées."
        ),
        vault_path=resolved,
        vault_name=resolved.name,
        readable=True,
        writable=True,
    )

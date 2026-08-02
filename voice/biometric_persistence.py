# =====================================
# Titan Biometric Persistence Validation
# =====================================

"""Phase 20.13 — durable voice biometric storage on persistent volumes.

Voice speaker profiles, encrypted ECAPA embeddings, enrollment sessions, and
metadata live under ``TITAN_DATA_DIR`` (Railway Volume mount ``/app/data``).

This module:
  • creates required biometric directories
  • probes writability
  • detects ephemeral container storage vs a persistent volume
  • refuses silent fallback to tempfile / non-data paths in production

Never logs encryption keys, embeddings, or decrypted biometric payloads.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.paths import ensure_directory, get_data_directory, is_directory_writable

logger = logging.getLogger(__name__)

# Subdirectories that must exist under the durable data root.
BIOMETRIC_SUBDIRS = (
    "voice_enrollment_tmp",
    "voice_live_tmp",
    "voice_models",
    "voice_models/ecapa",
)

PROFILES_FILENAME = "voice_speaker_profiles.json"


@dataclass
class BiometricStorageReport:
    """Startup / readiness diagnostics for biometric persistence."""

    ok: bool
    writable: bool
    persistent: bool
    persistence_required: bool
    data_dir: str
    profiles_path: str
    created_directories: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)
    ephemeral_fallback_blocked: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "writable": self.writable,
            "persistent": self.persistent,
            "persistence_required": self.persistence_required,
            "data_dir": self.data_dir,
            "profiles_path": self.profiles_path,
            "created_directories": list(self.created_directories),
            "diagnostics": list(self.diagnostics),
            "signals": dict(self.signals),
            "ephemeral_fallback_blocked": self.ephemeral_fallback_blocked,
            "architecture": "railway_volume_json_aes_gcm",
            "survives_redeploy": self.persistent and self.writable,
        }


def biometric_persistence_required() -> bool:
    """Return whether durable (volume-backed) biometric storage is mandatory.

    Explicit ``TITAN_BIOMETRIC_PERSISTENCE_REQUIRED`` wins. Otherwise require
    persistence only on Railway production (avoids local test pollution when
    ``TITAN_APP_ENV=production`` is set transiently). Dockerfile sets the
    explicit flag to ``true`` for cloud images.
    """
    raw = os.getenv("TITAN_BIOMETRIC_PERSISTENCE_REQUIRED", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    app_env = os.getenv("TITAN_APP_ENV", os.getenv("APP_ENV", "development")).strip().lower()
    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_SERVICE_NAME")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    )
    return app_env == "production" and on_railway


def resolve_profiles_path(profiles_path: Path | str | None = None) -> Path:
    """Resolve speaker profile store path — never silently use tempfile."""
    if profiles_path is not None:
        path = Path(profiles_path)
        if not path.is_absolute():
            path = get_data_directory() / path
        return path.resolve()
    env_path = os.getenv("TITAN_VOICE_SPEAKER_PROFILES_PATH", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if not path.is_absolute():
            path = get_data_directory() / path
        return path.resolve()
    # Always derive from live TITAN_DATA_DIR (not import-time settings freeze).
    return (get_data_directory() / PROFILES_FILENAME).resolve()


def _path_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _read_proc_mounts() -> list[str]:
    mounts_file = Path("/proc/mounts")
    if not mounts_file.is_file():
        return []
    try:
        return mounts_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def detect_persistent_storage(path: Path) -> tuple[bool, dict[str, Any]]:
    """Detect whether ``path`` lives on durable volume-backed storage.

    Signals (any one is sufficient):
      1. Operator affirmation ``TITAN_BIOMETRIC_STORAGE_PERSISTENT=true``
      2. Railway volume mount env covers the path
      3. Path or an ancestor (below filesystem root) is a mount point
      4. ``/proc/mounts`` lists the data directory as a mount
    """
    signals: dict[str, Any] = {
        "operator_affirmed": False,
        "railway_volume_mount": None,
        "ismount_hits": [],
        "proc_mount_hit": False,
        "under_temp": False,
    }
    resolved = path.resolve()
    data_dir = get_data_directory().resolve()

    affirmed = os.getenv("TITAN_BIOMETRIC_STORAGE_PERSISTENT", "").strip().lower()
    if affirmed in {"1", "true", "yes", "on"}:
        signals["operator_affirmed"] = True
        return True, signals

    railway_mount = (
        os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
        or os.getenv("TITAN_RAILWAY_VOLUME_MOUNT", "").strip()
    )
    if railway_mount:
        mount_path = Path(railway_mount).expanduser().resolve()
        signals["railway_volume_mount"] = str(mount_path)
        if _path_under(resolved, mount_path) or resolved == mount_path:
            return True, signals

    # Never treat system temp as durable biometric storage (after overrides).
    tmp_root = Path(tempfile.gettempdir()).resolve()
    signals["under_temp"] = _path_under(resolved, tmp_root)
    if signals["under_temp"]:
        return False, signals

    # Walk ancestors; skip filesystem root so ephemeral /app/data still fails.
    cursor = resolved if resolved.is_dir() else resolved.parent
    root = Path(cursor.anchor)
    while cursor != root:
        try:
            if cursor.is_mount():
                signals["ismount_hits"].append(str(cursor))
                return True, signals
        except OSError:
            pass
        if cursor == cursor.parent:
            break
        cursor = cursor.parent

    for line in _read_proc_mounts():
        parts = line.split()
        if len(parts) < 2:
            continue
        mount_point = parts[1]
        if mount_point in {str(data_dir), str(resolved), str(resolved.parent)}:
            signals["proc_mount_hit"] = True
            return True, signals
        # Railway commonly mounts exactly /app/data
        if mount_point == "/app/data" and _path_under(resolved, Path("/app/data")):
            signals["proc_mount_hit"] = True
            return True, signals

    return False, signals


def ensure_biometric_directories(
    *,
    data_dir: Path | None = None,
    profiles_path: Path | None = None,
) -> list[str]:
    """Create missing biometric directories under the durable data root."""
    root = (data_dir or get_data_directory()).resolve()
    created: list[str] = []
    ensure_directory(root)
    for relative in BIOMETRIC_SUBDIRS:
        target = root / relative
        before = target.exists()
        ensure_directory(target)
        if not before:
            created.append(str(target))
    profiles = (profiles_path or resolve_profiles_path()).resolve()
    if not profiles.parent.exists():
        ensure_directory(profiles.parent)
        created.append(str(profiles.parent))
    elif not profiles.parent.is_dir():
        raise OSError(f"Biometric profiles parent is not a directory: {profiles.parent}")
    return created


def validate_biometric_storage(
    *,
    profiles_path: Path | str | None = None,
    require_persistent: bool | None = None,
) -> BiometricStorageReport:
    """Validate biometric storage layout, writability, and persistence.

    Never silently redirects to ephemeral tempfile storage.
    """
    data_dir = get_data_directory().resolve()
    profiles = resolve_profiles_path(profiles_path)
    required = (
        biometric_persistence_required()
        if require_persistent is None
        else bool(require_persistent)
    )
    diagnostics: list[str] = []
    created: list[str] = []

    # Hard rule in production: profiles must live under TITAN_DATA_DIR.
    # Dev/tests may use tmp_path fixtures when persistence is not required.
    outside_data = not _path_under(profiles, data_dir) and profiles != data_dir
    if outside_data and required:
        diagnostics.append(
            f"Profiles path {profiles} is outside TITAN_DATA_DIR {data_dir}. "
            "Refusing ephemeral / alternate storage fallback."
        )
        return BiometricStorageReport(
            ok=False,
            writable=False,
            persistent=False,
            persistence_required=required,
            data_dir=str(data_dir),
            profiles_path=str(profiles),
            diagnostics=diagnostics,
            signals={"outside_data_dir": True},
        )
    if outside_data:
        diagnostics.append(
            f"Profiles path {profiles} is outside TITAN_DATA_DIR {data_dir} "
            "(allowed only because persistence is not required)."
        )

    try:
        created = ensure_biometric_directories(data_dir=data_dir, profiles_path=profiles)
    except OSError as exc:
        diagnostics.append(f"Cannot create biometric directories: {exc}")
        return BiometricStorageReport(
            ok=False,
            writable=False,
            persistent=False,
            persistence_required=required,
            data_dir=str(data_dir),
            profiles_path=str(profiles),
            diagnostics=diagnostics,
        )

    writable = is_directory_writable(profiles.parent)
    if not writable:
        diagnostics.append(f"Biometric storage is not writable: {profiles.parent}")

    # Probe write specifically for the profiles file parent.
    probe = profiles.parent / ".titan_biometric_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except OSError as exc:
        writable = False
        diagnostics.append(f"Biometric write probe failed: {exc}")

    persistent, signals = detect_persistent_storage(profiles)
    if required and not persistent:
        diagnostics.append(
            "Biometric persistence required but storage does not look volume-backed. "
            "Mount a Railway Volume at /app/data, set TITAN_DATA_DIR=/app/data, "
            "and redeploy. Do not enroll until persistence is confirmed. "
            "Operator override (only if you verified durability): "
            "TITAN_BIOMETRIC_STORAGE_PERSISTENT=true"
        )

    ok = writable and (persistent or not required)
    if ok and not diagnostics:
        diagnostics.append(
            "Biometric storage writable"
            + (" and persistent (redeploy-safe)." if persistent else " (persistence not required).")
        )

    report = BiometricStorageReport(
        ok=ok,
        writable=writable,
        persistent=persistent,
        persistence_required=required,
        data_dir=str(data_dir),
        profiles_path=str(profiles),
        created_directories=created,
        diagnostics=diagnostics,
        signals=signals,
    )
    if not ok:
        logger.error(
            "BIOMETRIC_STORAGE_VALIDATION_FAILED writable=%s persistent=%s "
            "required=%s path=%s diagnostics=%s",
            writable,
            persistent,
            required,
            profiles,
            diagnostics,
        )
    else:
        logger.info(
            "BIOMETRIC_STORAGE_READY writable=%s persistent=%s path=%s",
            writable,
            persistent,
            profiles,
        )
    return report


def bootstrap_biometric_storage(
    *,
    profiles_path: Path | str | None = None,
) -> BiometricStorageReport:
    """Create directories and validate storage at application startup."""
    return validate_biometric_storage(profiles_path=profiles_path)


def collect_biometric_storage_readiness() -> dict[str, Any]:
    """Readiness payload fragment for ``/ready`` (no secrets / embeddings)."""
    report = validate_biometric_storage()
    required = report.persistence_required
    return {
        "name": "biometric_storage",
        "ok": report.ok,
        "required": required,
        "writable": report.writable,
        "persistent": report.persistent,
        "affects_ready": required,
        "message": "; ".join(report.diagnostics) if report.diagnostics else "ok",
        "data_dir": report.data_dir,
        "profiles_path": report.profiles_path,
        "architecture": "railway_volume_json_aes_gcm",
        "survives_redeploy": report.persistent and report.writable,
        "signals": {
            "operator_affirmed": bool(report.signals.get("operator_affirmed")),
            "railway_volume_mount": report.signals.get("railway_volume_mount"),
            "ismount_hits": report.signals.get("ismount_hits"),
            "proc_mount_hit": bool(report.signals.get("proc_mount_hit")),
            "under_temp": bool(report.signals.get("under_temp")),
        },
    }

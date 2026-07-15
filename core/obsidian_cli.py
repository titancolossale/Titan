# =====================================
# Titan Obsidian CLI
# =====================================

"""Manual Obsidian health and smoke-test commands (production readiness sprint)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from tools.connectors.obsidian_connector import ObsidianConnector
from tools.connectors.obsidian_validator import (
    ObsidianValidationCode,
    validate_obsidian_config,
)
from tools.connectors.vault_path_guard import relative_vault_path
from tools.permission_manager import PermissionLevel, PermissionManager


_SMOKE_TEST_FOLDER = "_titan_smoke_test"
_SMOKE_TEST_NOTE = f"{_SMOKE_TEST_FOLDER}/smoke-test.md"


def _snapshot_vault(vault_root: Path) -> dict[str, str]:
    """Return relative path → content hash for all markdown notes."""
    snapshot: dict[str, str] = {}
    for path in sorted(vault_root.rglob("*.md")):
        if not path.is_file():
            continue
        rel = relative_vault_path(path, vault_root)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot[rel] = digest
    return snapshot


def _print_step(label: str, success: bool, detail: str = "") -> None:
    status = "OK" if success else "ÉCHEC"
    line = f"  [{status}] {label}"
    if detail:
        line = f"{line} — {detail}"
    print(line)


def run_obsidian_health() -> int:
    """Validate Obsidian configuration and print a French health report."""
    result = validate_obsidian_config()
    print(result.format_report())
    return 0 if result.ok else 1


def run_obsidian_smoke_test() -> int:
    """Run an end-to-end Obsidian connector smoke test against the configured vault."""
    validation = validate_obsidian_config()
    if not validation.ok:
        print(validation.format_report())
        return 1

    vault_root = validation.vault_path
    assert vault_root is not None

    connector = ObsidianConnector(vault_root, enabled=True)
    print("=== Obsidian — smoke test ===")
    print(f"Vault : {vault_root}")
    print("")

    before_snapshot = _snapshot_vault(vault_root)
    failures = 0

    list_result = connector.execute("list_notes", {"recursive": True})
    _print_step("list_notes", list_result.success, list_result.data.splitlines()[0])
    failures += 0 if list_result.success else 1

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    create_content = (
        f"# Titan smoke test\n\n"
        f"Note temporaire créée le {timestamp}.\n"
        f"Supprimée automatiquement à la fin du test.\n"
    )
    create_result = connector.execute(
        "create_note",
        {"path": _SMOKE_TEST_NOTE, "content": create_content},
    )
    _print_step("create_note", create_result.success, _SMOKE_TEST_NOTE)
    failures += 0 if create_result.success else 1

    read_result = connector.execute("read_note", {"path": _SMOKE_TEST_NOTE})
    read_ok = read_result.success and "Titan smoke test" in read_result.data
    _print_step("read_note", read_ok)
    failures += 0 if read_ok else 1

    update_result = connector.execute(
        "patch_note",
        {
            "path": _SMOKE_TEST_NOTE,
            "update_mode": "append",
            "new_content": "\nLigne ajoutée par le smoke test.\n",
        },
    )
    _print_step("patch_note (append)", update_result.success)
    failures += 0 if update_result.success else 1

    search_result = connector.execute(
        "search_notes",
        {"mode": "filename", "query": "smoke-test"},
    )
    search_ok = search_result.success and "smoke-test" in search_result.data
    _print_step("search_notes", search_ok)
    failures += 0 if search_ok else 1

    permission = PermissionManager().evaluate(
        "obsidian",
        "delete_note",
        {"action": "delete_note", "path": _SMOKE_TEST_NOTE},
    )
    delete_blocked = permission.level == PermissionLevel.CONFIRMATION_REQUIRED
    _print_step(
        "delete_note (confirmation requise via Brain)",
        delete_blocked,
        permission.reason,
    )
    failures += 0 if delete_blocked else 1

    delete_result = connector.execute(
        "delete_note",
        {"path": _SMOKE_TEST_NOTE},
    )
    _print_step("delete_note (direct CLI cleanup)", delete_result.success)
    failures += 0 if delete_result.success else 1

    smoke_folder = vault_root / _SMOKE_TEST_FOLDER
    if smoke_folder.exists() and smoke_folder.is_dir():
        try:
            smoke_folder.rmdir()
            _print_step("cleanup smoke folder", True)
        except OSError as exc:
            _print_step("cleanup smoke folder", False, str(exc))
            failures += 1

    after_snapshot = _snapshot_vault(vault_root)
    unchanged = before_snapshot == after_snapshot
    _print_step(
        "vault inchangé (hors note temporaire)",
        unchanged,
        f"{len(before_snapshot)} notes avant/après",
    )
    failures += 0 if unchanged else 1

    print("")
    if failures == 0:
        print("Smoke test : SUCCÈS — Obsidian est opérationnel.")
        return 0
    print(f"Smoke test : ÉCHEC — {failures} étape(s) en erreur.")
    return 1


def print_obsidian_cli_help() -> None:
    """Print Obsidian CLI subcommand help."""
    print(
        "Commandes Obsidian :\n"
        "  python main.py obsidian-health      — valider la configuration du vault\n"
        "  python main.py obsidian-smoke-test  — test bout-en-bout (note temporaire)\n"
    )


def dispatch_obsidian_command(command: str) -> int | None:
    """Run an Obsidian CLI subcommand; return exit code or None if unknown."""
    normalized = command.strip().lower().replace("_", "-")
    if normalized == "obsidian-health":
        return run_obsidian_health()
    if normalized == "obsidian-smoke-test":
        return run_obsidian_smoke_test()
    if normalized in {"obsidian-help", "obsidian"}:
        print_obsidian_cli_help()
        return 0
    return None

# =====================================
# Titan Dead Module Guard Tests
# =====================================

"""CI guard: ensure deleted legacy modules stay deleted (P1-044)."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DELETED_MODULES = [
    PROJECT_ROOT / "core" / "action_manager.py",
    PROJECT_ROOT / "core" / "context.py",
]


@pytest.mark.parametrize(
    "module_path",
    DELETED_MODULES,
    ids=lambda p: str(p.relative_to(PROJECT_ROOT)),
)
def test_deleted_module_does_not_exist(module_path: Path) -> None:
    """Retired modules must not reappear after P1-042 and P1-043."""
    assert not module_path.exists(), f"Dead module resurrected: {module_path}"

# =====================================
# Titan Web V2 — Phase 4 Sidebar Reconstruction Tests
# =====================================

"""Frontend contracts for left-sidebar-only Cognitive OS reconstruction.

Scope guard: Phase 4 may touch sidebar CSS/JS + version/load order only.
Does not require Brain, API, Memory, Voice, neural, orchestrator, or dock changes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_node(script: str) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def test_phase4_sidebar_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/sidebar.css" in html
    assert (V2 / "design" / "sidebar.css").exists()
    assert html.index("./design/reference-final.css") < html.index("./design/sidebar.css")


def test_phase4_sidebar_css_reconstruction_contracts() -> None:
    css = (V2 / "design" / "sidebar.css").read_text(encoding="utf-8")
    for token in (
        "Phase 4",
        "LEFT SIDEBAR ONLY",
        "--tdl-sidebar-width: 204px",
        "--tdl-sidebar-glass",
        "--tdl-sidebar-icon: 10px",
        "tdl-v2-region--sidebar",
        "tdl-v2-presence-card",
        "background: transparent",
        "tdl-v2-sidebar-tools",
        "display: none !important",
        "sprint-2.7-reference-composition.png",
    ):
        assert token in css


def test_phase4_preserves_full_height_rail_against_context_drawer() -> None:
    """Nav must not collapse: context drawer stays absolute out of flex flow."""
    css = (V2 / "design" / "sidebar.css").read_text(encoding="utf-8")
    assert ".tdl-v2-layer--workspace > .tdl-v2-context-panel" in css
    assert "position: absolute" in css
    assert "height: 100%" in css
    assert "align-self: stretch" in css


def test_phase4_sidebar_material_is_carved_not_boxed() -> None:
    css = (V2 / "design" / "sidebar.css").read_text(encoding="utf-8")
    # Hairline outline + inset reflection — not thick container borders
    assert "outline: 1px solid var(--tdl-sidebar-edge)" in css
    assert "border: none !important" in css
    assert "tdl-sidebar-neural-bleed" in css
    assert "tdl-sidebar-reflect" in css


def test_phase4_presence_merged_into_sidebar_structure() -> None:
    sidebar = (V2 / "sidebar" / "sidebar-region.js").read_text(encoding="utf-8")
    assert 'dataset.phase = "5"' in sidebar or 'dataset.phase = "4"' in sidebar
    assert "tdl-v2-sidebar-presence" in sidebar
    assert "TITAN PRESENCE" in sidebar
    assert "TITAN ONLINE" in sidebar
    assert "CERVEAU ACTIF" in sidebar
    assert "tdl-v2-sidebar-presence__block" in sidebar
    assert "Réduire" in sidebar
    # Nested tool chips removed from the rail (status lives in dock)
    assert "SIDEBAR_TOOL_IDS" not in sidebar
    assert "tdl-v2-sidebar-tools" not in sidebar


def test_phase4_navigation_remains_quiet_and_complete() -> None:
    router = (V2 / "core" / "router.js").read_text(encoding="utf-8")
    sidebar = (V2 / "sidebar" / "sidebar-region.js").read_text(encoding="utf-8")
    for label in (
        "Chat",
        "Projects",
        "Memory",
        "Exploration",
        "Calendar",
        "Trading",
        "Tools",
        "Settings",
    ):
        assert f'label: "{label}"' in router
    assert "tdl-v2-nav-item--conversation" in sidebar
    assert "BIENTÔT" in sidebar
    assert 'PRESENCE_LABELS.idle' in sidebar or '"Je suis prêt. À tes côtés."' in sidebar


def test_phase4_does_not_touch_frozen_architecture_surfaces() -> None:
    """Guardrail: Phase 4 is sidebar reconstruction only."""
    css = (V2 / "design" / "sidebar.css").read_text(encoding="utf-8")
    assert "does not touch topbar" in css.lower() or "left sidebar only" in css.lower()
    # Frozen systems remain present and untouched by this stylesheet's charter
    assert (ROOT / "api" / "app.py").exists()
    assert (ROOT / "brain" / "brain.py").exists()
    assert (V2 / "neural").exists() or (V2 / "design" / "neural.css").exists()
    assert (V2 / "orchestrator" / "orchestrator-region.js").exists()
    assert (V2 / "center" / "topbar-region.js").exists()


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase4_ui_version_bump() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
if (!/^0\\.2[8-9]|^0\\.3|^0\\.4/.test(TITAN_UI_VERSION)) throw new Error('expected 0.28+ UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["version"].startswith("0.")

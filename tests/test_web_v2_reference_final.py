# =====================================
# Titan Web V2 — Sprint 2.10 Reference Visual Fidelity Tests
# =====================================

"""Frontend contracts for reference-first visual fidelity polish.

Validates acrylic materials layer, stylesheet load order, orchestrator
story hierarchy, layout geometry, and frontend-only scope.
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


def test_reference_final_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/reference-final.css" in html
    assert (V2 / "design" / "reference-final.css").exists()
    assert html.index("./design/presence.css") < html.index("./design/reference-final.css")
    assert html.index("./design/composition.css") < html.index("./design/reference-final.css")


def test_reference_final_css_acrylic_contracts() -> None:
    css = (V2 / "design" / "reference-final.css").read_text(encoding="utf-8")
    for token in (
        "tdl-acrylic-bg",
        "tdl-acrylic-depth",
        "tdl-acrylic-neural-bleed",
        "tdl-v2-glow-ambient",
        "tdl-v2-acrylic-breathe",
        "--tdl-sidebar-width: 200px",
        "--tdl-orchestrator-width: 300px",
        "tdl-v2-orchestrator-section",
        "tdl-v2-float-card",
        "prefers-reduced-motion",
        "sprint-2.7-reference-composition.png",
    ):
        assert token in css


def test_reference_final_removes_obvious_panel_borders() -> None:
    css = (V2 / "design" / "reference-final.css").read_text(encoding="utf-8")
    assert ".tdl-v2-region--sidebar" in css
    assert ".tdl-v2-region--orchestrator" in css
    assert "border: none" in css
    assert "outline: 1px solid" in css


def test_orchestrator_story_hierarchy_titles() -> None:
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    # Phase 4.2 command-center hierarchy (supersedes Sprint 2.10 story titles).
    assert "Current Objective" in orch
    assert "Execution Pipeline" in orch
    assert "Active Tools" in orch
    assert "Neural Activity" in orch
    # Previous dashboard labels must not regress into the mounted sections.
    assert '"Current State"' not in orch
    assert '"Plan in Progress"' not in orch
    assert '"Tools Used"' not in orch
    assert '"System Presence"' not in orch
    assert '"Cognitive State"' not in orch
    assert '"Execution Timeline"' not in orch
    assert '"Instruments"' not in orch
    assert '"Neural Field"' not in orch


def test_sidebar_and_status_regions_remain_wired() -> None:
    sidebar = (V2 / "sidebar" / "sidebar-region.js").read_text(encoding="utf-8")
    status = (V2 / "status" / "status-region.js").read_text(encoding="utf-8")
    assert "TITAN ONLINE" in sidebar
    assert "tdl-v2-sidebar-presence" in sidebar
    assert "tdl-v2-float-card" in status
    assert "tdl-v2-dock-status-cards--float" in status
    assert "Presence" in status


def test_no_backend_or_brain_changes_in_reference_final() -> None:
    """Guardrail: Sprint 2.10 is frontend chrome only."""
    css = (V2 / "design" / "reference-final.css").read_text(encoding="utf-8")
    assert "frontend chrome only" in css.lower() or "no backend" in css.lower()
    api = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    assert 'mount("/app"' in api or "web/v2" in api


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_ui_version_bump_for_reference_final() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
if (!/^0\\.2[7-9]|^0\\.3|^0\\.4/.test(TITAN_UI_VERSION)) throw new Error('expected 0.27+ UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["version"].startswith("0.")

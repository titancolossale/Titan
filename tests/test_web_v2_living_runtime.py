# =====================================
# Titan Web V2 — Phase 7 Living Runtime Experience Tests
# =====================================

"""Frontend contracts for Phase 7 Living Runtime Experience.

Scope guard: presentation only — topbar / workspace activity datasets /
living-runtime.css / atmosphere. No Brain, API, Memory, neural engine,
sidebar redesign, or composer structure changes required.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
TOPBAR = V2 / "center" / "topbar-region.js"
STATUS = V2 / "status" / "status-region.js"
SHELL = V2 / "layout" / "shell.js"
CSS = V2 / "design" / "living-runtime.css"
DOCS = ROOT / "docs" / "WEB_APP_LIVING_RUNTIME.md"


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


def test_phase7_living_runtime_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/living-runtime.css" in html
    assert CSS.exists()
    assert html.index("./design/living-orchestrator.css") < html.index(
        "./design/living-runtime.css"
    )
    assert html.index("./design/floating-workspaces.css") < html.index(
        "./design/living-runtime.css"
    )


def test_phase7_living_runtime_css_contracts() -> None:
    css = CSS.read_text(encoding="utf-8")
    for token in (
        "Phase 7",
        "LIVING RUNTIME EXPERIENCE",
        "tdl-lr-atmosphere-shift",
        "tdl-lr-dot-think",
        "tdl-lr-memory-scan",
        "tdl-lr-vault-glow",
        "tdl-lr-browser-shimmer",
        "tdl-lr-cognitive-breathe",
        "tdl-lr-presence-calm",
        "data-activity",
        "data-runtime",
        "prefers-reduced-motion",
        "Does not touch Titan Core",
    ):
        assert token in css


def test_phase7_topbar_runtime_activities() -> None:
    topbar = TOPBAR.read_text(encoding="utf-8")
    assert "tdl-v2-topbar--living" in topbar
    assert (
        'dataset.phase = "10"' in topbar
        or 'dataset.phase = "9"' in topbar
        or 'dataset.phase = "8"' in topbar
        or 'dataset.phase = "7"' in topbar
    )
    assert (
        "_resolveRuntime" in topbar
        or "resolveDominantOsState" in topbar
        or "resolveModuleTelemetry" in topbar
    )
    assert '"searching"' in topbar
    assert '"remembering"' in topbar or '"reading"' in topbar
    assert '"working"' in topbar or '"writing"' in topbar
    assert '"planning"' in topbar
    assert '"thinking"' in topbar or '"reasoning"' in topbar
    assert '"idle"' in topbar
    assert 'this._pill("mode", "Cerveau"' in topbar or "PILL_LABELS.mode" in topbar or "Cerveau" in topbar
    assert "dataset.activity" in topbar
    assert "cognitiveState" in topbar
    assert "activeToolIds" in topbar
    assert "root.dataset.runtime" in topbar


def test_phase7_workspace_activity_datasets() -> None:
    status = STATUS.read_text(encoding="utf-8")
    assert (
        'dataset.living = "10"' in status
        or 'dataset.living = "9"' in status
        or 'dataset.living = "8"' in status
        or 'dataset.living = "7"' in status
    )
    assert "tdl-v2-workspace-dock--living" in status
    assert 'memoryActive ? "remembering"' in status
    assert 'obsidianActive ? "syncing"' in status
    assert 'browserActive ? "searching"' in status
    assert '"engaged"' in status
    assert "activity" in status


def test_phase7_shell_atmosphere() -> None:
    shell = SHELL.read_text(encoding="utf-8")
    assert (
        'dataset.phase = "10"' in shell
        or 'dataset.phase = "9"' in shell
        or 'dataset.phase = "8"' in shell
        or 'dataset.phase = "7"' in shell
    )
    assert (
        'dataset.living = "10"' in shell
        or 'dataset.living = "9"' in shell
        or 'dataset.living = "8"' in shell
        or 'dataset.living = "7"' in shell
    )
    assert "tdl-v2-glow-ambient--living" in shell
    assert "_createLivingComms" in shell
    assert "tdl-v2-living-comms" in shell
    assert "Phase 7" in shell or "Phase 8" in shell or "Phase 9" in shell


def test_phase7_honest_state_only() -> None:
    topbar = TOPBAR.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    for banned in (
        "fetch(",
        "apiFetch",
        "remember_user_note",
        "create_note",
        "POST /api",
    ):
        assert banned not in topbar
        assert banned not in status


def test_phase7_docs_exist() -> None:
    assert DOCS.exists()
    docs = DOCS.read_text(encoding="utf-8")
    assert "Phase 7" in docs
    assert "Living Runtime Experience" in docs
    assert "Idle" in docs
    assert "Thinking" in docs
    assert "Remembering" in docs


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase7_ui_version_bump() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
const ok = ['0.51.0','0.50.0', '0.48.0', '0.47.0', '0.46.0'].includes(TITAN_UI_VERSION);
if (!ok) throw new Error('expected 0.50.0 / 0.48.0 / 0.47.0 / 0.46.0 UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["version"] in {"0.51.0","0.50.0", "0.48.0", "0.47.0", "0.46.0"}


def test_phase7_settings_version_bump() -> None:
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    assert (
        'VERSION = "0.43.0"' in settings
        or 'VERSION = "0.42.0"' in settings
        or 'VERSION = "0.41.0"' in settings
    )


def test_phase7_index_meta_version() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert (
        'content="0.51.0"' in html or 'content="0.50.0"' in html
        or 'content="0.48.0"' in html
        or 'content="0.47.0"' in html
        or 'content="0.46.0"' in html
    )
    assert "Living" in html or "Cognitive Operating System" in html

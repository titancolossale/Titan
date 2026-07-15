# =====================================
# Titan Web V2 — Phase 8 Living Presence Tests
# =====================================

"""Frontend contracts for Phase 8 Living Presence.

Scope guard: presentation only — Core presence markers / satellite packets /
atmosphere particles / workspace wake / orchestrator life / living-presence.css.
No Brain, API, Memory, neural engine rewrite, layout redesign, or color system
changes required.
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
SATELLITES = V2 / "center" / "cognitive-satellites.js"
ORCH = V2 / "orchestrator" / "orchestrator-region.js"
CSS = V2 / "design" / "living-presence.css"
DOCS = ROOT / "docs" / "WEB_APP_LIVING_PRESENCE.md"


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


def test_phase8_living_presence_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/living-presence.css" in html
    assert CSS.exists()
    assert html.index("./design/living-runtime.css") < html.index(
        "./design/living-presence.css"
    )
    assert html.index("./design/living-orchestrator.css") < html.index(
        "./design/living-presence.css"
    )
    # Phase 9 may load after Phase 8 — presence still after runtime/orchestrator.
    if "./design/cognitive-os.css" in html:
        assert html.index("./design/living-presence.css") < html.index(
            "./design/cognitive-os.css"
        )


def test_phase8_living_presence_css_contracts() -> None:
    css = CSS.read_text(encoding="utf-8")
    for token in (
        "Phase 8",
        "LIVING PRESENCE",
        "tdl-lp-core-heartbeat",
        "tdl-lp-core-energy",
        "tdl-lp-core-wave",
        "tdl-lp-particle-drift",
        "tdl-lp-distant-flash",
        "tdl-lp-ambient-breathe",
        "tdl-lp-workspace-wake",
        "tdl-lp-objective-breathe",
        "tdl-lp-pipeline-pulse",
        "tdl-v2-satellite-packet",
        "prefers-reduced-motion",
        "Does not redesign layout",
        "Does not touch Titan Core structure",
    ):
        assert token in css


def test_phase8_shell_atmosphere() -> None:
    shell = SHELL.read_text(encoding="utf-8")
    assert (
        'dataset.phase = "10"' in shell
        or 'dataset.phase = "9"' in shell
        or 'dataset.phase = "8"' in shell
    )
    assert (
        'dataset.living = "10"' in shell
        or 'dataset.living = "9"' in shell
        or 'dataset.living = "8"' in shell
    )
    assert "_createLivingPresence" in shell
    assert "tdl-v2-living-presence" in shell
    assert "tdl-v2-glow-ambient--presence" in shell
    assert "Phase 8" in shell or "Phase 9" in shell


def test_phase8_core_presence_markers() -> None:
    satellites = SATELLITES.read_text(encoding="utf-8")
    assert 'dataset.presence = "8"' in satellites
    assert "tdl-v2-satellite-core__heartbeat" in satellites
    assert "tdl-v2-satellite-core__energy" in satellites
    assert "tdl-v2-satellite-core__wave" in satellites
    assert "tdl-v2-satellite-core__attention" in satellites
    assert "_startPacketLoop" in satellites
    assert "_spawnLightPacket" in satellites
    assert "tdl-v2-satellite-packet-layer" in satellites
    assert "Presentation only" in satellites


def test_phase8_topbar_presence() -> None:
    topbar = TOPBAR.read_text(encoding="utf-8")
    assert "tdl-v2-topbar--presence" in topbar
    assert (
        'dataset.phase = "10"' in topbar
        or 'dataset.phase = "9"' in topbar
        or 'dataset.phase = "8"' in topbar
    )
    assert (
        'dataset.living = "10"' in topbar
        or 'dataset.living = "9"' in topbar
        or 'dataset.living = "8"' in topbar
    )
    assert (
        'root.dataset.living = "10"' in topbar
        or 'root.dataset.living = "9"' in topbar
        or 'root.dataset.living = "8"' in topbar
    )


def test_phase8_workspace_presence() -> None:
    status = STATUS.read_text(encoding="utf-8")
    assert (
        'dataset.living = "10"' in status
        or 'dataset.living = "9"' in status
        or 'dataset.living = "8"' in status
    )
    assert "tdl-v2-workspace-dock--presence" in status
    assert "Phase 8" in status or "Phase 9" in status


def test_phase8_orchestrator_presence() -> None:
    orch = ORCH.read_text(encoding="utf-8")
    assert "tdl-v2-orchestrator--presence" in orch
    assert (
        'dataset.phase = "10"' in orch
        or 'dataset.phase = "9"' in orch
        or 'dataset.phase = "8"' in orch
    )
    assert "tdl-v2-orch-activity-marker" in orch
    assert (
        "no fake execution" in orch.lower()
        or "Phase 8: subtle life" in orch
        or "Phase 9" in orch
    )


def test_phase8_honest_state_only() -> None:
    for path in (TOPBAR, STATUS, SATELLITES, ORCH, SHELL):
        text = path.read_text(encoding="utf-8")
        for banned in (
            "remember_user_note",
            "create_note",
            "POST /api",
        ):
            assert banned not in text


def test_phase8_docs_exist() -> None:
    assert DOCS.exists()
    docs = DOCS.read_text(encoding="utf-8")
    assert "Phase 8" in docs
    assert "Living Presence" in docs
    assert "heartbeat" in docs.lower()
    assert "packet" in docs.lower()


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_phase8_ui_version_bump() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
const ok = ['0.51.0','0.50.0', '0.48.0', '0.47.0'].includes(TITAN_UI_VERSION);
if (!ok) throw new Error('expected 0.50.0 / 0.48.0 / 0.47.0 UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["version"] in {"0.51.0","0.50.0", "0.48.0", "0.47.0"}


def test_phase8_settings_version_bump() -> None:
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    assert 'VERSION = "0.43.0"' in settings or 'VERSION = "0.42.0"' in settings


def test_phase8_index_meta_version() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert (
        'content="0.51.0"' in html or 'content="0.50.0"' in html
        or 'content="0.48.0"' in html
        or 'content="0.47.0"' in html
    )
    assert "Living Presence" in html or "Cognitive Operating System" in html

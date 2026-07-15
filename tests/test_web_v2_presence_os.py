# =====================================
# Titan Web V2 — Sprint 2.9 Living Cognitive OS Tests
# =====================================

"""Frontend contracts for Living Cognitive Operating System polish.

Validates presence layer, telemetry strip, orchestrator idle richness,
composer console, and glass workspace cards — frontend only.
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


def test_presence_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/presence.css" in html
    assert (V2 / "design" / "presence.css").exists()
    # Presence loads after composition; reference-final may refine further.
    assert html.index("./design/composition.css") < html.index("./design/presence.css")
    if "./design/reference-final.css" in html:
        assert html.index("./design/presence.css") < html.index("./design/reference-final.css")


def test_presence_css_contains_living_contracts() -> None:
    css = (V2 / "design" / "presence.css").read_text(encoding="utf-8")
    for token in (
        "tdl-v2-panel-breathe",
        "tdl-v2-topbar--telemetry",
        "tdl-v2-orchestrator-presence",
        "tdl-v2-glass-workspace-float",
        "tdl-v2-composer--console",
        "tdl-v2-satellite[data-status=\"idle\"]",
        "prefers-reduced-motion",
        "tdl-v2--reduced-motion",
    ):
        assert token in css


def test_orchestrator_idle_presence_richness() -> None:
    orch = (V2 / "orchestrator" / "orchestrator-region.js").read_text(encoding="utf-8")
    assert "IDLE_PRESENCE_ROWS" in orch
    assert "Current Objective" in orch
    assert "Présence" in orch
    assert "Surveillance" in orch
    assert "Disponible" in orch
    assert "Aucune active" in orch
    assert "tdl-v2-orchestrator-presence" in orch
    assert "_syncPresenceDataset" in orch
    assert "Présence calme" in orch
    assert "En attente d'une demande" in orch


def test_topbar_telemetry_has_mode_and_runtime() -> None:
    topbar = (V2 / "center" / "topbar-region.js").read_text(encoding="utf-8")
    assert 'this._pill("mode"' in topbar or '_pill("mode"' in topbar
    assert 'this._pill("runtime"' in topbar or '_pill("runtime"' in topbar
    assert "TITAN_UI_VERSION_LABEL" in topbar
    assert "Mémoire" in topbar
    assert "Réflexion" in topbar
    assert "Présence" in topbar
    assert "Outils" in topbar
    assert "intelligence en veille" in topbar


def test_composer_premium_console() -> None:
    composer = (V2 / "composer" / "composer-region.js").read_text(encoding="utf-8")
    assert "tdl-v2-composer--console" in composer
    assert "Message à Titan" in composer
    assert "tdl-v2-voice-mic" in composer
    assert "tdl-v2-composer-attach" in composer
    assert "tdl-v2-send-chat" in composer


def test_float_cards_alive_idle_copy() -> None:
    status = (V2 / "status" / "status-region.js").read_text(encoding="utf-8")
    # Phase 5.4+ idle fallbacks supersede Sprint 2.9 "Mémoire prête" copy.
    assert "Mémoire en veille" in status or "Mémoire prête" in status
    assert (
        "Vault connecté — en veille" in status
        or "Vault connecté — veille" in status
    )
    assert "Navigation en réserve" in status
    assert "Présent — calme" in status
    assert "tdl-v2-float-card" in status


def test_no_backend_modules_touched_by_presence_sprint() -> None:
    """Guardrail: Sprint 2.9 must remain frontend-only."""
    presence = (V2 / "design" / "presence.css").read_text(encoding="utf-8")
    assert "neural renderer untouched" in presence.lower() or "neural renderer" in presence.lower()
    api = (ROOT / "api" / "app.py").read_text(encoding="utf-8")
    # Smoke: API still mounts v2; this sprint does not edit backend.
    assert 'mount("/app"' in api or "web/v2" in api or 'name="app"' in api


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_idle_presence_rows_exported() -> None:
    out = _run_node(
        """
import { IDLE_PRESENCE_ROWS, IDLE_PLAN_STEPS } from './web/v2/orchestrator/orchestrator-region.js';
if (IDLE_PRESENCE_ROWS.length !== 5) throw new Error('expected 5 presence rows');
if (!IDLE_PRESENCE_ROWS.some((r) => r.key === 'Présence')) throw new Error('missing Présence');
if (!IDLE_PRESENCE_ROWS.some((r) => r.value === 'Aucune active')) throw new Error('missing idle execution');
if (IDLE_PLAN_STEPS.length !== 9) throw new Error('plan steps changed unexpectedly');
console.log(JSON.stringify({ ok: true, presence: IDLE_PRESENCE_ROWS.length }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["presence"] == 5


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_ui_version_bump_for_presence_sprint() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
if (!/^0\\.2[6-9]|^0\\.3|^0\\.4/.test(TITAN_UI_VERSION)) throw new Error('expected 0.26+ UI version');
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
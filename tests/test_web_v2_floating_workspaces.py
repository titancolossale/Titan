# =====================================
# Titan Web V2 — Phase 5.4 Floating Cognitive Workspaces Tests
# =====================================

"""Frontend contracts for Phase 5.4 floating cognitive workspaces.

Validates the five workspace cards, real state source wiring, idle fallbacks,
composer preservation, and dock geometry — without Brain/API mutations.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
STATUS = V2 / "status" / "status-region.js"
CSS = V2 / "design" / "floating-workspaces.css"
DOCS = ROOT / "docs" / "WEB_APP_FLOATING_WORKSPACES.md"


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


def test_floating_workspaces_stylesheet_loaded_last() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/floating-workspaces.css" in html
    assert CSS.exists()
    assert html.index("./design/reference-scene.css") < html.index(
        "./design/floating-workspaces.css"
    )
    # Later phases may load after floating-workspaces authority
    for later in ("./design/living-orchestrator.css", "./design/living-runtime.css"):
        if later in html:
            assert html.index("./design/floating-workspaces.css") < html.index(later)


def test_floating_workspaces_css_contracts() -> None:
    css = CSS.read_text(encoding="utf-8")
    for token in (
        "Phase 5.4",
        "FLOATING COGNITIVE WORKSPACES",
        "tdl-v2-workspace-dock",
        "tdl-v2-workspace-card",
        "tdl-fw-breathe",
        "overflow-x: auto",
        "prefers-reduced-motion",
        "max-height: min(42vh, 22rem)",
    ):
        assert token in css


def test_all_five_workspaces_render() -> None:
    status = STATUS.read_text(encoding="utf-8")
    for title in (
        "Mémoire Récente",
        "Obsidian",
        "Browser",
    ):
        assert title in status
    assert "Cognitive State" in status or "État Cognitif" in status
    assert "Presence" in status or "Présence" in status
    for card_id in (
        "card-recent-memory",
        "card-obsidian",
        "card-browser",
        "card-cognitive",
        "tdl-v2-card-presence",
    ):
        assert card_id in status
    assert "tdl-v2-workspace-dock" in status
    assert 'dataset.phase = "5.4"' in status


def test_real_state_sources_remain_connected() -> None:
    status = STATUS.read_text(encoding="utf-8")
    for token in (
        "onStateChanged",
        "onToolActivity",
        "onMemoryActivity",
        "onConversationActivity",
        "getMemoryEngine",
        "getActiveMemories",
        "getActiveTools",
        "presenceLevel",
        "memoryStatusLine",
        "systemsUsed",
        "connectionState",
    ):
        assert token in status


def test_safe_idle_fallbacks_are_presentation_only() -> None:
    status = STATUS.read_text(encoding="utf-8")
    for fallback in (
        "Mémoire en veille",
        "Aucune note récente",
        "Vault connecté — en veille",
        "Navigation en réserve",
        "Aucune recherche active",
        "Présent — en attente",
        "Présent — calme",
        "Activité faible",
        "En attente de Nolan",
    ):
        assert fallback in status
    # Must not invent backend mutations / fake API writes
    for banned in (
        "fetch(",
        "POST",
        "apiFetch",
        "remember_user_note",
        "create_note",
        "activateTool(",
    ):
        assert banned not in status


def test_cards_do_not_cover_titan_core() -> None:
    shell = (V2 / "layout" / "shell.js").read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert 'dataset.role = "floating-workspaces"' in shell
    assert "REGION_IDS.dock" in shell or "dockStatusCards" in shell
    assert "max-height: min(42vh, 22rem)" in css
    assert "tdl-v2-region--dock" in css


def test_responsive_horizontal_behavior() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "overflow-x: auto" in css
    assert "tdl-v2--mode-tablet" in css
    assert "tdl-v2--mode-phone" in css
    assert "scroll-snap-type: x proximity" in css


def test_composer_ids_still_work() -> None:
    composer = (V2 / "composer" / "composer-region.js").read_text(encoding="utf-8")
    manager = (V2 / "conversation" / "conversation-manager.js").read_text(encoding="utf-8")
    assert "tdl-v2-chat-input" in composer
    assert "tdl-v2-send-chat" in composer
    assert "tdl-v2-send-chat" in manager
    assert "tdl-v2-voice-mic" in composer
    assert "SEND" in composer or "Envoyer" in composer


def test_app_still_loads_assets() -> None:
    html = (V2 / "index.html").read_text(encoding="utf-8")
    assert (
        'content="0.51.0"' in html or 'content="0.50.0"' in html or 'content="0.48.0"' in html
        or 'content="0.47.0"' in html
        or 'content="0.46.0"' in html
        or 'content="0.45.0"' in html
        or 'content="0.44.0"' in html
    )
    assert "./main.js" in html
    assert "./design/floating-workspaces.css" in html
    assert (V2 / "main.js").exists()
    assert DOCS.exists()


def test_documentation_covers_phase_contracts() -> None:
    docs = DOCS.read_text(encoding="utf-8")
    for token in (
        "Phase 5.4",
        "component hierarchy",
        "state sources",
        "idle fallback",
        "interaction",
        "responsive",
        "reference",
        "Obsidian",
        "Browser",
        "Cognitive State",
        "Presence",
    ):
        assert token.lower() in docs.lower()
    assert "recent memory" in docs.lower() or "mémoire récente" in docs.lower()


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_ui_version_phase54() -> None:
    out = _run_node(
        """
import { TITAN_UI_VERSION, TITAN_UI_VERSION_LABEL } from './web/v2/core/version.js';
if (!['0.51.0','0.50.0', '0.48.0', '0.47.0', '0.46.0', '0.45.0', '0.44.0'].includes(TITAN_UI_VERSION)) {
  throw new Error('expected 0.47.0 / 0.46.0 / 0.45.0 / 0.44.0');
}
if (!TITAN_UI_VERSION_LABEL.includes(TITAN_UI_VERSION)) throw new Error('bad label');
console.log(JSON.stringify({ ok: true, version: TITAN_UI_VERSION }));
"""
    )
    assert (
        "0.51.0" in out or "0.50.0" in out
        or "0.48.0" in out
        or "0.47.0" in out
        or "0.46.0" in out
        or "0.45.0" in out
        or "0.44.0" in out
    )


@pytest.mark.skipif(not _node_available(), reason="node not available")
def test_memory_idle_and_active_presentation_helpers() -> None:
    out = _run_node(
        """
import { StatusRegion } from './web/v2/status/status-region.js';
import { getMemoryDefinition } from './web/v2/memory/memory-registry.js';

const def = getMemoryDefinition('long_term');
if (!def.title) throw new Error('memory registry missing title');
if (!def.icon) throw new Error('memory registry missing icon');

// StatusRegion must export constructible class with workspace mount helpers
if (typeof StatusRegion !== 'function') throw new Error('StatusRegion missing');
const proto = StatusRegion.prototype;
for (const method of [
  '_memoryCard',
  '_obsidianCard',
  '_browserCard',
  '_cognitiveCard',
  '_presenceCard',
  '_idleMemoryHtml',
  '_updateMemoryUi',
  '_updateToolUi',
  '_updateCognitiveCard',
  '_updatePresenceCard',
]) {
  if (typeof proto[method] !== 'function') throw new Error('missing ' + method);
}

const idle = proto._idleMemoryHtml.call({ _idleMemoryHtml: proto._idleMemoryHtml });
if (!idle.includes('Mémoire en veille')) throw new Error('idle fallback missing');
if (!idle.includes('Aucune note récente')) throw new Error('idle calm state missing');
// Presentation fallback must not invent fake filenames when idle
if (idle.includes('Titan_Context.md')) throw new Error('fabricated memory rows in idle');

console.log(JSON.stringify({ ok: true }));
"""
    )
    assert '"ok":true' in out.replace(" ", "")

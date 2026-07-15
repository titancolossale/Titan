# =====================================
# Titan Web V2 — Canonical Final Reference Tests
# =====================================

"""Frontend contracts for the approved canonical Titan Web App composition.

Scope: presentation reconstruction only. No Brain / API / Memory / runtime rewrite.
Canonical image: docs/design/screenshots/titan-final-canonical-reference.png
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
HTML = V2 / "index.html"
CSS = V2 / "design" / "canonical-final.css"
LOGO_JS = V2 / "components" / "titan-logo.js"
LOGO_SVG = V2 / "assets" / "titan-logo.svg"
SIDEBAR = V2 / "sidebar" / "sidebar-region.js"
TOPBAR = V2 / "center" / "topbar-region.js"
CENTER = V2 / "center" / "center-region.js"
SATELLITES = V2 / "center" / "cognitive-satellites.js"
ORCH = V2 / "orchestrator" / "orchestrator-region.js"
STATUS = V2 / "status" / "status-region.js"
COMPOSER = V2 / "composer" / "composer-region.js"
SHELL = V2 / "layout" / "shell.js"
VERSION = V2 / "core" / "version.js"
API = ROOT / "api" / "app.py"
DOCS = ROOT / "docs" / "TITAN_FINAL_REFERENCE_IMPLEMENTATION.md"
REF_PNG = ROOT / "docs" / "design" / "screenshots" / "titan-final-canonical-reference.png"


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


def test_canonical_reference_image_present() -> None:
    assert REF_PNG.exists()
    assert REF_PNG.stat().st_size > 10_000


def test_canonical_stylesheet_loaded_last() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert "./design/canonical-final.css" in html
    assert CSS.exists()
    assert html.rfind("./design/") == html.rfind("./design/canonical-final.css")
    assert html.index("./design/cognitive-os.css") < html.index("./design/canonical-final.css")


def test_single_production_frontend_root() -> None:
    api = API.read_text(encoding="utf-8")
    assert '"/app"' in api or "'/app'" in api
    assert "web/v2" in api.replace("\\", "/")
    # No second SPA mount invented for this phase
    assert "web/v3" not in api


def test_titan_logo_branding_present() -> None:
    assert LOGO_JS.exists()
    assert LOGO_SVG.exists()
    logo = LOGO_JS.read_text(encoding="utf-8")
    assert "createTitanLogo" in logo
    assert "tdl-v2-brand-mark" in logo
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert "createTitanLogo" in sidebar or "createTitanLogoGlyph" in sidebar
    orch = ORCH.read_text(encoding="utf-8")
    assert "createTitanLogo" in orch


def test_no_decorative_branding_spheres_in_canonical_css() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "Kill decorative branding spheres" in css or "branding spheres" in css
    assert ".tdl-v2-brand-mark" in css
    # Functional status dots remain allowed
    assert "pill-dot" in css or "alive-dot" in css


def test_shell_canonical_dataset() -> None:
    shell = SHELL.read_text(encoding="utf-8")
    assert 'dataset.canonical = "final"' in shell
    assert 'dataset.phase = "10"' in shell


def test_sidebar_region_canonical() -> None:
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert "TITAN" in sidebar
    assert "TITAN PRESENCE" in sidebar
    assert "Je suis prêt. À tes côtés." in sidebar
    assert "Réduire" in sidebar or "RÉDUIRE" in sidebar.upper()
    assert "Chat" in sidebar or "chat" in sidebar


def test_six_top_telemetry_modules() -> None:
    topbar = TOPBAR.read_text(encoding="utf-8")
    for module in ("memory", "reflection", "presence", "tools", "mode", "runtime"):
        assert f'"{module}"' in topbar or f"pill--{module}" in topbar
    for label in ("Mémoire", "Réflexion", "Présence", "Outils", "Cerveau", "Runtime"):
        assert label in topbar
    assert "tdl-v2-topbar__pill-spark" in topbar


def test_titan_core_and_eight_subsystems() -> None:
    sats = SATELLITES.read_text(encoding="utf-8")
    assert 'title: "TITAN CORE"' in sats
    assert "Conscience & Orchestration" in sats
    for name in (
        "MÉMOIRE",
        "PLANIFICATION",
        "NAVIGATION",
        "CALENDAR",
        "OBSIDIAN",
        "TRADING",
        "OUTILS",
        "COMMUNICATION",
    ):
        assert name in sats
    center = CENTER.read_text(encoding="utf-8")
    assert "Activité Neurale" in center or "Activité neurale" in center
    assert "Focus" in center


def test_cognitive_orchestrator_nine_pipeline_steps() -> None:
    orch = ORCH.read_text(encoding="utf-8")
    steps = [
        "Compréhension",
        "Analyse",
        "Planification",
        "Collecte d'informations",
        "Synthèse",
        "Génération",
        "Validation",
        "Réponse",
        "Apprentissage",
    ]
    for step in steps:
        assert step in orch
    assert "Objectif Actuel" in orch
    assert "Pipeline d'Exécution" in orch
    assert "Systèmes Connectés" in orch
    assert "Comprendre et assister" in orch
    for status in ("Terminé", "Active", "En attente", "Erreur"):
        assert status in orch


def test_five_floating_workspaces() -> None:
    status = STATUS.read_text(encoding="utf-8")
    for title in (
        "Mémoire Récente",
        "Obsidian Vault",
        "Browser",
        "État Cognitif",
        "Présence",
    ):
        assert title in status
    assert "card-recent-memory" in status
    assert "card-obsidian" in status
    assert "card-browser" in status
    assert "card-cognitive" in status
    assert "tdl-v2-card-presence" in status


def test_composer_functional_contracts() -> None:
    composer = COMPOSER.read_text(encoding="utf-8")
    assert "Message à Titan" in composer
    assert "tdl-v2-send-chat" in composer
    assert "tdl-v2-chat-input" in composer
    assert "tdl-v2-voice-mic" in composer


def test_bottom_technical_strip_labels() -> None:
    status = STATUS.read_text(encoding="utf-8")
    for token in ("FPS", "BRAIN", "MEMORY", "TOOLS", "RUNTIME"):
        assert token in status


def test_honest_idle_fallbacks() -> None:
    telemetry = (V2 / "core" / "cognitive-os-telemetry.js").read_text(encoding="utf-8")
    assert "Comprendre et assister" in telemetry
    assert "never invents" in telemetry.lower() or "Never invents" in telemetry
    orch = ORCH.read_text(encoding="utf-8")
    assert "Analyser la demande, orchestrer les ressources nécessaires" in orch


def test_reduced_motion_support() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css


def test_responsive_desktop_first() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "desktop fidelity" in css.lower() or "max-width: 1280px" in css


def test_documentation_present() -> None:
    assert DOCS.exists()
    docs = DOCS.read_text(encoding="utf-8")
    assert "canonical" in docs.lower()
    assert "titan-final-canonical-reference.png" in docs


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_canonical_version_exports() -> None:
    out = _run_node(
        """
import {
  TITAN_UI_VERSION,
  TITAN_PRODUCT_VERSION,
  TITAN_UI_VERSION_LABEL,
} from './web/v2/core/version.js';
if (TITAN_UI_VERSION !== '0.51.0') throw new Error('expected UI 0.51.0');
if (TITAN_PRODUCT_VERSION !== '0.43.0') throw new Error('expected product 0.43.0');
if (!TITAN_UI_VERSION_LABEL.includes('0.43.0')) throw new Error('brand label');
console.log(JSON.stringify({
  ok: true,
  ui: TITAN_UI_VERSION,
  product: TITAN_PRODUCT_VERSION,
  label: TITAN_UI_VERSION_LABEL,
}));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert payload["ui"] == "0.51.0"
    assert payload["product"] == "0.43.0"


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_pipeline_steps_export_count() -> None:
    out = _run_node(
        """
import { IDLE_PLAN_STEPS } from './web/v2/orchestrator/orchestrator-region.js';
if (IDLE_PLAN_STEPS.length !== 9) throw new Error('expected 9 steps');
console.log(JSON.stringify({ ok: true, steps: IDLE_PLAN_STEPS }));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["ok"] is True
    assert len(payload["steps"]) == 9


def test_logo_factory_contracts() -> None:
    logo = LOGO_JS.read_text(encoding="utf-8")
    assert "export function createTitanLogo" in logo
    assert "export function createTitanLogoGlyph" in logo
    assert "tdl-v2-brand-mark" in logo

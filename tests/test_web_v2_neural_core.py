# =====================================
# Titan Web V2 Living Neural Core Tests
# =====================================

"""Sprint 2 tests — Living Neural Core V1 (central neural experience).

The frontend is browser-native ES modules with no build step, so these tests
combine static source contracts (structure that must hold) with Node-based unit
tests of the pure NeuralStatusAdapter (skipped when Node.js is unavailable).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"

SATELLITE_IDS = (
    "memory",
    "planning",
    "browser",
    "obsidian",
    "tools",
    "communication",
    "trading",
    "calendar",
)


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


# --- Static source contracts -------------------------------------------------


def test_status_adapter_defines_behaviors_and_satellites() -> None:
    content = (V2 / "center" / "neural-status-adapter.js").read_text(encoding="utf-8")
    for behavior in ("IDLE", "LISTENING", "THINKING", "EXECUTING", "ERROR", "OFFLINE"):
        assert behavior in content
    assert "resolveNeuralStatus" in content
    assert "resolveBehavior" in content
    for satellite in SATELLITE_IDS:
        assert satellite in content


def test_cognitive_satellites_define_full_ring() -> None:
    content = (V2 / "center" / "cognitive-satellites.js").read_text(encoding="utf-8")
    assert "class CognitiveSatellite" in content
    assert "class CognitiveSatelliteField" in content
    # Sprint 2.7 Titan Core label and subtitle.
    assert "TITAN CORE" in content
    assert (
        "Conscience & Orchestrateur" in content
        or "Conscience & Orchestration" in content
    )
    # Canonical / Sprint 2.7 subsystem roster (French or English labels).
    for name in (
        "OBSIDIAN",
        "COMMUNICATION",
        "TRADING",
        "CALENDAR",
    ):
        assert name in content
    assert "MEMORY" in content or "MÉMOIRE" in content
    assert "PLANNING" in content or "PLANIFICATION" in content
    assert "BROWSER" in content or "NAVIGATION" in content
    assert "TOOLS" in content or "OUTILS" in content
    # Statuses are IDLE / ACTIVE / WAITING.
    for status in ("IDLE", "ACTIVE", "WAITING"):
        assert status in content
    # Clicking emits a frontend event for future panels (no navigation).
    assert "titan:satellite-select" in content


def test_satellite_stylesheet_uses_red_tokens_and_reduced_motion() -> None:
    content = (V2 / "design" / "satellites.css").read_text(encoding="utf-8")
    assert "tdl-v2-satellite-core__title" in content
    assert "tdl-v2-satellite-link" in content
    # Canonical red identity tokens, never purple/blue.
    assert "--tdl-red" in content
    assert "purple" not in content.lower()
    assert "blue" not in content.lower()
    # Reduced motion must retain a readable static state.
    assert "reduced-motion" in content
    assert "prefers-reduced-motion" in content
    for behavior in ("OFFLINE", "ERROR", "LISTENING", "THINKING", "EXECUTING"):
        assert behavior in content


def test_index_html_loads_satellite_layer() -> None:
    content = (V2 / "index.html").read_text(encoding="utf-8")
    assert "./design/satellites.css" in content


def test_center_region_reads_state_and_cleans_up() -> None:
    content = (V2 / "center" / "center-region.js").read_text(encoding="utf-8")
    assert "resolveNeuralStatus" in content
    assert "CognitiveSatelliteField" in content
    # Pointer parallax must respect reduced motion.
    assert "reducedMotion" in content
    # Cleanup on unmount: listener removal + unsubscribe + field teardown.
    assert "destroy()" in content
    assert "removeEventListener" in content
    assert "_unsubscribe" in content


def test_neural_stage_pointer_parallax_and_cleanup() -> None:
    content = (V2 / "neural" / "stage.js").read_text(encoding="utf-8")
    assert "pointermove" in content
    assert "setPointerParallax" in content
    assert "removeEventListener" in content
    assert "cancelAnimationFrame" in content


def test_camera_pointer_parallax_respects_reduced_motion() -> None:
    content = (V2 / "neural" / "camera.js").read_text(encoding="utf-8")
    assert "setPointerParallax" in content
    assert "prefersReducedMotion" in content


def test_single_neural_renderer_no_duplication() -> None:
    """Only one canvas neural engine may be instantiated across the frontend."""
    engine_instantiations = 0
    for path in V2.rglob("*.js"):
        engine_instantiations += path.read_text(encoding="utf-8").count("new NeuralEngine(")
    assert engine_instantiations == 1, (
        f"expected a single NeuralEngine instantiation, found {engine_instantiations}"
    )


def test_app_destroy_tears_down_center_region() -> None:
    content = (V2 / "core" / "app.js").read_text(encoding="utf-8")
    assert "this._regions.center.destroy?.()" in content


# --- Sprint 2.1: Neural Core Visual Correction -------------------------------


def test_edge_tracer_uses_screen_space_control_points() -> None:
    """Root cause of the diagonal streaks: world-space control points drawn
    against screen-space endpoints. traceEdge must now take explicit control
    points and the renderer must project them consistently."""
    bezier = (V2 / "neural" / "bezier.js").read_text(encoding="utf-8")
    # New signature carries screen-space control points; no world-space
    # `edge.cp1x` read inside the tracer anymore.
    assert "export function traceEdge(ctx, pa, pb" in bezier
    assert "edge.cp1x" not in bezier.split("export function traceEdge")[1]

    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    # The renderer projects control points to screen space before tracing.
    assert "_edgeControls(" in renderer
    assert "_screenXY(" in renderer
    # Every traceEdge call passes projected endpoints + controls (never a raw
    # edge object, which was the streak bug).
    assert "traceEdge(ctx, e, pa, pb)" not in renderer
    assert "traceEdge(ctx, pa, pb, controls" in renderer


def test_no_full_screen_speed_line_layer() -> None:
    """Connections must stay short/medium and only span adjacent depth layers,
    so no single pathway crosses the whole workspace."""
    config = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    match = re.search(r"connectionMaxDistRatio:\s*([0-9.]+)", config)
    assert match, "connectionMaxDistRatio not found"
    assert float(match.group(1)) <= 0.16

    nodes = (V2 / "neural" / "nodes.js").read_text(encoding="utf-8")
    # Edges only connect adjacent layers (large parallax gaps stretched edges).
    assert "Math.abs(na.layer - nb.layer) <= 1" in nodes


def test_titan_core_present_in_renderer_and_config() -> None:
    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    assert "_drawNeuralCore(" in renderer
    core = (V2 / "neural" / "core.js").read_text(encoding="utf-8")
    assert "class NeuralCore" in core
    config = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    assert "whiteCenterRadius" in config
    assert "auraMaxScreenPx" in config


def test_neural_organism_not_star_topology() -> None:
    """Sprint 2.6 / Phase 5.2 — galactic field with voids, not a radial star or yarn-ball."""
    core = (V2 / "neural" / "core.js").read_text(encoding="utf-8")
    assert "buildCoreTissue" in core
    assert "Star topology" not in core
    assert "radial: true" not in core
    assert "not a separate brain object" in core.lower()

    tissue = (V2 / "neural" / "tissue.js").read_text(encoding="utf-8")
    assert "buildCoreTissue" in tissue
    assert "buildFieldTissue" in tissue
    assert "_seedDensityPockets" in tissue
    assert "_microScribble" in tissue
    # Phase 5.2: intentional voids + fringe (not uniform void-fill).
    assert "_voidFringeWisp" in tissue or "_voidFillWisp" in tissue
    assert "_seedMajorColonies" in tissue or "_seedGalaxies" in tissue or "_seedFieldPockets" in tissue
    assert "veryFar" in tissue

    renderer = (V2 / "neural" / "renderer.js").read_text(encoding="utf-8")
    assert "_drawCoreTissue(" in renderer
    assert "_drawFieldTissue(" in renderer
    assert "_drawMicroNeurons(" in renderer
    assert 'veryFar"' in renderer or '"veryFar"' in renderer
    assert "Radial consciousness axons" not in renderer
    assert "star topology" not in renderer.lower()
    # Removed circular energy-ring aura / white-hot orb heart.
    assert "energyRingCount" not in renderer
    assert "whiteR * 6.5" not in renderer

    config = (V2 / "neural" / "config.js").read_text(encoding="utf-8")
    assert "coreStrandCount" in config
    assert "maxTissueDrawn" in config
    assert "asymmetry" in config
    assert "energyRingCount: 0" in config
    assert "voidCount" in config or "voidFillCount" in config
    assert "veryFarStrandCount" in config

def test_organic_density_gradient_is_center_biased() -> None:
    nodes = (V2 / "neural" / "nodes.js").read_text(encoding="utf-8")
    # Center-biased, jittered sampling — not a uniform grid or starburst.
    assert "_samplePosition(" in nodes
    assert "Math.pow(Math.random()" in nodes


def test_satellite_cards_are_lightweight_not_heavy_panels() -> None:
    content = (V2 / "design" / "satellites.css").read_text(encoding="utf-8")
    # Satellites embed in the field: transparent container at rest, luminous node.
    assert "background: transparent;" in content
    assert "tdl-v2-satellite__node" in content


# --- Pure adapter unit tests (Node) ------------------------------------------


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_adapter_default_state_is_idle() -> None:
    out = _run_node(
        """
import { resolveNeuralStatus, NEURAL_BEHAVIORS } from './web/v2/center/neural-status-adapter.js';
const r = resolveNeuralStatus({});
if (r.behavior !== NEURAL_BEHAVIORS.IDLE) throw new Error('expected IDLE, got ' + r.behavior);
const allIdle = Object.values(r.satellites).every((s) => s === 'idle');
if (!allIdle) throw new Error('expected all satellites idle');
console.log(JSON.stringify({ ok: true }));
"""
    )
    assert json.loads(out.splitlines()[-1])["ok"] is True


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_adapter_graceful_fallback_on_unknown_state() -> None:
    out = _run_node(
        """
import { resolveNeuralStatus } from './web/v2/center/neural-status-adapter.js';
const r = resolveNeuralStatus({ cognitiveState: 'totally-unknown', presence: 'weird' });
console.log(r.behavior);
"""
    )
    assert out.splitlines()[-1] == "IDLE"


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_adapter_visual_state_transitions() -> None:
    out = _run_node(
        """
import { resolveNeuralStatus } from './web/v2/center/neural-status-adapter.js';
const results = {
  listening: resolveNeuralStatus({ cognitiveState: 'listening' }),
  thinking: resolveNeuralStatus({ cognitiveState: 'reasoning' }),
  executing: resolveNeuralStatus({ cognitiveState: 'tool_execution', activeToolCount: 1, activeToolIds: ['browser'] }),
  error: resolveNeuralStatus({ lastError: 'boom' }),
  offline: resolveNeuralStatus({ bootComplete: true, connectionState: 'disconnected' }),
};
console.log(JSON.stringify({
  listening: results.listening.behavior,
  listeningComm: results.listening.satellites.communication,
  thinking: results.thinking.behavior,
  thinkingPlanning: results.thinking.satellites.planning,
  thinkingMemory: results.thinking.satellites.memory,
  executing: results.executing.behavior,
  executingTools: results.executing.satellites.tools,
  executingBrowser: results.executing.satellites.browser,
  error: results.error.behavior,
  offline: results.offline.behavior,
}));
"""
    )
    payload = json.loads(out.splitlines()[-1])
    assert payload["listening"] == "LISTENING"
    assert payload["listeningComm"] == "active"
    assert payload["thinking"] == "THINKING"
    assert payload["thinkingPlanning"] == "active"
    assert payload["thinkingMemory"] == "active"
    assert payload["executing"] == "EXECUTING"
    assert payload["executingTools"] == "active"
    assert payload["executingBrowser"] == "active"
    assert payload["error"] == "ERROR"
    assert payload["offline"] == "OFFLINE"


@pytest.mark.skipif(not _node_available(), reason="Node.js not installed")
def test_adapter_online_connection_is_not_offline() -> None:
    out = _run_node(
        """
import { resolveNeuralStatus } from './web/v2/center/neural-status-adapter.js';
const r = resolveNeuralStatus({ bootComplete: true, connectionState: 'connected' });
console.log(r.behavior);
"""
    )
    assert out.splitlines()[-1] == "IDLE"

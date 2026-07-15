# Titan Web App — Living Neural Core

**Phase:** Titan Web App Finalization — Neural Core Master Polish  
**Frontend:** `web/v2/` (single production frontend — evolved in place)  
**Served at:** `http://127.0.0.1:8000/app/` (redesign target) and `/v2` (same sources)

This document describes the central neural experience of the Titan web app: the
living neural field, its cognitive satellites, and how they read from existing
frontend state. It is a **frontend-only** evolution — the Brain, Cognitive
Operating System, and every reasoning subsystem are unchanged. No second neural
renderer was introduced; Sprint 2 extends the existing canvas engine and adds a
restrained DOM overlay on top of it. Sprint 2.1 corrected axon coordinate space;
**Sprint 2.3** transformed the renderer into a living organic intelligence;
**Sprint 2.4** moved toward full-canvas tissue; **Sprint 2.5** removed the
separate “brain object”; **Sprint 2.6** densifies continuous edge-to-edge tissue;
**Neural Core Master Polish (v0.51.0)** raises microscopic density, organic colonies,
curved neural highways, Core gravity, soft volumetric bloom, and cinematic atmosphere
so the field reads as a living artificial intelligence — not a background
(see `docs/LIVING_NEURAL_INTELLIGENCE.md`).

---

## 0. Sprint 2.1 — Neural Core Visual Correction

### 0.1 Why the "speed-line" appearance was removed

The previous build rendered large bright diagonal red/white streaks that crossed
the entire workspace, making the stage look like a warp/speed effect instead of a
living network. The **root cause was a coordinate-space mismatch in the Bézier
axon tracer** (`neural/bezier.js → traceEdge`):

- Edge control points (`edge.cp1x/cp1y/cp2x/cp2y`) are computed and stored in
  **world space** (`buildOrganicControls`).
- Edge endpoints passed to `traceEdge` were already projected to **screen space**
  (`camera.worldToScreen` minus padding).
- `traceEdge` then called `bezierCurveTo` with the **world-space** control points
  against the **screen-space** endpoints.

Because world→screen is a translation of roughly `2 × padding × viewport` plus a
per-layer parallax offset, every edge's control points landed hundreds of pixels
away from its endpoints. The Bézier curve therefore swung far off toward the
control point and back — producing long diagonal beams spanning the viewport. The
brighter an edge's glow (foreground/core edges), the more prominent the streak,
which is why the effect read as white-hot speed lines.

### 0.2 The fix

`traceEdge` now takes **screen-space control points** and the renderer projects
them consistently with the endpoints:

- `NeuralRenderer._screenXY()` projects any world point through the same camera
  transform used for node endpoints.
- `NeuralRenderer._edgeControls()` projects `cp1` with node A's parallax and
  `cp2` with node B's parallax, so every axon stays anchored to its two nodes.
- `traceEdge(ctx, pa, pb, c1, c2)` falls back to a straight `lineTo` when an edge
  has no control points, so it can never fling a curve off-screen again.

With endpoints and control points in the same space, curves are now short, local
and organic — no pathway spans the whole display.

### 0.2.1 Core hierarchy

Titan Core is the unambiguous centre of gravity — a **dense region of one
continuous field**, not a bright point, radial hub, yarn-ball, or glowing orb.
On the canvas (`renderer.js → _drawNeuralCore`) brightness emerges from overlapping
local pocket tissue (`tissue.js → buildCoreTissue`), short hub synapses, and
microscopic neuron dust — with no circular aura rings and no white-hot nucleus.
The DOM label (`design/satellites.css`) remains readable. Full-canvas atmospheric
tissue (`buildFieldTissue`) blends into the dense region without a hard boundary.

### 0.2.2 Depth layers

Depth is built from six restrained parallax layers (`config.layers`, `abyss →
foreground`) mapped onto four conceptual bands (**very far / far / medium / near**)
plus tissue strands (`veryFar`, `far`, `mid`, `bridge`, `near`) that differ in
opacity, radius, drift, blur, fog dimming and parallax. Soft multi-patch depth fog,
foreground occlusion fog, and a restrained edge vignette (`renderer.js`) support
atmosphere without carving a center object. Distant neurons stay faint and slow;
foreground neurons are brighter; brightness in the dense region emerges from
overlapping microscopic tissue. Very slow camera drift/breathe and subtle pointer
parallax create movement without a flat-wallpaper feel.

### 0.2.3 Satellite connection design

The eight cognitive satellites are embedded in the field rather than sitting on
it as cards: containers are near-transparent at rest, the luminous node is the
dominant element, and each satellite is joined to the core by an SVG neural link
whose endpoints are measured from the rendered geometry. Active state brightens
both the node and its link; idle stays visible but restrained (see §5).

### 0.2.4 Performance implications

All existing protections are preserved: adaptive node density, `render.maxDpr`
cap, hidden-tab pause, resize handling, lifecycle cleanup, reduced-motion
support and graceful fallback. Sprint 2.6 raises density and tissue budgets
substantially while keeping shorter connection distances and adaptive density
floors so the engine can back off under frame pressure.

### 0.3 Supporting refinements

- **Short/medium connections only** — `world.connectionMaxDistRatio` kept short
  (`≤ 0.16`, currently ~0.058), and edges may only connect **adjacent** depth
  layers (`|Δlayer| ≤ 1`). Large parallax gaps stretched edges; both stay bounded.
- **Restrained motion** — impulse speeds stay moderate; white-hot edge halo
  overlays remain cut back so active axons stay meaningful.
- **Continuous density ramp** — `NeuralNodes._samplePosition()` mixes a soft center
  bias, region pockets, ~140 micro-ganglia, and edge/void fill; no grid, starburst,
  or empty black frame around a hot nucleus.
- **Thousands of synaptic bridges** — procedural `tissue.bridgeCount` + dendrite
  branches + void-fill wisps keep the canvas microscopically alive edge to edge.

---

## 0.4 Sprint 2.6 — Continuous living tissue

Sprint 2.6 targets the remaining “neural object in the centre” read:

1. Neuron density increased roughly **2–3×** (adaptive ~5600–14500).
2. Many more tiny local clusters across the whole viewport (`microSeedCount ~140`).
3. Wider soft density scale + void-fill tissue erase center/field separation.
4. Tissue bands cover **edge to edge** (`veryFar` → `near` + dust + void fill).
5. Density ramps gradually toward an asymmetric focus (`clusterPower ~1.22`).
6. ~1400 tiny synaptic bridges plus denser node mesh and dendrites.
7. Explicit void-fill strands eliminate remaining empty black pockets.
8. Four depth bands with distinct opacity and parallax.
9. Brightness from overlapping density — multi-patch haze, near-zero bloom, dim anchor.
10. Connections stay short, curved, irregular, and biologically local.

## 1. Visual Philosophy

Titan's workspace is an **artificial neural intelligence operating inside a deep
black digital space** — not a background image, particle demo, glowing circle,
screensaver, or dashboard chart. It must feel alive *before* the user interacts.

- **Pure black void** (`--tdl-bg-void: #030303`) with strong depth.
- **Premium red identity** — deep Titan red for structure, bright red for active
  energy, controlled white‑red at the core. No purple, no blue, no bright gray.
- **Thousands of neural points** — uneven distribution, soft density ramp toward
  an asymmetric focus, continuous micro-clusters edge to edge.
- **Restrained cognitive satellites** embedded in the field, linked back to the dense region.
- **Calm motion** — slow, organic, GPU‑conscious; more active only when Titan is
  working; fully respectful of `prefers-reduced-motion`.

Glow is used sparingly so that genuinely active elements stay meaningful, and the
whole stage remains readable behind the floating panels that future sprints add.
Brightness in the dense region emerges from overlapping tissue — never from a
glowing orb.

---

## 2. Component Architecture

The neural experience is split into **rendering**, **state adaptation**, **visual
configuration**, **interaction**, and **accessibility**, each in its own place.

```
NeuralStage (neural/stage.js)                ← mount + pointer parallax + lifecycle
└── NeuralEngine (neural/engine.js)          ← STATE · WORLD · CAMERA · RENDERER orchestrator
    ├── NeuralState (neural/state.js)        ← master + cognitive state, intensity, breathe
    ├── NeuralCamera (neural/camera.js)      ← cinematic drift, breathe, recall dive, pointer parallax
    ├── NeuralNodes (neural/nodes.js)        ← organic node/edge field (the neural network)
    ├── NeuralSignals (neural/signals.js)    ← travelling impulses (the neural impulse layer)
    ├── DepthField (neural/depth.js)         ← infinite depth, ghosts, fog
    ├── CognitiveOverlay (neural/cognitive.js)
    └── NeuralRenderer (neural/renderer.js)  ← Canvas 2D pipeline (core, field, impulses, fog, vignette)

CenterRegion (center/center-region.js)       ← DOM overlay owner (reads state only)
├── CognitiveSatelliteField (center/cognitive-satellites.js)
│   ├── Titan Core label ("TITAN CORE" / "Cognitive Operating System")
│   ├── CognitiveSatellite ×8 (node + label + status + tooltip + click event)
│   └── SVG neural links (satellite → core, geometry measured from the DOM)
└── NeuralStatusAdapter (center/neural-status-adapter.js)  ← pure state → visual mapping

design/satellites.css                        ← all satellite/core/link visual tokens
```

**No inline design styling and no duplicated tokens** — colors, spacing, glow and
motion all come from `design/tokens.css`; satellite geometry lives only in
`design/satellites.css` and the SVG links measure the rendered positions so there
is a single source of truth. The only runtime `style.transform` writes are the
camera transform (pre‑existing) and the pointer‑parallax translate, matching the
existing engine pattern.

---

## 3. Rendering Approach

The neural field, Titan Core, impulses, depth, fog and vignette are all drawn on a
**single Canvas 2D** surface (`neural/renderer.js`), the renderer that has always
powered Titan's core. Canvas 2D was kept deliberately:

- It is the **existing, project‑native** renderer — reusing it avoids a second
  competing implementation and needs **no large third‑party graphics dependency**.
- It already implements the layered depth model, adaptive density, the organic
  (non‑grid) node field, travelling impulses, and the cognitive overlay.

Sprint 2 layers a **thin DOM overlay** (satellites, Titan Core label, neural
links) over the canvas. Text labels and interactive nodes are far better as
accessible DOM (focusable buttons, tooltips, ARIA) than as canvas pixels, and they
stay crisp at any DPR. The neural links are an SVG `<line>` per satellite whose
endpoints are measured from the rendered geometry.

---

## 4. Neural / Behavior States

The stage supports six behavior modes. They are derived from **existing frontend
state** by the pure `NeuralStatusAdapter` and always fall back to `IDLE`.

| Behavior | Trigger (from `StateStore`) | Feel |
|----------|-----------------------------|------|
| `IDLE` | default / `cognitiveState: idle` | slow breathing, minimal impulses, faint satellites — awake and waiting |
| `LISTENING` | `cognitiveState: listening`/`voice`, `presence: listening` | gentle inward pulses, Communication satellite active |
| `THINKING` | `thinking`/`reasoning`/`planning`/`writing`/`memory_recall`, `recallActive` | focused activity; Reasoning/Memory/Knowledge/World Model illuminate |
| `EXECUTING` | active tools, or `tool_execution`/`browser_research`/`obsidian`/`calendar`/`trading` | directional pathways; Tools/Workflow active |
| `ERROR` | `lastError` present | restrained warning pulse, no aggressive flashing |
| `OFFLINE` | `bootComplete` and `connectionState` not live | reduced brightness, minimal movement, status visible |

The canvas master/cognitive states (`neural/cognitive.js`) continue to drive the
richer canvas visuals; the behavior mode above is the coarse, satellite‑facing
projection. If runtime state is missing or unknown, the adapter yields `IDLE`
with every satellite idle — the stage never crashes or invents backend state.

---

## 5. Cognitive Satellite System

Eight restrained satellites ring the Titan Core. **In this sprint they are visual
representations only** — no new backend capability is created.

`MEMORY` · `REASONING` · `PLANNING` · `KNOWLEDGE` · `WORLD MODEL` · `TOOLS` ·
`COMMUNICATION` · `WORKFLOW`

Each satellite has a luminous node, a short label, a status (`IDLE` / `ACTIVE` /
`WAITING`), a neural link to the core (brighter when active), and a tooltip
(name, role, current status). Status is resolved per‑satellite from the current
cognitive state and active tools:

- **ACTIVE** — the satellite maps to the current cognitive state or an active tool
  (e.g. `memory_recall` → Memory + Knowledge; `tool_execution` + `browser` →
  Tools + Workflow + Knowledge).
- **WAITING** — a supporting satellite for the current behavior that is warming up
  but not yet primary (e.g. during `THINKING`, Memory/Knowledge/World Model).
- **IDLE** — otherwise.

### Interaction

- **Pointer parallax** — a subtle reaction to pointer movement nudges the canvas
  camera and translates the satellite field for depth (disabled under reduced
  motion).
- **Hover / focus** — emphasis on the satellite and its tooltip.
- **Click** — emits a bubbling `titan:satellite-select` `CustomEvent`
  (`detail: { id, title, role, status }`) for future panels. It performs **no
  navigation and no business logic** in this sprint.

---

## 6. Performance Strategy

Performance protections are inherited from the engine and extended for the
overlay:

- **Adaptive density** — node count and depth budget auto‑adjust to hold the
  frame budget (`neural/config.js → performance`), targeting ~60 FPS with graceful
  degradation on weaker hardware.
- **Device pixel ratio cap** — `render.maxDpr = 2`.
- **Hidden‑tab pause** — the animation loop stops on `visibilitychange` and
  resumes cleanly.
- **rAF throttling** — pointer parallax (both camera and satellite field) is
  throttled to one update per frame.
- **Lifecycle cleanup** — `NeuralStage.destroy()` and `CenterRegion.destroy()`
  cancel animation frames, remove `pointermove`/`resize` listeners, unsubscribe
  from the store, and tear down satellites — no leaked frames or listeners.
- **Non‑blocking** — browser‑native ES modules + CSS, no build step; the overlay
  reads state and never blocks page load or the chat input region.

---

## 7. Accessibility & Reduced Motion

- The satellite host is a labeled `role="group"`; each satellite is a focusable
  `<button>` with an `aria-label` (name — role — status) and a `role="tooltip"`
  description. Purely decorative canvas and glow layers stay `aria-hidden`.
- Under `prefers-reduced-motion` (media query **and** the app's `reducedMotion`
  state): parallax is disabled, the camera holds centered, satellite/core/link
  pulse animations stop, and a **readable static neural state** is retained.

---

## 8. Future Backend Telemetry Integration

Satellites are presentation‑only today but are designed to bind to real telemetry
later without a second renderer:

- Map live subsystem activity (Memory, Reasoning, Planning, Knowledge Learning,
  World Model, Tool Execution, Communication, Autonomous Workflow) onto satellite
  `ACTIVE`/`WAITING` status via the existing status/SSE channels.
- Feed the `titan:satellite-select` event into the future right‑hand orchestrator
  and inspector panels (Sprint 3+).
- Surface per‑satellite metrics (load, last activity) in the tooltip once the
  Brain exposes them through the Web API.

---

## Related Documents

- `docs/WEB_APP_LAYOUT.md` — layout foundation (Sprint 1)
- `docs/LIVING_NEURAL_INTELLIGENCE.md` — Sprint 2.3 living organism visual authority
- `docs/WEB_RUNTIME.md` — Web Runtime V1 (API, auth, streaming, request flow)
- `docs/design/TITAN_NEURAL_ENGINE.md` — neural engine design reference
- `docs/ARCHITECTURE.md` — runtime execution paths

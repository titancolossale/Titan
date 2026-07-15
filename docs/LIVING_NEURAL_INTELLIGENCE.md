# Living Neural Intelligence

**Phase:** Titan Web App Finalization — Neural Core Master Polish (v0.51.0)  
**Frontend:** `web/v2/neural/` + `web/v2/center/` + `web/v2/design/satellites.css`  
**Status:** Authoritative visual specification for Titan’s living cognitive field

This work is **frontend-only**. Brain, Memory, API, Reasoning Engine, Workflow Engine,
World Model, and Meta-Cognition are unchanged. No second renderer was introduced —
the existing Canvas 2D neural engine evolved in place.

**Master Polish purpose:** Titan Core is the visual gravity center of the application —
a living artificial intelligence, not an animated wallpaper. Density, organic colonies,
curved highways, cinematic depth (5+ layers), soft Core bloom, and neural atmosphere
are tuned so the first impression is “I am looking at a living AI.” There is still no
separate central “brain object,” yarn-ball silhouette, glowing orb plate, or hard radial
boundary. Brightness emerges from overlapping tissue attracted toward the Core.

---

## 1. Visual Philosophy

Titan’s workspace is not a dashboard with a decorative background.

It is a **living artificial nervous system** made visible.

- The neural field **is** Titan thinking — not wallpaper.
- Pure black dominates; Titan red guides attention; heat comes from **collective density**, not artificial light sources.
- Motion is organic, continuous, and restrained — never cinematic lens flares, never
  a full-field flash, never a geometric mesh, force graph, constellation, or crystal lattice.
- Idle life never goes still: breathing, micro-flickers, dust, slow impulses.
- Thinking and execution amplify **local** activity only.

Users should feel they are looking into continuous tissue the moment the app opens.
They must **never** think “there is a ball of neurons in the middle.”

---

## 2. Depth System

Spatial depth is built from **four conceptual bands** (implemented as six parallax
node layers + tissue bands):

| Band | Layers / tissue | Feel |
|------|-----------------|------|
| Very far | `abyss`, veryFar strands + dust axons | Faintest dust — infinity beyond the viewport |
| Far | `deep`, far strands + void-fill | Soft slow tissue still filling the frame |
| Medium | `background` / `midground`, mid strands + bridges | Readable synapses, moderate brightness |
| Near | `near` / `foreground`, near strands | Larger neurons, higher opacity, nearby activity |

Dense cognitive heat emerges where microscopic pockets overlap — not from a drawn
sphere. Soft multi-patch haze, depth fog, dust, vignette, and restrained bloom
support atmosphere without carving an object.

Camera breathe, cinematic drift, and pointer parallax create subtle depth parallax
so space never reads as a flat wallpaper.

---

## 3. Neural Field (Living Tissue, Not a Graph)

The field is **biological tissue**, not a particle graph:

- Thousands of neurons (adaptive ~7200–16800) with **variable size and brightness**
- **Irregular neural colonies** of mixed sizes — never grids, never clock symmetry
- **Procedural filaments** (`tissue.js`) — local scribbles, micro bridges, secondary /
  tertiary twigs, multi-segment curved highways, far dust axons
- Dense local synapses + short neural bridges fill gaps; soft voids breathe without
  looking empty
- Adjacent-layer edges only — no long warp streaks across the viewport
- Variable synapse opacity with soft fade / reappear for idle life
- Soft Core bloom + red fog + micro dust + foreground bokeh for cinematic depth

No visible grid. No polygon mesh. No star topology. No yarn-ball. No circular boundary
around Titan Core. No empty black halo separating “the brain” from “the background.”

---

## 4. Titan Core Hierarchy (Density, Not Object)

Titan Core is the **dense region of one continuous field** — hundreds of overlapping
local clusters that merge, branch, and fade into the surrounding network.

1. Asymmetric soft density peak (`config.core.asymmetry`) with a **wide gradual ramp**
2. Overlapping microscopic pocket tissue (`buildCoreTissue` → local ganglia)
3. Dense nearest-neighbor hub synapses (short local mesh only)
4. Microscopic neuron dust that spills into mid-field (no spherical packing)
5. Continuous blend into full-canvas atmospheric tissue (`buildFieldTissue`)
6. Soft breathing of the field (idle and faster when thinking)
7. Sparse short feeders into surrounding tissue — never radial explosion
8. DOM label (`TITAN CORE` / `Cognitive Operating System`) with soft halo —
   readable immediately on open

Brightness comes from **thousands of nearby neurons and bridges**, not from a white-hot
orb or energy rings. The user should never perceive where the “brain starts.”

---

## 5. Neural Activity

### Impulses

Travel only on **selected paths**:

- Accelerate mid-path, slow near terminals
- Branch occasionally when thinking
- Fade with afterglow on arrival
- Occasionally **converge toward the dense region**
- Idle micro-pulses and soft electrical impulses keep life continuous

### Thinking state

Raises local activity, pulse speed, dense-region energy, and nearby synaptic fire.
Nearby satellites / regions respond subtly via region focus.

### Execution state

Only the **relevant cognitive region** brightens (`activateWorldPoint` with falloff).
The entire neural field never flashes simultaneously.

---

## 6. Implementation Map

| Concern | Module |
|---------|--------|
| Density pocket tissue + void fill | `web/v2/neural/tissue.js` |
| Dense-region hubs + micro dust | `web/v2/neural/core.js` |
| Organic field sampling | `web/v2/neural/nodes.js` |
| Canvas draw (no orb / rings) | `web/v2/neural/renderer.js` |
| Composition parameters | `web/v2/neural/config.js` |
| DOM label + satellites | `web/v2/center/` + `design/satellites.css` |

UI layout, panels, sidebars, typography, and backend APIs are out of scope for this sprint.

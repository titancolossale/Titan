# Titan Neural Engine

**Phase D1 — Official Product Specification**

**Status:** Authoritative specification for Titan's neural brain visualization.

**Scope:** Depth model, signals, nodes, connections, layers, camera, infinite space, state machine, performance budget, canvas rendering, and future WebGL path. No implementation code.

---

## Document Authority

The neural engine is Titan's **primary visual identity**. This document defines what must be rendered and how it behaves — not library choices.

Companion: `TITAN_ANIMATION_GUIDE.md` (timing), `TITAN_UI_BIBLE.md` (metaphor).

---

## 1. Purpose

### 1.1 What the Neural Engine Is

A real-time, generative visualization representing Titan's **continuous cognition** — memory, reasoning, tool use, and response synthesis as synaptic activity in infinite dark space.

### 1.2 What It Is Not

- Wallpaper or screensaver
- Particle explosion demo
- Data visualization chart (no axes, no legends)
- Game environment
- Optional theme

### 1.3 Success Criteria

| Criterion | Measure |
|-----------|---------|
| Presence | User feels Titan is alive within 2s of load |
| Depth | Perceived layers recede beyond screen edges |
| Honesty | Activity level correlates with backend cognitive state |
| Performance | 60 FPS target on modern laptop integrated GPU |
| Identity | Signature red-on-black instantly recognizable |

---

## 2. Architectural Overview

```
┌─────────────────────────────────────────────────────────┐
│                    NEURAL ENGINE                         │
├──────────────┬──────────────┬──────────────┬─────────────┤
│   STATE      │   WORLD      │   CAMERA     │  RENDERER   │
│   MACHINE    │   MODEL      │   CONTROLLER │             │
├──────────────┴──────────────┴──────────────┴─────────────┤
│  NODES · CONNECTIONS · SIGNALS · DEPTH · COGNITIVE HOOKS │
└─────────────────────────────────────────────────────────┘
         ↑ activity events from Presence / Brain / Tools
```

---

## 3. Infinite Brain

### 3.1 Concept

The brain has **no boundaries**. The viewport is a window into an unbounded neural field.

### 3.2 Infinite Space Rules

| Property | Specification |
|----------|---------------|
| World wrap | Nodes reposition when exiting wrap margin (28px beyond viewport) |
| World expansion | 55% padding beyond visible area populated with nodes |
| Edge streams | New nodes spawn at edges at rate 0.22% per frame |
| Connection reach | Edges may connect across wrap boundary |
| Visual fade | Edge fade strength 48% — connections dissolve in void |

### 3.3 User Perception

- Never see a hard rectangular clip of the network
- Corner vignette reinforces "extends beyond"
- Camera drift reveals different local neighborhoods over time

---

## 4. Depth Model

### 4.1 Layer Stack

Five primary render layers, back to front:

| Layer ID | Depth index | Base opacity | Drift mult | Parallax | Node radius (relative) | Fog dim |
|----------|-------------|--------------|------------|----------|------------------------|---------|
| abyss | 0 | 0.10 | 0.18 | 0.22 | 0.35 – 0.72 | 0.28 |
| deep | 1 | 0.16 | 0.28 | 0.38 | 0.50 – 1.00 | 0.40 |
| background | 2 | 0.22 | 0.38 | 0.55 | 0.70 – 1.30 | 0.52 |
| midground | 3 | 0.42 | 0.68 | 0.78 | 1.00 – 2.00 | 0.72 |
| foreground | 4 | 0.68 | 1.00 | 1.00 | 1.30 – 2.60 | 0.88 |

### 4.2 Parallax Depth Bands (Atmospheric)

Additional non-interactive bands for depth illusion:

| Band | Parallax | Node count | Speed mult | Opacity range |
|------|----------|------------|------------|---------------|
| void | 0.12 | 10 | 0.35 | 0.03 – 0.08 |
| far | 0.28 | 12 | 0.48 | 0.05 – 0.12 |
| distant | 0.45 | 10 | 0.62 | 0.06 – 0.14 |
| horizon | 0.62 | 8 | 0.78 | 0.07 – 0.16 |

### 4.3 Depth Effects

| Effect | Strength | Purpose |
|--------|----------|---------|
| Far layer dim | 0.42× brightness | Recession |
| Near brightness boost | 1.18× | Proximity |
| Depth fog | 0.08 | Atmospheric perspective |
| Haze | 0.08 | Void blending |
| Ghost nodes (recall) | 36 extra | Memory retrieval |
| Void lines | 18 | Horizon grid whisper |

### 4.4 Ghost and Recall

During memory retrieval:

- Recall boost opacity +0.45
- Camera recall dive (see Camera section)
- Ghost nodes fade in over 600ms organic

---

## 5. Nodes

### 5.1 Node Anatomy

Each node is a ** luminous point** with optional halo:

| Property | Range / rule |
|----------|--------------|
| Position | World coordinates; wrapped |
| Radius | Layer-dependent; modulated by breathe |
| Color | Red core rgba + white dim halo |
| Opacity | Layer base × vitality × activity boost |
| Pulse phase | Unique per node |
| Pulse speed | 0.006 – 0.016 rad/frame |
| Drift velocity | Vector; 0.022 – 0.085 magnitude |

### 5.2 Population

| Parameter | Value |
|-----------|-------|
| Min count | 180 |
| Max count | 380 |
| Density formula | `(width × height) / 6200 × density` |
| Default density | 1.72 |
| Adaptive | Scales down under performance pressure |

### 5.3 Breathe Modulation

Global breathe applies sinusoidal radius modifier:

- Amplitude: 0.24
- Speed: 0.00042 rad/frame
- Coupled to presence `breatheScale`

### 5.4 Central Core

Special node cluster at cognitive center:

- Strength multiplier: 1.65×
- Always visible through panel gaps
- Brightest red-white convergence
- Not a literal anatomical brain diagram — abstract energy core

---

## 6. Connections

### 6.1 Topology

| Rule | Value |
|------|-------|
| Max distance | 38% of viewport diagonal |
| Connection probability | 62% when within range |
| Max connections per node | 11 |
| New connection interval | 3200ms |
| New connection chance | 72% per interval |

### 6.2 Edge Rendering

| Property | Specification |
|----------|---------------|
| Color | White dim low alpha default |
| Active pulse | Red glow propagates along edge |
| Curve | Foreground layer may use curved edges |
| Width | 0.5 – 1.5px by depth |
| Glow decay | 0.018/frame after signal pass |

### 6.3 Dynamic Graph

Connections form and dissolve slowly — graph is **living**, not static. Never full rewire flash.

---

## 7. Signals

### 7.1 Signal Particles

Synaptic pulses traveling along edges.

| Property | Range |
|----------|-------|
| Speed | 0.28 – 0.62 path units/ms |
| Size | 1.8px |
| Trail length | 42% decay |
| Particle glow | 0.62 strength |
| Max active (idle) | 14 |
| Max active (thinking) | 32 |
| Spawn interval idle | 1600ms |
| Spawn interval thinking | 140ms |

### 7.2 Waves

Radial waves from activated nodes:

| Property | Value |
|----------|-------|
| Radius | 108px |
| Speed | 0.065 px/frame |
| Decay | 0.009/frame |

### 7.3 Wave Styles (Tool Profiles)

| Style | Character |
|-------|-----------|
| default | Balanced radial |
| central | Converges to core — memory |
| distributed | Multiple origins — browser, email |
| circular | Even ring expansion — calendar, speaking |
| sharp | Fast attack, short decay — trading |
| geometric | Angular bias — Obsidian |

### 7.4 Micro-Pulses

During thinking: random node micro-glow every ~850ms within nearby radius (26% viewport).

---

## 8. Cognitive Hooks

Activity events the engine subscribes to:

| Hook | Source | Effect |
|------|--------|--------|
| `brain_activity` | Brain pipeline | General intensity |
| `tool_usage` | Tool orchestrator | Directed tool waves |
| `memory_retrieval` | Memory subsystem | Recall dive + central waves |
| `reasoning` | Planner / reasoning loop | Planning paths |
| `voice` | Voice input | Listening ripple |
| `speaking` | TTS output | Circular pulses |
| `browser_research` | Browser tool | Distributed waves |

Hooks map to cognitive mode classes on canvas (see Animation Guide §16).

---

## 9. State Machine

### 9.1 Master States

```
BOOTING → AWAKE → { IDLE ↔ LISTENING ↔ THINKING ↔ WORKING ↔ SPEAKING }
                      ↓ memory recall overlay
                 DEPTH_RECALL (transient)
```

### 9.2 State Definitions

| State | Entry condition | Neural behavior |
|-------|-----------------|-----------------|
| BOOTING | App load | Fade from black; sparse nodes |
| AWAKE | Launch complete | Full density; idle profile |
| IDLE | No active work | Ambient drift, rare pulses |
| LISTENING | Voice input open | Elevated attention |
| THINKING | Chat request in flight | High signal density |
| WORKING | Tool executing | Tool profile waves |
| SPEAKING | TTS active | Rhythmic circular pulses |
| DEPTH_RECALL | Memory hook | Camera dive + ghosts |

### 9.3 Cognitive Sub-States

Orthogonal tag for region highlighting:

`idle | listening | thinking | deep | memory | planning | tool | trading | browser | calendar | email | voice`

One cognitive tag active; combines with master state (e.g., THINKING + cognitive-memory).

### 9.4 Transitions

- All transitions lerped via presence engine
- No instantaneous density resets
- THINKING decay when request completes: 0.0028/frame activity reduction

### 9.5 Priority

Listening > Thinking > Speaking / Working > Idle

---

## 10. Camera

### 10.1 Specification

Virtual camera over world space — **not user-controlled in V1**.

| Parameter | Value |
|-----------|-------|
| Drift speed X | 0.00006 rad/frame |
| Drift speed Y | 0.00005 rad/frame |
| Amplitude X | 4.8% viewport width |
| Amplitude Y | 3.8% viewport height |
| Easing toward target | 0.00012 factor |
| Breathe zoom amplitude | ±1.4% |
| Breathe zoom speed | 0.00035 rad/frame |
| Thinking focus mult | 0.58× amplitude |
| Thinking zoom in | +1.6% |
| Idle drift boost | ×1.12 |

### 10.2 Recall Dive

| Parameter | Value |
|-----------|-------|
| Scale push | 5.5% inward |
| Decay | 0.0035/frame |

### 10.3 Reduced Motion

Amplitude and zoom modulation → 0. Static centered view.

---

## 11. Renderer

### 11.1 Canvas Phase (Current Target)

| Property | Specification |
|----------|---------------|
| API | 2D canvas context |
| DPR cap | 2× |
| Clear | Void black each frame |
| Draw order | Depth bands → edges → nodes → signals → core → vignette |
| Edge fade | Post-process gradient at viewport bounds |
| Ambient glow | Separate DOM layer (not canvas) |
| Panel occlusion | 2% dim under panel regions optional |

### 11.2 Visual Parameters

| Parameter | Value |
|-----------|-------|
| Thinking brightness | 1.38× |
| Ambient glow strength | 0.38 |
| Central core strength | 1.65 |
| Signal particle glow | 0.62 |
| Vitality idle floor/ceiling | 0.12 / 0.28 |

### 11.3 Color System

| Role | Color character |
|------|-----------------|
| Red core | rgba(204, 0, 0, α) |
| Red glow | rgba(255, 26, 26, α) |
| White dim | rgba(255, 255, 255, α) |
| Vignette | rgba(0, 0, 0, α) |

Alpha driven by layer, activity, and hooks — synced to TDL red tokens.

---

## 12. Performance

### 12.1 Budget

| Metric | Target |
|--------|--------|
| Frame rate | 60 FPS |
| Frame budget | 16.8ms |
| Sample window | 45 frames for adaptive decisions |

### 12.2 Adaptive Quality

| Trigger | Response |
|---------|----------|
| Sustained slow frames | Reduce node density toward 55% floor |
| Recovery 8s stable | Restore density gradually |
| Tab hidden | Pause animation loop |
| Reduced motion | Lower signal count, zero drift |

### 12.3 Node Count Adaptive

`adaptiveNodeCount: true` — engine measures FPS and scales population within min/max bounds.

### 12.4 Mobile

Reduce max count by ~30%; maintain infinite illusion; disable curved edges if needed.

---

## 13. Integration with UI

### 13.1 Z-Index

Canvas at `tdl-z-neural` (0). UI at 10+. Canvas never captures pointer events.

### 13.2 Region Labels

HTML module labels (`tdl-neural-module`) align to approximate world regions — sync optional via normalized coordinates.

### 13.3 Presence Sync

Presence engine publishes:

- `activityTarget`
- `thinkingTarget`
- `glowLevel`
- `signalDensity`
- `brightness`

Engine lerps toward targets each frame.

### 13.4 Telemetry

FPS displayed in footer — diagnostic transparency, not user requirement.

---

## 14. Future WebGL

### 14.1 Motivation

Canvas 2D reaches limits at ultrawide + max density + complex fog. WebGL enables:

- GPU instanced nodes (10× population)
- Volumetric fog shaders
- Subsurface glow on edges
- True depth buffer parallax

### 14.2 Migration Principles

| Principle | Rule |
|-----------|------|
| Visual parity | WebGL must match this spec's character — not a redesign |
| Fallback | Canvas path remains indefinitely |
| State machine | Unchanged — same hooks and profiles |
| Token sync | Same color alpha rules |
| Feature detect | WebGL opt-in after quality benchmark |

### 14.3 WebGL Enhancements (Permitted Later)

- Soft bloom post-process (red constrained)
- Instanced particle signals
- 3D camera parallax on depth buffer
- Shader-based void vignette

### 14.4 WebGL Prohibitions

- PBR materials, literal brain mesh
- HDR neon palette
- VR-style free flight camera
- User-triggered explosion effects

---

## 15. Boot Sequence (Neural)

| Phase | Time | Visual |
|-------|------|--------|
| T0 | 0ms | Void black canvas |
| T1 | 400ms | Sparse nodes fade in far layers |
| T2 | 600ms | Connection probability ramps 0→62% |
| T3 | 800ms | Full density reached |
| T4 | 1000ms | AWAKE — idle profile active |

Launch overlay text syncs with T1–T4.

---

## 16. Testing Checklist

- [ ] Infinite wrap — no visible pop at edges
- [ ] Idle pulse occurs within 12s
- [ ] Thinking doubles signal count within 200ms
- [ ] Memory hook triggers recall dive
- [ ] Tool profiles match wave style table
- [ ] FPS adaptive reduces nodes under load
- [ ] Hidden tab pauses engine
- [ ] Reduced motion static view
- [ ] Colors match TDL red identity
- [ ] Canvas visible through glass panels

---

## Document Metadata

| Field | Value |
|-------|-------|
| Phase | D1 |
| Version | 1.0.0 |
| Established | 2026-07-06 |

---

**End of Titan Neural Engine — Phase D1**

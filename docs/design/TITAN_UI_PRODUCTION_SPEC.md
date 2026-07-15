# Titan UI Production Specification

**Phase D4 — Final Technical Authority for Frontend V2**

**Status:** Mandatory implementation contract. All frontend rebuild work must conform to this document exactly.

**Scope:** Exact layout, neural field, component, typography, color, animation, accessibility, and implementation rules derived from Phase D1–D3 design authority. No creative interpretation. No new features. No redesign.

**This document contains no implementation code.** It defines measurable values engineers must implement.

---

## Document Authority

| Rule | Description |
|------|-------------|
| **Mandatory** | No frontend code ships without conforming to this spec. |
| **Hierarchy** | Constitution → Experience Manifesto → UI Bible → Master Blueprint → Master Mockup → **Production Spec** → D1 companion specs (Design Language, Layout, Animation, Neural Engine, Components). |
| **Conflict resolution** | Visual detail: **Master Mockup wins**. Behavioral/backend mapping: **Master Blueprint wins**. Implementation measurements: **this document wins** when it consolidates D1–D3 into a single numeric contract. |
| **Missing values** | If a required value is absent here and absent in upstream docs, **stop and ask** — do not invent. |
| **Backend** | Backend APIs, data shapes, and orchestration logic remain unchanged. Frontend rebuilds to match Master Mockup. |
| **Change control** | Amendments require explicit product approval and version note. |

### Source Documents (Read-Only Reference)

| Document | Role in this spec |
|----------|-------------------|
| `TITAN_UI_BIBLE.md` | Philosophy, presence states, interaction law |
| `TITAN_MASTER_BLUEPRINT.md` | Screen architecture, panel inventory, states |
| `TITAN_MASTER_MOCKUP.md` | Visual composition, glass values, eye flow |
| `TITAN_DESIGN_LANGUAGE.md` | TDL token names and values |
| `TITAN_LAYOUT_GUIDE.md` | Breakpoints, grid, z-index |
| `TITAN_NEURAL_ENGINE.md` | Neural rendering law |
| `TITAN_ANIMATION_GUIDE.md` | Motion timing and profiles |
| `TITAN_COMPONENT_LIBRARY.md` | Component anatomy |

---

## 1. Layout

### 1.1 Desktop Grid (≥1280px — Reference)

| Region | Width | Height | Behavior |
|--------|-------|--------|----------|
| **Neural stage** | 100vw | 100vh | Fixed full viewport; z-index 0; never unmounts |
| **Sidebar** | 218px fixed | `calc(100vh - bottom dock)` | Left column; always visible |
| **Orchestrator** | 318px fixed | Same as sidebar | Right column; always visible |
| **Center column** | `flex: 1` | Same as sidebar | Min width 480px |
| **Bottom dock** | 100% workspace width | Min 11.75rem (188px) | Spans sidebar + center + orchestrator |

**Workspace container:**

| Property | Value |
|----------|-------|
| Outer padding | 1.25rem (`tdl-workspace-padding`) |
| Inter-region gap | 0.875rem (`tdl-workspace-gap`) |
| Layout model | CSS grid or equivalent: `sidebar · main · orchestrator` + full-width dock row |
| Background | Transparent — neural visible through gaps |
| Minimum neural visibility | 15% of viewport neural field perceptible through gaps and glass at all times |

**Center column structure (top → bottom):**

| Element | Height | Notes |
|---------|--------|-------|
| Topbar | 48–56px | Transparent or minimal glass strip |
| Neural module labels | Overlay (absolute) | Does not reflow chat |
| Active view content | `flex: 1` | Chat max-width 720px centered |
| — | — | Min 200px chat area above dock on desktop |

**Bottom dock rows:**

| Row | Height | Content |
|-----|--------|---------|
| Status cards | 88–104px | 5 equal flex columns |
| Status lines | ~24px auto | Tool and/or memory status line |
| Composer | 56–72px | Mic + textarea + actions |
| Telemetry (status bar) | 32px | Mono xs diagnostic strip |

### 1.2 Sidebar Width

| Viewport | Width |
|----------|-------|
| Desktop ≥1280px | 218px |
| Laptop 1024–1279px | 218px |
| Ultrawide ≥2560px | 240px |
| Tablet 768–1023px | 56px icon rail (default); 218px overlay drawer when expanded |
| Phone <768px | Bottom sheet navigation |

### 1.3 Orchestrator Width

| Viewport | Width |
|----------|-------|
| Desktop ≥1280px | 318px |
| Laptop 1024–1279px | 280px minimum |
| Ultrawide ≥2560px | 318px (unchanged) |
| Tablet | Hidden default; slide-over 318px or 85vw max |
| Phone | Sheet only |

### 1.4 Center Neural Field Area

| Property | Value |
|----------|-------|
| Coverage | Full viewport behind all panels |
| Pointer events | None — passes through to UI |
| Perceptual strength through chat glass | ~40% |
| Module labels | Absolute overlay in center column; fixed design anchors (not draggable V1) |
| Chat transcript max-width | 720px centered in center column |
| Transcript inner padding | 1.5rem horizontal; md (12px) vertical message gap |
| Intentional void | Gaps between sidebar/center/orchestrator reveal neural — no widgets in gaps |

### 1.5 Bottom Composer Height

| Property | Value |
|----------|-------|
| Row height | 56–72px |
| Mic button | 40px circle (44×44px min touch target) |
| Textarea | Auto-grow 1–4 lines |
| Container surface | Elevated glass: alpha 0.46, blur 16px |
| Separation from status lines | lg (24px) gap above composer |
| Phone | Sticky above `env(safe-area-inset-bottom)` |

### 1.6 Status Bar Height

| Property | Value |
|----------|-------|
| Telemetry row | 32px (`tdl-statusbar-height`) |
| Z-index | 20 (`tdl-z-statusbar`) |
| Font | xs mono muted |
| Visibility | Desktop/laptop always; tablet optional; phone hidden (Settings → Developer) |

### 1.7 Responsive Breakpoints

| Name | Range | Layout mode |
|------|-------|-------------|
| Phone | <768px | Single column + sheets |
| Tablet | 768–1023px | Icon rail + drawer |
| Laptop | 1024–1279px | Compact three-column |
| Desktop | 1280–1919px | Reference three-column |
| Wide | 1920–2559px | Reference + wider chat |
| Ultrawide | ≥2560px | Reference + max chat 840px |

### 1.8 Mobile Behavior (<768px)

| Element | Behavior |
|---------|----------|
| Layout | Single column; chat full bleed |
| Sidebar | Bottom sheet navigation |
| Orchestrator | Sheet only (via "Cerveau") |
| Topbar | Mini one-line presence |
| Status cards | Single combined chip |
| Module labels | Hidden |
| Telemetry | Hidden |
| Composer | Sticky; safe-area inset respected |
| Typography | Base sm (14px); display uses xl not display token |
| Neural | Node count −30%; signal max −40% |
| Touch targets | Minimum 44×44px |
| Priority stack (top→bottom) | Composer sticky → Chat scroll → Topbar → Everything else in sheets |

### 1.9 Tablet Behavior (768–1023px)

| Element | Behavior |
|---------|----------|
| Sidebar | 56px icon rail; 218px overlay drawer on hamburger |
| Orchestrator | Hidden; right slide-over 318px or 85vw max via "Cerveau" |
| Status cards | Horizontal scroll row; snap; min card width 160px |
| Module labels | Hidden; active module chip in topbar only |
| Neural | Node count −20% |
| Touch targets | 44×44px minimum |
| Orchestrator access | Within 2 taps |

### 1.10 Ultrawide Behavior

| Viewport | Sidebar | Orchestrator | Chat max-width | Rule |
|----------|---------|--------------|----------------|------|
| 1920–2559px | 218px | 318px | 780px | Extra breathing room in void |
| ≥2560px | 240px | 318px | 840px | Side panels fixed — do not stretch |
| All ultrawide | — | — | — | Minimum 40% viewport width visible neural; **no third sidebar** |

### 1.11 Z-Index Stack (Implementation)

| Layer | Token | Value | Contents |
|-------|-------|-------|----------|
| Neural stage | `tdl-z-neural` | 0 | Canvas, placeholders |
| Ambient glow | `tdl-z-glow` | 1 | Edge radial pulse |
| Workspace | `tdl-z-content` | 10 | Sidebar, main, orchestrator, dock |
| Floating cards | — | 15 | Memory, tool, exploration, planning, trading alerts |
| Status emphasis | `tdl-z-statusbar` | 20 | Telemetry elevation |
| Overlays | `tdl-z-overlay` | 100 | Settings, LIVE confirmation, voice immersive |
| Toasts | `tdl-z-toast` | 110 | Future notifications |

### 1.12 Panel Load Stagger (Cold Load)

| Region | Delay | Duration | Easing |
|--------|-------|----------|--------|
| Sidebar | 0ms | 350ms opacity 0→1 | enter |
| Main column | 200ms | 350ms | enter |
| Orchestrator | 400ms | 350ms | enter |
| Bottom dock | 600ms | 350ms | enter |

No slide-from-offscreen. No bounce. No scale pop.

---

## 2. Neural Field

### 2.1 Node Density

| Parameter | Value |
|-----------|-------|
| Min node count | 180 |
| Max node count | 380 |
| Default density multiplier | 1.72 |
| Density formula | `(width × height) / 6200 × density` |
| World padding beyond viewport | 55% |
| Edge spawn rate | 0.22% per frame |
| Adaptive scaling | Enabled; floor 55% under performance pressure |
| Phone reduction | −30% max count |
| Tablet reduction | −20% max count |

### 2.2 Node Sizes

| Layer | Depth index | Node radius (relative) | Base opacity |
|-------|-------------|------------------------|--------------|
| abyss | 0 | 0.35 – 0.72 | 0.10 |
| deep | 1 | 0.50 – 1.00 | 0.16 |
| background | 2 | 0.70 – 1.30 | 0.22 |
| midground | 3 | 1.00 – 2.00 | 0.42 |
| foreground | 4 | 1.30 – 2.60 | 0.68 |

**Breathe modulation:** amplitude 0.24; speed 0.00042 rad/frame; coupled to `breatheScale`.

**Central core:** strength multiplier 1.65×; brightest red-white convergence at cognitive center.

**Ghost nodes (memory recall):** +36 extra in far bands; opacity boost +0.45; fade in 600ms organic.

### 2.3 Connection Thickness

| Depth | Width |
|-------|-------|
| Far layers | 0.5px |
| Mid layers | ~1.0px |
| Foreground | up to 1.5px |

| Topology rule | Value |
|---------------|-------|
| Max connection distance | 38% viewport diagonal |
| Connection probability | 62% when in range |
| Max connections per node | 11 |
| New connection interval | 3200ms |
| New connection chance | 72% per interval |
| Edge fade strength | 48% |
| World wrap margin | 28px beyond viewport |

Default edge color: white dim low alpha. Active pulse: red glow along edge. Glow decay: 0.018/frame.

### 2.4 Glow Intensity

| State / element | Glow level (0–1) | Notes |
|-----------------|------------------|-------|
| Idle | 0.44 | Ambient edge 38–44% of presence glow |
| Thinking | 0.78 | Core brightens ×1.38 |
| Listening | Elevated | Activity 0.22 |
| Speaking | ×1.07 brightness | Circular pulses |
| Memory recall | Central convergence | Ghost halo 0.45 boosted |
| Error calm | Decay to idle | Within 900ms |
| Ambient glow strength | 0.38 | Separate DOM layer |
| Signal particle glow | 0.62 | — |
| Red pixel budget | ≤15% | Of visible pixels in static frame |

**Ambient edge glow:** 5.5s breath cycle; red radial; no hue shift.

### 2.5 Central Core Size

| Property | Value |
|----------|-------|
| Strength multiplier | 1.65× vs standard nodes |
| Position | Center of viewport, behind center column |
| Character | Abstract energy convergence — not anatomical brain |
| Visibility | Always perceptible through panel gaps |
| Pulse | Coupled to cognitive load; 2.4s thinking oscillation |

### 2.6 Pulse Speed

| Context | Interval / speed |
|---------|------------------|
| Node pulse speed | 0.006 – 0.016 rad/frame per node |
| Ambient glow breath | 5.5s cycle |
| Thinking brightness oscillation | 2.4s cycle |
| Presence widget breathe | 6s cycle |
| Background drift cycle | 14s |
| Idle synaptic edge pulse | Every 8–12s along one edge |
| Thinking micro-pulses | ~850ms at nearby nodes |
| Module label ACTIF pulse | 2.4s organic cycle |
| Orchestrator orb breathe | 2.4s during thinking |

### 2.7 Signal Speed

| Property | Range / value |
|----------|---------------|
| Particle speed | 0.28 – 0.62 path units/ms |
| Particle size | 1.8px |
| Trail decay | 42% |
| Wave radius | 108px |
| Wave speed | 0.065 px/frame |
| Wave decay | 0.009/frame |
| Max active signals (idle) | 14; spawn ~1600ms |
| Max active signals (thinking) | 32; spawn ~140ms |
| Node drift velocity | 0.022 – 0.085 magnitude |
| Glow decay (node) | 0.014/frame |
| Glow decay (edge) | 0.018/frame |

### 2.8 Depth Layers

**Render order (back → front):** Depth bands → edges → nodes → signals → core → vignette.

**Parallax depth bands (atmospheric, non-interactive):**

| Band | Parallax | Node count | Speed mult | Opacity |
|------|----------|------------|------------|---------|
| void | 0.12 | 10 | 0.35 | 0.03 – 0.08 |
| far | 0.28 | 12 | 0.48 | 0.05 – 0.12 |
| distant | 0.45 | 10 | 0.62 | 0.06 – 0.14 |
| horizon | 0.62 | 8 | 0.78 | 0.07 – 0.16 |

**Depth effects:**

| Effect | Strength |
|--------|----------|
| Far layer dim | 0.42× brightness |
| Near brightness boost | 1.18× |
| Depth fog | 0.08 |
| Haze | 0.08 |
| Void lines | 18 (horizon grid whisper) |
| UI panel parallax | **None** — panels static over field |

### 2.9 Camera Drift

| Parameter | Idle | Thinking | Memory recall | Tool working | Voice listening | Voice speaking | Reduced motion |
|-----------|------|----------|---------------|--------------|-----------------|----------------|----------------|
| Amplitude X | 4.8% viewport width | ×0.58 | — | Region bias ≤8% offset | Reduced (stable) | — | 0 |
| Amplitude Y | 3.8% viewport height | ×0.58 | — | — | — | — | 0 |
| Zoom | Baseline 1.0; breathe ±1.4% | +1.6% | +5.5% over 600ms | Baseline | Baseline | +0.8% | 1.0 fixed |
| Drift speed X | 0.00006 rad/frame | — | — | — | — | — | 0 |
| Drift speed Y | 0.00005 rad/frame | — | — | — | — | — | 0 |
| Breathe zoom speed | 0.00035 rad/frame | — | — | — | — | — | 0 |
| Easing to target | 0.00012 factor/frame | — | — | — | — | — | — |
| Idle drift boost | ×1.12 | — | — | — | — | — | — |
| Recall decay | — | — | 0.0035/frame to baseline | — | — | — | — |
| User pan/zoom V1 | **Forbidden** | — | — | — | — | — | — |

### 2.10 Idle Behavior

| Parameter | Target (0–1 scale) |
|-----------|-------------------|
| Activity | 0.08 |
| Thinking intensity | 0 |
| Glow level | 0.44 |
| Breathe scale | 1.02 |
| Ambient motion | 0.42 |
| Signal density | 0.32 |
| Brightness | 1.0 |
| Vitality oscillation | Floor 0.12 – ceiling 0.28 over ~6s |
| Master state | IDLE |
| Status copy (FR) | Présent — en attente |
| UI | Presence ring ±5% fill oscillation; waveform low amplitude |

### 2.11 Thinking Behavior

| Parameter | Target |
|-----------|--------|
| Activity | 0.88 (×2.15 boost vs idle) |
| Thinking intensity | 0.92 |
| Glow level | 0.78 |
| Breathe scale | 1.14 |
| Ambient motion | 0.72 |
| Signal density | 0.95 |
| Brightness | 1.08 (render ×1.38) |
| Drift boost | ×1.48 |
| Decay on stop | 0.0028/frame activity reduction |
| Transition in | 700ms enter easing |
| Status copy | Réflexion en cours / Formulation de la réponse |
| UI | "Titan réfléchit…" fade 200ms; stop button fade 200ms; orb 2.4s pulse |
| Path spread chance | 68% branching |
| Nearby node glow | 0.78 within 26% viewport radius |

### 2.12 Memory Behavior

| Parameter | Value |
|-----------|-------|
| Cognitive tag | `memory` |
| Wave style | Central — converges to core |
| Hook | `memory_retrieval` |
| Pulse interval | ~1600ms |
| Wave burst count | 2 |
| Camera | Recall dive +5.5% over 600ms |
| Ghost nodes | +36 |
| Brightness near core | ×1.18 during active recall |
| Module label | MÉMOIRE ACTIF; red border pulse |
| UI cards | Stagger 80ms; float translateY −12px; dissolve 400ms exit |
| Status line | "Recherche en mémoire…" |

### 2.13 Browser Behavior

| Parameter | Value |
|-----------|-------|
| Cognitive tag | `browser` |
| Wave style | Distributed |
| Hook | `browser_research` |
| Pulse interval | ~1200ms |
| Wave burst count | 3 |
| Speed multiplier | 1.18× |
| Module | BROWSER ACTIF |
| Camera | Horizontal bias ±6% on active research |
| Synthesis | Thinking brightness + distributed waves combined |
| Status copy | Exploration web… / Analyse de la source… / Synthèse en cours… |

### 2.14 Trading Behavior

| Parameter | Value |
|-----------|-------|
| Cognitive tag | `trading` |
| Wave style | Sharp — fast attack, short decay |
| Pulse interval | ~1100ms |
| Wave burst count | 3 |
| Speed multiplier | 1.35× |
| Character | Controlled urgency — **never strobe** |
| Risk block | Neural calms immediately to idle |
| LIVE confirmation | Neural pauses; frozen drift |
| Status copy | Analyse des marchés / Exécution en cours… |
| Module | TRADING ACTIF when engaged |

### 2.15 Voice Behavior

| State | Activity | Visual |
|-------|----------|--------|
| Listening | 0.22 | Ripple from core; `--tdl-voice-ripple` 0→1 over 900ms; mic ring 2px red @ 60% |
| Processing | THINKING profile | Wave frozen brief → thinking |
| Speaking | 0.76 | Circular pulses ~520ms; brightness ×1.07 |
| Continuous listen | LISTENING low | Persistent subtle mic ring |
| Interrupt | — | Immediate halt; presence snap 200ms (exception to lerp) |

**Wave visualization (Voice screen):**

| Property | Value |
|----------|-------|
| Min size desktop | 320px × 120px |
| Bar count | 32–48 centered |
| Idle amplitude | 10% — not zero |
| Listening | 60fps audio envelope; red fill |
| Speaking | Symmetrical ripple from output envelope |
| Reduced motion | Static bars at last level |

### 2.16 Performance Targets

| Metric | Target |
|--------|--------|
| Frame rate | 60 FPS |
| Frame budget | 16.8ms |
| Sample window | 45 frames for adaptive decisions |
| DPR cap | 2× |
| Tab hidden | Pause animation loop |
| FPS < 45 for 45 frames | Reduce node density toward 55% floor |
| Recovery | Restore over 8000ms after stable 60fps |
| Renderer | Canvas 2D V1; WebGL permitted later with visual parity |
| Clear color | `#000000` void each frame |
| Draw order | Depth bands → edges → nodes → signals → core → vignette |

**Boot sequence:**

| Phase | Time | Visual |
|-------|------|--------|
| T0 | 0ms | Void black |
| T1 | 400ms | Sparse nodes fade in |
| T2 | 600ms | Connection probability 0→62% |
| T3 | 800ms | Full density |
| T4 | 1000ms | AWAKE idle profile |

---

## 3. Components

All components use TDL tokens. Values below are the implementation contract.

### 3.1 Buttons (`tdl-btn`)

| Property | Primary | Secondary | Ghost |
|----------|---------|-----------|-------|
| **Height** | 36–40px implicit | Same | Same |
| **Padding** | sm horizontal (8px) + md vertical (12px) | Same | Same |
| **Radius** | `tdl-radius-sm` (4px) | 4px | 4px |
| **Border** | Red core / red border | `tdl-border-subtle` | Transparent |
| **Background** | `tdl-red-core` fill or red border + glow hover | `tdl-bg-elevated` | Transparent |
| **Opacity** | 1.0 | 1.0 | 1.0 |
| **Blur** | None | None | None |
| **Shadow** | `tdl-glow-red-sm` on hover | `tdl-shadow-sm` | None |
| **Text** | `tdl-text-primary` | `tdl-text-secondary` | `tdl-text-secondary` |
| **Weight** | medium (500) | medium | medium |
| **Hover** | Brightness increase + border brighten | Elevated wash | `rgba(255,255,255,0.06)` wash |
| **Active** | `translateY(1px)` | `translateY(1px)` | `translateY(1px)` |
| **Disabled** | 40% opacity; no glow | 40% opacity | 40% opacity |
| **Focus** | 2px ring `tdl-border-focus` | Same | Same |
| **Animation** | `tdl-duration-fast` (200ms) `tdl-ease-standard` | Same | Same |

**Send button:** Primary variant; red accent when composer input non-empty.

**Stop button:** Ghost; red tint; hidden default; fades in 200ms during thinking/streaming.

**Interrupt (Voice):** Ghost red outline; min 120px wide; "INTERROMPRE" sm semibold uppercase; phone 56px floating bottom-right.

### 3.2 Inputs (`tdl-input`, `tdl-composer__input`)

| Property | Value |
|----------|-------|
| **Height** | 44px (search/memory); composer auto 1–4 lines |
| **Padding** | md (12px) horizontal; sm–md vertical |
| **Radius** | `tdl-radius-md` (8px) |
| **Border** | 1px `tdl-border-subtle`; focus → `tdl-border-focus` |
| **Background** | `tdl-bg-elevated` (`#111111`) |
| **Opacity** | 1.0 |
| **Blur** | None on input itself |
| **Shadow** | None |
| **Text** | `tdl-text-primary` |
| **Placeholder** | `tdl-text-muted` |
| **Hover** | Border brighten to `tdl-border-default` |
| **Active** | Focus ring 2px `tdl-border-focus` |
| **Disabled** | 40% opacity |
| **Animation** | Border color `200ms` standard; no scale on focus |

**Composer textarea placeholder:** "Que veux-tu accomplir ?" (Home); screen-specific per Blueprint.

### 3.3 Panels (Reference Shell Glass)

| Variant | Background alpha | Blur | Border | Shadow | Inner highlight |
|---------|------------------|------|--------|--------|-----------------|
| Standard panel | 0.38 | 16px | 1px white @ 4% | `0 8px 32px black @ 45%` | None |
| Reference shell (sidebar, chat, orchestrator) | 0.38 | 22px | 1px white @ 4% | Same | Top edge 1px @ 6% |
| Elevated card | 0.46 | 16px | 1px white @ 6% | `0 4px 12px black @ 60%` | None |
| Status card | 0.44 | 12px | 1px white @ 6% | `0 4px 12px black @ 50%` | None |
| Settings card | 0.88 | 22px | 1px white @ 6% | `tdl-shadow-lg` | Top edge 1px @ 8% |

| Property | Value |
|----------|-------|
| **Padding** | 1.5rem (`tdl-panel-padding`) default |
| **Radius** | `tdl-radius-md` (8px) sidebar/chat; settings `tdl-radius-lg` (12px) |
| **Hover** | N/A (structural) |
| **Active** | N/A |
| **Disabled** | Settings-open: orchestrator dimmed non-interactive |
| **Animation** | Appear: 350ms opacity 0→1 enter; no slide |

### 3.4 Cards

#### Status Card (`tdl-ref-status-card`)

| Property | Value |
|----------|-------|
| **Size** | Equal flex column in row; min 160px tablet scroll |
| **Height** | Within 88–104px row |
| **Padding** | md (12px) internal |
| **Radius** | md (8px) |
| **Border** | 1px white @ 6% |
| **Background** | alpha 0.44; blur 12px |
| **Header** | sm medium title + optional 16px icon leading |
| **Body** | sm secondary; cross-fade 200ms on update |
| **Hero emphasis** | Larger body text; red top edge 1px (per screen matrix) |
| **Hover** | None |
| **Animation** | Body text cross-fade 200ms |

**Instances:** Mémoire Récente · Obsidian · Browser · État Cognitif · Présence

#### Memory Card (`tdl-memory-card`)

| Property | Value |
|----------|-------|
| **Size** | Grid: equal width 2-col; min height 120px; float: ~280px wide |
| **Padding** | lg (24px) |
| **Radius** | md (8px) |
| **Border** | 1px white @ 6%; high relevance red left border |
| **Background** | alpha 0.46; blur 16px |
| **Shadow** | `tdl-shadow-md` |
| **Header** | Category chip xs + timestamp mono xs right |
| **Body** | sm primary; 3-line clamp; max excerpt 120 chars |
| **Footer** | Relevance bar 2px red fill proportion |
| **Hover** | Elevated wash; border 10% white |
| **Selected** | Red border active |
| **Animation** | Stagger enter 80ms; fade + translateY −12px; dissolve exit 400ms |
| **Max visible float** | 4 stacked; right-aligned above chat |

#### Exploration Card (`tdl-view-placeholder__card--exploration`)

| Property | Value |
|----------|-------|
| **Size** | ~300px wide; auto height |
| **Padding** | md–lg |
| **Radius** | xl (16px) |
| **Border** | 1px white @ 6%; active session red top edge 1px |
| **Background** | alpha 0.46; blur 16px |
| **Shadow** | `tdl-shadow-md` |
| **Header** | sm semibold + timestamp mono xs |
| **Body** | sm; 4-line clamp |
| **Footer** | Source count badge + status dot |
| **Screenshot** | Optional 16:9 thumbnail; radius md; scale 0.96→1.0 slow enter |
| **Animation** | Enter fade + translateY 12px 350ms; exit dissolve 400ms |
| **Max visible** | 3 |

#### Trading Cards

| Type | Size / style |
|------|-------------|
| Watchlist tile | Symbol sm mono semibold; price base mono; change via semantic dot only |
| Position row | Table row; P&L mono semibold |
| Alert row | Amber left border; pulse once on trigger |
| Alert float | Max 3; top-right center below topbar; enter 200ms |
| Risk gauge | Horizontal bar; red fill proportional |

#### Planning Cards

| Property | Value |
|----------|-------|
| **Size** | Float center-left; max 2 visible |
| **Padding** | md |
| **Radius** | md |
| **Background** | alpha 0.46; blur 16px |
| **Active** | Red left border 2px |
| **Animation** | Sequential highlight 300ms; exit cross-fade 350ms |

### 3.5 Badges (`tdl-badge`)

| Property | Value |
|----------|-------|
| **Size** | xs text (12px) |
| **Padding** | xs sm (4px 8px) |
| **Radius** | full (pill) |
| **Border** | Optional 1px subtle |
| **Background** | Elevated or transparent |
| **Dot** | 6–8px circle leading |
| **Variants** | online `#22c55e` · warning `#ca8a04` · error `#dc2626` · idle `#737373` |
| **Rule** | Semantic color in dot/badge only — never panel fills |
| **Animation** | Amber/red pulse once on trigger — not repeating |

### 3.6 Tool Timeline (`tdl-tool-timeline`)

| Property | Value |
|----------|-------|
| **Location** | Orchestrator tools section |
| **Item** | Timestamp mono xs + tool name + outcome chip |
| **Order** | Reverse chronological |
| **Max visible** | 8 — scroll within section |
| **Padding** | sm per item |
| **Gap** | sm vertical |
| **Border** | None per item; section divider 1px subtle |
| **Animation** | New item fade 200ms |

### 3.7 Orchestrator Steps (`tdl-orchestrator-steps`)

| Property | Value |
|----------|-------|
| **Type** | Ordered list |
| **Item padding** | sm md |
| **Radius** | sm on active inset |
| **Border** | Active: 2px red left; complete: none |
| **Background** | Active: red subtle wash alpha 0.15 |
| **States** | pending · active · complete · failed |
| **Complete** | Strikethrough; opacity 0.5; fade 400ms |
| **Failed** | Semantic error badge |
| **Empty copy** | "En attente de demande…" |
| **Animation** | Sequential highlight 300ms per step |
| **Active step transition** | 500ms border + opacity (module labels) |

### 3.8 Orchestrator Panel (`tdl-ref-orchestrator`)

| Property | Value |
|----------|-------|
| **Width** | 318px (see §1.3) |
| **Padding** | 1.5rem |
| **Radius** | md (8px) |
| **Background** | alpha 0.38; blur 22px |
| **Border** | 1px white @ 4% |
| **Shadow** | panel shadow |
| **State orb** | Breathe sphere; scale 1.0→1.06; 2.4s cycle |
| **Sparkline** | Full width × 48px canvas |
| **Section refocus** | 300ms; outgoing opacity 0.7; incoming 1.0 |
| **Slim variant (Voice)** | State orb + tool line only |

### 3.9 Browser Source Cards / Rows

| Property | Value |
|----------|-------|
| **Row height** | 48px min (touch) |
| **Padding** | sm md |
| **Border** | Active: red left border 2px |
| **Background** | Transparent on glass panel |
| **URL** | sm mono primary truncated |
| **Snippet** | xs secondary 2-line |
| **Pending** | Amber badge pulse once |
| **Complete** | Green dot once |
| **Animation** | Row enter 350ms |

### 3.10 Status Widgets

#### Presence Block (Sidebar)

| Element | Spec |
|---------|------|
| Waveform canvas | 40px wide (sidebar) / 120×32px (expanded) |
| Mini core orb | 12px |
| Status copy | xs |
| System row | Green dot + "Titan Online" |
| Brain row | Red dot + "Cerveau Actif" |

#### Presence Ring (Status card)

| Property | Value |
|----------|-------|
| **Type** | SVG circular progress |
| **Track** | Muted circle |
| **Fill** | Red arc; dashoffset 0–100% activity |
| **Center label** | Percentage xs mono |
| **Animation** | Arc lerps with activity; ±5% oscillation idle |

#### Topbar Pills

| Pill | Dot color | Behavior |
|------|-----------|----------|
| Memory | Green | Pulse when subsystem active |
| Tools | Blue | Pulse when tool active |
| Reflection | Red | Intensifies during THINKING |

| Property | Value |
|----------|-------|
| **Height** | 48–56px topbar |
| **Padding** | lg horizontal |
| **Status cross-fade** | 200ms |

#### Telemetry Bar (`tdl-ref-telemetry`)

| Property | Value |
|----------|-------|
| **Height** | 32px |
| **Font** | xs mono muted |
| **Format** | `FPS {n} · Brain {STATE} · Mem {count} · Tools {active} · Refl {status} · {HH:MM:SS}` |
| **Animation** | Numeric cross-fade 100ms — no slot-machine |

### 3.11 Composer (`tdl-composer`)

| Property | Value |
|----------|-------|
| **Row height** | 56–72px |
| **Container background** | alpha 0.46 |
| **Container blur** | 16px |
| **Container radius** | md (8px) |
| **Container border** | 1px white @ 6% |
| **Container shadow** | `tdl-shadow-md` |
| **Internal gap** | sm (8px) |
| **Layout** | Mic (40px circle) · textarea flex 1 · attach · stop · send |
| **Focus** | Border → `tdl-border-focus` @ 60% |
| **Mic idle** | Ghost; icon secondary |
| **Mic listening** | 2px red ring @ 60%; pulse 900ms organic |
| **Mic size Voice** | 48px enlarged option |
| **Slim variant** | Single line; Voice screen |
| **Keyboard** | Enter send; Shift+Enter newline |
| **Hidden** | Settings overlay open |

### 3.12 Sidebar Items (`tdl-nav__item`)

| Property | Value |
|----------|-------|
| **Width** | 100% of sidebar |
| **Padding** | sm md (8px 12px) |
| **Radius** | sm (4px) |
| **Gap icon to label** | 12px |
| **Icon size** | 16px leading stroke |
| **Text** | sm (14px) |
| **Default** | `tdl-text-secondary` |
| **Hover** | Elevated wash; primary text; 100ms opacity |
| **Active** | 2px red left border + `tdl-red-subtle` wash + primary text |
| **Active transition** | 350ms border fade |
| **Placeholder nav** | Muted + "phase ultérieure" marker |
| **Focus** | 2px `tdl-border-focus` ring |

**Nav keys:** chat · projects · memory · obsidian · browser · calendar · trading · voice · settings

### 3.13 Neural Module Labels (`tdl-neural-module`)

| Property | Value |
|----------|-------|
| **Font** | sm uppercase; tracking 0.04em |
| **Subtitle** | xs secondary |
| **Padding** | sm |
| **Radius** | sm |
| **IDLE** | Muted; 50% opacity; muted border |
| **ACTIF** | Primary text; 1px red border; 2.4s pulse glow |
| **Transition** | IDLE→ACTIF 500ms organic |
| **Visibility** | Desktop: all modules; laptop: core + active; tablet: chip in topbar; phone: hidden |

**Modules:** CORE · MÉMOIRE · PLANIFICATION · BROWSER · OBSIDIAN · OUTILS · COMMUNICATION · TRADING · CALENDAR

### 3.14 Tool Progress Card (`tdl-tool-progress-card`)

| Property | Value |
|----------|-------|
| **Size** | Auto; ~280px typical |
| **Position** | Float above dock, right-aligned |
| **Padding** | md |
| **Radius** | md |
| **Background** | alpha 0.46; blur 16px |
| **Shadow** | `tdl-shadow-md` |
| **Max stack** | 3; oldest dismiss first |
| **Animation** | Enter translateY 12px + opacity 350ms; exit 400ms |
| **Progress bar** | Linear; max 30s visible |

### 3.15 Messages (`tdl-message`)

| Variant | Border accent | Label | Text |
|---------|---------------|-------|------|
| User | Left white 10% | "Toi" xs semibold | base primary |
| Titan | Left red 20% | "Titan" xs | base primary relaxed leading |
| System | None | — | sm muted |
| Error | Semantic badge | — | sm primary + error badge |

| Property | Value |
|----------|-------|
| **Padding** | md vertical between messages |
| **Radius** | md — flat blocks, no bubble tails |
| **Animation** | New message fade + translateY 8px 350ms enter |
| **Streaming cursor** | Optional blink 530ms |
| **Forbidden** | Candy bubbles, avatars, emoji reactions |

### 3.16 Settings Overlay (`tdl-settings-panel`)

| Property | Value |
|----------|-------|
| **Scrim** | alpha 0.72 black; blur 0 |
| **Card max-width** | 640px desktop; 560px laptop; 90vw tablet |
| **Card padding** | xl (32px) outer; lg inner |
| **Card radius** | lg (12px) |
| **Card background** | alpha 0.88; blur 22px |
| **Section nav** | 35% width vertical desktop; horizontal chips tablet/phone |
| **Section content** | 65% width |
| **Animation** | Scrim 350ms enter; card scale 0.96→1 slow enter; section cross-fade 200ms |
| **Neural behind** | 28% visibility; continues drifting |

### 3.17 LIVE Confirmation Overlay

| Property | Value |
|----------|-------|
| **Scrim** | 72% black |
| **Card max-width** | 480px |
| **Card radius** | lg (12px) |
| **Actions** | Annuler ghost · Confirmer primary red |
| **Neural** | Paused |

---

## 4. Typography

### 4.1 Font Families

| Token | Stack | Use |
|-------|-------|-----|
| `tdl-font-sans` | Inter, Segoe UI, system-ui, -apple-system, sans-serif | All UI and conversation |
| `tdl-font-mono` | JetBrains Mono, Cascadia Code, Consolas, monospace | Telemetry, timestamps, code, trading data |

**Forbidden:** Display serif; rounded playful fonts.

### 4.2 Title Sizes

| Token | Size | Weight | Color | Use |
|-------|------|--------|-------|-----|
| `tdl-text-display` | 36px / 2.25rem | medium (500) | primary | Launch title only |
| `tdl-text-2xl` | 24px / 1.5rem | semibold (600) | primary | Screen titles |
| `tdl-text-xl` | 20px / 1.25rem | semibold | primary | Panel titles |
| `tdl-text-lg` | 18px / 1.125rem | medium | primary | Section labels |

### 4.3 Body Sizes

| Token | Size | Weight | Color | Use |
|-------|------|--------|-------|-----|
| `tdl-text-base` | 16px / 1rem | normal (400) | primary | Conversation, descriptions, composer |
| `tdl-text-sm` | 14px / 0.875rem | normal | secondary | Labels, nav, metadata, thinking line |
| `tdl-text-xs` | 12px / 0.75rem | normal | muted | Timestamps, badges, telemetry |

### 4.4 Label Sizes

| Context | Style |
|---------|-------|
| Module labels | sm uppercase; tracking 0.04em |
| Form labels | sm medium secondary |
| Message name labels | xs semibold above body |
| Table headers (trading) | xs uppercase wide tracking muted |
| Voice presence | 2xl semibold centered |
| Voice interrupt | sm semibold uppercase tracking-wide |

### 4.5 Tracking

| Token | Value | Use |
|-------|-------|-----|
| `tdl-tracking-tight` | −0.01em | Dense data rows |
| `tdl-tracking-normal` | 0 | Body |
| `tdl-tracking-wide` | 0.04em | Display, wordmark, module titles |

### 4.6 Weight

| Token | Value | Use |
|-------|-------|-----|
| `tdl-weight-normal` | 400 | Body |
| `tdl-weight-medium` | 500 | Labels, nav, buttons |
| `tdl-weight-semibold` | 600 | Titles, emphasis, trading symbols |

### 4.7 Line Height

| Token | Value | Use |
|-------|-------|-----|
| `tdl-leading-tight` | 1.25 | Headings, compact lists |
| `tdl-leading-normal` | 1.5 | Body |
| `tdl-leading-relaxed` | 1.65 | Transcript paragraphs, research summary |

**Hierarchy rule:** Weight and opacity — not color variety.

---

## 5. Colors

### 5.1 Titan Red

| Token | Hex / value | Role |
|-------|-------------|------|
| `tdl-red-core` | `#8b0000` | Primary brand red |
| `tdl-red-glow` | `#b91c1c` | Active states, synaptic highlights, "AI" wordmark |
| `tdl-red-dim` | `#5c0000` | Inactive module borders |
| `tdl-red-subtle` | `rgba(139, 0, 0, 0.15)` | Hover washes, active nav background |
| `tdl-red-pulse` | `rgba(185, 28, 28, 0.35)` | Glow shadows, pulse halos |

**Neural canvas reds:** core `rgba(204, 0, 0, α)` · glow `rgba(255, 26, 26, α)`.

### 5.2 Deep Red Glow

| Context | Specification |
|---------|---------------|
| Ambient edge | Red radial; 8–38% peak opacity; 5.5s breath |
| Thinking core | ×1.38 brightness multiplier |
| Active module | Red border 1–2px; 2.4s pulse |
| Mic listening ring | 2px @ 60% `tdl-border-focus` |
| Composer focus | `tdl-border-focus` @ 60% |
| Glow shadows | `tdl-glow-red-sm/md/lg` tokens |
| Budget | ≤15% red pixels per static frame |

### 5.3 White Text

| Token | Value | Rule |
|-------|-------|------|
| `tdl-text-primary` | `#f5f5f5` | Body, titles — **not pure #FFFFFF** for large blocks |
| Neural white dim | `rgba(255, 255, 255, α)` | Edge halos, node halos |
| Panel edge highlight | 1px white @ 4–8% | Top edge glass catch |

### 5.4 Gray Text

| Token | Value | Role |
|-------|-------|------|
| `tdl-text-secondary` | `#a3a3a3` | Labels, metadata, subtitles |
| `tdl-text-muted` | `#525252` | Placeholders, tertiary, telemetry |
| `tdl-status-idle` | `#737373` | Inactive indicators |

### 5.5 Black Background

| Token | Value | Role |
|-------|-------|------|
| `tdl-bg-void` | `#000000` | Primary canvas — absolute black |
| `tdl-bg-surface` | `#0a0a0a` | Elevated panel base |
| `tdl-bg-elevated` | `#111111` | Inputs, insets |
| Vignette | `rgba(0, 0, 0, α)` | 38–72% at edges |

**Forbidden:** White/light mode; structural surfaces above `#111111`.

### 5.6 Panel Background

| Context | Alpha / value |
|---------|---------------|
| Standard glass | `rgba(0, 0, 0, 0.38)` |
| Elevated glass | `rgba(0, 0, 0, 0.46)` |
| Status card | `rgba(0, 0, 0, 0.44)` |
| Settings card | `rgba(0, 0, 0, 0.88)` |
| Scrim | `rgba(0, 0, 0, 0.72)` |
| High contrast override | ~88% opaque black panels |

### 5.7 Border Colors

| Token | Value |
|-------|-------|
| `tdl-border-subtle` | `rgba(255, 255, 255, 0.06)` |
| `tdl-border-default` | `rgba(255, 255, 255, 0.10)` |
| `tdl-border-active` | `rgba(139, 0, 0, 0.40)` |
| `tdl-border-focus` | `rgba(185, 28, 28, 0.60)` |
| High contrast subtle | `rgba(255, 255, 255, 0.14)` |
| High contrast default | `rgba(255, 255, 255, 0.22)` |
| Split divider (Obsidian) | 1px white @ 6% |

### 5.8 Disabled Colors

| Element | Treatment |
|---------|-----------|
| Buttons/inputs | 40% opacity |
| Text | `tdl-text-muted` |
| Mic disabled | 40% opacity; no ring |
| Placeholder nav | Muted + phase marker |
| **No unique gray fill** | Use opacity on standard tokens |

### 5.9 Status Colors (Dots and Badges Only)

| Token | Value | Use |
|-------|-------|-----|
| `tdl-status-online` | `#22c55e` | Healthy, connected |
| `tdl-status-warning` | `#ca8a04` | PAPER mode, caution, pending |
| `tdl-status-error` | `#dc2626` | Failure |
| `tdl-status-idle` | `#737373` | Inactive |

**Forbidden:** Semantic colors as panel backgrounds or large fills. P&L uses dot only — not row background.

---

## 6. Animation

### 6.1 Durations

| Token | Duration | Primary use |
|-------|----------|-------------|
| `tdl-duration-instant` | 100ms | Hover opacity, icon nudge, numeric cross-fade, nav hover |
| `tdl-duration-fast` | 200ms | Buttons, focus, mic ring, status cross-fade, thinking line |
| `tdl-duration-normal` | 350ms | Panel show/hide, nav switch, screen cross-fade, card enter |
| `tdl-duration-slow` | 600ms | Launch fade, recall ghost fade, progress bar organic |
| `tdl-duration-breath` | 5.5s | Ambient glow cycle |
| `tdl-duration-neural` | 14s | Background drift cycle |
| `tdl-duration-thinking` | 2.4s | Thinking brightness oscillation |
| `tdl-duration-presence-idle` | 6s | Presence widget breathe |

**Presence transitions:**

| Transition | Duration |
|------------|----------|
| Any → Idle | 900ms |
| Any → Listening | 500ms |
| Any → Thinking | 700ms |
| Any → Speaking | 600ms |
| Any → Working | 650ms |
| Voice interrupt → Idle | 200ms (exception) |
| Neural cognitive mode | 650–900ms |
| Orchestrator refocus | 300ms |

### 6.2 Easing

| Token | Bezier | Use |
|-------|--------|-----|
| `tdl-ease-standard` | (0.4, 0, 0.2, 1) | General transitions |
| `tdl-ease-enter` | (0, 0, 0.2, 1) | Elements appearing |
| `tdl-ease-exit` | (0.4, 0, 1, 1) | Elements leaving |
| `tdl-ease-organic` | (0.45, 0.05, 0.55, 0.95) | Glow breathe, neural drift, presence |

### 6.3 Fade Rules

| Event | Duration | Easing | Notes |
|-------|----------|--------|-------|
| Launch neural fade in | 600ms | enter | After 400ms void hold |
| Panel opacity appear | 350ms | enter | Staggered per §1.12 |
| Screen center swap | 350ms | exit + enter | Sidebar/orchestrator stable |
| Settings scrim | 350ms | enter/exit | — |
| Settings card | 350ms | scale 0.96→1 enter | — |
| Message appear | 350ms | fade + translateY 8px | User: opacity only variant 200ms |
| Thinking line | 200ms | enter/exit | — |
| Floating card exit | 400ms | dissolve | — |
| Error message | 350ms | enter | Semantic dot only |
| Status copy | 200ms | cross-fade | — |
| Module ACTIF | 500ms | organic | Then 2.4s pulse loop |

**Forbidden:** Skeleton fades; fake progress fades; slot-machine numeric fades.

### 6.4 Panel Movement

| Action | Movement |
|--------|----------|
| Panel appear | Opacity only — **no slide from offscreen** |
| Panel hide (screen switch) | Center cross-fade only |
| Sidebar tablet collapse | Width 218→56 over 350ms; labels fade 200ms first |
| Orchestrator tablet close | Slide off-screen right 350ms exit |
| Settings card | Scale 0.96→1 — no bounce |
| Button active | translateY 1px only |
| Nav hover | Background fade only — no lateral slide |
| UI panels | **No mouse parallax** |

### 6.5 Card Movement

| Card type | Enter | Exit |
|-----------|-------|------|
| Memory float | Stagger 80ms; fade + translateY −12px | Dissolve 400ms |
| Tool progress | Fade + translateY 12px from bottom 350ms | 400ms; oldest first |
| Exploration | Fade + translateY 12px 350ms | Dissolve 400ms |
| Planning | Sequential highlight 300ms | Cross-fade 350ms |
| Trading alert | 200ms; amber pulse once | Fade 350ms |
| Message | Fade + translateY 8px 350ms | — |

### 6.6 Neural Pulse

| Profile | Pulse interval | Bursts | Speed × | Wave style |
|---------|----------------|--------|---------|------------|
| Idle | 8–12s edge | — | 1.0 | ambient drift |
| Thinking | ~850ms micro | — | 2.15 activity | default radial |
| Memory | 1600ms | 2 | 1.0 | central |
| Planning | 1500ms | 2 | 1.05 | structured |
| Browser | 1200ms | 3 | 1.18 | distributed |
| Trading | 1100ms | 3 | 1.35 | sharp |
| Calendar | 1800ms | 1 | 0.90 | circular |
| Email | 2000ms | 1 | 0.85 | distributed |
| Obsidian | 1700ms | 2 | 0.95 | geometric |
| Voice listen | 900ms | 2 | 1.20 | ripple |
| Voice speak | 520ms | — | 1.1 | circular |
| Default tool | 1600ms | 1 | 1.0 | default |

### 6.7 Tool Activity

| Element | Animation |
|---------|-----------|
| Tool status line | Fade in 200ms when tool starts |
| Tool pill (topbar) | Blue dot pulse when active |
| Orchestrator tools list | Item fade 200ms on add |
| Tool timeline | Reverse chrono; fade 200ms |
| Progress bar | Linear to task duration; max 30s visible |
| Neural | Directed waves toward active cognitive region |

### 6.8 Thinking State

| System | Behavior |
|--------|----------|
| Neural | Activity 0.88; signals max 32; brightness ×1.38 |
| Camera | +1.6% zoom; drift ×0.58 |
| Topbar | "Réflexion en cours" / "Formulation de la réponse" |
| Transcript | "Titan réfléchit…" italic sm |
| Stop button | Fade in 200ms |
| Orchestrator orb | 2.4s breathe |
| Reflection pill | Red dot intensifies |
| Decay on complete | 0.0028/frame → idle over 900ms presence |

### 6.9 Memory Recall

| System | Behavior |
|--------|----------|
| Neural | Recall dive +5.5%; ghost +36; central waves |
| Camera | 600ms organic inward; decay 0.0035/frame |
| MÉMOIRE label | ACTIF 500ms |
| Cards | Stagger 80ms float |
| Status line | "Recherche en mémoire…" |
| Float indicators | Opacity breathe 4s — no bounce |

### 6.10 Voice Ripple

| Phase | Animation |
|-------|-----------|
| Start listening | Mic ring 900ms organic; ripple 0→1 |
| Envelope | Waveform 60fps |
| Speaking | Circular pulses from core 520ms |
| Core glow | Expands with wave rings |
| Mode toggle | Red wash on selected |
| Interrupt | All motion stops 200ms |

### 6.11 Reduced Motion Behavior

When `prefers-reduced-motion` or Settings "Réduire les animations":

| Property | Override |
|----------|----------|
| All durations | 0.01ms effective max 200ms presence |
| Neural drift | Amplitude → 0 |
| Camera | Fixed center; zoom 1.0 |
| Parallax | 0 |
| Ambient glow | Static mean opacity |
| Signal particles | Max 4; spawn interval ×4 |
| Waveform Voice | Static bars |
| Panel transitions | Instant or 100ms |
| Module pulse | Disabled |
| Launch | Instant panel appear acceptable |

---

## 7. Accessibility

### 7.1 Keyboard Navigation

| Requirement | Implementation |
|-------------|----------------|
| Skip link | `#chat-composer`; copy "Aller au message"; visible on focus only |
| Tab order | Sidebar → Topbar → Center content → Orchestrator → Dock composer |
| Focus visible | 2px ring `tdl-border-focus` on all interactive elements |
| Composer | Always reachable; Enter send; Shift+Enter newline |
| Settings | Trap focus within overlay card when open |
| Orchestrator tablet | Open via "Cerveau" button focusable |
| Escape | Closes settings overlay and tablet drawers |
| Nav items | Focusable; activate on Enter/Space |

### 7.2 High Contrast Mode

| Override | Value |
|----------|-------|
| `tdl-border-subtle` | `rgba(255, 255, 255, 0.14)` |
| `tdl-border-default` | `rgba(255, 255, 255, 0.22)` |
| `tdl-text-muted` | `#bdbdbd` |
| `tdl-text-secondary` | `#e0e0e0` |
| Panel background | ~88% opaque black |
| `tdl-red-pulse` | ~0.55 alpha |
| Void | Remains `#000000` |
| Neural field | Unchanged |
| Layout dimensions | Unchanged |

### 7.3 Reduced Motion

See §6.11. Settings toggle "Réduire les animations" mirrors system preference; persists locally; immediate effect.

### 7.4 Font Scaling

| Setting | Root scale |
|---------|------------|
| 100% | 1rem base |
| 112% | 1.12× |
| 125% | 1.25× |

**Effects:** Composer min-height increases; cards may wrap 2 rows at 125% on laptop; immediate apply without save.

**Minimum rendered size:** 12px (xs) on mobile; prefer sm for secondary.

### 7.5 Focus Rings

| Property | Value |
|----------|-------|
| Width | 2px |
| Color | `tdl-border-focus` — `rgba(185, 28, 28, 0.60)` |
| Offset | 2px standard |
| Style | Solid |
| Settings | Red on all interactive elements |
| Never remove | `outline: none` without `:focus-visible` replacement |

### 7.6 Minimum Contrast

| Requirement | Rule |
|-------------|------|
| Text on glass | WCAG AA against **composited** glass-over-neural background |
| Primary on void | `#f5f5f5` on `#000000` — verify AA |
| Muted text | Use only xs/sm sizes for non-essential copy |
| Semantic dots | Must remain distinguishable in high contrast |
| Error states | Badge + text — not color alone |

### 7.7 Touch Targets

| Context | Minimum |
|---------|---------|
| Mobile | 44×44px |
| Mic button | 44×44px |
| Phone interrupt | 56×56px |
| Source rows | 48px height |
| Search input (memory) | 44px height |

### 7.8 ARIA Requirements

| Component | Attribute |
|-----------|-----------|
| Launch overlay | `aria-live="polite"` |
| Conversation scroll | `aria-live="polite"` |
| Tool status line | `aria-live="polite"` |
| Mic button | `aria-pressed` when listening; label "Parler à Titan" |
| Ambient glow | `aria-hidden="true"` |
| Memory cards layer (decorative) | `aria-hidden="true"` when decorative |
| Neural canvas | `aria-hidden="true"` — status communicated via topbar |

---

## 8. Implementation Rules

### 8.1 No Creative Freedom

| Rule | Enforcement |
|------|-------------|
| Layout | Implement exact grid in §1 — no alternative column counts |
| Colors | TDL tokens only — no hex outside spec |
| Spacing | TDL space tokens only — no arbitrary 13px, 17px |
| Components | Use §3 definitions — no new component families without spec amendment |
| Screens | Nine screens per Master Mockup — no merged or split screens |
| French copy | Presence states and empty states exactly as Blueprint/Mockup |
| Neural | Never replace with static image, CSS gradient, or video loop |

### 8.2 Do Not Reinterpret Mockup

| Forbidden interpretation | Required behavior |
|--------------------------|-------------------|
| "Close enough" spacing | Measure against token values |
| "Modern refresh" of chat | Flat blocks with border accents — no bubbles |
| "Cleaner" opaque panels | Glass alphas exactly as §3.3 |
| "Better" loading UX | Presence + neural — no skeletons |
| "Simpler" nav | All nav keys present; placeholders marked |
| Custom thinking indicator | "Titan réfléchit…" — no bouncing dots |
| Stock dashboard patterns | Mission-aware Projects — not Kanban clone |

### 8.3 Missing Spec Protocol

```
IF required value missing from Production Spec
  AND missing from Master Mockup
  AND missing from D1 companion docs
THEN stop implementation
  AND request product clarification
  AND document answer in spec amendment
ELSE IF missing from Production Spec only
THEN resolve from Master Mockup → Blueprint → D1 docs in order
```

### 8.4 Backend Unchanged

| Layer | Rule |
|-------|------|
| API endpoints | No frontend-driven API changes |
| WebSocket / polling | Consume existing status shapes |
| Brain pipeline | Presence states map to existing enums |
| Tool orchestrator | Display data — do not invent tool outcomes |
| Memory | User isolation Nolan ≠ Ibrahim — enforce in UI |
| Auth | Bearer secret client-side — settings field only |
| Trading | PAPER default; LIVE requires confirmation overlay |
| Obsidian | Existing vault only — never conflate with Titan Memory |

### 8.5 Frontend Rebuild Requirements

| Requirement | Specification |
|-------------|---------------|
| Target | Titan Frontend V2 full rebuild |
| Visual authority | `TITAN_MASTER_MOCKUP.md` composition per screen |
| Shell | Persistent — neural never unmounts on nav |
| Routing | Nav keys: chat, projects, memory, obsidian, browser, trading, calendar, voice, settings |
| Settings | Overlay — not destructive route |
| Token implementation | CSS variables or equivalent mapping 1:1 to TDL tokens |
| Neural engine | Canvas 2D per `TITAN_NEURAL_ENGINE.md`; hooks wired to backend events |
| Performance | Adaptive quality per §2.16 |
| Tests | Visual regression against spec values; presence state integration smoke |
| Language | French UI copy; English code identifiers |

### 8.6 Prohibited Patterns (Release Blockers)

| Pattern | Reference |
|---------|-----------|
| Screen without neural field | UI Bible §2 |
| Opaque white/light panels | Design Language §2 |
| Skeleton loading screens | Blueprint global |
| Candy chat bubbles | Mockup forbidden |
| Bouncy spring physics | Animation Guide §18 |
| Strobe / flash > 3Hz | Animation Guide §18 |
| Three-dot typing indicator | UI Bible §4.9 |
| Slot-machine numeric scroll | Mockup §6 Trading |
| Red fill >15% static frame | Design Language §2.2 |
| Agent personas with avatars | Single intelligence |
| Trading LIVE without confirmation | Mockup §6.13 |
| Memory mixed across users | Constitution |
| Obsidian as Titan memory | Product policy |
| Auto-create Obsidian vault | Product policy |
| Third sidebar on ultrawide | Layout Guide §7 |
| User pan/zoom neural V1 | Neural Engine §10 |
| Invented layouts not in mockup | Mockup authority |

### 8.7 Implementation Verification Checklist

Before any frontend PR merges:

- [ ] Layout matches §1 at all six breakpoints
- [ ] Neural field matches §2 parameters and performance targets
- [ ] Every component in §3 matches size, padding, radius, border, background, states
- [ ] Typography uses §4 tokens exclusively
- [ ] Colors use §5 tokens exclusively
- [ ] Animation uses §6 durations, easing, and profiles
- [ ] Accessibility §7 keyboard, contrast, motion, scale tested
- [ ] No §8.6 prohibited patterns
- [ ] Screen composition matches Master Mockup diagram for active screen
- [ ] Presence copy French and honest to backend state
- [ ] Empty, loading, error states per Blueprint — no lorem ipsum
- [ ] Backend integration unchanged — display-only mapping

---

## Appendix A — Screen Quick Reference

| Screen | Nav key | Chat max-width | Hero panel | Hero status card | ACTIF module |
|--------|---------|----------------|------------|------------------|--------------|
| Home | chat | 720px | Conversation | All 5 equal | CORE + dynamic |
| Projects | projects | — | Active project header | État Cognitif | PLANIFICATION |
| Memory | memory | — | Memory cards grid | Mémoire Récente | MÉMOIRE |
| Obsidian | obsidian | — | Note reader 60% | Obsidian | OBSIDIAN |
| Exploration | browser | — | Research summary | Browser | BROWSER |
| Trading | trading | — | Market overview | État Cognitif + trading | TRADING |
| Calendar | calendar | — | Agenda grid | Agenda chip | CALENDAR + PLANIFICATION |
| Voice | voice | — | Wave visualization | Présence | CORE + COMMUNICATION |
| Settings | settings | — | Settings card overlay | Hidden | All IDLE 40% |

---

## Appendix B — Presence State Copy (French)

| State | Copy |
|-------|------|
| Idle | Présent — en attente |
| Listening | À l'écoute |
| Thinking | Réflexion en cours |
| Streaming | Formulation de la réponse |
| Speaking | Titan parle |
| Working | En action |
| Planning | Planification |
| Error | Problème détecté |
| Interrupted (Voice) | Interrompu — prêt |

**Priority when concurrent:** Listening > Thinking > Speaking / Working > Idle.

---

## Appendix C — Authority Hierarchy (Complete)

```
1. Constitution (core/constitution/titan_constitution.md)
2. Experience Manifesto (TITAN_EXPERIENCE_MANIFESTO.md)
3. UI Bible (TITAN_UI_BIBLE.md) — philosophy, interaction law
4. Master Blueprint (TITAN_MASTER_BLUEPRINT.md) — screen behavior, states
5. Master Mockup (TITAN_MASTER_MOCKUP.md) — visual composition authority
6. Production Spec (this document) — consolidated implementation measurements
7. D1 Companion Specs — token and subsystem detail:
   - TITAN_DESIGN_LANGUAGE.md
   - TITAN_LAYOUT_GUIDE.md
   - TITAN_ANIMATION_GUIDE.md
   - TITAN_NEURAL_ENGINE.md
   - TITAN_COMPONENT_LIBRARY.md
8. Frontend implementation code
```

**Resolution rules:**

- Visual detail conflict: Mockup > Blueprint > UI Bible
- Behavioral/backend mapping: Blueprint > Mockup
- Numeric implementation: Production Spec > D1 docs when consolidated here
- Missing value: Ask product — never invent

---

## Document Metadata

| Field | Value |
|-------|-------|
| Phase | D4 |
| Version | 1.0.0 |
| Established | 2026-07-06 |
| Authors | Titan Product (Nolan Hassing) |
| Predecessor | Phase D3 Master Mockup |
| Successor | Phase D5+ Frontend V2 implementation |
| Authority | **Final technical authority before frontend rebuild** |

---

**End of Titan UI Production Specification — Phase D4**

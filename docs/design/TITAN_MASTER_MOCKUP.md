# Titan Master Mockup

**Phase D3 — Official Visual Specification**

**Status:** The **only** visual authority for Titan frontend work. No developer may invent layouts, spacing, hierarchy, or visual behavior after this document exists.

**Scope:** Complete visual specification for every major screen — composition, hierarchy, depth, light, motion, panel behavior, and perceptual flow. This document defines **what the user sees** — not how it is built.

**This is not implementation.** No CSS. No HTML. No JavaScript. No React. No code of any kind appears in this document.

---

## Document Authority

| Rule | Description |
|------|-------------|
| **Mandatory** | All frontend design and implementation must conform to this mockup. Deviations require explicit product approval. |
| **Hierarchy** | Constitution → Experience Manifesto → UI Bible → Master Blueprint → **Master Mockup** → D1 companion specs (Design Language, Layout, Animation, Neural Engine, Components). |
| **Conflict resolution** | When Blueprint and Mockup differ on visual detail, **Mockup wins**. Blueprint wins on behavioral/backend mapping. |
| **Change control** | Visual amendments require version note and product approval. |

### Companion Documents

| Document | Role |
|----------|------|
| `TITAN_MASTER_BLUEPRINT.md` | Screen purpose, panel inventory, states |
| `TITAN_DESIGN_LANGUAGE.md` | Visual tokens (TDL) |
| `TITAN_LAYOUT_GUIDE.md` | Spatial measurements and breakpoints |
| `TITAN_NEURAL_ENGINE.md` | Neural field rendering law |
| `TITAN_ANIMATION_GUIDE.md` | Motion timing and easing |
| `TITAN_COMPONENT_LIBRARY.md` | Component anatomy |
| `TITAN_UI_BIBLE.md` | Philosophy and interaction law |

---

## The Governing Visual Law

Every screen in Titan must feel like:

> **"The user is inside Titan's mind."**

This is not metaphor alone. It is a perceptual contract:

- The void is infinite and alive beneath all surfaces
- Glass instruments float in dark space — never opaque walls
- Cognition is visible before content is read
- The eye always knows where Titan is, what Titan is doing, and where to act next
- No screen resembles a separate application

---

## Global Visual Foundation

These properties apply to **every screen** unless a screen section explicitly overrides them.

### Layer Stack (Perceptual Z-Order)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 0 — NEURAL STAGE        Full viewport. Always visible. Alive.   │
│  LAYER 1 — AMBIENT GLOW        Edge pulse. Atmospheric red presence.    │
│  LAYER 2 — WORKSPACE           Sidebar · Center · Orchestrator · Dock   │
│  LAYER 3 — FLOATING CARDS      Memory, tool, exploration, planning      │
│  LAYER 4 — STATUS EMPHASIS     Telemetry elevation, urgent badges       │
│  LAYER 5 — OVERLAYS            Settings, confirmations, voice immersive │
│  LAYER 6 — TOASTS              Future notifications                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Universal Composition (Desktop Reference ≥1280px)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░░░░░░░ NEURAL FIELD (full bleed, infinite) ░░░░░░░░░░░░░ │
│ ┌──────────┬────────────────────────────────────────────┬─────────────────┐ │
│ │          │  TOPBAR — session truth, pills, actions      │                 │ │
│ │ SIDEBAR  ├────────────────────────────────────────────┤  ORCHESTRATOR    │ │
│ │  218px   │                                              │  318px           │ │
│ │          │  CENTER — active screen content              │  cognitive       │ │
│ │  glass   │  (chat, projects, memory, etc.)              │  transparency    │ │
│ │          │                                              │  glass           │ │
│ │          │  [neural module labels — center overlay]     │                 │ │
│ └──────────┴────────────────────────────────────────────┴─────────────────┘ │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ BOTTOM DOCK — status cards · tool/memory lines · composer · telemetry   │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Workspace outer padding:** 1.25rem from viewport edges.
**Inter-region gap:** 0.875rem between sidebar, center, orchestrator.
**Neural visibility rule:** Minimum 15% of viewport neural field must remain perceptible through gaps and glass at all times on desktop.

---

### Depth Hierarchy (Global)

| Depth tier | Visual character | Elements |
|------------|------------------|----------|
| **Abyss** | Farthest. Barely visible nodes. 10% opacity. | Neural abyss layer, void vignette |
| **Atmosphere** | Edge glow, haze, ambient pulse | Red radial at corners, depth fog |
| **Mind surface** | Mid-depth neural activity | Active synapses, cognitive regions |
| **Glass instruments** | Floating panels, translucent | Sidebar, center, orchestrator, dock |
| **Foreground cognition** | Ephemeral floats | Memory cards, tool progress, exploration cards |
| **Command surface** | Highest legibility | Composer, interrupt controls, confirmations |
| **Overlay plane** | Scrim + solid card | Settings, LIVE confirmation |

Depth is communicated through **opacity, blur, parallax, and glow** — never through perspective transforms that tilt panels.

---

### Light Behavior (Global)

| Light source | Position | Character |
|--------------|----------|-----------|
| **Neural core** | Center of viewport, behind center column | Brightest convergence — red-white point. Pulses with cognitive load. |
| **Ambient edge glow** | Viewport perimeter | Soft red radial. 5.5s breath cycle. Peak 38–44% of presence glow. |
| **Panel edge highlight** | Top edge of glass panels | 1px white at 4–6% opacity — simulates light catching glass from above |
| **Active module glow** | Cognitive region label position | Red border pulse when ACTIF |
| **Semantic dots** | Inline with status elements | Green/amber/red — point sources only, never area fills |

**No directional daylight.** No top-left white shadows. All luminance emerges from the void and synaptic energy.

---

### Glow Behavior (Global)

| Glow type | Trigger | Visual |
|-----------|---------|--------|
| **Idle breathe** | Default | Low red halo at screen edges; core dim pulse |
| **Thinking intensify** | Brain processing | Core brightens ×1.38; nearby nodes glow 0.78; glow level → 0.78 |
| **Tool directed** | Tool active | Signal paths glow toward active cognitive region |
| **Memory recall** | Retrieval | Central convergence wave; ghost nodes at +0.45 opacity |
| **Voice listening** | Mic active | Circular ripple from core; mic ring red pulse |
| **Voice speaking** | TTS output | Rhythmic circular pulses; brightness ×1.07 |
| **Error calm** | Failure | All glow decays to idle within 900ms — never alarm strobing |

Red glow never exceeds ~15% of visible pixels in a static frame.

---

### Glass Effect (Global Panel Treatment)

| Property | Standard panel | Reference shell | Elevated card | Status card |
|----------|----------------|-----------------|---------------|-------------|
| **Background alpha** | 0.38 | 0.38 | 0.46 | 0.44 |
| **Backdrop blur** | 16px | 22px | 16px | 12px |
| **Border** | 1px white @ 4% | 1px white @ 4% | 1px white @ 6% | 1px white @ 6% |
| **Shadow** | 0 8px 32px black @ 45% | same | 0 4px 12px black @ 60% | 0 4px 12px black @ 50% |
| **Inner highlight** | None | Top edge 1px @ 6% | None | None |

Text must meet WCAG AA against **composited** glass-over-neural background.

---

### Typography Hierarchy (Global)

| Tier | Token | Size | Weight | Color | Use |
|------|-------|------|--------|-------|-----|
| **Display** | display | 36px | medium | primary | Launch title only |
| **Screen title** | 2xl | 24px | semibold | primary | Screen headers |
| **Panel title** | xl | 20px | semibold | primary | Section headers |
| **Section label** | lg | 18px | medium | primary | Subsection headers |
| **Body** | base | 16px | normal | primary | Conversation, descriptions |
| **Secondary** | sm | 14px | normal | secondary | Labels, nav, metadata |
| **Tertiary** | xs | 12px | normal | muted | Timestamps, badges, telemetry |
| **Data** | xs/sm mono | 12–14px | normal | secondary | FPS, version, ticks, code |
| **Module label** | sm uppercase | 14px | medium | secondary/muted | TITAN CORE, MÉMOIRE — wide tracking 0.04em |

Hierarchy through **weight and opacity**, not color variety.

---

### Icon Placement Law (Global)

| Zone | Icon size | Color | Placement |
|------|-----------|-------|-----------|
| Sidebar nav | 16px left of label | currentColor secondary; primary when active | Leading, 12px gap to text |
| Topbar actions | 16px | secondary; red accent on brain button | Trailing right, 8px gap between |
| Composer | 18px mic; 16px attach/send | secondary; mic red ring when active | Leading mic, trailing actions |
| Status card header | 16px | secondary | Leading before card title |
| Orchestrator section | 14px | muted | Leading before section label |
| Settings section nav | 16px | secondary; primary when active | Leading before section name |

Stroke icons only. 1.5px stroke at 24px viewBox. No filled colorful icons.

---

### Sidebar Behavior (Global)

| Aspect | Specification |
|--------|---------------|
| **Width** | 218px fixed (240px ultrawide ≥2560px) |
| **Position** | Left edge of workspace, full height minus dock |
| **Surface** | Reference glass (22px blur) |
| **Structure** | Logo block (top) → Nav list (center, flex grow) → Presence block (bottom) |
| **Logo** | "Titan" + "AI" (red accent) + version mono xs below |
| **Active nav** | 2px red left border + subtle red wash background + primary text |
| **Inactive nav** | Secondary text; hover → elevated wash 100ms |
| **Presence block** | Mini waveform + state orb + status copy xs |
| **Collapse** | Tablet: 56px icon rail. Phone: bottom sheet. |
| **Neural behind** | Fully visible through glass — sidebar never opaque |

---

### Top Navigation (Global)

| Aspect | Specification |
|--------|---------------|
| **Position** | Top of center column, above active view content |
| **Height** | ~48–56px |
| **Surface** | Transparent or minimal glass strip — no heavy panel box |
| **Left zone** | Subsystem pills: Memory (green dot), Tools (blue dot), Reflection (red dot) |
| **Center zone** | Presence copy — authoritative French status, sm/base |
| **Right zone** | Icon actions: info, window, menu + "Cerveau" brain button (red accent) |
| **Screen context** | Optional pill after pills: project name, vault name, broker mode, date |
| **Animation** | Status cross-fade 200ms on state change |

---

### Bottom Dock (Global)

| Row | Height | Content |
|-----|--------|---------|
| **Status cards** | 88–104px | 5 equal-width glass cards |
| **Status lines** | auto (~24px) | Tool activity line and/or memory status line |
| **Composer** | 56–72px | Mic + textarea + attach + stop + send |
| **Telemetry** | 32px | Mono xs strip: FPS · Brain · Memory · Tools · Reflection · clock |

**Dock spans** full workspace width (sidebar + center + orchestrator).
**Dock surface** is transparent container — individual rows have their own glass treatment.
**Composer** is always the highest legibility element in the dock.

---

### Floating Card Families (Global)

| Card type | Max visible | Position | Enter | Exit |
|-----------|-------------|----------|-------|------|
| **Memory cards** | 4 stacked | Center column, above chat, right-aligned | Stagger 80ms, fade + translateY -12px | Dissolve 400ms |
| **Tool progress** | 3 stacked | Above dock, right of center | Fade + translateY 12px from bottom, 350ms | Oldest dismiss first |
| **Planning cards** | 2 | Center-left, below topbar | Sequential highlight 300ms | Cross-fade out 350ms |
| **Exploration cards** | 3 | Center, interleaved with content | Fade + translateY 12px | Dissolve 400ms |
| **Trading alerts** | 3 | Top-right of center, below topbar | Enter 200ms, amber pulse once | Fade 350ms |

All floating cards use elevated glass (0.46 alpha, 16px blur, md shadow).

---

### Panel Appearance and Disappearance (Global)

**Appearance (screen load / region reveal):**
1. Neural field already visible and alive
2. Region fades from opacity 0 → 1 over 350ms (enter easing)
3. Stagger order on cold load: sidebar (0ms) → main (200ms) → orchestrator (400ms) → dock (600ms)
4. No slide-from-offscreen. No bounce. No scale pop.

**Disappearance (overlay open / screen switch):**
1. Center content cross-fades 350ms — outgoing fades exit easing, incoming fades enter easing
2. Sidebar, orchestrator, dock remain stable
3. Floating cards dissolve before center swap if context changes
4. Settings overlay: workspace dims to 28% visibility; does not unmount

**Collapse (tablet/mobile):**
1. Sidebar compresses to rail over 350ms — labels fade 200ms before width change
2. Orchestrator slides off-screen right 350ms exit easing
3. Dock compresses rows — status cards become scroll or chip

---

### Transition Law (Global)

| Event | Duration | Easing | Visual |
|-------|----------|--------|--------|
| Screen switch | 350ms | enter/exit | Center cross-fade; neural cognitive mode lerps 650–900ms |
| Orchestrator refocus | 300ms | standard | Section emphasis shift; no layout jump |
| Presence state | 500–900ms | organic | Copy cross-fade; glow lerps |
| Module label ACTIF | 500ms | organic | Border + opacity; pulse begins 2.4s cycle |
| Floating card | 350ms | enter/exit | As card family table |
| Neural mode change | 650–900ms | organic | Activity, brightness, camera lerp |

---

### Eye Flow Model (Global)

On every screen, the perceptual path is:

```
1. PERIPHERAL ALIVE — neural motion registers subconsciously (void is not dead)
2. PRESENCE ANCHOR — topbar center copy or voice stage presence confirms Titan state
3. PRIMARY CONTENT — center column hero draws focused attention
4. COGNITIVE DEPTH — orchestrator provides "what Titan is doing" for curious eye
5. COMMAND — bottom composer is the action terminus (where the user acts)
6. AMBIENT CONTEXT — status cards and sidebar provide peripheral subsystem awareness
```

The brain attracts attention through **motion contrast** — idle drift is slow; thinking intensifies; the eye is drawn to change, not to a static logo.

---

### Neural Field Visibility (Global)

| Condition | Visibility |
|-----------|------------|
| Desktop idle | Full field; 15%+ visible through all glass gaps |
| Desktop active thinking | Field brightens behind center column; visible through glass |
| Tablet | Field visible in top/bottom gaps; reduced node count −20% |
| Phone | Field visible above topbar and behind composer; reduced −30% nodes |
| Settings overlay | Field at 28% through scrim — still alive, still drifting |
| Voice immersive | Field elevated; wave stage does not obscure field |
| High contrast mode | Field unchanged; panels more opaque |

---

### Camera Position (Global)

| State | Position | Zoom | Drift |
|-------|----------|------|-------|
| **Idle** | Centered on neural core | Baseline (1.0) | ±4.8% × 3.8% viewport gentle drift; breathe ±1.4% |
| **Thinking** | Subtle inward focus | +1.6% | Drift amplitude ×0.58 |
| **Memory recall** | Recall dive inward | +5.5% over 600ms | Central convergence |
| **Tool working** | Bias toward active cognitive region | Baseline | Directed — region offset ≤8% viewport |
| **Voice listening** | Centered | Baseline | Reduced drift — stability for attention |
| **Voice speaking** | Centered | +0.8% | Rhythmic micro-pulse |
| **Reduced motion** | Fixed center | 1.0 | No drift |

---

### Brain Visibility (Global)

The brain is **always visible** as the neural field. There is no mode where the brain is replaced by a static background, white fill, or opaque panel.

| Element | Visibility |
|---------|------------|
| Neural canvas | 100% viewport, always rendering |
| Cognitive module labels | Desktop: all modules shown; tablet: active chip only; phone: hidden |
| Orchestrator sparkline | Miniature neural activity echo |
| Telemetry brain state | Text mirror of neural state enum |
| Presence orb | Abstract core representation in sidebar and orchestrator |

---

## Screen Index

| # | Screen | Nav key | Visual identity |
|---|--------|---------|-----------------|
| 1 | Home | `chat` | Conversation hero — the mind speaks here |
| 2 | Projects | `projects` | Mission cathedral — structured intent |
| 3 | Memory | `memory` | Recall sanctuary — depth and ghosts |
| 4 | Obsidian | `obsidian` | Knowledge vault — geometric precision |
| 5 | Exploration | `browser` | Research horizon — distributed signals |
| 6 | Trading | `trading` | Market sharpness — controlled urgency |
| 7 | Calendar | `calendar` | Temporal rhythm — circular time |
| 8 | Voice | `voice` | Immersive presence — the mind listens |
| 9 | Settings | `settings` | Configuration veil — mind behind scrim |

---

---

# 1. HOME

**Nav key:** `chat`  
**Visual identity:** The command surface — conversation as hero, mind as atmosphere.

---

## 1.1 Overall Composition

The user stands at the center of Titan's consciousness. The conversation column is the brightest glass instrument. The neural field breathes behind and between all panels. The orchestrator reveals depth without competing with dialogue.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░░░░ NEURAL — full bleed, idle/thinking profile ░░░░░░░ │
│ ┌──────────┬────────────────────────────────────────────┬────────────────┐ │
│ │ SIDEBAR  │ TOPBAR: [pills] · Présent — en attente · [actions]         │ │
│ │          ├────────────────────────────────────────────┤ ORCHESTRATOR   │ │
│ │ Chat ●   │  [CORE]  [MÉMOIRE]  [PLAN]  [BROWSER]      │ ┌─ State ────┐ │ │
│ │ Projects │       (module labels — overlay)             │ │ Plan       │ │ │
│ │ Memory   │ ┌──────────────────────────────────────┐   │ │ Tools      │ │ │
│ │ ...      │ │                                      │   │ │ Sparkline  │ │ │
│ │          │ │     CONVERSATION (max 720px)         │   │ └────────────┘ │ │
│ │          │ │     centered in column               │   │                │ │
│ │          │ │                                      │   │                │ │
│ │          │ └──────────────────────────────────────┘   │                │ │
│ │ [presence│                                            │                │ │
│ │  block]  │                                            │                │ │
│ └──────────┴────────────────────────────────────────────┴────────────────┘ │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ [Mémoire][Obsidian][Browser][Cognitif][Présence]  ← status cards       │ │
│ │ Tool: Exploration web…                    ← optional status line        │ │
│ │ [mic] [textarea — Que veux-tu accomplir ?] [attach] [send]              │ │
│ │ FPS 60 · Brain IDLE · Mem 12 · Tools 0 · Refl -- · 14:32:01            │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 1.2 What the User Sees First

1. **Neural motion** — peripheral registration of living void (subconscious, <2s)
2. **Topbar presence copy** — "Présent — en attente" centered (conscious anchor)
3. **Conversation area** — welcome message or last exchange (primary focal point)
4. **Composer** — input field at bottom (action affordance)

The sidebar and orchestrator are **orientation**, not first impression.

---

## 1.3 Eye Flow

```
Neural periphery → Topbar presence → Conversation transcript → Composer
                              ↘ Orchestrator (if user seeks depth)
                              ↘ Status cards (peripheral glance)
```

During thinking: eye is drawn **upward** to topbar status change ("Réflexion en cours") and **behind** glass to intensified neural glow — then back to transcript for "Titan réfléchit…" line.

---

## 1.4 Panel Positions and Hierarchy

| Priority | Panel | Position | Visual weight |
|----------|-------|----------|---------------|
| 1 | Conversation | Center column, flex 1 | Primary glass, brightest text |
| 1 | Composer | Bottom dock | Primary — highest legibility |
| 2 | Orchestrator | Right 318px | Secondary glass — cognitive depth |
| 2 | Sidebar | Left 218px | Secondary glass — navigation |
| 3 | Topbar | Center top | Tertiary — minimal chrome |
| 3 | Status cards | Dock row 1 | Tertiary — compact summaries |
| 4 | Module labels | Center overlay | Decorative — 50% opacity when IDLE |
| 4 | Telemetry | Dock footer | Quaternary — mono xs |
| 5 | Floating cards | Center above chat | Ephemeral — elevated glass |

---

## 1.5 Spacing Philosophy

- **Conversation breathing room:** 1.5rem inner padding; messages separated by md (12px) gap
- **Transcript max-width 720px** centered — void visible left and right within center column
- **Welcome state:** generous vertical centering — 2xl space above first message
- **Composer separation:** lg (24px) gap between status lines and composer
- **Intentional void:** gaps between sidebar/center/orchestrator reveal neural — never fill with widgets

---

## 1.6 Depth Hierarchy (Home)

| Layer | Elements |
|-------|----------|
| Abyss | Deep neural nodes behind orchestrator |
| Mind surface | TITAN CORE label region — brightest when thinking |
| Glass | Chat panel, sidebar, orchestrator |
| Foreground | Memory cards, tool progress cards floating above chat |
| Command | Composer, stop button when active |

---

## 1.7 Neural Field Visibility

| State | Field character |
|-------|-----------------|
| Idle | Ambient drift; TITAN CORE label IDLE (50% opacity); activity 0.08 |
| Thinking | Core brightens; signals increase; COMMUNICATION + CORE labels ACTIF |
| Tool active | Directed waves toward active module (BROWSER, OBSIDIAN, etc.) |
| Memory recall | MÉMOIRE ACTIF; recall dive; ghost nodes; memory cards float |
| Streaming | Sustained thinking profile; "Formulation de la réponse" in topbar |

Neural field visible through chat glass at ~40% perceptual strength behind panel.

---

## 1.8 Camera Position (Home)

| State | Camera |
|-------|--------|
| Idle | Centered; gentle drift; breathe ±1.4% |
| Thinking | Inward focus +1.6% zoom; drift ×0.58 |
| Tool | Bias toward active module region (max 8% offset) |
| Memory recall | Recall dive +5.5% over 600ms |

---

## 1.9 Light and Glow (Home)

| Element | Light behavior |
|---------|----------------|
| Neural core | Visible through center column; pulses with thinking |
| Topbar Reflection pill | Red dot intensifies during THINKING |
| Active nav (Chat) | Red left border glow |
| Orchestrator orb | Breathes 2.4s cycle during thinking; dim at idle |
| Presence ring (sidebar) | Slow ±5% fill oscillation |
| Composer focus | Border transitions to `tdl-border-focus` red @ 60% |

---

## 1.10 Glass, Blur, Transparency (Home)

| Panel | Alpha | Blur |
|-------|-------|------|
| Sidebar | 0.38 | 22px |
| Chat panel | 0.38 | 22px |
| Orchestrator | 0.38 | 22px |
| Status cards | 0.44 | 12px |
| Composer container | 0.46 | 16px |
| Floating memory/tool cards | 0.46 | 16px |

---

## 1.11 Typography (Home)

| Element | Style |
|---------|-------|
| Welcome message | base, secondary, centered |
| User message | base, primary, semibold name label xs above |
| Titan message | base, primary, relaxed leading — no bubble tails |
| Thinking line | sm, secondary, italic — "Titan réfléchit…" |
| System message | sm, muted |
| Error message | sm, primary body + semantic error badge |
| Composer placeholder | base, muted — "Que veux-tu accomplir ?" |
| Module labels | sm uppercase, wide tracking, secondary/ACTIF primary |

---

## 1.12 Chat Placement

- **Region:** Center column, below topbar, above dock
- **Width:** Max 720px centered horizontally in center column
- **Height:** Flex 1 — fills available vertical space
- **Scroll:** Vertical; auto-scroll unless user scrolled up
- **Messages:** Flat blocks — not speech bubbles. Subtle left border accent: user = white 10%, Titan = red 20%

---

## 1.13 Composer Placement

- **Region:** Bottom dock, row 3
- **Layout:** Horizontal flex — mic (40px circle) · textarea (flex 1) · attach · stop (hidden) · send
- **Mic:** Full radius; 18px icon; red ring 2px when listening
- **Textarea:** Single line default; expands to 4 lines max
- **Stop:** Fades in 200ms during thinking/streaming; red ghost button
- **Send:** Primary red accent when input non-empty

---

## 1.14 Status Placement

| Element | Position |
|---------|----------|
| Topbar presence | Center of topbar — authoritative |
| Subsystem pills | Topbar left |
| Orchestrator state badge | Top of orchestrator panel |
| Status cards | Dock row 1 — 5 equal cards |
| Tool status line | Dock row 2, left-aligned |
| Memory status line | Dock row 2, below or beside tool line |
| Telemetry | Dock row 4, full width mono strip |

---

## 1.15 Tool Placement (Home)

| Element | Position |
|---------|----------|
| Tool timeline | Orchestrator — Tools section |
| Tool status line | Above composer |
| Tool progress cards | Float above dock, right-aligned, max 3 stack |
| Tool pill (topbar) | Blue dot pulses when tool active |

---

## 1.16 Memory Cards (Home)

When memory retrieval occurs during conversation:

- **Position:** Float above conversation, right-aligned, max 4 stacked
- **Size:** ~280px wide, auto height
- **Content:** Category chip + note excerpt + relevance indicator
- **Surface:** Elevated glass (0.46 alpha)
- **Enter:** Stagger 80ms; fade + translateY -12px
- **Exit:** Dissolve 400ms when recall completes
- **Visual:** Subtle red left border; ghost nodes appear in neural field behind

---

## 1.17 Sidebar (Home)

- Chat nav item **active** — red left border + wash
- Presence block at bottom: mini waveform (40px wide) + orb (12px) + "Présent" xs
- Other nav items secondary; hover wash 100ms

---

## 1.18 Top Navigation (Home)

- Pills: Memory · Tools · Reflection — dots only active when subsystem engaged
- Center: Presence copy (changes with state)
- Right: Info, window, menu icons + "Cerveau" button

---

## 1.19 Bottom Telemetry (Home)

- Full strip visible desktop/laptop
- Format: `FPS {n} · Brain {STATE} · Mem {count} · Tools {active} · Refl {status} · {HH:MM:SS}`
- Mono xs, muted text, secondary values
- Numeric cross-fade 100ms on update — no slot-machine scroll

---

## 1.20 How Panels Appear and Disappear (Home)

| Event | Behavior |
|-------|----------|
| Cold load | Void → neural fade 600ms → panel stagger 200ms each → welcome visible |
| Send message | Thinking line fades in 200ms; stop button fades in; no modal |
| Tool start | Tool line fades in 200ms; progress card enters from bottom |
| Memory recall | Memory cards stagger in; MÉMOIRE label → ACTIF 500ms |
| Response complete | Thinking line fades; stop fades; presence → idle 900ms |
| Navigate away | Chat persists in memory; center cross-fades to new screen |

---

## 1.21 Neural Field Reaction (Home)

| User action | Neural response |
|-------------|-----------------|
| Type in composer | No change until send |
| Send message | THINKING profile over 700ms; activity ×2.15 |
| Tool invoked | WORKING profile; directed waves to module |
| Memory query | Recall dive; ghost nodes; central convergence |
| Voice mic tap | LISTENING profile; ripple from core |
| Stop generation | Immediate decay to idle |

---

## 1.22 Empty State Visual

- Conversation area: centered welcome — "Titan est présent. Que veux-tu accomplir ?" — sm secondary
- Orchestrator: "En attente de demande…" muted
- Status cards: each shows idle copy
- Neural: idle profile — never frozen

---

## 1.23 Responsive Visual Summary

| Viewport | Key visual changes |
|----------|-------------------|
| Desktop | Full layout as specified |
| Laptop | Chat max 680px; orchestrator 280px min |
| Tablet | Sidebar → rail; orchestrator drawer; cards scroll; module labels hidden |
| Phone | Chat full bleed; composer sticky; single status chip; no telemetry |

---

*Screen 2 — Projects follows.*

---

# 2. PROJECTS

**Nav key:** `projects`  
**Visual identity:** Mission cathedral — structured intent, progress as architecture.

---

## 2.1 Overall Composition

The center column becomes a **project command bridge**. Active mission dominates the upper viewport. Progression reads as vertical architecture — steps as rungs. The PLANIFICATION cognitive region glows when Brain engages.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────┬────────────────────────────────────────────┬────────────────┐ │
│ │ SIDEBAR  │ TOPBAR: [pills] · [Active Project pill] · [actions]         │ │
│ │          ├────────────────────────────────────────────┤ ORCHESTRATOR   │ │
│ │ Projects●│  [PLANIFICATION ●]  [CORE]  [OUTILS]        │ Mission steps  │ │
│ │          │ ┌──────────────────────────────────────────┐ │ Agent summary  │ │
│ │          │ │ ACTIVE PROJECT HEADER                    │ │ Tool timeline  │ │
│ │          │ │ Title · Phase · Progress bar             │ │                │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ TASK PROGRESSION (mission steps)         │ │                │ │
│ │          │ │ ● Step 1 complete                        │ │                │ │
│ │          │ │ ◉ Step 2 active                          │ │                │ │
│ │          │ │ ○ Step 3 pending                         │ │                │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ ACTIVE PLANS (planner output)            │ │                │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ PROJECT CARDS GRID (secondary projects)    │ │                │ │
│ │          │ └──────────────────────────────────────────┘ │                │ │
│ └──────────┴────────────────────────────────────────────┴────────────────┘ │
│ [Cognitif ●][Mémoire][Obsidian][Browser][Présence]                          │
│ [mic] [textarea] [attach] [send]                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2.2 What the User Sees First

1. **Active project header** — title, phase badge, progress bar (immediate context)
2. **Task progression** — current step highlighted with red accent
3. **PLANIFICATION module label** — ACTIF state in overlay
4. **Orchestrator mission section** — Brain involvement at right periphery

---

## 2.3 Eye Flow

```
Active project title → Current step (red accent) → Progress bar → Plan steps
                              ↘ Project cards (secondary scan)
                              ↘ Orchestrator (Brain activity)
```

---

## 2.4 Panel Positions and Hierarchy

| Priority | Panel | Position |
|----------|-------|----------|
| 1 | Active project header | Center top |
| 1 | Task progression | Center, below header |
| 2 | Active plans | Center, below progression |
| 2 | Orchestrator (mission focus) | Right |
| 3 | Project cards grid | Center bottom |
| 3 | Planning cards (floating) | Center-left when plan generating |
| 4 | Status cards | Dock — État Cognitif hero |

---

## 2.5 Spacing Philosophy

- **Header block:** xl padding bottom; clear separation from progression
- **Step items:** md vertical gap; active step has lg padding inset with red wash
- **Progress bar:** Full width of content area; 4px height; red fill on near-black track
- **Project cards:** sm gap in grid; 2-column desktop, 1-column laptop/phone
- **Vertical rhythm:** Each section separated by lg (24px) minimum

---

## 2.6 Depth Hierarchy (Projects)

| Layer | Elements |
|-------|----------|
| Mind surface | PLANIFICATION region — structured path bursts when planning |
| Glass | Project dashboard, cards, orchestrator |
| Foreground | Planning cards floating during plan generation |
| Command | Composer scoped to active project |

---

## 2.7 Neural Field Visibility

- PLANIFICATION module ACTIF on enter (500ms)
- Structured path bursts when Brain analyzes project
- OUTILS region pulses when project tools execute
- Field visible through all glass; planning activity increases signal density

---

## 2.8 Camera Position (Projects)

| State | Camera |
|-------|--------|
| Browsing | Default idle drift |
| Brain analyzing | Bias toward PLANIFICATION region (+6% upward offset) |
| Tool execution | Bias toward OUTILS region |

---

## 2.9 Light and Glow (Projects)

- Active step: red left border 2px + subtle red wash background
- Complete step: strikethrough text at 50% opacity; green semantic dot
- Progress bar fill: red glow on leading edge during active work
- Project card selected: red border accent 200ms

---

## 2.10 Glass, Blur, Transparency (Projects)

| Panel | Alpha | Blur |
|-------|-------|------|
| Dashboard container | 0.38 | 22px |
| Project cards | 0.44 | 16px |
| Active step inset | 0.46 | 16px |
| Planning float cards | 0.46 | 16px |

---

## 2.11 Typography (Projects)

| Element | Style |
|---------|-------|
| Project title | 2xl semibold primary |
| Phase badge | xs uppercase, red border pill |
| Step labels | base primary; active semibold |
| Step metadata | sm secondary |
| Plan step | sm mono prefix (1. 2. 3.) + base body |
| Card title | lg medium |
| Card description | sm secondary, 2-line clamp |

---

## 2.12 Planning Cards (Projects)

When planner generates steps:

- **Position:** Float center-left, below topbar, max 2 visible
- **Content:** Step number + objective + reasoning truncated
- **Enter:** Sequential highlight 300ms per card
- **Active card:** Red left border; others muted
- **Exit:** Cross-fade 350ms when plan stabilizes into dashboard

---

## 2.13 Status, Tool, Composer Placement

| Element | Position |
|---------|----------|
| Project pill | Topbar center-left, after subsystem pills |
| État Cognitif card | Dock card 1 — hero emphasis |
| Tool timeline | Orchestrator bottom section |
| Composer | Full dock; placeholder "Instruction pour ce projet…" |

---

## 2.14 Transitions and Neural Reaction

| Event | Visual |
|-------|--------|
| Enter Projects | Center cross-fade 350ms; PLANIFICATION → ACTIF 500ms |
| Step complete | Strike-through 400ms; progress bar fill 600ms organic |
| Plan update | Planning cards appear; orchestrator steps append |
| Brain starts task | Planning animation profile; orb intensifies |

---

## 2.15 Empty State Visual

- Dashboard: "Aucun projet actif. Décris un objectif à Titan pour commencer une mission." — centered, lg secondary
- No cards grid visible; single CTA block
- Neural: idle; PLANIFICATION label visible but IDLE

---

## 2.16 Responsive Visual Summary

| Viewport | Key changes |
|----------|-------------|
| Desktop | Full dashboard + 2-column card grid |
| Laptop | 2-column cards; truncated plan text |
| Tablet | Single column; orchestrator drawer |
| Phone | Header + current step only; cards horizontal carousel |

---

# 3. MEMORY

**Nav key:** `memory`  
**Visual identity:** Recall sanctuary — depth, ghosts, temporal truth.

---

## 3.1 Overall Composition

The center column becomes a **memory observatory**. Timeline descends vertically like strata. Cards group by category. The MÉMOIRE region is the neural focal point. Recall is a visible event — not a silent database query.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────┬────────────────────────────────────────────┬────────────────┐ │
│ │ SIDEBAR  │ TOPBAR: [pills] · [User: Nolan pill] · [actions]            │ │
│ │          ├────────────────────────────────────────────┤ ORCHESTRATOR   │ │
│ │ Memory ● │  [MÉMOIRE ●]  [CORE]                        │ Retrieval chain│ │
│ │          │ ┌──────────────────────────────────────────┐ │ Recent writes  │ │
│ │          │ │ SEARCH BAR (full width)                   │ │ Sparkline      │ │
│ │          │ │ [goals] [preferences] [projects] [notes]  │ │                │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ MEMORY TIMELINE (vertical)                │ │                │ │
│ │          │ │ ├─ event                                  │ │                │ │
│ │          │ │ ├─ event                                  │ │                │ │
│ │          │ │ MEMORY CARDS (2-col grid)                 │ │                │ │
│ │          │ │ CONVERSATION MEMORY (collapsible)         │ │                │ │
│ │          │ └──────────────────────────────────────────┘ │                │ │
│ └──────────┴────────────────────────────────────────────┴────────────────┘ │
│ [Mémoire ●][Obsidian][Browser][Cognitif][Présence]                          │
│ Memory: Recherche en mémoire…                                              │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 3.2 What the User Sees First

1. **Search bar** — full-width, prominent, elevated glass input
2. **MÉMOIRE module** — ACTIF with red pulse in overlay
3. **Memory cards** — category-grouped excerpts (if data exists)
4. **User identity pill** — when personal data shown (Nolan / Ibrahim)

---

## 3.3 Eye Flow

```
Search bar → Filter chips → Memory cards → Timeline (scroll down)
                    ↘ Orchestrator retrieval chain (when searching)
                    ↘ Neural ghost nodes (peripheral, during recall)
```

---

## 3.4 Panel Positions and Hierarchy

| Priority | Panel | Position |
|----------|-------|----------|
| 1 | Search + filters | Center top, sticky on scroll |
| 1 | Memory cards grid | Center primary content |
| 2 | Memory timeline | Center left or above cards |
| 2 | Orchestrator (memory focus) | Right |
| 3 | Conversation memory | Center bottom, collapsible |
| 4 | Memory float cards | Above content during active recall |
| 1 (dock) | Mémoire Récente card | Hero emphasis |

---

## 3.5 Spacing Philosophy

- **Search:** lg padding below topbar; input height 44px
- **Filter chips:** sm gap horizontal; md gap below search
- **Cards:** md gap in 2-column grid; lg padding inside each card
- **Timeline:** md gap between events; left border 1px red @ 20% connecting events
- **Recall state:** extra xl padding top for floating cards

---

## 3.6 Depth Hierarchy (Memory)

| Layer | Elements |
|-------|----------|
| Abyss | Ghost nodes at 36 extra count during recall |
| Mind surface | MÉMOIRE region — central convergence waves |
| Glass | Search, cards, timeline, orchestrator |
| Foreground | Ephemeral memory float cards during retrieval |
| Command | Composer — "Souviens-toi de…" / "Oublie…" |

---

## 3.7 Neural Field Visibility

- MÉMOIRE module ACTIF on enter; recall dive camera +5.5%
- Ghost nodes fade in 600ms organic during search/recall
- Central wave convergence toward MÉMOIRE label
- Field brightness increases 1.18× near core during active recall
- Returns to muted MÉMOIRE (low intensity) when browsing idle

---

## 3.8 Camera Position (Memory)

| State | Camera |
|-------|--------|
| Browse idle | Slight inward bias (+2%) — sanctuary feel |
| Active recall | Recall dive +5.5% over 600ms; central focus |
| Write pipeline | Brief central pulse; camera holds |

---

## 3.9 Light and Glow (Memory)

- Memory cards: category chip with colorless semantic dot; red left border on high relevance
- Timeline events: dot on spine glows red when selected
- Ghost nodes: white-red dim halo at 0.45 boosted opacity
- Search focus: red focus ring on input

---

## 3.10 Memory Cards (Memory Screen)

| Property | Specification |
|----------|---------------|
| Size | Equal width in 2-col grid; min height 120px |
| Header | Category chip xs + timestamp mono xs right |
| Body | sm primary; 3-line clamp |
| Footer | Relevance bar — thin 2px red fill proportion |
| Hover | Elevated wash; border brightens to 10% white |
| Selected | Red border active; orchestrator shows retrieval chain |

**Float variant (during recall):** Same anatomy; positioned right-aligned above grid; max 4 stack; dissolve 400ms on complete.

---

## 3.11 Typography (Memory)

| Element | Style |
|---------|-------|
| Search input | base primary |
| Filter chip | xs medium uppercase |
| Card category | xs badge |
| Card excerpt | sm primary |
| Timeline event | sm secondary + mono xs timestamp |
| Section header | lg medium — "Mémoire permanente" |

---

## 3.12 Status and Composer Placement

| Element | Position |
|---------|----------|
| User pill | Topbar — "Nolan" or "Ibrahim" with subtle avatar initial |
| Memory status line | Dock row 2 — "Recherche en mémoire…" during recall |
| Mémoire card | Dock card 1 — expanded emphasis, larger body text |
| Composer | "Souviens-toi de…" placeholder |

---

## 3.13 Transitions and Neural Reaction

| Event | Visual |
|-------|--------|
| Enter Memory | MÉMOIRE ACTIF 500ms; recall dive if retrieval in-flight |
| Search/filter | Results cross-fade 200ms; cards stagger 80ms |
| Active recall | Ghost nodes; float cards; central convergence |
| New write | Card enters from timeline anchor 350ms |
| Leave Memory | Float cards dissolve; MÉMOIRE → IDLE 500ms |

---

## 3.14 Empty State Visual

- "Aucune mémoire permanente pour toi. Dis « souviens-toi de… » pour commencer." — centered
- Timeline area empty with muted spine line
- Neural: MÉMOIRE label ACTIF muted — sanctuary, not error

---

## 3.15 Responsive Visual Summary

| Viewport | Key changes |
|----------|-------------|
| Desktop | 2-column cards; timeline left |
| Laptop | 2-column narrow |
| Tablet | Single column; filters collapsible |
| Phone | Search sticky; no float cards — status line only; simplified recall |

---

*Screens 4–6 follow.*

---

# 4. OBSIDIAN

**Nav key:** `obsidian`  
**Visual identity:** Knowledge vault — geometric precision, user's notes not Titan's brain.

---

## 4.1 Overall Composition

Split-pane **vault command center**. Left: folder tree and note list. Right: reader/editor. Knowledge graph optional below or overlay. OBSIDIAN cognitive region uses geometric wave bias — sharper, more structured than organic chat flow.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────┬────────────────────────────────────────────┬────────────────┐ │
│ │ SIDEBAR  │ TOPBAR: [pills] · [Vault: Titan AI] · [actions]             │ │
│ │          ├────────────────────────────────────────────┤ ORCHESTRATOR   │ │
│ │ Obsidian●│  [OBSIDIAN ●]  [OUTILS]                    │ Connector      │ │
│ │          │ │ RECENT NOTES (horizontal strip)           │ │ Operation      │ │
│ │          │ ├──────────────┬───────────────────────────┤ │ Decision       │ │
│ │          │ │ VAULT BROWSER│ NOTE READER / EDITOR      │ │ Timeline       │ │
│ │          │ │ folder tree  │ markdown structure        │ │                │ │
│ │          │ │ note list    │ headings · body · tags    │ │                │ │
│ │          │ ├──────────────┴───────────────────────────┤ │                │ │
│ │          │ │ KNOWLEDGE GRAPH (toggle, 40% height)        │ │                │ │
│ │          │ └──────────────────────────────────────────┘ │                │ │
│ └──────────┴────────────────────────────────────────────┴────────────────┘ │
│ [Obsidian ●][Mémoire][Browser][Cognitif][Présence]                          │
│ Tool: Consultation d'Obsidian…                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 4.2 What the User Sees First

1. **Vault name pill** — "Titan AI" in topbar (confirms correct vault)
2. **Recent notes strip** — horizontal scroll of last accessed notes
3. **Split pane** — browser left, reader right (the work surface)
4. **OBSIDIAN module** — ACTIF in neural overlay

---

## 4.3 Eye Flow

```
Recent notes strip → Note list selection → Reader content
                              ↘ Graph (when toggled — relationship scan)
                              ↘ Orchestrator operation status
```

---

## 4.4 Panel Positions and Hierarchy

| Priority | Panel | Position |
|----------|-------|----------|
| 1 | Note reader/editor | Center right 60% |
| 1 | Vault browser | Center left 40% |
| 2 | Recent notes strip | Center top, full width |
| 2 | Search (persistent) | Above browser or top of browser pane |
| 3 | Knowledge graph | Center bottom 40% or overlay modal |
| 2 | Orchestrator (Obsidian focus) | Right |
| 1 (dock) | Obsidian status card | Hero |

---

## 4.5 Spacing Philosophy

- **Split divider:** 1px white @ 6%; draggable affordance 4px handle
- **Recent notes:** sm gap; cards 160px min-width; horizontal scroll
- **Note list items:** sm vertical gap; selected item red wash
- **Reader:** lg padding; heading hierarchy mirrors markdown (# = xl, ## = lg)
- **Graph:** nodes 8px radius; edges white @ 8%; labels xs muted

---

## 4.6 Depth Hierarchy (Obsidian)

| Layer | Elements |
|-------|----------|
| Mind surface | OBSIDIAN region — geometric wave patterns |
| Glass | Browser, reader, graph container |
| Foreground | Patch confirmation pulse on saved section |
| Command | Composer — vault NL commands |

---

## 4.7 Neural Field Visibility

- OBSIDIAN module ACTIF; geometric wave bias (sharper angles than chat)
- Graph view: optional decorative sync — low-intensity signals between linked note positions
- Distributed low-intensity when browsing; sharp micro-pulse on patch confirmation
- Field remains visible through split panes

---

## 4.8 Camera Position (Obsidian)

| State | Camera |
|-------|--------|
| Browse | Default; slight right bias (+4%) toward reader |
| Search/read | Stable; geometric wave profile |
| Graph open | Pull back -2% zoom for spatial context |

---

## 4.9 Light and Glow (Obsidian)

- Selected note: red left border 2px in list
- Patch save: brief red pulse on affected section — 200ms — not celebration
- Sync icon: single 600ms rotation on refresh
- Graph selected node: red ring; connected edges brighten to 18% white

---

## 4.10 Glass, Blur, Transparency (Obsidian)

| Panel | Alpha | Blur |
|-------|-------|------|
| Browser pane | 0.38 | 22px |
| Reader pane | 0.38 | 22px |
| Recent note chips | 0.44 | 12px |
| Graph container | 0.40 | 18px |
| Editor inset (code blocks) | 0.46 | 16px |

---

## 4.11 Typography (Obsidian)

| Element | Style |
|---------|-------|
| Vault name | sm medium pill |
| Note title (list) | sm primary; selected semibold |
| Note title (reader) | xl semibold |
| Markdown H1 | xl semibold |
| Markdown H2 | lg medium |
| Body | base primary, relaxed leading |
| Tags | xs mono, muted, pill shape |
| Folder path | xs secondary mono |

---

## 4.12 Icon Placement (Obsidian)

| Location | Icon |
|----------|------|
| Search | 16px leading in search input |
| Folder tree | 16px folder/note icons per row |
| Sync status | 14px trailing in topbar vault pill |
| Graph toggle | 16px in reader toolbar |
| Patch mode | 16px in editor toolbar |

---

## 4.13 Status, Tool, Composer

| Element | Position |
|---------|----------|
| Vault pill | Topbar — name + sync dot (green/amber/red) |
| Obsidian card | Dock hero — last operation + note count |
| Tool status line | "Consultation d'Obsidian…" / "Mise à jour du vault…" |
| Composer | "Cherche dans le vault…" / "Ajoute à la note…" |

---

## 4.14 Transitions and Neural Reaction

| Event | Visual |
|-------|--------|
| Enter Obsidian | OBSIDIAN ACTIF; geometric wave 500ms |
| Note select | Reader cross-fade 200ms; graph node highlight 300ms |
| Graph toggle | Panel expand 350ms; nodes stagger 60ms |
| Patch apply | Section pulse; orchestrator step complete |
| Leave → Memory | One-time tooltip: "Mémoire Titan ≠ Vault Obsidian" |

---

## 4.15 Empty State Visual

- Vault unset: persistent banner, amber badge — "Vault Obsidian non configuré"
- Vault empty: reader shows centered muted message
- Graph no links: "Pas encore de liens entre notes." centered in graph area

---

## 4.16 Responsive Visual Summary

| Viewport | Key changes |
|----------|-------------|
| Desktop | 40/60 split; graph bottom 40% |
| Laptop | 40/60 split; graph overlay |
| Tablet | Browser full width; reader sheet |
| Phone | Note list only; reader full-screen sheet; graph hidden |

---

# 5. EXPLORATION

**Nav key:** `browser`  
**Visual identity:** Research horizon — distributed signals, sources as evidence.

---

## 5.1 Overall Composition

**Research command center** — summary at top, exploration cards and sources below, comparison when multi-select. BROWSER region emits distributed waves — signals spread wide, not convergent.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────┬────────────────────────────────────────────┬────────────────┐ │
│ │ SIDEBAR  │ TOPBAR: [pills] · [Exploration web] · [actions]             │ │
│ │          ├────────────────────────────────────────────┤ ORCHESTRATOR   │ │
│ │ Explor. ●│  [BROWSER ●]  [CORE]  [COMMUNICATION]       │ Browser health │ │
│ │          │ ┌──────────────────────────────────────────┐ │ Fetch steps    │ │
│ │          │ │ RESEARCH SUMMARY (synthesized findings)   │ │ Active URLs    │ │
│ │          │ ├──────────────────────────────────────────┤ │ Timeline       │ │
│ │          │ │ EXPLORATION CARDS (session snapshots)     │ │                │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ SOURCES LIST │ COMPARISON (when ≥2)       │ │                │ │
│ │          │ └──────────────────────────────────────────┘ │                │ │
│ └──────────┴────────────────────────────────────────────┴────────────────┘ │
│ [Browser ●][Mémoire][Obsidian][Cognitif][Présence]                          │
│ Tool: Exploration web…                                                     │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 5.2 What the User Sees First

1. **Research summary** — Titan's synthesized findings (top of center)
2. **Exploration cards** — session snapshots with visual weight
3. **BROWSER module** — ACTIF with distributed neural activity
4. **Sources list** — evidence chain

---

## 5.3 Eye Flow

```
Summary paragraph → Exploration card → Source URL → Orchestrator fetch status
                              ↘ Comparison (when active)
                              ↘ Screenshot thumbnail (when captured)
```

---

## 5.4 Panel Positions and Hierarchy

| Priority | Panel | Position |
|----------|-------|----------|
| 1 | Research summary | Center top |
| 1 | Exploration cards | Center, below summary |
| 2 | Sources list | Center left or full width |
| 2 | Comparison view | Center right when ≥2 sources selected |
| 3 | Screenshot preview | Inline in source row or card |
| 2 | Orchestrator (browser focus) | Right |
| 1 (dock) | Browser status card | Hero |

---

## 5.5 Spacing Philosophy

- **Summary:** lg padding; paragraph spacing relaxed leading
- **Exploration cards:** md gap; cards min 280px wide
- **Sources:** sm gap rows; 48px min row height for touch
- **Comparison:** equal width columns; md gap divider

---

## 5.6 Exploration Cards (Browser)

| Property | Specification |
|----------|---------------|
| Size | ~300px wide; auto height; max 3 visible |
| Header | Session title sm semibold + timestamp mono xs |
| Body | Summary excerpt sm; 4-line clamp |
| Footer | Source count badge + status dot |
| Screenshot | Optional 16:9 thumbnail top of card; radius md |
| Surface | Elevated glass; red top edge 1px when active session |
| Enter | Fade + translateY 12px, 350ms |
| Exit | Dissolve 400ms on session end |

---

## 5.7 Depth Hierarchy (Exploration)

| Layer | Elements |
|-------|----------|
| Mind surface | BROWSER region — distributed waves, 3-burst pattern |
| Glass | Summary, cards, sources, comparison |
| Foreground | Active fetch progress on source rows |
| Command | Composer — "Cherche…" / "Compare…" / "Résume…" |

---

## 5.8 Neural Field Visibility

- BROWSER module ACTIF; distributed waves at 1.18× speed
- 3-burst signal pattern on active research
- Synthesis: thinking brightness + browser waves combined
- Field visible behind summary glass; activity spreads horizontally

---

## 5.9 Camera Position (Exploration)

| State | Camera |
|-------|--------|
| Idle on screen | Default; BROWSER region visible |
| Active research | Horizontal bias ±6% following distributed activity |
| Synthesis | Inward focus +1.6% (thinking profile) |

---

## 5.10 Light and Glow (Exploration)

- Active source row: red left border; pending badge amber pulse once
- Exploration card active: red top edge glow
- Screenshot capture: thumbnail scale 0.96 → 1.0 over slow enter
- Fetch complete: source row green dot once

---

## 5.11 Typography (Exploration)

| Element | Style |
|---------|-------|
| Summary | base primary, relaxed leading |
| Card title | sm semibold |
| Source URL | sm mono primary, truncated |
| Source snippet | xs secondary, 2-line |
| Comparison header | lg medium per column |

---

## 5.12 Status, Tool, Composer

| Element | Position |
|---------|----------|
| "Exploration web" | Topbar context label when active |
| Browser card | Dock hero — active URLs count |
| Tool status line | "Exploration web…" / "Analyse de la source…" / "Synthèse en cours…" |
| Brain indicator | Topbar Reflection pill + orchestrator |

---

## 5.13 Transitions and Neural Reaction

| Event | Visual |
|-------|--------|
| Enter Exploration | BROWSER ACTIF; distributed waves 500ms |
| New source | Row enter 350ms; card update |
| Comparison toggle | Split animate 350ms |
| Session end | Cards dissolve; module → IDLE |

---

## 5.14 Empty State Visual

- "Aucune exploration en cours. Demande une recherche à Titan." — centered below summary area
- Sources: "En attente de la première source." muted
- Neural: BROWSER label visible, low activity

---

## 5.15 Responsive Visual Summary

| Viewport | Key changes |
|----------|-------------|
| Desktop | Summary top; sources left; comparison right |
| Laptop | Stacked; comparison overlay |
| Tablet | Cards horizontal scroll; sources sheet |
| Phone | Single card full-width; sources/comparison sheets |

---

# 6. TRADING

**Nav key:** `trading`  
**Visual identity:** Market sharpness — controlled urgency, never casino.

---

## 6.1 Overall Composition

**Market oversight bridge** — overview top, positions and performance middle, strategies and alerts below, execution log and risk at bottom. TRADING region uses sharp wave profile — angular, faster, disciplined.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────┬────────────────────────────────────────────┬────────────────┐ │
│ │ SIDEBAR  │ TOPBAR: [pills] · [PAPER badge] · [actions]                 │ │
│ │          ├────────────────────────────────────────────┤ ORCHESTRATOR   │ │
│ │ Trading ●│  [TRADING ●]  [CORE]                        │ Analysis steps │ │
│ │          │ ┌──────────────────────────────────────────┐ │ Broker health  │ │
│ │          │ │ MARKET OVERVIEW (indices, watchlist)      │ │ Orders         │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ POSITIONS TABLE │ PERFORMANCE SUMMARY      │ │                │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ STRATEGIES │ ALERTS FEED                   │ │                │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ EXECUTION LOG │ RISK PANEL                 │ │                │ │
│ │          │ └──────────────────────────────────────────┘ │                │ │
│ └──────────┴────────────────────────────────────────────┴────────────────┘ │
│ [Cognitif ●][Trading][Browser][Mémoire][Présence]                           │
│ Tool: Analyse des marchés…                                                 │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 6.2 What the User Sees First

1. **Broker mode badge** — PAPER or LIVE (amber/red) — topbar
2. **Market overview** — indices and watchlist ticks
3. **Positions table** — exposure at a glance
4. **TRADING module** — ACTIF when engaged

---

## 6.3 Eye Flow

```
PAPER/LIVE badge → Market overview ticks → Positions P&L → Risk panel
                              ↘ Alerts (if triggered — amber pulse)
                              ↘ Orchestrator analysis steps
```

---

## 6.4 Panel Positions and Hierarchy

| Priority | Panel | Position |
|----------|-------|----------|
| 1 | Market overview | Center top |
| 1 | Positions table | Center middle-left |
| 2 | Performance summary | Center middle-right |
| 2 | Strategies + alerts | Center row below |
| 2 | Execution log + risk | Center bottom split |
| 3 | Trading alert floats | Top-right center, below topbar |
| 2 | Orchestrator (trading focus) | Right |
| 1 (dock) | État Cognitif + trading extension | Hero |

---

## 6.5 Trading Cards (Trading Screen)

| Card type | Position | Visual |
|-----------|----------|--------|
| Watchlist tile | In market overview grid | Symbol sm mono semibold + price base mono + change colored semantic dot only |
| Position row | Table row | Symbol · side · size · P&L mono semibold |
| Alert row | Alerts feed | Amber left border; pulse once on trigger |
| Execution row | Log table | Timestamp mono xs + status badge |
| Risk gauge | Risk panel | Horizontal bar; red fill proportional to exposure |

---

## 6.6 Spacing Philosophy

- **Data density:** tighter than other screens — sm gaps in tables
- **Numeric alignment:** right-aligned mono figures
- **Section separation:** lg between overview and positions; md within tables
- **Risk panel:** always visible — never collapsed on desktop

---

## 6.7 Depth Hierarchy (Trading)

| Layer | Elements |
|-------|----------|
| Mind surface | TRADING region — sharp waves 1.35× speed |
| Glass | All data panels |
| Foreground | Alert float cards (max 3) |
| Overlay | LIVE confirmation scrim 72% |

---

## 6.8 Neural Field Visibility

- TRADING module ACTIF when engaged; sharp angular waves
- Analysis: controlled urgency — never strobe
- Risk block: neural calms immediately — activity drops to idle
- Order pipeline: sharp + directed tool signals

---

## 6.9 Camera Position (Trading)

| State | Camera |
|-------|--------|
| Idle on screen | Default; TRADING region muted until engaged |
| Market analysis | Sharp micro-pulses; stable camera |
| LIVE confirmation | Neural pauses — frozen drift |

---

## 6.10 Light and Glow (Trading)

- PAPER badge: amber semantic pill
- LIVE badge: red semantic pill — never full red background
- Price tick: numeric cross-fade 100ms only
- Alert trigger: amber badge pulse once — not repeating
- P&L positive/negative: semantic dot only — not row background fill

---

## 6.11 Typography (Trading)

| Element | Style |
|---------|-------|
| Symbol | sm mono semibold |
| Price | base mono primary |
| Change % | xs mono + semantic dot |
| P&L | base mono semibold |
| Table header | xs uppercase wide tracking muted |
| Risk label | sm medium |

**All numeric data uses mono font.** No slot-machine digit scroll.

---

## 6.12 Status, Tool, Composer

| Element | Position |
|---------|----------|
| PAPER/LIVE badge | Topbar center-left — always visible |
| Broker status | Orchestrator + market overview header |
| Trading card | Dock — position count + mode |
| Composer | "Analyse…" / "Position…" — LIVE gated |

---

## 6.13 LIVE Confirmation Overlay

When LIVE execution requested:

- Scrim 72% black over workspace
- Neural pauses
- Confirmation card centered: max 480px; lg radius
- Copy: clear French explanation of LIVE risk
- Actions: Annuler (ghost) · Confirmer (primary red)
- Orchestrator frozen behind scrim

---

## 6.14 Transitions and Neural Reaction

| Event | Visual |
|-------|--------|
| Enter Trading | TRADING ACTIF; sharp wave profile |
| Price tick | Cross-fade 100ms |
| Alert | Row enter 200ms; float card if critical |
| Order | Execution row enter; risk recalculates 300ms |
| Blocked action | Neural calms; inline error — no silent fail |

---

## 6.15 Empty State Visual

- No broker: "Trading non configuré." + settings link
- No positions: table header visible; "Aucune position ouverte." centered in body
- No strategies/alerts: muted empty copy per section

---

## 6.16 Responsive Visual Summary

| Viewport | Key changes |
|----------|-------------|
| Desktop | Full grid as specified |
| Laptop | Strategies collapsible |
| Tablet | Overview only; tabs for rest |
| Phone | Watchlist scroll; positions/alerts sheets |

---

*Screens 7–9 follow.*

---

# 7. CALENDAR

**Nav key:** `calendar`  
**Visual identity:** Temporal rhythm — circular time, planning convergence.

---

## 7.1 Overall Composition

**Temporal command center** — daily focus banner top, agenda grid center, upcoming tasks adjacent. PLANIFICATION + CALENDAR dual module emphasis during scheduling. Circular wave profile.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────┬────────────────────────────────────────────┬────────────────┐ │
│ │ SIDEBAR  │ TOPBAR: [pills] · [Aujourd'hui · 6 juil.] · [actions]       │ │
│ │          ├────────────────────────────────────────────┤ ORCHESTRATOR   │ │
│ │ Calendar●│  [CALENDAR ●]  [PLANIFICATION]            │ Planning steps   │ │
│ │          │ ┌──────────────────────────────────────────┐ │ Conflicts        │ │
│ │          │ │ DAILY FOCUS BANNER (priority block)      │ │ Calendar tool    │ │
│ │          │ ├──────────────────────────────────────────┤ │                │ │
│ │          │ │ AGENDA (day/week toggle)                  │ │                │ │
│ │          │ │ ┌───┬───┬───┬───┬───┬───┬───┐            │ │                │ │
│ │          │ │ │   │   │   │   │   │   │   │ time grid  │ │                │ │
│ │          │ │ └───┴───┴───┴───┴───┴───┴───┘            │ │                │ │
│ │          │ │ UPCOMING TASKS                            │ │                │ │
│ │          │ └──────────────────────────────────────────┘ │                │ │
│ └──────────┴────────────────────────────────────────────┴────────────────┘ │
│ [Agenda][Mémoire][Obsidian][Browser][Présence]                              │
│ Tool: Planification…                                                       │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 7.2 What the User Sees First

1. **Daily focus banner** — curated priority for today (red left accent)
2. **Agenda grid** — current day with time blocks
3. **Date pill** — "Aujourd'hui" + date in topbar
4. **CALENDAR module** — ACTIF in overlay

---

## 7.3 Eye Flow

```
Daily focus banner → Current time slot (now indicator) → Upcoming tasks
                              ↘ Day/week toggle
                              ↘ Orchestrator planning steps (when scheduling)
```

---

## 7.4 Panel Positions and Hierarchy

| Priority | Panel | Position |
|----------|-------|----------|
| 1 | Daily focus banner | Center top, full width |
| 1 | Agenda grid | Center primary |
| 2 | Upcoming tasks | Center right column or below agenda |
| 2 | Scheduling panel | Inline in agenda or orchestrator-driven |
| 2 | Orchestrator (calendar focus) | Right |
| 3 | Planning cards | Float when Brain scheduling |
| 1 (dock) | Custom agenda chip | Hero — next event countdown |

---

## 7.5 Spacing Philosophy

- **Focus banner:** lg padding; md gap between priority items
- **Agenda grid:** hour rows 48px min height; 15min subdivisions at 12px
- **Event blocks:** md internal padding; sm margin from grid lines
- **Now indicator:** red horizontal line 1px + dot 8px at current time
- **Upcoming tasks:** sm gap; deadline items have amber dot if <2h

---

## 7.6 Depth Hierarchy (Calendar)

| Layer | Elements |
|-------|----------|
| Mind surface | CALENDAR + PLANIFICATION — circular waves + planning paths |
| Glass | Focus banner, agenda, upcoming tasks |
| Foreground | Ghost event block during create-in-flight |
| Command | Composer — "Planifie…" / "Rappelle-moi…" |

---

## 7.7 Neural Field Visibility

- CALENDAR module ACTIF; circular wave pattern (radial, not distributed)
- Scheduling: PLANIFICATION joins — dual module ACTIF
- Conflict resolution: moderate thinking profile
- Low activity when browsing idle calendar

---

## 7.8 Camera Position (Calendar)

| State | Camera |
|-------|--------|
| Browse | Default gentle drift |
| Scheduling | Circular wave bias; slight upward +3% |
| Conflict | Stable; thinking profile |

---

## 7.9 Light and Glow (Calendar)

- Focus banner: red left border 3px; subtle red wash
- Current time indicator: red line + dot pulse 2.4s
- Event block: white border 6%; red border when selected
- Conflict: amber badge pulse once on row
- Ghost event (pending create): 50% opacity + dashed border

---

## 7.10 Typography (Calendar)

| Element | Style |
|---------|-------|
| Focus item | base semibold primary |
| Event title | sm medium |
| Event time | xs mono secondary |
| Day header | lg medium |
| Hour label | xs mono muted |
| Upcoming task | sm primary + relative time xs muted |

---

## 7.11 Planning Cards (Calendar)

When Brain schedules:

- **Position:** Float below focus banner, max 2
- **Content:** Proposed event title + time + conflict warning if any
- **Enter:** 350ms; planning step highlight in orchestrator syncs
- **Conflict card:** Amber left border; warning icon 16px

---

## 7.12 Status, Tool, Composer

| Element | Position |
|---------|----------|
| Date pill | Topbar — "Aujourd'hui" + formatted date |
| Agenda chip | Dock — next event name + countdown mono |
| Tool status | "Planification…" / "Synchronisation du calendrier…" |
| Composer | Scheduling NL commands |

---

## 7.13 Transitions and Neural Reaction

| Event | Visual |
|-------|--------|
| Enter Calendar | CALENDAR ACTIF; circular wave 500ms |
| Day navigation | Agenda cross-fade 200ms; focus update 350ms |
| Event create | Block enter 350ms from slot; ghost → solid |
| Conflict | Amber pulse; planning card warning |

---

## 7.14 Empty State Visual

- No calendar connected: banner "Calendrier non connecté." + settings link
- No events today: grid empty with now indicator still visible; "Rien de prévu aujourd'hui."
- Focus banner suggests Brain-generated priority when empty

---

## 7.15 Responsive Visual Summary

| Viewport | Key changes |
|----------|-------------|
| Desktop | Day/week toggle; upcoming right column |
| Laptop | Single column; upcoming below |
| Tablet | Day view default; week sheet |
| Phone | Today only; swipe day change; focus one-line strip |

---

# 8. VOICE

**Nav key:** `voice`  
**Visual identity:** Immersive presence — the mind listens and speaks.

---

## 8.1 Overall Composition

**Immersive voice stage** — wave visualization dominates center (≥60% visual weight). Sidebar may collapse. Orchestrator slim. Transcript minimized to last 2 turns. The user is inside Titan's auditory consciousness.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░ ELEVATED NEURAL — ripple, circular pulses ░░░░░░░░░░░ │
│ ┌─┬──────────────────────────────────────────────────────┬───────────────┐ │
│ │▌│ TOPBAR: [voice mode badge] · À l'écoute · [actions]  │ ORCHESTRATOR  │ │
│ │▌├──────────────────────────────────────────────────────┤ (slim)        │ │
│ │▌│                                                      │ State orb     │ │
│ │▌│              WAVE VISUALIZATION (hero)               │ Tool line     │ │
│ │▌│              large central audio envelope              │               │ │
│ │▌│                                                      │               │ │
│ │▌│              Présent — en attente (large)            │               │ │
│ │▌│              [Push-to-talk | Continu]                │               │ │
│ │▌│              [ INTERRUPT ]                           │               │ │
│ │▌│              minimal transcript (last 2 turns)         │               │ │
│ └─┴──────────────────────────────────────────────────────┴───────────────┘ │
│ [mic ●] [textarea slim] [send]                                              │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 8.2 What the User Sees First

1. **Wave visualization** — large central canvas, bars or envelope responding to audio
2. **Presence copy** — large, centered below wave — "À l'écoute" / "Titan parle"
3. **Mic ring** — red pulse when listening (composer + center mirrored)
4. **Neural ripples** — elevated activity behind wave stage

---

## 8.3 Eye Flow

```
Wave visualization → Presence copy → Interrupt button
                              ↘ Mode toggle (push / continuous)
                              ↘ Minimal transcript (optional glance)
```

Eye does **not** scan sidebar or orchestrator unless tool triggered.

---

## 8.4 Panel Positions and Hierarchy

| Priority | Panel | Position |
|----------|-------|----------|
| 1 | Wave visualization | Center hero, 60%+ column height |
| 1 | Presence copy | Center, below wave, xl–2xl size |
| 1 | Interrupt control | Center, below mode toggle — always reachable |
| 2 | Mode toggle | Center, below presence |
| 2 | Mic (large) | Center or composer mirrored |
| 3 | Minimal transcript | Center bottom, 2 turns max |
| 4 | Orchestrator slim | Right — orb + tool line only |
| 5 | Sidebar | Collapsed to rail optional |

---

## 8.5 Spacing Philosophy

- **Generous void** around wave — xl–2xl padding; wave breathes
- **Presence copy:** 2xl margin below wave
- **Interrupt button:** lg margin above transcript
- **Transcript:** sm max-width 480px centered; muted styling

---

## 8.6 Depth Hierarchy (Voice)

| Layer | Elements |
|-------|----------|
| Mind surface | Elevated neural — ripples, circular pulses from core |
| Glass | Minimal — wave stage has no heavy panel box |
| Wave canvas | Foreground — appears above neural, below UI chrome |
| Command | Interrupt button + composer mic — highest priority |

---

## 8.7 Neural Field Visibility

- **Elevated** compared to other screens — activity 0.22 when listening
- LISTENING: ripple from core; `--voice-ripple` 0→1 over 900ms
- SPEAKING: circular pulses 520ms; brightness ×1.07
- THINKING (processing speech): standard thinking between listen/speak
- Field fully visible around wave — wave canvas may be semi-transparent center

---

## 8.8 Camera Position (Voice)

| State | Camera |
|-------|--------|
| Ready | Centered; reduced drift — stability |
| Listening | Centered; baseline zoom |
| Speaking | +0.8% zoom; rhythmic micro-pulse |
| Interrupted | Snap center — 200ms exception for agency |

---

## 8.9 Light and Glow (Voice)

- Mic ring: 2px red @ 60%; pulse 900ms organic when listening
- Wave bars: red gradient fill from core color to dim; white tips at peak
- Interrupt button: red ghost outline; brightens on hover
- Speaking: core glow expands — circular wave rings emanate
- Mode toggle active: red wash on selected option

---

## 8.10 Wave Visualization

| Property | Specification |
|----------|---------------|
| Size | Min 320px wide × 120px tall desktop; scales with column |
| Bar count | 32–48 bars centered |
| Idle | Flat line at 10% amplitude — not zero (alive) |
| Listening | Bars follow input level 60fps; red fill |
| Speaking | Bars follow output envelope; symmetrical ripple |
| Reduced motion | Static bars at last level — no 60fps animation |

---

## 8.11 Typography (Voice)

| Element | Style |
|---------|-------|
| Presence copy | 2xl semibold primary centered |
| Mode toggle | sm medium |
| Interrupt | sm semibold uppercase tracking-wide |
| Transcript user | sm secondary |
| Transcript Titan | sm primary |
| Voice badge (topbar) | xs uppercase pill |

---

## 8.12 Sidebar Behavior (Voice)

- Desktop: optional auto-collapse to 56px rail on enter (350ms)
- Exit Voice: sidebar restores (350ms)
- Phone: sidebar hidden entirely

---

## 8.13 Composer (Voice)

- **Slim variant:** Single line textarea; mic enlarged to 48px in center OR composer
- **Text fallback:** Always available — partnership includes typing
- **Telemetry:** Hidden by default; available in settings

---

## 8.14 Interrupt Control

- **Position:** Center, below mode toggle; min 120px wide button
- **Label:** "INTERROMPRE" — sm semibold uppercase
- **Behavior:** Immediate halt — presence snap to "Interrompu — prêt" 200ms
- **Phone:** 56px floating button bottom-right; red ring

---

## 8.15 Transitions and Neural Reaction

| Event | Visual |
|-------|--------|
| Enter Voice | Sidebar collapse optional; wave expand 350ms |
| Start listening | Mic ring; ripple; LISTENING 500ms |
| Processing | Wave frozen brief → THINKING |
| Speaking | Circular pulses; SPEAKING 600ms |
| Interrupt | Immediate halt; all motion stops 200ms |
| Tool triggered | Orchestrator slides in if hidden |

---

## 8.16 Empty State Visual

- "Appuie sur le micro ou parle en mode continu." — sm secondary below wave
- Transcript hidden until first exchange
- Wave flat line idle — neural still alive behind

---

## 8.17 Responsive Visual Summary

| Viewport | Key changes |
|----------|-------------|
| Desktop | Full immersive; orchestrator slim |
| Laptop | Wave height reduced 20% |
| Tablet | Orchestrator hidden; interrupt floating |
| Phone | Full bleed; 56px interrupt; one-line composer |

---

# 9. SETTINGS

**Nav key:** `settings`  
**Visual identity:** Configuration veil — mind visible through scrim, never replaced.

---

## 9.1 Overall Composition

**Overlay plane** — 72% scrim over preserved workspace. Settings card floats centered. Neural field continues at 28% visibility behind scrim. Underlying screen does not unmount.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░░░ SCRIM 72% — neural visible beneath ░░░░░░░░░░░░░░░░ │
│ ┌────────────────────────────────────────────────────────────────────────┐ │
│ │                    SETTINGS CARD (max 640px centered)                   │ │
│ │  ┌─────────────┬──────────────────────────────────────────────────────┐ │ │
│ │  │ SECTION NAV │ SECTION CONTENT                                       │ │ │
│ │  │ Appearance  │ Font scale: ( ) 100%  ( ) 112%  ( ) 125%             │ │ │
│ │  │ Voice       │ Reduced motion: [toggle]                              │ │ │
│ │  │ Memory      │ High contrast: [toggle]                               │ │ │
│ │  │ Tools       │                                                       │ │ │
│ │  │ Accounts    │                                                       │ │ │
│ │  │ Security    │                                                       │ │ │
│ │  │ Developer   │                                                       │ │ │
│ │  │ Performance │                                                       │ │ │
│ │  └─────────────┴──────────────────────────────────────────────────────┘ │ │
│ │  [Fermer]                                              [Enregistrer]      │ │
│ └────────────────────────────────────────────────────────────────────────┘ │
│ (workspace dimmed, non-interactive, neural still drifting)                  │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 9.2 What the User Sees First

1. **Scrim darken** — immediate depth cue that configuration layer is active
2. **Settings card** — centered, solid elevated glass
3. **Section nav** — left column vertical tabs (desktop)
4. **Neural motion** — still perceptible through scrim — Titan has not gone away

---

## 9.3 Eye Flow

```
Card title → Section nav → Active section fields → Save/Close actions
                              ↘ Neural (peripheral — still alive)
```

---

## 9.4 Panel Positions and Hierarchy

| Priority | Panel | Position |
|----------|-------|----------|
| 1 | Settings card | Center viewport; max 640px desktop |
| 1 | Section content | Card right 65% |
| 2 | Section nav | Card left 35% |
| 3 | Scrim | Full viewport |
| — | Background workspace | Dimmed, non-interactive |
| — | Neural stage | Continues rendering at 28% visibility |

---

## 9.5 Spacing Philosophy

- **Card padding:** xl (32px) outer; lg inner sections
- **Section nav items:** md vertical gap; md horizontal padding
- **Form fields:** lg gap between groups; md between label and input
- **Actions:** lg margin top; right-aligned Enregistrer + left Fermer

---

## 9.6 Depth Hierarchy (Settings)

| Layer | Elements |
|-------|----------|
| Mind surface | Neural at 28% through scrim |
| Scrim | 72% black overlay — z=100 |
| Settings card | Elevated glass 0.88 alpha (more opaque for legibility) |
| Form controls | Solid elevated inputs within card |

---

## 9.7 Neural Field Visibility

- **Never pauses** when settings open
- Visible through scrim at 28% — user knows Titan is still present
- Performance density change: engine adapts next frame — smooth lerp
- Reduced motion toggle: immediate effect — drift → 0

---

## 9.8 Camera Position (Settings)

Camera unchanged from pre-overlay state — settings does not affect neural camera.

---

## 9.9 Light and Glow (Settings)

- Card: top edge highlight 1px white @ 8%
- Scrim: no glow — flat darken
- Focus ring: red on all interactive elements
- Toggle on: red fill track; off: elevated surface
- Save success: button brief confirm 200ms — green dot flash once

---

## 9.10 Glass, Blur, Transparency (Settings)

| Element | Alpha | Blur |
|---------|-------|------|
| Scrim | 0.72 | 0px (no blur on scrim itself) |
| Settings card | 0.88 | 22px |
| Inputs within card | 0.46 on elevated surface | 0px |

---

## 9.11 Typography (Settings)

| Element | Style |
|---------|-------|
| Card title | xl semibold — "Paramètres" |
| Section nav | sm medium; active semibold primary |
| Section header | lg medium |
| Field label | sm secondary |
| Field description | xs muted |
| Mono values | xs mono — paths, endpoints |

---

## 9.12 Settings Sections Visual

| Section | Key visual elements |
|---------|---------------------|
| Appearance | Radio pills font scale; toggle switches |
| Voice | Mode radio; mic test button secondary |
| Memory | User identity selector (Nolan / Ibrahim); read-only path mono |
| Tools | Mode selector LIVE/PAPER/SIMULATION/MOCK; connector rows |
| Accounts | OAuth connect buttons; status dots per service |
| Security | Secret key input masked; session clear destructive ghost |
| Developer | Telemetry toggle; debug brain toggle |
| Performance | Slider neural density; FPS cap numeric |

---

## 9.13 Icon Placement (Settings)

- Section nav: 16px leading icon per section
- Connector rows: 16px service icon + status dot 8px trailing
- Close: 16px X top-right card header
- Toggles: no icon — switch component only

---

## 9.14 Status, Composer, Dock (Settings)

| Element | Behavior |
|---------|----------|
| Topbar | Dimmed behind scrim — retains last presence copy |
| Composer | Hidden — non-interactive |
| Status cards | Hidden behind scrim |
| Telemetry | Hidden |
| Orchestrator | Dimmed, frozen snapshot — not interactive |

---

## 9.15 Transitions

| Event | Visual |
|-------|--------|
| Open | Scrim fade 350ms enter; card scale 0.96→1 slow enter |
| Section switch | Content cross-fade 200ms |
| Live preview (font scale) | Immediate apply — no save wait |
| Close | Card exit 350ms; scrim fade exit |
| Return | Underlying screen exactly as left — no reload |

---

## 9.16 Responsive Visual Summary

| Viewport | Key changes |
|----------|-------------|
| Desktop | 640px card centered; vertical section nav |
| Laptop | 560px card |
| Tablet | 90vw card; section nav horizontal chips |
| Phone | Full-screen sheet slide up; horizontal nav; close sticky top-right |

---

*Cross-screen architecture follows.*

---

# Cross-Screen Visual Architecture

## Navigation Visual Model

| Rule | Visual specification |
|------|---------------------|
| Single shell | Neural + sidebar + dock persist visually; center content cross-fades |
| Active nav | Red left border 2px + wash; 350ms transition between items |
| Settings | Overlay — underlying screen preserved and dimmed |
| Voice | May collapse sidebar; returns on exit |
| Deep link | Each screen addressable; no full-page reload visual |

---

## Orchestrator Visual Refocus

| Screen | Sections receiving visual emphasis (bold header + brighter border) |
|--------|---------------------------------------------------------------------|
| Home | State · Plan · Tools · Sparkline |
| Projects | State · Mission · Agent summary · Tools |
| Memory | State · Retrieval chain · Writes · Sparkline |
| Obsidian | Connector · Operation · Decision · Timeline |
| Exploration | Browser health · URLs · Fetch steps · Timeline |
| Trading | Analysis · Broker · Orders · Risk |
| Calendar | Planning · Conflicts · Tool status |
| Voice | State orb only (+ Tools if triggered) |
| Settings | Frozen dimmed snapshot |

Refocus animation: 300ms standard; outgoing section opacity 0.7; incoming 1.0.

---

## Status Cards Emphasis Matrix

| Screen | Hero card visual treatment |
|--------|---------------------------|
| Home | All 5 equal weight |
| Projects | État Cognitif — larger body text, red top edge |
| Memory | Mémoire Récente — expanded body, activity ring |
| Obsidian | Obsidian — vault name + sync dot |
| Exploration | Browser — URL count + status |
| Trading | État Cognitif + trading extension chip |
| Calendar | Custom agenda — next event countdown |
| Voice | Présence — ring arc prominent |
| Settings | Hidden behind scrim |

---

## Cognitive Region Activation Matrix

| Screen | ACTIF modules | IDLE modules |
|--------|---------------|--------------|
| Home | CORE + dynamic per activity | Others at 50% opacity |
| Projects | PLANIFICATION | Others |
| Memory | MÉMOIRE | Others |
| Obsidian | OBSIDIAN | Others |
| Exploration | BROWSER | Others |
| Trading | TRADING (when engaged) | Others |
| Calendar | CALENDAR + PLANIFICATION | Others |
| Voice | CORE + COMMUNICATION | Others |
| Settings | All IDLE at 40% opacity | — |

**ACTIF visual:** red border 1px, primary text, 2.4s pulse glow.
**IDLE visual:** muted text, 50% opacity, no pulse.

---

## Composer Visual Availability

| Screen | Composer visual |
|--------|-----------------|
| Home | Full — hero command |
| Projects | Full — project-scoped placeholder |
| Memory | Full — memory commands |
| Obsidian | Full — vault commands |
| Exploration | Full — research commands |
| Trading | Full — LIVE badge visible in topbar simultaneously |
| Calendar | Full — scheduling commands |
| Voice | Slim — single line fallback |
| Settings | Hidden |

---

## The Brain as Attention Anchor

Across all screens, the brain attracts attention through **differential motion**:

| Mechanism | Perceptual effect |
|-----------|-------------------|
| Idle drift | Peripheral life — user knows mind is present |
| State change | Motion intensifies — eye drawn to brightness change behind glass |
| Cognitive module ACTIF | Red pulse at region — eye tracks active capability |
| Directed signals | Paths travel toward active region — eye follows motion |
| Recall dive | Inward camera + ghost nodes — eye drawn to center depth |
| Voice ripple | Circular expansion — eye drawn to core |
| Error calm | Motion decays — eye notices sudden stillness |

The brain never competes with primary content through chaos — only through **purposeful change**.

---

## How Panels Appear — Universal Sequence

```
Frame 0:   Neural field visible (never frame 0 without mind)
Frame 1:   Ambient glow stabilizes
Frame 2:   Sidebar opacity 0 → 1 (350ms)
Frame 3:   Main column opacity 0 → 1 (350ms, +200ms delay)
Frame 4:   Orchestrator opacity 0 → 1 (350ms, +400ms delay)
Frame 5:   Bottom dock opacity 0 → 1 (350ms, +600ms delay)
Frame 6:   Center content populated (cross-fade if switching)
Frame 7:   Status resolves — "Présent — en attente"
```

No spinner. No skeleton. No progress bar.

---

## How Panels Disappear — Universal Sequence

```
Screen switch:
  1. Floating cards dissolve (400ms) if context changes
  2. Center content cross-fade (350ms exit + 350ms enter)
  3. Orchestrator sections refocus (300ms)
  4. Module labels update ACTIF/IDLE (500ms)
  5. Neural cognitive mode lerps (650–900ms)
  6. Sidebar, dock — NO change

Settings open:
  1. Scrim fade in (350ms)
  2. Workspace dims to 28% visibility
  3. Card scale enter (350ms)
  4. Composer/dock hidden

Settings close:
  1. Card exit (350ms)
  2. Scrim fade out (350ms)
  3. Workspace restores 100% — no reload
```

---

## How the Neural Field Reacts — Universal Table

| Backend state | Visual within 700ms |
|---------------|---------------------|
| Idle | Activity 0.08; drift ambient; glow 0.44 |
| Thinking | Activity 0.88; drift ×1.48; glow 0.78; brightness ×1.38 |
| Working (tool) | Directed waves; tool-specific profile; module ACTIF |
| Memory retrieval | Recall dive; ghost +36 nodes; central convergence |
| Listening | Ripple; activity 0.22; mic ring |
| Speaking | Circular pulses; brightness ×1.07 |
| Planning | Structured path bursts; PLANIFICATION ACTIF |
| Error | Decay to idle 900ms; no strobe |

---

## Forbidden Visual Patterns

| Pattern | Why forbidden |
|---------|---------------|
| Opaque white/light panels | Breaks void identity |
| Screen without neural field | Breaks "inside the mind" contract |
| Skeleton loading screens | Dishonest loading; use presence + neural |
| Candy chat bubbles | Generic chatbot |
| Per-tool app icons launching separate chrome | Tools are limbs |
| Three-dot typing indicator as primary thinking signal | Cliché; use neural + presence |
| Strobe / flash / bouncy springs | Animation guide violation |
| Slot-machine numeric scroll | Trading and telemetry |
| Red fill >15% static frame | Red is pulse, not paint |
| Agent personas with avatars | Single intelligence principle |
| Obsidian conflated with Titan Memory | Product policy |
| Trading LIVE without confirmation overlay | Safety |
| Memory mixed across Nolan/Ibrahim | User isolation |
| Invented layouts not in this mockup | **This document is the only visual authority** |

---

## Visual Verification Checklist

Before any frontend work ships:

- [ ] Screen matches mockup composition diagram
- [ ] Eye flow follows specified path
- [ ] Neural field visible per visibility table
- [ ] Glass alpha and blur match panel table
- [ ] Typography hierarchy uses specified tokens
- [ ] Icon placement follows global law
- [ ] Status elements in specified positions
- [ ] Floating cards respect max count and animation
- [ ] Panel appear/disappear follows universal sequence
- [ ] Neural reaction maps to backend state table
- [ ] Empty/loading/error states match screen section
- [ ] Responsive behavior matches screen summary
- [ ] Screen feels like "inside Titan's mind"
- [ ] No visual element invented outside this mockup

---

## Document Metadata

| Field | Value |
|-------|-------|
| Phase | D3 |
| Version | 1.0.0 |
| Established | 2026-07-06 |
| Authors | Titan Product (Nolan Hassing) |
| Predecessor | `TITAN_MASTER_BLUEPRINT.md` (Phase D2) |
| Successor | Phase D4+ implementation (frontend rebuild) |
| Authority | **Sole visual authority for Titan frontend** |

---

**End of Titan Master Mockup — Phase D3**

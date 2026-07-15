# Titan Design Language (TDL)

**Phase 17.2** — Official visual identity foundation for Titan's private web interface.

**Phase 17.3** — Titan Interface V1 ships at `GET /` using TDL across the full app shell.

TDL defines how Titan *feels* before the final dashboard is built. It is the contract between product identity, frontend implementation, and future UI phases.

---

## Design Philosophy

Titan AI is not a normal app. It is Nolan's QG, partner, and copilot — a single intelligence that thinks, remembers, and acts on his behalf.

The interface should communicate:

1. **Presence** — Titan is here, awake, and attentive.
2. **Depth** — cognition happens beneath the surface; the mind extends beyond the screen.
3. **Purpose** — every pixel earns its place; no decorative clutter.
4. **Partnership** — tools are extensions of Titan's will, not separate applications.
5. **Restraint** — minimalist first, futuristic second.

Opening Titan should feel like **entering Titan's mind**, not launching another SaaS dashboard.

---

## Emotional Target

| State | User should feel |
|-------|------------------|
| Idle | Calm presence — Titan is alive, breathing, watching quietly |
| Thinking | Focused energy — subtle pulse, not frantic loading spinners |
| Responding | Clarity — information arrives with confidence and precision |
| Acting (tools) | Titan is doing something *for* Nolan, not opening another app |
| Error | Honest, direct — no panic colors, no blame theatrics |

Titan never feels empty, noisy, playful-for-playfulness, or corporate-generic.

---

## Color Palette

### Core

| Token | Value | Role |
|-------|-------|------|
| `--tdl-bg-void` | `#000000` | Primary canvas — pure black |
| `--tdl-bg-surface` | `#0a0a0a` | Elevated panels |
| `--tdl-bg-elevated` | `#111111` | Nested surfaces, inputs |
| `--tdl-red-core` | `#8b0000` | Signature deep red |
| `--tdl-red-glow` | `#b91c1c` | Active states, neural pulses |
| `--tdl-red-dim` | `#5c0000` | Subtle accents, borders |
| `--tdl-text-primary` | `#f5f5f5` | Primary copy |
| `--tdl-text-secondary` | `#a3a3a3` | Labels, metadata |
| `--tdl-text-muted` | `#525252` | Disabled, placeholders |
| `--tdl-border-subtle` | `rgba(255, 255, 255, 0.06)` | Panel edges |
| `--tdl-border-active` | `rgba(139, 0, 0, 0.4)` | Focus, selection |

### Semantic (sparse use)

| Token | Value | Role |
|-------|-------|------|
| `--tdl-status-online` | `#22c55e` | System healthy (badge only) |
| `--tdl-status-warning` | `#ca8a04` | Caution |
| `--tdl-status-error` | `#dc2626` | Failure |

Semantic colors are **badges and indicators only** — never dominate the layout. Red remains Titan's identity color.

---

## Typography Direction

### Principles

- Clean, readable, slightly technical — not playful, not corporate slab.
- High contrast on black; never pure white body text at large sizes (use `--tdl-text-primary`).
- Hierarchy through weight and opacity, not rainbow colors.

### Font Stack (Phase 17.2)

| Role | Stack |
|------|-------|
| UI / body | `"Inter", "Segoe UI", system-ui, sans-serif` |
| Display / titles | Same stack, tighter tracking, lighter weight |
| Monospace / data | `"JetBrains Mono", "Cascadia Code", monospace` |

### Scale

| Token | Size | Use |
|-------|------|-----|
| `--tdl-text-xs` | 0.75rem | Badges, timestamps |
| `--tdl-text-sm` | 0.875rem | Labels, secondary |
| `--tdl-text-base` | 1rem | Body |
| `--tdl-text-lg` | 1.125rem | Section headers |
| `--tdl-text-xl` | 1.25rem | Panel titles |
| `--tdl-text-2xl` | 1.5rem | Page subtitles |
| `--tdl-text-display` | 2.25rem | Hero / Titan AI title |

Letter-spacing: slightly expanded on display text (`0.04em`); normal on body.

---

## Animation Rules

### Principles

1. **Organic, not mechanical** — ease curves mimic breathing, not clock ticks.
2. **Subtle by default** — motion supports comprehension; it never distracts.
3. **Always alive** — idle state has slow ambient motion (neural drift, soft glow pulse).
4. **Purpose-driven** — thinking states intensify existing motion; do not add new UI chrome.

### Timing

| Token | Duration | Use |
|-------|----------|-----|
| `--tdl-duration-instant` | 100ms | Hover feedback |
| `--tdl-duration-fast` | 200ms | Buttons, focus rings |
| `--tdl-duration-normal` | 350ms | Panel transitions |
| `--tdl-duration-slow` | 600ms | Page reveals |
| `--tdl-duration-breath` | 4s | Idle ambient pulse |
| `--tdl-duration-neural` | 12s | Background drift cycle |

### Easing

- Standard: `cubic-bezier(0.4, 0, 0.2, 1)`
- Enter: `cubic-bezier(0, 0, 0.2, 1)`
- Exit: `cubic-bezier(0.4, 0, 1, 1)`
- Organic: `cubic-bezier(0.45, 0.05, 0.55, 0.95)`

### Prohibited

- Bouncy spring animations
- Fast strobing or flashing
- Parallax overload
- Auto-playing sound
- Loading spinners as the primary thinking indicator (prefer neural pulse)

---

## Neural Network Behavior

The neural network is Titan's **core visual metaphor** — not wallpaper.

### Character

- Feels **infinite** — nodes and connections extend beyond viewport edges.
- Feels **deep** — layered depth via opacity, blur, and parallax (subtle).
- Feels **partially beyond the screen** — edges fade into void, not hard crop.
- Feels **alive when idle** — slow drift, occasional synaptic pulse along edges.

### Layers (implementation target)

| Layer | Opacity | Motion |
|-------|---------|--------|
| Far field | 0.15–0.25 | Very slow drift |
| Mid field | 0.35–0.50 | Slow drift + rare pulse |
| Near field | 0.60–0.80 | Pulse on thinking / tool use |

### Interaction

- **Idle**: ambient drift, 1 pulse every ~8–12s on a random edge.
- **Thinking**: pulse frequency increases; near-field nodes brighten slightly.
- **Tool execution**: brief synaptic flash along a path toward the active tool region.
- **Never**: explode into particles, rainbow trails, or game-like effects.

Phase 17.2 shipped CSS placeholders only. **Phase 17.3** adds a canvas neural network in the center column (`neural-network.js`) with layered nodes, drifting connections, and thinking-mode pulse. WebGL remains a future enhancement.

---

## Logo Direction

Phase 17.3 ships a **wordmark** in the sidebar: **Titan AI** — clean, spaced, one red accent on "AI". Symbol (abstract neural node) remains future work.

---

## Layout Principles

### Structure

```
┌─────────────────────────────────────────────────────┐
│  [Neural background — full viewport, behind all UI]   │
│  ┌──────────┬──────────────────────────────────────┐ │
│  │ Sidebar  │  Main content / conversation         │ │
│  │ (tools,  │  (primary focus)                     │ │
│  │  status) │                                      │ │
│  └──────────┴──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Rules

1. **Neural background is always present** — UI floats above it, never replaces it.
2. **Content max-width** — readable line length for text; neural field fills remaining space.
3. **Glass panels** — dark translucent surfaces (`--tdl-bg-surface` + subtle border), not opaque cards.
4. **Sidebar is contextual** — tools and status, not a second app launcher.
5. **Single focus** — conversation / mission is the hero; everything else supports it.
6. **Whitespace is intentional** — empty space is part of the void, not a bug.

### Z-index stack

| Layer | Z |
|-------|---|
| Neural background | 0 |
| Ambient glow | 1 |
| Panels / sidebar | 10 |
| Modals / overlays | 100 |
| Toasts | 110 |

---

## Mobile Principles

- Neural background remains; reduce node density for performance.
- Sidebar collapses to bottom sheet or icon rail.
- Touch targets minimum 44×44px.
- Typography scales down one step; display title remains legible.
- Animations respect `prefers-reduced-motion`.
- Pure black background preserved — OLED-friendly.

---

## What to Avoid

| Avoid | Why |
|-------|-----|
| White or light gray backgrounds | Breaks the "inside the mind" metaphor |
| Bright saturated accent colors | Competes with signature deep red |
| Card grids like Notion/Linear clones | Titan is not a generic productivity app |
| Separate "app icons" per tool | Tools are Titan's capabilities, not apps |
| Heavy borders and box shadows | Use glow and opacity instead |
| Stock illustrations / AI art avatars | Undermines authenticity |
| Chat bubbles with rounded candy colors | Use minimal transcript styling |
| Aggressive red everywhere | Red is accent and pulse, not fill |
| Public SaaS onboarding patterns | Titan is private, personal, local |
| Building the full dashboard in 17.2 | Foundation only — tokens, classes, preview |

---

## File Map

| Path | Purpose |
|------|---------|
| `docs/TITAN_DESIGN_LANGUAGE.md` | This document |
| `web/static/design/tokens.css` | CSS custom properties |
| `web/static/design/titan-ui.css` | Reusable component classes + Phase 17.3 app layout |
| `web/static/design.html` | Live preview at `GET /design` |
| `web/static/index.html` | Titan Interface V1 at `GET /` |
| `web/static/neural-network.js` | Canvas neural network animation |
| `web/static/app.js` | Interface logic (chat, nav, status, context panels) |

---

## Preview

With web mode enabled:

```powershell
python main.py web
```

- `http://127.0.0.1:8000/` — Titan Interface V1 (Phase 17.3)
- `http://127.0.0.1:8000/design` — TDL component gallery (Phase 17.2)

---

**End of Titan Design Language — Phase 17.3**

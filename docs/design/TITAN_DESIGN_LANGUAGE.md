# Titan Design Language

**Phase D1 — Official Product Specification**

**Status:** Authoritative visual token system for all Titan interface surfaces.

**Codename:** TDL (Titan Design Language)

**Scope:** Colors, typography, components (visual grammar), icons, borders, shadows, blur, transparency, animation principles, spacing, radius, and layout grid. No implementation code — token names are specified as the contract between design and engineering.

---

## Document Authority

TDL is binding. Any visual element not expressible in these tokens requires a spec amendment before use.

Companion documents:

- `TITAN_UI_BIBLE.md` — philosophy and interaction law
- `TITAN_ANIMATION_GUIDE.md` — motion timing and easing detail
- `TITAN_COMPONENT_LIBRARY.md` — component anatomy
- `TITAN_LAYOUT_GUIDE.md` — spatial application of grid tokens

---

## 1. Design Philosophy (Visual)

### 1.1 Emotional Target

| State | Visual character |
|-------|------------------|
| Idle | Calm void, soft red ambient, slow neural drift |
| Thinking | Elevated glow, increased signal density, no new chrome |
| Responding | Stable panels, confident typography, streaming legibility |
| Acting | Directed red synaptic paths toward active region |
| Error | Semantic badge only; void and red identity preserved |

### 1.2 Visual Tenets

1. **Void first** — black is the default, not a dark theme variant
2. **Red as pulse** — signature color is energy, not fill
3. **Glass over mind** — panels are translucent instruments
4. **Hierarchy through opacity** — not through hue proliferation
5. **OLED fidelity** — true `#000000` canvas where possible

---

## 2. Colors

### 2.1 Void and Surfaces

| Token | Value | Role |
|-------|-------|------|
| `tdl-bg-void` | `#000000` | Primary canvas — absolute black |
| `tdl-bg-surface` | `#0a0a0a` | Elevated panel base |
| `tdl-bg-elevated` | `#111111` | Nested surfaces, inputs, inset areas |
| `tdl-bg-overlay` | `rgba(0, 0, 0, 0.72)` | Modal scrim |

**Rule:** No token above `#111111` for structural surfaces. White backgrounds are forbidden.

### 2.2 Signature Red

| Token | Value | Role |
|-------|-------|------|
| `tdl-red-core` | `#8b0000` | Primary brand red — deep, restrained |
| `tdl-red-glow` | `#b91c1c` | Active states, synaptic highlights |
| `tdl-red-dim` | `#5c0000` | Subtle accents, inactive module borders |
| `tdl-red-subtle` | `rgba(139, 0, 0, 0.15)` | Tint fills, hover washes |
| `tdl-red-pulse` | `rgba(185, 28, 28, 0.35)` | Glow shadows, pulse halos |

**Rule:** Red never exceeds ~15% of visible pixels in a static frame. It punctuates; it does not dominate.

### 2.3 Text

| Token | Value | Role |
|-------|-------|------|
| `tdl-text-primary` | `#f5f5f5` | Body copy, titles |
| `tdl-text-secondary` | `#a3a3a3` | Labels, metadata, subtitles |
| `tdl-text-muted` | `#525252` | Disabled, placeholders, tertiary |
| `tdl-text-inverse` | `#000000` | Text on rare light accent fills only |

**Rule:** Never use pure `#FFFFFF` for large body blocks — primary off-white reduces halation on OLED.

### 2.4 Borders

| Token | Value | Role |
|-------|-------|------|
| `tdl-border-subtle` | `rgba(255, 255, 255, 0.06)` | Default panel edges |
| `tdl-border-default` | `rgba(255, 255, 255, 0.10)` | Emphasized dividers |
| `tdl-border-active` | `rgba(139, 0, 0, 0.40)` | Selected nav, active module |
| `tdl-border-focus` | `rgba(185, 28, 28, 0.60)` | Keyboard focus ring color |

### 2.5 Semantic (Badges and Dots Only)

| Token | Value | Role |
|-------|-------|------|
| `tdl-status-online` | `#22c55e` | System healthy indicator |
| `tdl-status-warning` | `#ca8a04` | Caution, pending confirmation |
| `tdl-status-error` | `#dc2626` | Failure indicator |
| `tdl-status-idle` | `#737373` | Inactive, placeholder |

**Rule:** Semantic colors appear only in dots, badges, and small pills — never as panel backgrounds or large fills.

### 2.6 Neural-Specific Colors

| Token | Character |
|-------|-----------|
| Neural node core | Red at variable alpha (0.08–0.85 by depth layer) |
| Neural edge | White at low alpha (0.04–0.18) with red pulse overlay |
| Ambient glow | Red radial gradient, 8–38% peak opacity |
| Depth haze | Black vignette, 38–72% at edges |
| Central core | Brightest red-white convergence at cognitive center |

Neural colors sync with TDL red tokens — never introduce alternate hue families (blue/purple synapses forbidden unless spec amended).

### 2.7 High Contrast Mode Overrides

When high contrast accessibility mode is active:

| Token | Override |
|-------|----------|
| `tdl-border-subtle` | `rgba(255, 255, 255, 0.14)` |
| `tdl-border-default` | `rgba(255, 255, 255, 0.22)` |
| `tdl-text-muted` | `#bdbdbd` |
| `tdl-text-secondary` | `#e0e0e0` |
| Panel background | More opaque (`~88%` black) |
| `tdl-red-pulse` | Stronger alpha (`~0.55`) |

Void remains black. High contrast increases legibility, not brightness of canvas.

---

## 3. Typography

### 3.1 Font Families

| Token | Stack | Role |
|-------|-------|------|
| `tdl-font-sans` | Inter, Segoe UI, system-ui, -apple-system, sans-serif | All UI and conversation text |
| `tdl-font-mono` | JetBrains Mono, Cascadia Code, Consolas, monospace | Telemetry, timestamps, code, data |

**Rule:** No display serif. No rounded playful fonts. No brand-new typeface without spec amendment.

### 3.2 Size Scale

| Token | Size | Use |
|-------|------|-----|
| `tdl-text-xs` | 0.75rem (12px) | Badges, timestamps, telemetry labels |
| `tdl-text-sm` | 0.875rem (14px) | Labels, secondary body, nav items |
| `tdl-text-base` | 1rem (16px) | Primary body, composer input |
| `tdl-text-lg` | 1.125rem (18px) | Section headers |
| `tdl-text-xl` | 1.25rem (20px) | Panel titles |
| `tdl-text-2xl` | 1.5rem (24px) | Page subtitles |
| `tdl-text-display` | 2.25rem (36px) | Hero wordmark, launch title |

### 3.3 Weight

| Token | Value | Use |
|-------|-------|-----|
| `tdl-weight-normal` | 400 | Body, descriptions |
| `tdl-weight-medium` | 500 | Labels, nav, buttons |
| `tdl-weight-semibold` | 600 | Titles, module headers, emphasis |

Display titles use lighter perceived weight via size and tracking, not ultra-light (100–200) weights.

### 3.4 Tracking and Leading

| Token | Value | Use |
|-------|-------|-----|
| `tdl-tracking-tight` | -0.01em | Dense data rows |
| `tdl-tracking-normal` | 0 | Body |
| `tdl-tracking-wide` | 0.04em | Display, wordmark, module titles (uppercase) |
| `tdl-leading-tight` | 1.25 | Headings, compact lists |
| `tdl-leading-normal` | 1.5 | Body |
| `tdl-leading-relaxed` | 1.65 | Long transcript paragraphs |

### 3.5 Typography Rules

- Hierarchy through **weight and opacity**, not color variety
- Uppercase module labels (`TITAN CORE`, `MÉMOIRE`) use wide tracking
- Monospace for any string that is **data** (FPS, version, ISO time)
- Minimum 12px rendered size on mobile (xs token); prefer sm for secondary
- Font scale accessibility: 100%, 112%, 125% — scales from base rem root

---

## 4. Components (Visual Grammar)

Components are specified fully in `TITAN_COMPONENT_LIBRARY.md`. Here: the **visual rules** each component family shares.

### 4.1 Panel Family

| Property | Specification |
|----------|---------------|
| Background | `tdl-panel-bg`: `rgba(0, 0, 0, 0.38)` default |
| Solid variant | `rgba(0, 0, 0, 0.46)` for inputs and elevated cards |
| Border | `tdl-panel-border`: `rgba(255, 255, 255, 0.04)` |
| Blur | `tdl-panel-blur`: 16px (reference shell: 22px) |
| Shadow | `tdl-panel-shadow`: soft black, 32px spread max |
| Padding | `tdl-panel-padding`: 1.5rem default |

### 4.2 Button Family

| Variant | Visual |
|---------|--------|
| Primary | Red core fill or red border with glow on hover; white text |
| Secondary | Elevated surface, default border, secondary text |
| Ghost | Transparent; hover shows subtle white wash |
| Disabled | 40% opacity; no glow |

All buttons: 4px sm radius minimum, medium weight label, focus-visible ring using `tdl-border-focus`.

### 4.3 Input Family

| Property | Specification |
|----------|---------------|
| Background | `tdl-bg-elevated` |
| Border | `tdl-border-subtle`; focus → `tdl-border-focus` |
| Text | `tdl-text-primary` |
| Placeholder | `tdl-text-muted` |
| Radius | `tdl-radius-md` (8px) |

### 4.4 Badge Family

Small pill; semantic dot optional (8px circle before label); xs text; full radius.

### 4.5 Navigation Item

Full-width row in sidebar; sm text; active state: red border-left or background wash + primary text; placeholder items show subtle "phase ultérieure" marker.

---

## 5. Icons

### 5.1 Style

| Property | Value |
|----------|-------|
| Type | Stroke (outline), not filled |
| Stroke width | 1.5px at 24px viewBox |
| Standard size | 16px (toolbar), 18px (composer) |
| Color | `currentColor` inheriting text tier |
| Corner | Round caps and joins |

### 5.2 Icon Categories

| Category | Examples | Color rule |
|----------|----------|------------|
| **Chrome** | Menu, window, info, attach | Secondary text |
| **Voice** | Microphone | Primary; red ring when active |
| **Status** | Health, brain | Semantic dot separate from icon |
| **Tool** | Browser, Obsidian, calendar | Monochrome glyph in card header |

### 5.3 Logo

**Wordmark:** `Titan` + `AI` where **AI** uses `tdl-red-glow`.

**Symbol (future):** Abstract single neural node — minimal geometry, no literal brain illustration, no mascot.

### 5.4 Prohibited Iconography

- Emoji as functional icons
- Filled Material-style colorful icons
- Stock AI sparkle icons
- App-store style rounded square tool icons

---

## 6. Borders

### 6.1 Philosophy

Borders are **hairlines in light**, not structural boxes. Prefer opacity and glow over heavy framing.

### 6.2 Width

| Context | Width |
|---------|-------|
| Panel default | 1px |
| Focus ring | 2px |
| Active nav accent | 2px left bar |
| Divider | 1px at `tdl-border-subtle` |

### 6.3 Style

- Solid only — no dashed except placeholder/disabled annotations
- Red borders indicate **active/selected**, not error (error uses semantic badge)
- Corner borders follow radius system — never square notch cuts

---

## 7. Shadows

### 7.1 Shadow Tokens

| Token | Definition | Use |
|-------|------------|-----|
| `tdl-shadow-sm` | `0 1px 2px rgba(0,0,0,0.5)` | Buttons, small chips |
| `tdl-shadow-md` | `0 4px 12px rgba(0,0,0,0.6)` | Dropdowns, floating cards |
| `tdl-shadow-lg` | `0 8px 24px rgba(0,0,0,0.7)` | Modals, elevated orchestrator |
| `tdl-panel-shadow` | `0 8px 32px rgba(0,0,0,0.45)` | Standard glass panel |

### 7.2 Glow Tokens

| Token | Use |
|-------|-----|
| `tdl-glow-red-sm` | Button hover, active dot |
| `tdl-glow-red-md` | Neural core, presence widget |
| `tdl-glow-red-lg` | Launch awakening peak |
| `tdl-glow-white-sm` | Subtle edge highlight on glass |

### 7.3 Rules

- Shadows extend **downward into void** — never light drop shadows simulating daylight
- No multi-colored shadows
- Glow replaces heavy box shadow for emphasis
- Orchestrator focus state may add red-tinted orbit shadow at 8% red max

---

## 8. Blur

### 8.1 Backdrop Blur

| Context | Blur radius |
|---------|-------------|
| Standard panel | 16px |
| Reference shell panel | 22px |
| Modal overlay card | 16–22px |
| Neural stage overlay | No blur on canvas itself |

### 8.2 Rules

- Blur applies to **panel backgrounds**, not text
- When blur unsupported or reduced motion + performance mode: increase panel opacity instead
- Never blur the conversation text column selectively — whole panel blurs as unit

---

## 9. Transparency

### 9.1 Alpha Scale

| Level | Alpha | Use |
|-------|-------|-----|
| Ghost | 0.04–0.06 | Borders, hairlines |
| Veil | 0.15–0.25 | Hover washes |
| Glass | 0.38–0.46 | Panel backgrounds |
| Scrim | 0.72 | Modal overlay |
| Neural far layer | 0.10–0.25 | Depth field |
| Neural near layer | 0.60–0.85 | Foreground nodes |

### 9.2 Rules

- Transparency reveals neural field — opaque panels require justification
- Text contrast must meet WCAG AA against **composited** background (glass over neural)
- Status cards in bottom dock may be slightly more opaque for readability

---

## 10. Animation Principles

Detailed specs: `TITAN_ANIMATION_GUIDE.md`. Summary:

| Principle | Specification |
|-----------|---------------|
| Organic | Breathing curves, not linear mechanical |
| Subtle | Default motion barely perceptible |
| Always alive | Idle ambient never zero |
| Purpose-driven | Thinking intensifies existing loops |
| Accessible | Reduced motion collapses durations |

### Duration Tokens

| Token | Duration |
|-------|----------|
| `tdl-duration-instant` | 100ms |
| `tdl-duration-fast` | 200ms |
| `tdl-duration-normal` | 350ms |
| `tdl-duration-slow` | 600ms |
| `tdl-duration-breath` | 5.5s |
| `tdl-duration-neural` | 14s |
| `tdl-duration-thinking` | 2.4s |
| `tdl-duration-presence-idle` | 6s |

### Easing Tokens

| Token | Curve |
|-------|-------|
| `tdl-ease-standard` | cubic-bezier(0.4, 0, 0.2, 1) |
| `tdl-ease-enter` | cubic-bezier(0, 0, 0.2, 1) |
| `tdl-ease-exit` | cubic-bezier(0.4, 0, 1, 1) |
| `tdl-ease-organic` | cubic-bezier(0.45, 0.05, 0.55, 0.95) |

### Prohibited Motion

- Bouncy springs
- Strobe / flash
- Parallax overload
- Auto-play sound tied to animation

---

## 11. Spacing System

### 11.1 Scale

| Token | Value |
|-------|-------|
| `tdl-space-2xs` | 0.125rem (2px) |
| `tdl-space-xs` | 0.25rem (4px) |
| `tdl-space-sm` | 0.5rem (8px) |
| `tdl-space-md` | 0.75rem (12px) |
| `tdl-space-base` | 1rem (16px) |
| `tdl-space-lg` | 1.5rem (24px) |
| `tdl-space-xl` | 2rem (32px) |
| `tdl-space-2xl` | 3rem (48px) |
| `tdl-space-3xl` | 4rem (64px) |

### 11.2 Application

| Context | Spacing |
|---------|---------|
| Component internal padding | md–lg |
| Between related elements | sm–md |
| Section separation | lg–xl |
| Workspace outer padding | 1.25rem (`tdl-workspace-padding`) |
| Workspace gap | 0.875rem (`tdl-workspace-gap`) |
| Nav item vertical gap | xs–sm |

### 11.3 Rules

- Use tokens only — no arbitrary 13px, 17px spacing
- Void whitespace is ** intentional** — do not fill with decorative elements
- Composer dock maintains minimum 200px chat area above it on desktop

---

## 12. Radius System

| Token | Value | Use |
|-------|-------|-----|
| `tdl-radius-sm` | 4px | Buttons, inputs, small chips |
| `tdl-radius-md` | 8px | Cards, composer, panels inner |
| `tdl-radius-lg` | 12px | Large cards, settings card |
| `tdl-radius-xl` | 16px | Modal card, exploration cards |
| `tdl-radius-full` | 9999px | Badges, dots, mic button |
| `tdl-radius-pill` | full | Alias for circular/pill shapes |

**Rule:** No mixed radius on same component corner set. Chat transcript blocks use md, not speech-bubble tail radius.

---

## 13. Layout Grid

### 13.1 Desktop Reference (Primary)

| Token | Value |
|-------|-------|
| `tdl-ref-sidebar-width` | 218px |
| `tdl-ref-orchestrator-width` | 318px |
| `tdl-content-max-width` | 720px (780px @1920, 840px @2560) |
| `tdl-ref-bottom-height` | 11.75rem minimum |
| `tdl-statusbar-height` | 32px (telemetry row) |

### 13.2 Legacy / Orbit Tokens

| Token | Value |
|-------|-------|
| `tdl-sidebar-width` | 220px |
| `tdl-context-width` | 300px |
| `tdl-orbit-nav-width` | 196px |
| `tdl-orbit-panel-width` | 272px |

Reference shell (Phase 24 layout) takes precedence for new work.

### 13.3 Grid Behavior

- **12-column conceptual grid** on center column for chat max-width centering
- Sidebars fixed width; center flexes
- Bottom dock spans full workspace width below center + sidebars
- Neural stage ignores grid — full viewport

Full breakpoint matrix: `TITAN_LAYOUT_GUIDE.md`.

### 13.4 Z-Index Tokens

| Token | Value |
|-------|-------|
| `tdl-z-neural` | 0 |
| `tdl-z-glow` | 1 |
| `tdl-z-content` | 10 |
| `tdl-z-statusbar` | 20 |
| `tdl-z-overlay` | 100 |
| `tdl-z-toast` | 110 |

---

## 14. What to Avoid

| Avoid | Why |
|-------|-----|
| White/light gray backgrounds | Breaks mind metaphor |
| Bright saturated accents | Competes with signature red |
| Card grids like Notion/Linear | Generic productivity clone |
| Per-tool app icons | Tools are capabilities |
| Heavy borders + light shadows | Use glow and glass |
| Stock illustrations / AI avatars | Undermines authenticity |
| Candy chat bubbles | Consumer chatbot pattern |
| Aggressive red fills | Red is pulse, not paint |
| Public SaaS onboarding | Titan is private QG |

---

## 15. Token Governance

### 15.1 Adding Tokens

New tokens require:

1. Spec entry in this document
2. Use case justification
3. Accessibility verification
4. Companion component entry if applicable

### 15.2 Deprecation

Deprecated tokens remain documented for one major version with migration mapping.

---

## Document Metadata

| Field | Value |
|-------|-------|
| Phase | D1 |
| Version | 1.0.0 |
| Established | 2026-07-06 |
| Supersedes | `docs/TITAN_DESIGN_LANGUAGE.md` (Phase 17.x summary — this document is authoritative) |

---

**End of Titan Design Language — Phase D1**

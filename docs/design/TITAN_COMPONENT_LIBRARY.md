# Titan Component Library

**Phase D1 — Official Product Specification**

**Status:** Authoritative component catalog for Titan's interface.

**Scope:** Every user-facing component — anatomy, states, behavior, accessibility, and visual binding to TDL tokens. No implementation code.

---

## Document Authority

New UI surfaces must use components defined here or extend this document before shipping.

Visual tokens: `TITAN_DESIGN_LANGUAGE.md`. Motion: `TITAN_ANIMATION_GUIDE.md`. Spatial placement: `TITAN_LAYOUT_GUIDE.md`.

---

## 1. Component Index

| Category | Components |
|----------|------------|
| **Shell** | Workspace, Neural Stage, Launch Overlay, Ambient Glow |
| **Navigation** | Sidebar, Logo, Nav Item, Topbar |
| **Conversation** | Chat Panel, Message, Composer, Thinking Indicator |
| **Cognitive** | Neural Module Label, Orchestrator Panel, Orchestrator Sections |
| **Status** | Presence Widget, Status Cards, Telemetry Bar, Badges |
| **Tools** | Tool Timeline, Tool Progress Card, Tool Status Line |
| **Memory** | Memory Card, Memory Status Line, Memory Cards Layer |
| **Voice** | Mic Button, Waveform |
| **Input** | Button, Input, Textarea, Select, Label, Checkbox |
| **Overlay** | Settings Panel, View Placeholder, Toast |
| **Exploration** | Exploration Card |
| **Accessibility** | Skip Link, A11y Settings Group |

---

## 2. Shell Components

### 2.1 Workspace (`tdl-workspace`)

**Role:** Root layout container floating above neural stage.

| Property | Specification |
|----------|---------------|
| Structure | CSS grid: sidebar + main + orchestrator + bottom dock |
| Background | Transparent — neural visible through gaps |
| Padding | `tdl-workspace-padding` (1.25rem) |
| Gap | `tdl-workspace-gap` (0.875rem) |
| Variant | `--reference` — Phase 24 official layout |

**States:** Default; settings-open (orchestrator dimmed optional).

---

### 2.2 Neural Stage (`tdl-neural-stage`)

**Role:** Full-viewport container for canvas and view placeholders.

| Property | Specification |
|----------|---------------|
| Position | Fixed or absolute; inset 0 |
| Z-index | `tdl-z-neural` (0) |
| Contents | Canvas + optional placeholder overlays |
| Edge treatment | Vignette fade via pseudo-element |

**Behavior:** Never unmounts during session. Placeholders toggle visibility per active view.

---

### 2.3 Neural Canvas (`tdl-neural-canvas`)

**Role:** Render target for Titan Neural Engine.

| Property | Specification |
|----------|---------------|
| Size | 100% of stage; devicePixelRatio capped at 2 |
| Pointer events | None — passes through to UI |
| State classes | booting, awake, listening, thinking, working, speaking, cognitive-* |

See `TITAN_NEURAL_ENGINE.md`.

---

### 2.4 Launch Overlay (`tdl-launch`)

**Role:** Awakening sequence on cold load.

| Property | Specification |
|----------|---------------|
| Background | Void black |
| Content | Status line only — no logo animation, no spinner |
| Copy sequence | "Initialisation…" → "Éveil du réseau…" → "Présent." |
| Exit | Fade 400ms after panels ready |
| Accessibility | `aria-live="polite"` |

---

### 2.5 Ambient Glow (`tdl-glow-ambient`)

**Role:** Screen-edge red atmospheric pulse.

| Property | Specification |
|----------|---------------|
| Z-index | `tdl-z-glow` (1) |
| Motion | 5.5s breath cycle |
| Pointer events | None |
| aria-hidden | true |

---

## 3. Navigation Components

### 3.1 Sidebar (`tdl-ref-sidebar`)

**Role:** Primary navigation and presence summary.

| Property | Specification |
|----------|---------------|
| Width | 218px (`tdl-ref-sidebar-width`) |
| Surface | Reference panel glass |
| Sections | Logo → Nav → Presence block |
| Collapse | See layout guide for tablet/mobile |

---

### 3.2 Logo (`tdl-logo`)

| Element | Specification |
|---------|---------------|
| Wordmark | "Titan" primary + "AI" accent red |
| Tagline | Version string, xs muted mono |
| Size | Wordmark lg–xl weight medium |

---

### 3.3 Nav Item (`tdl-nav__item`)

**Role:** View switcher.

| State | Visual |
|-------|--------|
| Default | sm text, secondary color |
| Hover | Elevated wash, primary text |
| Active | Red border-left or background tint, primary text |
| Placeholder | Muted + subtle "phase ultérieure" marker after label |
| Focus | Focus-visible ring |

**Views:** chat, projects, memory, browser, calendar, trading, tools, settings

**Behavior:** Click switches center focus and orchestrator sections; does not hide neural field.

---

### 3.4 Topbar (`tdl-ref-topbar`)

**Role:** System state summary above center column.

| Element | Specification |
|---------|---------------|
| Pills | Memory (green dot), Tools (blue dot), Reflection (red dot) — small, metadata only |
| Status | Natural French presence copy, centered |
| Actions | Icon buttons (info, window, menu) + "Cerveau" brain button |
| Height | ~48–56px implicit |

**Brain button:** Invokes neural focus or future brain inspector — red accent icon.

---

## 4. Conversation Components

### 4.1 Chat Panel (`tdl-ref-chat`)

**Role:** Primary conversation surface.

| Property | Specification |
|----------|---------------|
| Position | Center column, below topbar |
| Surface | Glass panel |
| Min height | 200px chat area |
| Max text width | `tdl-content-max-width` centered |

---

### 4.2 Conversation Scroll (`tdl-conversation`)

| Property | Specification |
|----------|---------------|
| Scroll | Vertical; auto-scroll on new message unless user scrolled up |
| Live region | `aria-live="polite"` on scroll container |
| Inner padding | lg horizontal, md vertical |

---

### 4.3 Message (`tdl-message`)

**Role:** Single transcript entry.

| Variant | Specification |
|---------|---------------|
| User | Label "Toi" or username; text primary; minimal block — no bright bubble |
| Titan | Label "Titan"; text primary; optional subtle left border red dim |
| System | xs muted; centered optional |
| Error | Semantic error badge inline; text secondary |

**Forbidden:** Rounded candy bubbles, avatar images, emoji reactions row.

**Streaming:** Content appends in place; cursor optional at end.

---

### 4.4 Thinking Indicator (`tdl-conversation__thinking`)

| Property | Specification |
|----------|---------------|
| Visibility | Hidden when not thinking |
| Copy | "Titan réfléchit…" |
| Style | sm muted italic or secondary |
| Animation | Fade 200ms — no bouncing dots |

---

### 4.5 Composer (`tdl-composer`)

**Role:** Message input dock inside bottom footer.

| Element | Specification |
|---------|---------------|
| Mic button | Left — see Voice section |
| Textarea | Auto-grow 1–4 rows; placeholder "Écris ton message…" |
| Attach | Ghost icon button |
| Actions | Stop (ghost, hidden default) + Send (primary) |
| Surface | Elevated glass strip |

**Keyboard:** Enter sends; Shift+Enter newline. Focus trap does not apply — single form.

---

## 5. Cognitive Components

### 5.1 Neural Module Label (`tdl-neural-module`)

**Role:** Spatial label tying brain regions to architecture.

| Property | Specification |
|----------|---------------|
| Position | Absolute within center column over neural field |
| Modules | core, memory, planning, browser, obsidian, tools, communication, trading, calendar |
| Title | Uppercase, wide tracking, xs–sm |
| Subtitle | Secondary, xs |
| Status badge | ACTIF / IDLE |

| State | Visual |
|-------|--------|
| Active | Red border, higher opacity, optional pulse |
| Idle | Muted border, 50% opacity |

**Behavior:** Positions are fixed design anchors — not draggable in V1.

---

### 5.2 Orchestrator Panel (`tdl-ref-orchestrator`)

**Role:** Right column — cognitive transparency.

| Property | Specification |
|----------|---------------|
| Width | 318px |
| Title | "Cognitive Orchestrator" |
| Sections | Collapsible logically by view focus |

---

### 5.3 Orchestrator State (`tdl-orchestrator-state`)

| Element | Specification |
|---------|---------------|
| Orb | Animated breathe sphere — red glow |
| Badge | Current state: Idle, Thinking, Working, etc. |
| Detail | One sentence French explanation |

---

### 5.4 Orchestrator Steps (`tdl-orchestrator-steps`)

**Role:** Plan step list from planner/reasoning loop.

| Property | Specification |
|----------|---------------|
| Type | Ordered list |
| Item states | pending, active, complete, failed |
| Active | Red left border |
| Complete | Muted + strikethrough fade |
| Empty | "En attente de demande…" |

---

### 5.5 Orchestrator Tools (`tdl-orchestrator-tools`)

| Property | Specification |
|----------|---------------|
| Type | Unordered list |
| Item | Tool name + status chip |
| Empty | "Aucun outil actif" |

---

### 5.6 Orchestrator Neural Sparkline (`tdl-orchestrator-sparkline`)

| Property | Specification |
|----------|---------------|
| Canvas | ~full width × 48px |
| Data | Neural activity level over last N seconds |
| Caption | Matches presence label |

---

## 6. Status Components

### 6.1 Presence Block (`tdl-ref-presence-block`)

**Location:** Sidebar bottom.

| Element | Specification |
|---------|---------------|
| System row | Green dot + "Titan Online" |
| Brain row | Red dot + "Cerveau Actif" |
| Presence widget | Title + waveform + mini core |

---

### 6.2 Presence Waveform (`tdl-ref-waveform`)

| Property | Specification |
|----------|---------------|
| Canvas | ~120×32px |
| Motion | Bar heights driven by presence engine |
| Colors | Red gradient bars on transparent |

---

### 6.3 Presence Ring (`tdl-ref-presence-ring`)

**Location:** Presence status card in bottom dock.

| Property | Specification |
|----------|---------------|
| Type | SVG circular progress |
| Track | Muted circle |
| Fill | Red arc — dashoffset driven by activity 0–100% |
| Center label | Percentage xs mono |

---

### 6.4 Status Card (`tdl-ref-status-card`)

**Role:** Bottom dock summary tiles.

| Property | Specification |
|----------|---------------|
| Size | Equal flex columns in row |
| Structure | Header (title + optional icon) + body |
| Surface | Slightly more opaque glass for readability |

**Instances:**

| ID | Title | Body content |
|----|-------|--------------|
| Recent Memory | Mémoire Récente | Last memory lines |
| Obsidian | Obsidian | Vault status |
| Browser | Browser | Current research |
| Cognitive | État Cognitif | State enum |
| Presence | Présence | Activity level + ring |

---

### 6.5 Telemetry Bar (`tdl-ref-telemetry`)

**Role:** Footer diagnostic strip.

| Group | Items |
|-------|-------|
| Performance | FPS, Brain state |
| Subsystems | Memory count, Tools active, Reflection mood |
| Clock | Local time mono |

**Character:** xs mono muted — never competes with composer.

---

### 6.6 Badge (`tdl-badge`)

| Variant | Dot color | Use |
|---------|-----------|-----|
| online | green | System healthy |
| warning | amber | Pending confirmation |
| error | red | Failure |
| idle | gray | Inactive |

Always xs size; optional leading dot 6–8px.

---

## 7. Tool Components

### 7.1 Tool Timeline (`tdl-tool-timeline`)

| Property | Specification |
|----------|---------------|
| Location | Orchestrator tools section |
| Item | Timestamp + tool name + outcome |
| Order | Reverse chronological |
| Max visible | 8 — scroll within section |

---

### 7.2 Tool Progress Card (`tdl-tool-progress-card`)

| Property | Specification |
|----------|---------------|
| Location | Floating stack above bottom dock |
| Content | Tool name, progress bar, status text |
| Enter/exit | See animation guide |
| Stack | Max 3 visible — oldest dismiss first |

---

### 7.3 Tool Status Line (`tdl-tool-status-line`)

| Property | Specification |
|----------|---------------|
| Location | Above composer |
| Copy | Tool-specific natural French |
| Visibility | Hidden when no active tool |
| aria-live | polite |

---

## 8. Memory Components

### 8.1 Memory Card (`tdl-memory-card`)

| Property | Specification |
|----------|---------------|
| Location | `memory-cards-layer` float or memory view |
| Content | Category chip, note excerpt, timestamp |
| Max excerpt | 120 characters |
| Animation | Stagger enter 80ms |

---

### 8.2 Memory Status Line (`tdl-memory-status-line`)

| Property | Specification |
|----------|---------------|
| Copy | "Recherche en mémoire…" / result summary |
| Style | sm secondary |

---

### 8.3 Memory Cards Layer (`tdl-memory-cards`)

| Property | Specification |
|----------|---------------|
| Role | Ephemeral float layer for retrieval visualization |
| pointer-events | none |
| aria-hidden | true when decorative |

---

## 9. Voice Components

### 9.1 Mic Button (`tdl-voice-mic`)

| State | Visual |
|-------|--------|
| idle | Ghost circle, icon secondary |
| listening | Red ring pulse, icon primary |
| pressed | aria-pressed true |

| Property | Specification |
|----------|---------------|
| Size | 44×44px minimum |
| Label | "Parler à Titan" |
| Interaction | Push-to-talk default |

---

### 9.2 Waveform (Voice)

Shared with presence waveform — audio envelope drives bar heights when listening.

---

## 10. Input Components

### 10.1 Button (`tdl-btn`)

| Variant | Use |
|---------|-----|
| primary | Send, save, confirm |
| secondary | Alternate positive |
| ghost | Cancel, stop, attach |

| State | Behavior |
|-------|----------|
| hover | Brightness + border |
| active | translateY 1px |
| disabled | 40% opacity |
| focus-visible | Red focus ring |

---

### 10.2 Input (`tdl-input`)

Single-line text; password type for secret key; elevated surface.

---

### 10.3 Textarea (`tdl-composer__input`)

Multi-line; composer only in V1 — reusable pattern for future forms.

---

### 10.4 Select (`tdl-select`)

Native select styled — font scale preference, future theme options.

---

### 10.5 Label (`tdl-label`)

sm medium; optional `--checkbox` variant with inline input.

---

### 10.6 Checkbox

Native checkbox; label explains setting in French.

---

## 11. Overlay Components

### 11.1 Settings Panel (`tdl-settings-panel`)

| Property | Specification |
|----------|---------------|
| Scrim | overlay bg 72% black |
| Card | lg radius, panel glass |
| Fields | Secret key, voice continuous, a11y group |
| Actions | Save primary, Close ghost |

**Not a separate page** — overlay preserves neural context behind scrim.

---

### 11.2 View Placeholder (`tdl-view-placeholder`)

| Property | Specification |
|----------|---------------|
| Use | Calendar, Trading — future views |
| Content | Title + one-line French description |
| Card | Exploration variant for browser |

---

### 11.3 Toast (Future)

| Property | Specification |
|----------|---------------|
| Position | Bottom-right above dock |
| Z-index | 110 |
| Duration | 4s auto-dismiss |
| Style | Glass + semantic dot |

Spec reserved — not required V1.

---

## 12. Exploration Card (`tdl-view-placeholder__card--exploration`)

| Property | Specification |
|----------|---------------|
| Use | Browser active state center overlay |
| Title | "Exploration" |
| Body | Describes web research activity |

---

## 13. Accessibility Components

### 13.1 Skip Link (`tdl-skip-link`)

| Property | Specification |
|----------|---------------|
| Target | `#chat-composer` |
| Copy | "Aller au message" |
| Visible | On focus only |

---

### 13.2 A11y Settings Group (`tdl-a11y-group`)

| Option | Effect |
|--------|--------|
| Réduire les animations | Reduced motion class |
| Contraste élevé | High contrast tokens |
| Taille du texte | 100 / 112 / 125 % |

---

## 14. Component Composition Rules

### 14.1 Nesting

- Panels contain sections contain content — max 3 levels before flat list
- No panel inside panel without elevation change
- Orchestrator sections never contain chat transcript

### 14.2 Empty States

Every list component defines empty copy in French — never lorem ipsum.

### 14.3 Loading

No skeleton screens. Use presence state + honest copy + neural activity.

### 14.4 Confirmation

Destructive actions use secondary overlay with primary confirm + ghost cancel — never browser `alert()`.

---

## 15. Component ↔ Token Map (Summary)

| Component | Background | Border | Text | Radius |
|-----------|------------|--------|------|--------|
| Reference panel | panel-bg + blur | panel-border | primary/secondary | md |
| Status card | panel-bg-solid | subtle | sm | md |
| Button primary | red-core | focus ring | primary | sm |
| Composer | elevated | subtle | primary | md |
| Nav item active | red-subtle wash | active | primary | sm |

---

## Document Metadata

| Field | Value |
|-------|-------|
| Phase | D1 |
| Version | 1.0.0 |
| Established | 2026-07-06 |

---

**End of Titan Component Library — Phase D1**

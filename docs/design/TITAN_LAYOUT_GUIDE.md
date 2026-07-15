# Titan Layout Guide

**Phase D1 — Official Product Specification**

**Status:** Authoritative spatial system for Titan across all viewports.

**Scope:** Desktop, laptop, tablet, phone, ultrawide layouts; panel hierarchy; layer hierarchy; margins; spacing. No implementation code.

---

## Document Authority

All interface layout decisions defer to this guide and TDL spacing tokens (`TITAN_DESIGN_LANGUAGE.md`).

Component anatomy: `TITAN_COMPONENT_LIBRARY.md`.

---

## 1. Layout Philosophy

### 1.1 Principles

| Principle | Application |
|-----------|-------------|
| **Neural first** | Full viewport mind; UI floats above |
| **Conversation center** | Chat column is optical focal point |
| **Transparency** | Gaps and glass reveal the brain |
| **Fixed side columns** | Navigation and orchestrator stable; center flexes |
| **Bottom command dock** | Input and status always reachable |
| **Progressive collapse** | Complexity folds gracefully on smaller viewports |

### 1.2 Reference Layout (Primary)

Phase 24 **Reference Interface** is the canonical desktop layout:

```
┌────────────────────────────────────────────────────────────────────────┐
│ NEURAL STAGE (full viewport, z=0)                                       │
│ ┌──────────┬────────────────────────────────────────┬────────────────┐ │
│ │ SIDEBAR  │ MAIN COLUMN                             │ ORCHESTRATOR   │ │
│ │ 218px    │ ┌ topbar ─────────────────────────────┐ │ 318px        │ │
│ │          │ │ neural module labels (overlay)        │ │              │ │
│ │          │ ├ chat / active view ─────────────────┤ │              │ │
│ │          │ └─────────────────────────────────────┘ │              │ │
│ └──────────┴────────────────────────────────────────┴────────────────┘ │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ BOTTOM DOCK — status cards · composer · telemetry                 │ │
│ └──────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer Hierarchy

### 2.1 Z-Index Stack

| Order | Layer | Z-index token | Contents |
|-------|-------|---------------|----------|
| 0 | Neural stage | `tdl-z-neural` (0) | Canvas, placeholders |
| 1 | Ambient glow | `tdl-z-glow` (1) | Edge radial pulse |
| 2 | Workspace | `tdl-z-content` (10) | Sidebar, main, orchestrator, dock |
| 3 | Status emphasis | `tdl-z-statusbar` (20) | Telemetry row optional elevation |
| 4 | Overlays | `tdl-z-overlay` (100) | Settings, modals |
| 5 | Toasts | `tdl-z-toast` (110) | Future notifications |

### 2.2 Panel Hierarchy (Within Workspace)

```
Workspace
├── Sidebar (navigation authority)
├── Main column
│   ├── Topbar (session status)
│   ├── Center stack
│   │   ├── Neural module labels (decorative overlay)
│   │   └── Chat / view content (primary)
├── Orchestrator (cognitive transparency)
└── Bottom dock (command + summary)
    ├── Status cards row
    ├── Status lines (tool/memory)
    ├── Composer
    └── Telemetry
```

**Rule:** Deeper cognitive detail right (orchestrator); action input bottom; identity left (sidebar).

---

## 3. Desktop Layout (≥1280px)

### 3.1 Grid Definition

| Region | Width | Behavior |
|--------|-------|----------|
| Sidebar | 218px fixed | Always visible |
| Orchestrator | 318px fixed | Always visible |
| Main | `flex: 1` | Min width 480px |
| Bottom dock | 100% workspace width | Height min 11.75rem |

### 3.2 Main Column

| Element | Layout |
|---------|--------|
| Topbar | Full width; flex row: pills | status | actions |
| Center | Flex 1; chat panel fills |
| Module labels | Absolute positioned; do not reflow chat |
| Chat max-width | 720px centered in center column |

### 3.3 Bottom Dock

| Row | Height | Content |
|-----|--------|---------|
| Status cards | ~88–104px | 5 equal flex cards |
| Status lines | auto | Optional single line |
| Composer | ~56–72px | Mic + textarea + actions |
| Telemetry | 32px | xs mono strip |

### 3.4 Margins and Padding

| Context | Value |
|---------|-------|
| Workspace outer padding | 1.25rem |
| Inter-region gap | 0.875rem |
| Panel inner padding | 1.5rem |
| Chat inner horizontal | 1.5rem |

### 3.5 Ultrawide (≥2560px)

| Adjustment | Value |
|------------|-------|
| Sidebar | 240px |
| Orchestrator | 318px (unchanged) |
| Chat max-width | 840px |
| Neural field | Extra visible mind left/right of panels — never fill with widgets |

**Rule:** Ultrawide adds **breathing room**, not additional columns.

---

## 4. Laptop Layout (1024px – 1279px)

### 4.1 Adjustments

| Region | Change |
|--------|--------|
| Sidebar | 218px — may compress tagline |
| Orchestrator | 280px minimum — truncate long step text |
| Chat max-width | 680px |
| Status cards | 5 cards — smaller body text sm |
| Module labels | Reduce to core + active modules only |

### 4.2 Minimum Widths

| Region | Min |
|--------|-----|
| Main column | 400px |
| Composer textarea | 200px flex |

Below 1024px → tablet mode.

---

## 5. Tablet Layout (768px – 1023px)

### 5.1 Structure Change

```
┌──────────────────────────────────────┐
│ NEURAL STAGE                          │
│ ┌────────────────────────────────────┐│
│ │ TOPBAR (compact)                    ││
│ ├────────────────────────────────────┤│
│ │ MAIN (chat full width)              ││
│ ├────────────────────────────────────┤│
│ │ BOTTOM DOCK (cards scroll row)      ││
│ │ COMPOSER                            ││
│ └────────────────────────────────────┘│
│ [SIDEBAR → icon rail or bottom sheet] │
│ [ORCHESTRATOR → slide-over drawer]    │
└──────────────────────────────────────┘
```

### 5.2 Sidebar

| Mode | Specification |
|------|---------------|
| Default | Collapsed to 56px icon rail left |
| Expanded | Overlay drawer 218px over content |
| Trigger | Hamburger in topbar |

Icons only in rail; labels in drawer.

### 5.3 Orchestrator

| Mode | Specification |
|------|---------------|
| Default | Hidden |
| Open | Right slide-over 318px or 85vw max |
| Trigger | "Cerveau" button or swipe from right edge |

### 5.4 Status Cards

Horizontal scroll row; snap to card; min card width 160px.

### 5.5 Neural Module Labels

Hidden by default — show only active module chip in topbar.

### 5.6 Touch

All targets minimum 44×44px.

---

## 6. Phone Layout (<768px)

### 6.1 Structure

```
┌─────────────────────┐
│ NEURAL (reduced)     │
│ ┌───────────────────┐│
│ │ TOPBAR mini       ││
│ ├───────────────────┤│
│ │ CHAT (full bleed) ││
│ ├───────────────────┤│
│ │ COMPOSER sticky   ││
│ └───────────────────┘│
│ [Nav bottom sheet]   │
└─────────────────────┘
```

### 6.2 Priorities (Top → Bottom)

1. Composer — sticky above safe area inset
2. Chat transcript — scrollable
3. Topbar — presence status one line
4. Everything else — sheets

### 6.3 Hidden by Default

- Orchestrator (sheet only)
- Status cards (single combined status chip)
- Telemetry (settings diagnostic)
- Module labels

### 6.4 Neural Performance

Node count −30%; signal max −40%; infinite illusion preserved.

### 6.5 Typography

Base sm (14px); display title xl not display token.

### 6.6 Safe Areas

Respect `env(safe-area-inset-*)` on composer and bottom nav.

---

## 7. Ultrawide Layout (≥1920px)

### 7.1 1920px (Full HD+)

| Token | Value |
|-------|-------|
| Chat max-width | 780px |
| Workspace padding | 1.25rem |

### 7.2 3440px+ Ultrawide

| Rule | Specification |
|------|---------------|
| Max content spread | Chat stays max 840px centered |
| Side panels | Fixed width — do not stretch |
| Neural visibility | Minimum 40% viewport width visible mind |
| No third sidebar | Forbidden |

### 7.3 Dual Monitor

Spec silent on window spanning — single window follows ultrawide rules.

---

## 8. Panel Hierarchy Detail

### 8.1 Visual Weight

| Tier | Panels | Opacity / blur |
|------|--------|----------------|
| Primary | Chat | Standard glass |
| Secondary | Sidebar, Orchestrator | Standard glass |
| Tertiary | Status cards | Slightly more opaque |
| Ephemeral | Tool progress float | md shadow + glass |
| Overlay | Settings | Scrim + solid card |

### 8.2 Focus Routing

| Active view | Center | Orchestrator sections visible |
|-------------|--------|-------------------------------|
| chat | Conversation | State, Plan, Tools, Neural |
| projects | Projects placeholder | Projects, agenda |
| memory | Memory view | Memory activity |
| browser | Exploration overlay | Tools, browser card |
| tools | Tools summary | Metrics |
| settings | Settings overlay | Dimmed behind scrim |

---

## 9. Spacing Application Matrix

| Location | Token |
|----------|-------|
| Nav item padding | sm md |
| Section title margin-bottom | md |
| Orchestrator section gap | lg |
| Message gap | md |
| Card internal padding | md |
| Composer internal gap | sm |
| Topbar horizontal padding | lg |
| Status card gap | sm |

---

## 10. Radius Application Matrix

| Element | Radius |
|---------|--------|
| Sidebar panel | md |
| Chat panel | md |
| Status card | md |
| Composer | md |
| Buttons | sm |
| Mic button | full |
| Settings card | lg |
| Badges | full |

---

## 11. Breakpoint Summary

| Name | Range | Layout mode |
|------|-------|-------------|
| Phone | <768px | Single column + sheets |
| Tablet | 768–1023px | Rail + drawer |
| Laptop | 1024–1279px | Compact three-column |
| Desktop | 1280–1919px | Reference three-column |
| Wide | 1920–2559px | Reference + wider chat |
| Ultrawide | ≥2560px | Reference + max chat 840px |

---

## 12. Accessibility Layout

### 12.1 Font Scale

| Setting | Root scale |
|---------|------------|
| 100% | 1rem base |
| 112% | 1.12× |
| 125% | 1.25× |

Composer min-height increases; cards may wrap 2 rows at 125% on laptop.

### 12.2 High Contrast

Panels more opaque — layout dimensions unchanged.

### 12.3 Reduced Motion

Layout static — no parallax shift between regions.

---

## 13. Launch Layout

During launch overlay:

- Full viewport void
- No panel geometry visible until neural fade complete
- Panels appear in order: sidebar → main → orchestrator → dock
- Stagger 200ms per region

---

## 14. Forbidden Layout Patterns

| Pattern | Reason |
|---------|--------|
| White sidebar on black main | Breaks void identity |
| Three-column card dashboard grid | Generic SaaS |
| Chat squeezed below fold on desktop | Conversation not hero |
| Orchestrator wider than main | Cognitive detail dominates |
| Fixed 320px mobile width design only | Responsive required |
| Neural replaced by static image on mobile | Mind must stay alive |

---

## 15. Layout Verification Checklist

- [ ] Neural visible in gaps at desktop reference
- [ ] Chat readable max-width at all breakpoints
- [ ] Composer reachable without scroll on phone
- [ ] Sidebar accessible via keyboard in all modes
- [ ] Orchestrator available within 2 taps on tablet
- [ ] Ultrawide does not stretch chat beyond 840px
- [ ] Safe areas respected on iOS
- [ ] Skip link reaches composer

---

## Document Metadata

| Field | Value |
|-------|-------|
| Phase | D1 |
| Version | 1.0.0 |
| Established | 2026-07-06 |

---

**End of Titan Layout Guide — Phase D1**

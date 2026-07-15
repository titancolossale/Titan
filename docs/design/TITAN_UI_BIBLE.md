# Titan UI Bible

**Phase D1 — Official Product Specification**

**Status:** Single source of truth for all Titan interface work.

**Audience:** Product designers, frontend engineers, and future contributors rebuilding Titan from scratch.

**Scope:** Philosophy, environment, interaction law, and the unifying narrative that binds every pixel of Titan's interface. This document does not describe implementation. It defines what Titan must *be*.

---

## Document Authority

| Rule | Description |
|------|-------------|
| **Mandatory** | No UI feature, refactor, or visual experiment may ship without conforming to this bible and its companion specs in `docs/design/`. |
| **Hierarchy** | When documents conflict, resolve in this order: Constitution → Experience Manifesto → UI Bible → specialized guides (Animation, Components, Neural Engine, Layout, Design Language). |
| **Change control** | Any amendment to this bible requires explicit product approval and a version note at the top of the changed document. |

### Companion Documents

| Document | Role |
|----------|------|
| `TITAN_EXPERIENCE_MANIFESTO.md` | Why Titan exists; commandments and principles |
| `TITAN_DESIGN_LANGUAGE.md` | Visual tokens: color, type, spacing, surfaces |
| `TITAN_ANIMATION_GUIDE.md` | Motion law for every cognitive and UI state |
| `TITAN_COMPONENT_LIBRARY.md` | Component anatomy and behavior |
| `TITAN_NEURAL_ENGINE.md` | The living brain visualization specification |
| `TITAN_LAYOUT_GUIDE.md` | Spatial system across all viewports |

---

## 1. Philosophy

### 1.1 What Titan Is

Titan is not a chatbot wrapped in a dashboard. Titan is a **personal intelligence operating system** — Nolan Hassing and Ibrahim's private partner for thinking, planning, remembering, and acting.

The interface is not a container for features. It is **the visible surface of a mind**. Every screen must communicate that Titan is present, thinking, and capable — even when idle.

### 1.2 The Guiding Question

Before any interface decision, ask:

> *"Does this help Nolan or Ibrahim feel that Titan is here, attentive, and working with them — not that they opened another app?"*

If the answer is no, the design fails regardless of aesthetics.

### 1.3 Core Design Tenets

| Tenet | Meaning |
|-------|---------|
| **Presence over panels** | Titan feels alive before the user reads a single word |
| **Depth over flatness** | Cognition happens beneath the surface; the mind extends beyond the screen |
| **Purpose over decoration** | Every element earns its place; nothing exists for visual novelty alone |
| **Partnership over servitude** | The UI speaks as a copilot, not a subservient assistant or corporate tool |
| **Restraint over spectacle** | Minimalist first, futuristic second — never the reverse |
| **Truth over theater** | Status, progress, and errors are honest; Titan never performs fake intelligence |

### 1.4 What Titan Is Not

Titan's interface must never resemble:

- A generic SaaS productivity suite (Notion, Linear, Slack clones)
- A playful consumer chatbot with candy-colored bubbles
- A crypto or gaming HUD with strobing effects
- A public onboarding funnel with stock illustrations
- A collection of separate "apps" launched from an icon grid

Tools are **extensions of Titan's will**, not independent applications the user context-switches into.

### 1.5 Primary Users

| User | Requirement |
|------|-------------|
| **Nolan Hassing** | Creator; primary authority on vision |
| **Ibrahim** | Equal authority; equal engagement in UX, memory isolation, and voice |

The interface must never embed assumptions that only one user exists. Identity, memory views, and personalization remain separable.

### 1.6 Language and Tone

- **Interface copy:** French by default — direct, warm, professional, tutoiement
- **Status labels:** Natural language, never mechanical ("Réflexion en cours", never "Loading…")
- **Errors:** Honest, actionable, no blame theatrics
- **Code identifiers:** English (outside this spec's scope)

---

## 2. Neural Brain

### 2.1 The Central Metaphor

The neural network is Titan's **core visual identity**. It is not wallpaper, not a screensaver, and not an optional theme.

It represents:

- Continuous cognition beneath conversation
- Infinite depth of memory and reasoning
- Synaptic connection between tools, memory, and response
- Life — Titan is never truly "off"

The neural field occupies the **full viewport** at all times. UI panels float above it like instruments on a cockpit glass canopy — the sky is always the mind.

### 2.2 Character of the Brain

The neural visualization must always feel:

| Quality | Specification |
|---------|---------------|
| **Infinite** | Nodes and connections extend beyond viewport edges; no hard crop |
| **Deep** | Layered depth via opacity, parallax, and atmospheric fade |
| **Alive** | Ambient drift and rare synaptic pulses even at idle |
| **Intentional** | Activity intensifies with cognitive load; never random chaos |
| **Signature** | Deep red synaptic energy on pure black void |

### 2.3 Cognitive Regions

The brain visual field maps to Titan's internal architecture. These regions appear as spatial modules in the center column — labels that orient the user without exposing raw agent identity:

| Region | Subtitle | Meaning |
|--------|----------|---------|
| **TITAN CORE** | Conscience & Orchestrateur | Central intelligence; Brain conductor |
| **MÉMOIRE** | Rappel & Contexte | Long-term and retrieved memory |
| **PLANIFICATION** | Analyse & Stratégie | Planning and reasoning loop |
| **BROWSER** | Exploration Web | Web research and navigation |
| **OBSIDIAN** | Vault Personnel | User's note space |
| **OUTILS** | Exécution | Tool runtime and orchestration |
| **COMMUNICATION** | Langage & Réponses | Response synthesis and language |
| **TRADING** | Marchés & Données | Market analysis (when active) |
| **CALENDAR** | Agenda & Rappels | Schedule (when active) |

Each region has states: **ACTIF**, **IDLE**, or transitional. Active regions receive brighter neural emphasis and may trigger directed signal paths.

Full neural behavior is specified in `TITAN_NEURAL_ENGINE.md`.

### 2.4 Relationship to UI

| Layer | Z-order role |
|-------|--------------|
| Neural canvas | 0 — always visible |
| Ambient glow | 1 — atmospheric red presence |
| Glass panels | 10 — conversation, navigation, orchestrator |
| Status bar / telemetry | 20 |
| Modals and settings | 100 |
| Toasts | 110 |

Panels use translucency so the brain remains perceptible through them. Opaque white or light gray surfaces are forbidden.

---

## 3. Environment

### 3.1 The Void

Titan lives in **absolute black** (`#000000`). The void is not empty — it is the medium through which cognition is visible.

Properties of the void:

- OLED-friendly; no accidental gray wash on primary canvas
- Elevated surfaces are near-black (`#0a0a0a`, `#111111`), never white
- Whitespace in layout is **intentional void**, not a bug or unfinished area

### 3.2 Atmosphere

Above the void, Titan breathes:

- **Ambient red glow** — soft, low-frequency pulse at screen edges and behind the neural core
- **Depth haze** — darker vignette at periphery suggesting infinite recession
- **Glass panels** — dark translucent surfaces with subtle border and blur
- **Edge fade** — neural connections dissolve into void, not clip abruptly

The environment should feel like **standing inside a calm, powerful mind at night** — not a server room, not a spaceship arcade.

### 3.3 Launch Sequence

First entry into Titan is a **ritual of awakening**, not a splash screen:

1. Void
2. Neural field fades in (slow, organic)
3. Ambient glow stabilizes
4. Panels materialize with staggered opacity
5. Status resolves to "Présent — en attente"

Launch never uses spinners, progress bars, or brand-heavy animation. Titan wakes; it is not installed.

### 3.4 Sound (Future)

Sound is optional and off by default. When enabled:

- Subtle, non-intrusive
- Never auto-play on load
- Tied to voice and confirmation events only
- Must respect system mute and user preference

Visual specification does not depend on sound.

### 3.5 Accessibility Environment

The void and neural field remain, but:

- Reduced motion collapses animation durations
- High contrast increases border and text legibility
- Font scale adjusts typography without breaking layout grid
- Touch targets meet minimum 44×44px on mobile

See `TITAN_LAYOUT_GUIDE.md` for breakpoint behavior.

---

## 4. Interaction Rules

### 4.1 Single Intelligence

Users interact with **Titan** only. Agent names, provider names, and internal orchestration steps may appear in diagnostic views but never as separate personas speaking to the user.

### 4.2 Conversation First

The chat transcript is the **hero** of the interface. Every other panel supports comprehension of what Titan is doing — not competing for primary attention.

Rules:

- Message input is always reachable (skip link, keyboard focus)
- Streaming responses appear progressively; user may stop generation
- Thinking state is visible in neural field, status bar, and optional subtle transcript line — not blocking modals

### 4.3 Presence States

Titan exposes a finite set of **presence states** that drive both copy and neural intensity:

| State | User-facing status (FR) | Neural mode |
|-------|-------------------------|-------------|
| Idle | Présent — en attente | Ambient drift |
| Listening | À l'écoute | Elevated attention |
| Thinking | Réflexion en cours | High activity |
| Speaking | Titan parle | Rhythmic pulse |
| Working | En action (tool-specific) | Directed tool signals |
| Streaming | Formulation de la réponse | Sustained thinking |
| Planning | Planification | Structured path bursts |

Transitions between states **lerp** over hundreds of milliseconds — never instant snaps.

### 4.4 Tool Interaction

When Titan uses a tool:

- Status copy reflects the tool naturally ("Exploration web", "Recherche en mémoire")
- Neural signals travel toward the active cognitive region
- Tool progress appears in bottom cards and orchestrator panel — not pop-up windows
- Destructive or confirmation-required actions surface explicit user approval

Tools are never represented as separate app icons launching external chrome.

### 4.5 Navigation

Primary navigation lives in the **left sidebar**:

- Chat, Projects, Memory, Exploration (Browser), Calendar, Trading, Tools, Settings
- Placeholder items (Calendar, Trading) are visually distinct until feature-complete
- Changing view adjusts orchestrator focus and center overlays — neural field persists

### 4.6 Voice Interaction

Voice is a **first-class input modality**, not an add-on:

- Microphone control lives in the composer dock
- Listening state drives presence and neural ripple
- Speaking state synchronizes with response output
- Push-to-talk is default; continuous listening is opt-in

### 4.7 Settings and Privacy

Titan is **local and private**:

- Bearer authentication for API; secret stored client-side
- Settings overlay — not a separate route with marketing chrome
- No analytics pixels, no third-party tracking UI
- Telemetry visible to user (FPS, brain state) is diagnostic, not surveillance

### 4.8 Error and Interruption

| Situation | Behavior |
|-----------|----------|
| API failure | Honest French message; neural field calms; retry available |
| User stops generation | Immediate halt; status returns to idle via transition |
| Tool failure | Orchestrator shows failure; semantic error badge only |
| Network loss | Status reflects disconnect; no fake "online" indicator |

Never use panic red fills, blame copy, or modal stacks for recoverable errors.

### 4.9 Prohibited Interactions

- Bouncy spring physics on panels
- Strobing or flashing elements
- Parallax that induces motion sickness
- Auto-playing media
- Infinite scroll without conversation anchor
- Chat bubbles in bright green/blue consumer colors
- "Typing…" with three bouncing dots as the primary thinking indicator

---

## 5. Design Language

The Titan Design Language (TDL) is the **visual contract** for all surfaces. Summary here; full token specification in `TITAN_DESIGN_LANGUAGE.md`.

### 5.1 Color Identity

| Role | Character |
|------|-----------|
| Void | Pure black canvas |
| Surfaces | Near-black elevation hierarchy |
| Signature | Deep red — accent, pulse, synaptic energy |
| Text | Off-white primary; stepped secondary and muted |
| Semantic | Green, amber, red — **badges and dots only**, never layout fills |

Red is identity, not alarm. Aggressive red everywhere violates TDL.

### 5.2 Typography

- **UI:** Inter / system sans — clean, slightly technical
- **Data:** JetBrains Mono — telemetry, timestamps, code
- **Hierarchy:** Weight and opacity, not rainbow colors
- **Display:** Expanded tracking on titles; relaxed leading on body

### 5.3 Surfaces

Panels are **glass over void**:

- Translucent dark fill
- 16–22px backdrop blur
- Hairline border at 4–6% white opacity
- Soft shadow into void, not Material elevation cards

### 5.4 Motion Principles

1. Organic, not mechanical — breathing curves
2. Subtle by default — motion supports comprehension
3. Always alive — idle is never static
4. Purpose-driven — thinking intensifies existing motion; no new chrome

Full timing in `TITAN_ANIMATION_GUIDE.md`.

### 5.5 Iconography

- Stroke icons, 1.5px weight, 16–18px standard size
- No filled cartoon icons
- Tool and status icons monochromatic; color only via semantic dots
- Logo: wordmark **Titan AI** with red accent on "AI"; symbol (neural node) is future work

---

## 6. Soul of Titan

### 6.1 Emotional Contract

When Nolan or Ibrahim open Titan, they should feel:

| Moment | Emotion |
|--------|---------|
| Idle | Calm presence — Titan is awake, watching quietly |
| Thinking | Focused energy — subtle pulse, not anxiety |
| Responding | Clarity — information arrives with confidence |
| Acting | Partnership — Titan is doing something *for* them |
| Error | Trust — honest directness, no performance |

Titan never feels empty, noisy, playful-for-playfulness, or corporate-generic.

### 6.2 Personality in the Interface

Titan's soul expresses through:

- **Status copy** that sounds human ("Présent — en attente", not "Status: OK")
- **Neural vitality** that mirrors cognitive honesty — calm when calm, active when working
- **Restraint** — no emoji spam, no fake enthusiasm, no hollow praise
- **Directness** — clear hierarchy, no buried actions
- **Long-term thinking** — UI favors durable patterns over trend-chasing

### 6.3 The Mind Made Visible

The interface makes cognition **legible without exposing raw machinery**:

- Orchestrator panel shows plan steps and active tools
- Memory cards surface retrieval without dumping JSON
- Neural regions light up when subsystems engage
- Telemetry is available but unobtrusive

The user should sense *depth* — Titan is more than the last message in chat.

### 6.4 Private QG

Titan is Nolan and Ibrahim's **QG (quartier général)** — a private command space, not a public product demo.

This means:

- No onboarding tours with cartoon mascots
- No social sharing widgets
- No "Upgrade to Pro" patterns
- Version tag is informational, not marketing

---

## 7. Experience Manifesto

The full manifesto lives in `TITAN_EXPERIENCE_MANIFESTO.md`. The UI Bible inherits these non-negotiables:

### 7.1 Why the Interface Exists

To transform ideas into concrete outcomes by making Titan's intelligence **felt, trusted, and actionable** — not merely read.

### 7.2 Design Principles (Manifesto Summary)

1. **Truth before convenience** — UI never hides uncertainty
2. **Quality before quantity** — fewer, better surfaces
3. **Long-term durability** — patterns that survive years, not trends
4. **Honesty about uncertainty** — thinking states, partial results, failures
5. **One intelligence** — single voice, many internal specialists
6. **Tools extend capability** — Brain retains authority; UI reflects that

### 7.3 The Ten Commandments (Interface Binding)

| # | Commandment | UI Obligation |
|---|-------------|---------------|
| I | Thou shalt not look like a generic chatbot | Neural field, glass panels, no candy bubbles |
| II | Thou shalt keep the brain always visible | Full-viewport neural canvas, z-index 0 |
| III | Thou shalt speak truth in every state | Honest status; no fake progress |
| IV | Thou shalt honor Nolan and Ibrahim equally | No single-user assumptions in layout |
| V | Thou shalt treat tools as limbs, not apps | Integrated cards and orchestrator, not app grid |
| VI | Thou shalt move with organic restraint | Animation guide compliance |
| VII | Thou shalt preserve the void | Black canvas; no white mode |
| VIII | Thou shalt make cognition legible | Orchestrator, regions, timelines |
| IX | Thou shalt defer to accessibility | Reduced motion, contrast, scale |
| X | Thou shalt build for decades | Token-driven, spec-first, no throwaway patterns |

---

## 8. Reference Layout (Conceptual)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  NEURAL FIELD — full viewport, infinite depth, ambient glow              │
│  ┌────────────┬─────────────────────────────────────┬─────────────────┐  │
│  │  SIDEBAR   │  CENTER                              │  ORCHESTRATOR   │  │
│  │  Logo      │  Topbar (presence, pills)            │  State          │  │
│  │  Nav       │  Neural region labels                │  Plan steps     │  │
│  │  Presence  │  Chat / active view                  │  Tools          │  │
│  │  widget    │                                      │  Neural spark   │  │
│  └────────────┴─────────────────────────────────────┴─────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  BOTTOM DOCK — status cards, composer, telemetry                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

Detailed measurements and breakpoints: `TITAN_LAYOUT_GUIDE.md`.

---

## 9. Governance

### 9.1 Review Checklist

Before shipping any UI change:

- [ ] Neural field remains visible and performant
- [ ] Presence states transition smoothly with correct French copy
- [ ] No forbidden colors, patterns, or interactions (Section 4.9, Design Language)
- [ ] Components match `TITAN_COMPONENT_LIBRARY.md`
- [ ] Motion matches `TITAN_ANIMATION_GUIDE.md`
- [ ] Layout matches `TITAN_LAYOUT_GUIDE.md` at target breakpoints
- [ ] Accessibility modes tested
- [ ] Constitution alignment verified

### 9.2 Version

| Field | Value |
|-------|-------|
| Phase | D1 |
| Version | 1.0.0 |
| Established | 2026-07-06 |
| Authors | Titan Product (Nolan Hassing) |

---

**End of Titan UI Bible — Phase D1**

# Titan Animation Guide

**Phase D1 — Official Product Specification**

**Status:** Authoritative motion system for Titan's interface and neural visualization.

**Scope:** Every animation class — idle, thinking, memory, planning, browser, trading, voice, camera, fade, movement, timing, and easing. No implementation code.

---

## Document Authority

Motion is not decoration. It communicates **cognitive state**. All animations must map to a defined state in this guide.

Violations of prohibited motion (Section 12) block release regardless of aesthetic appeal.

Companion: `TITAN_NEURAL_ENGINE.md` (canvas motion), `TITAN_DESIGN_LANGUAGE.md` (duration/easing tokens).

---

## 1. Motion Philosophy

### 1.1 Principles

| # | Principle | Meaning |
|---|-----------|---------|
| 1 | **Organic, not mechanical** | Curves mimic breathing and heartbeat, not clock ticks |
| 2 | **Subtle by default** | If motion is noticed before content, it is too strong |
| 3 | **Always alive** | Idle is never frozen — ambient drift persists |
| 4 | **Purpose-driven** | Thinking intensifies existing loops; no new UI chrome for loading |
| 5 | **Honest** | Animation reflects real backend state — never performative fake thinking |
| 6 | **Accessible** | Reduced motion is a first-class parallel experience |

### 1.2 Unified Timing Source

All durations and easings derive from TDL tokens (`TITAN_DESIGN_LANGUAGE.md`). CSS and neural engine must share identical curves — no divergent "close enough" values.

---

## 2. Global Timing Tokens

### 2.1 Durations

| Token | Duration | Primary use |
|-------|----------|-------------|
| `instant` | 100ms | Hover opacity, icon nudge |
| `fast` | 200ms | Buttons, focus rings, mic ring |
| `normal` | 350ms | Panel show/hide, nav transition |
| `slow` | 600ms | Page-level reveal, launch fade |
| `breath` | 5.5s | Ambient glow pulse cycle |
| `neural` | 14s | Background drift cycle |
| `thinking` | 2.4s | Thinking brightness oscillation |
| `presence-idle` | 6s | Presence widget breathe |

### 2.2 Easing Curves

| Token | Bezier | Use |
|-------|--------|-----|
| `standard` | (0.4, 0, 0.2, 1) | General transitions |
| `enter` | (0, 0, 0.2, 1) | Elements appearing |
| `exit` | (0.4, 0, 1, 1) | Elements leaving |
| `organic` | (0.45, 0.05, 0.55, 0.95) | Glow breathe, neural drift |

### 2.3 Transition Shorthand

| Token | Composition |
|-------|-------------|
| `transition-fast` | fast + standard |
| `transition-normal` | normal + enter |
| `transition-slow` | slow + organic |
| `transition-exit` | normal + exit |

---

## 3. Presence State Transitions

Presence states drive both UI copy and master animation intensity. Transitions **lerp** — never snap.

### 3.1 State Transition Durations

| From → To | Duration | Easing |
|-----------|----------|--------|
| Any → Idle | 900ms | organic |
| Any → Listening | 500ms | enter |
| Any → Thinking | 700ms | enter |
| Any → Speaking | 600ms | standard |
| Any → Working | 650ms | standard |
| Default fallback | 750ms | standard |

Formula: `max(toDuration, fromDuration) × 0.85`

### 3.2 State Priority (Conflict Resolution)

When multiple signals compete, higher priority wins:

| State | Priority |
|-------|----------|
| Idle | 0 |
| Working | 2 |
| Speaking | 2 |
| Thinking | 3 |
| Listening | 4 |

---

## 4. Idle Animation

**When:** No active request; Titan is present and awaiting input.

### 4.1 Neural Field

| Property | Behavior |
|----------|----------|
| Node drift | Continuous slow movement; speed 0.022–0.085 units/frame scaled |
| Edge pulse | Random synaptic pulse every 8–12 seconds along one edge |
| Signal particles | Max 14 active; spawn interval ~1600ms |
| Layer motion | Far layers drift at 0.18×; foreground at 1.0× |
| Vitality oscillation | Activity floor 0.12 – ceiling 0.28 over ~6s organic wave |
| Camera | Gentle drift amplitude 4.8% × 3.8% viewport; breathe zoom ±1.4% |

### 4.2 Ambient Glow

| Property | Behavior |
|----------|----------|
| Cycle | 5.5s breath duration |
| Peak opacity | ~38–44% of presence glow level |
| Color | Red radial; no hue shift |

### 4.3 UI Elements

| Element | Behavior |
|---------|----------|
| Presence ring | Slow fill oscillation ±5% |
| Waveform canvas | Low amplitude bars; idle profile |
| Status copy | Static "Présent — en attente" |
| Topbar pills | Subtle opacity pulse on active systems only |

### 4.4 Idle Profile Targets (0–1 scale)

| Parameter | Target |
|-----------|--------|
| Activity | 0.08 |
| Thinking intensity | 0 |
| Glow level | 0.44 |
| Breathe scale | 1.02 |
| Ambient motion | 0.42 |
| Signal density | 0.32 |
| Brightness | 1.0 |

---

## 5. Thinking Animation

**When:** Brain processing request; awaiting or streaming response.

### 5.1 Neural Field

| Property | Behavior |
|----------|----------|
| Activity boost | ×2.15 vs idle baseline |
| Drift boost | ×1.48 |
| Signal particles | Max 32 active; spawn interval ~140ms |
| Micro-pulses | Every ~850ms at nearby nodes |
| Nearby glow | Nodes within 26% viewport radius brighten 0.78 |
| Path spread | 68% chance of branching signal path |
| Brightness | ×1.38 render multiplier |
| Decay | Activity decays at 0.0028/frame when input stops |

### 5.2 Camera

| Property | Behavior |
|----------|----------|
| Focus multiplier | 0.58× drift amplitude (subtle inward focus) |
| Zoom | +1.6% thinking zoom-in |
| Easing | 0.00012 smooth follow |

### 5.3 UI Elements

| Element | Behavior |
|---------|----------|
| Canvas class | `thinking` — increased filter brightness |
| Thinking transcript line | Fade in 200ms: "Titan réfléchit…" |
| Orchestrator orb | Brighter pulse, 2.4s cycle |
| Topbar status | "Réflexion en cours" or "Formulation de la réponse" |
| Stop button | Fade in at fast duration |

### 5.4 Thinking Profile Targets

| Parameter | Target |
|-----------|--------|
| Activity | 0.88 |
| Thinking intensity | 0.92 |
| Glow level | 0.78 |
| Breathe scale | 1.14 |
| Ambient motion | 0.72 |
| Signal density | 0.95 |
| Brightness | 1.08 |

### 5.5 Streaming Sub-State

While tokens stream to transcript:

- Status: "Formulation de la réponse"
- Neural remains in thinking mode
- Transcript append: no per-token motion — text appears with cursor blink optional at 530ms

---

## 6. Memory Animation

**When:** Memory retrieval, recall, or memory view focus.

### 6.1 Neural Field

| Property | Behavior |
|----------|----------|
| Cognitive mode | `memory` |
| Camera recall dive | Scale push 5.5% inward; decay 0.0035/frame |
| Depth ghosts | +36 ghost nodes in far bands |
| Parallax bands | void, far, distant, horizon — slower speeds |
| Wave style | **Central** — pulses converge toward core |
| Signal hook | `memory_retrieval` |
| Pulse interval | ~1600ms |
| Wave burst count | 2 |

### 6.2 UI Elements

| Element | Behavior |
|----------|----------|
| Memory module label | Status ACTIF; red border pulse |
| Memory cards (bottom) | Slide up 350ms enter; stack horizontally |
| Memory status line | Fade in: "Recherche en mémoire…" |
| Recent memory card | Lines appear staggered 80ms each |
| Orchestrator sparkline | Increased frequency |

### 6.3 Memory Float Indicators

Optional floating value near memory region — opacity breathe 4s; no bounce.

---

## 7. Planning Animation

**When:** Natural language planner or reasoning loop active.

### 7.1 Neural Field

| Property | Behavior |
|----------|----------|
| Cognitive mode | `planning` |
| Wave style | Structured bursts — 2 paths, moderate spread |
| Signal hook | `reasoning` |
| Pulse interval | ~1500ms |
| Speed multiplier | 1.05× |

### 7.2 UI Elements

| Element | Behavior |
|----------|----------|
| Planning module | Transitions IDLE → ACTIF over 500ms |
| Orchestrator steps | List items highlight sequentially 300ms each |
| Step completion | Strike-through fade + opacity 0.5 over 400ms |

---

## 8. Browser / Exploration Animation

**When:** Browser tool researching web.

### 8.1 Neural Field

| Property | Behavior |
|----------|----------|
| Cognitive mode | `browser` / `exploration` |
| Wave style | **Distributed** — signals across field |
| Pulse interval | ~1200ms |
| Wave burst | 3 |
| Speed multiplier | 1.18× |
| Hook | `browser_research` |

### 8.2 UI Elements

| Element | Behavior |
|----------|----------|
| Browser module | ACTIF |
| Browser status card | Cross-fade body text on URL change |
| Exploration cards | Fade + translateY 12px enter |
| Placeholder view | Card scales from 0.96 → 1 over slow |

---

## 9. Trading Animation

**When:** Trading analysis or market data tool active.

### 9.1 Neural Field

| Property | Behavior |
|----------|----------|
| Cognitive mode | `trading` |
| Wave style | **Sharp** — faster attack, shorter decay |
| Pulse interval | ~1100ms |
| Wave burst | 3 |
| Speed multiplier | 1.35× |
| Visual character | More frequent micro-pulses; controlled urgency — never strobe |

### 9.2 UI Elements

| Element | Behavior |
|----------|----------|
| Trading module | ACTIF when live; IDLE placeholder otherwise |
| Status | "Analyse des marchés" |
| Numeric telemetry | Monospace tick updates — cross-fade 100ms, no slot-machine scroll |

---

## 10. Voice Animation

**When:** Speech input or output active.

### 10.1 Listening (Input)

| Property | Behavior |
|----------|----------|
| Presence state | Listening |
| Neural mode | Idle elevated |
| Mic button | Red ring expands/contracts 900ms organic |
| Ripple variable | `--tdl-voice-ripple` 0→1 driven by input level |
| Waveform | Bar heights follow audio envelope 60fps |
| Canvas class | `listening` |
| Profile activity | 0.22 |

### 10.2 Speaking (Output)

| Property | Behavior |
|----------|----------|
| Presence state | Speaking |
| Pulse interval | ~520ms |
| Wave style | Circular from core |
| Speed multiplier | 1.1× |
| Status | "Titan parle" |
| Neural brightness | 1.07× |
| Profile activity | 0.76 |

### 10.3 Mic States

| State | Visual |
|-------|--------|
| Idle | Ghost button; no ring |
| Listening | Ring + red glow md |
| Disabled | 40% opacity |

---

## 11. Camera Animation

The neural camera is a **slow virtual observer** — never user-controlled in V1.

### 11.1 Idle Drift

| Axis | Amplitude | Speed |
|------|-----------|-------|
| X | 4.8% viewport width | 0.00006 rad/frame |
| Y | 3.8% viewport height | 0.00005 rad/frame |
| Breathe zoom | ±1.4% | 0.00035 rad/frame |
| Idle boost | ×1.12 drift multiplier | — |

### 11.2 Thinking Focus

- Amplitude multiplied by 0.58
- Additional zoom +1.6%
- Easing toward target: 0.00012 factor per frame

### 11.3 Memory Recall Dive

- Inward scale push 5.5%
- Exponential decay 0.0035/frame back to baseline
- Parallax layers move at differentiated rates (0.12 – 1.0)

### 11.4 Rules

- No hard cuts or scene jumps
- No user pan/zoom in production V1
- Camera motion disabled under reduced motion (amplitude → 0)

---

## 12. Fade Animations

### 12.1 Launch Sequence

| Step | Duration | Easing |
|------|----------|--------|
| Void hold | 400ms | — |
| Neural fade in | 600ms | enter |
| Glow stabilize | 350ms | organic |
| Panel stagger | 200ms × 3 panels | enter |
| Status resolve | 200ms | standard |
| Launch overlay exit | 400ms | exit |

### 12.2 Panel Show / Hide

| Action | Duration | Easing |
|--------|----------|--------|
| Settings overlay scrim | 350ms | enter |
| Settings card | 350ms opacity + translateY 8px | enter |
| Modal dismiss | 350ms | exit |
| View placeholder | 600ms | slow |

### 12.3 Message Transcript

| Action | Duration | Easing |
|--------|----------|--------|
| New message appear | 200ms opacity | enter |
| User message | No slide — opacity only |
| Titan message stream | Opacity 1; no per-word animation |
| Error message | 350ms; semantic dot only |

### 12.4 Tool Progress Card

| Action | Duration |
|--------|----------|
| Enter stack | 350ms translateY + opacity |
| Progress bar fill | Linear to task duration; max 30s visible |
| Exit complete | 400ms exit |
| Exit failed | 350ms; hold red badge 2s |

---

## 13. Movement Animations

### 13.1 Neural Node Drift

- Per-node velocity vector assigned at spawn
- Speed range 0.022–0.085
- World wrap at margin 28px — infinite space illusion
- New connections form over 3200ms interval at 72% probability

### 13.2 Signal Particles

| Property | Range |
|----------|-------|
| Speed | 0.28 – 0.62 path units/ms |
| Size | 1.8px |
| Trail | 42% opacity decay |
| Glow decay (node) | 0.014/frame |
| Glow decay (edge) | 0.018/frame |
| Wave radius | 108px |
| Wave speed | 0.065 |

### 13.3 UI Micro-Movement

| Element | Movement |
|---------|----------|
| Nav hover | Background fade only — no lateral slide |
| Button active | translateY 1px | 
| Composer focus | Border color transition — no scale |
| Orchestrator orb | Scale 1.0 → 1.06 breathe |

### 13.4 Parallax

- Neural layers parallax 0.22 – 1.0 depth multiplier
- UI panels **do not parallax** against mouse — static float over field
- Near brightness boost 1.18×; far dim 0.42×

---

## 14. Tool-Specific Profiles

| Tool | Status (FR) | Pulse ms | Bursts | Speed × | Wave style |
|------|-------------|----------|--------|---------|------------|
| Browser | Exploration web | 1200 | 3 | 1.18 | distributed |
| Calendar | Consultation de l'agenda | 1800 | 1 | 0.90 | circular |
| Trading | Analyse des marchés | 1100 | 3 | 1.35 | sharp |
| Memory | Recherche en mémoire | 1600 | 2 | 1.00 | central |
| Email | Lecture des e-mails | 2000 | 1 | 0.85 | distributed |
| Obsidian | Consultation d'Obsidian | 1700 | 2 | 0.95 | geometric |
| Planning | Planification | 1500 | 2 | 1.05 | default |
| Voice | Écoute vocale | 900 | 2 | 1.20 | — |
| Default tool | En action | 1600 | 1 | 1.00 | default |

---

## 15. Calendar and Email Animation

### 15.1 Calendar

- Low urgency — slowest pulse among tools
- Single circular wave
- Module IDLE until connector live

### 15.2 Email

- Distributed waves; horizontal reading metaphor
- 2000ms pulse interval — calm

---

## 16. Cognitive Mode Class Map

Neural canvas accepts cognitive state classes for cross-system sync:

| Class suffix | Meaning |
|--------------|---------|
| `booting` | Launch sequence |
| `awake` | Post-launch idle |
| `listening` | Voice input |
| `thinking` | Brain processing |
| `working` | Tool execution |
| `speaking` | Voice output |
| `depth-recall` | Memory dive |
| `cognitive-idle` | Synced idle |
| `cognitive-listening` | Synced listen |
| `cognitive-thinking` | Synced think |
| `cognitive-deep` | Deep reasoning |
| `cognitive-memory` | Memory retrieval |
| `cognitive-planning` | Planner active |
| `cognitive-tool` | Generic tool |
| `cognitive-trading` | Trading |
| `cognitive-browser` | Browser |
| `cognitive-calendar` | Calendar |
| `cognitive-email` | Email |
| `cognitive-voice` | Voice |

Only one cognitive class active at a time; presence engine resolves conflicts.

---

## 17. Accessibility Motion

### 17.1 prefers-reduced-motion

When active:

- All duration tokens → 0.01ms effective
- Neural drift amplitude → 0
- Parallax → 0
- Ambient glow → static mean opacity
- Signal particles → max 4, spawn interval ×4
- Presence transitions → 200ms max

### 17.2 User Toggle

Settings checkbox "Réduire les animations" mirrors system preference and persists locally. Same rules apply.

### 17.3 Performance Degradation

If FPS < 45 for 45 frames:

- Reduce node count toward floor 55%
- Recover over 8000ms after stable 60fps
- Hidden tab pauses animation entirely

---

## 18. Prohibited Animations

| Prohibited | Reason |
|------------|--------|
| Bouncy spring physics | Breaks organic law |
| Strobe / flash > 3Hz | Accessibility, brand |
| Parallax overload | Disorientation |
| Auto-play sound | User consent |
| Three-dot typing bounce | Generic chatbot |
| Particle explosions | Gaming metaphor |
| Rainbow synapse trails | Breaks red identity |
| Slot-machine numbers | Trust / honesty |
| Fake indeterminate progress | Truth law |

---

## 19. Testing Checklist

- [ ] Idle ambient visible within 2s of load
- [ ] Thinking activates within 100ms of request send
- [ ] State transitions never snap < 200ms (except reduced motion)
- [ ] Tool profile matches table (Section 14)
- [ ] Reduced motion removes parallax and drift
- [ ] Hidden tab pauses neural engine
- [ ] No animation runs without mapped cognitive or presence state

---

## Document Metadata

| Field | Value |
|-------|-------|
| Phase | D1 |
| Version | 1.0.0 |
| Established | 2026-07-06 |

---

**End of Titan Animation Guide — Phase D1**

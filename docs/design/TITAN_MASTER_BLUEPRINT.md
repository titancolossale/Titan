# Titan Master Blueprint

**Phase D2 — Official Screen Architecture**

**Status:** Authoritative specification for every major screen in Titan.

**Scope:** Screen purpose, panel hierarchy, cognitive behavior, animation, presence, states, and responsive layout across all viewports. This document defines **what each screen is** — not how it is built.

**This is not implementation.** No CSS, HTML, JavaScript, React, or code of any kind appears in this document.

---

## Document Authority

| Rule | Description |
|------|-------------|
| **Mandatory** | All future frontend work must conform to this blueprint and its D1 companion specs. |
| **Hierarchy** | Constitution → Experience Manifesto → UI Bible → **Master Blueprint** → Layout Guide, Animation Guide, Component Library, Neural Engine, Design Language. |
| **Change control** | Screen additions or structural changes require explicit product approval and a version note. |

### Companion Documents

| Document | Role |
|----------|------|
| `TITAN_UI_BIBLE.md` | Philosophy, interaction law, presence states |
| `TITAN_LAYOUT_GUIDE.md` | Spatial system, breakpoints, z-index |
| `TITAN_NEURAL_ENGINE.md` | Neural field behavior and cognitive hooks |
| `TITAN_ANIMATION_GUIDE.md` | Motion timing and state transitions |
| `TITAN_COMPONENT_LIBRARY.md` | Component anatomy referenced by panels |
| `TITAN_DESIGN_LANGUAGE.md` | Visual tokens |

---

## Global Architecture

Every screen shares a **persistent shell**. The neural field never unmounts. Navigation changes what floats above the mind — not the mind itself.

### Universal Shell Layers

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 0 — NEURAL STAGE (full viewport, always visible)                  │
│  LAYER 1 — AMBIENT GLOW (edge pulse)                                     │
│  LAYER 2 — WORKSPACE (sidebar · center · orchestrator · bottom dock)     │
│  LAYER 3 — STATUS EMPHASIS (telemetry elevation)                         │
│  LAYER 4 — OVERLAYS (settings, confirmations, voice immersive)           │
│  LAYER 5 — TOASTS (future notifications)                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

### Universal Regions

| Region | Role | Persists across screens |
|--------|------|-------------------------|
| **Sidebar** | Primary navigation, logo, presence summary | Yes |
| **Neural Stage** | Full-viewport cognitive visualization | Yes |
| **Center Column** | Active screen content | Content swaps |
| **Orchestrator** | Cognitive transparency panel (right) | Yes; sections refocus per screen |
| **Bottom Dock** | Status cards, tool lines, composer, telemetry | Yes; content adapts per screen |

### Universal Presence States

All screens subscribe to the same presence engine. Copy is French; neural intensity follows state.

| State | User-facing copy | Applies when |
|-------|------------------|--------------|
| Idle | Présent — en attente | No active work |
| Listening | À l'écoute | Voice input active |
| Thinking | Réflexion en cours | Brain processing |
| Streaming | Formulation de la réponse | Tokens arriving |
| Speaking | Titan parle | TTS output active |
| Working | En action | Tool executing |
| Planning | Planification | Planner / reasoning loop active |
| Error | Problème détecté | Recoverable failure |

### Universal Transition Law

| Transition type | Duration | Easing |
|-----------------|----------|--------|
| Screen switch (center content) | 350ms | enter / exit |
| Orchestrator section refocus | 300ms | standard |
| Neural cognitive mode change | 650–900ms | organic lerp |
| Presence state change | 500–900ms | per Animation Guide §3 |
| Panel stagger on load | 200ms × region | enter |

Screen switches **cross-fade** center content. Sidebar, neural field, and orchestrator frame remain stable. No hard cuts, no slide-from-offscreen page transitions.

### Universal State Patterns

| State | Rule (all screens) |
|-------|-------------------|
| **Empty** | Honest French copy; no lorem ipsum; neural idle profile |
| **Loading** | Presence + neural activity; no skeleton screens |
| **Error** | Inline semantic badge; calm copy; retry when applicable; neural calms |
| **Reduced motion** | Static layout; neural drift disabled; transitions instant or 100ms |

### Responsive Modes (Reference)

| Viewport | Mode | Shell behavior |
|----------|------|----------------|
| Desktop ≥1280px | Reference three-column | Sidebar 218px · Orchestrator 318px · Full dock |
| Laptop 1024–1279px | Compact three-column | Truncated orchestrator text; smaller cards |
| Tablet 768–1023px | Rail + drawer | Sidebar icon rail; orchestrator slide-over |
| Phone <768px | Single column + sheets | Composer sticky; cards collapsed to chip |

Detailed measurements: `TITAN_LAYOUT_GUIDE.md`.

---

## Screen Index

| # | Screen | Nav key | Primary purpose |
|---|--------|---------|-----------------|
| 1 | Home / Chat | `chat` | Primary conversation and command surface |
| 2 | Projects | `projects` | Mission and project execution dashboard |
| 3 | Memory | `memory` | Durable knowledge inspection and recall |
| 4 | Obsidian | `obsidian` | User vault read/write and knowledge graph |
| 5 | Exploration | `browser` | Web research, sources, and synthesis |
| 6 | Trading | `trading` | Market analysis, positions, and execution oversight |
| 7 | Calendar | `calendar` | Schedule, focus, and temporal planning |
| 8 | Voice | `voice` | Immersive voice conversation mode |
| 9 | Settings | `settings` | Configuration, accounts, and developer tools |

---

# 1. HOME / CHAT

## Purpose

The default command surface of Titan. Nolan and Ibrahim speak to **one intelligence** here. Every other screen supports comprehension of what happens when a message is sent — but Home / Chat is where intent enters the system.

Home / Chat must answer: *"What do I want Titan to do right now?"* and *"What is Titan doing about it?"*

---

## Panel Inventory

### Primary Panels

| Panel | Location | Why it exists |
|-------|----------|---------------|
| **Sidebar** | Left fixed | Navigation authority; persistent orientation; presence at a glance |
| **Neural Space** | Full viewport (Layer 0) | Titan's living identity; cognition made visible beneath all UI |
| **Conversation** | Center column | Hero transcript — the partnership dialogue |
| **Composer** | Bottom dock | Always-reachable input; voice and text command entry |
| **Cognitive Orchestrator** | Right fixed | Legible depth — plan, tools, state without exposing raw agents |

### Secondary Panels

| Panel | Location | Why it exists |
|-------|----------|---------------|
| **Topbar** | Center column top | Session presence, subsystem pills, brain access |
| **Neural Module Labels** | Center overlay | Spatial map of active cognitive regions |
| **Status Cards** | Bottom dock row | At-a-glance subsystem summaries during conversation |
| **Tool Activity Line** | Above composer | Natural-language description of active tool |
| **Memory Status Line** | Above composer | Recall activity during retrieval |
| **Tool Progress Cards** | Float above dock | Ephemeral multi-tool progress (max 3 stacked) |
| **Memory Cards Layer** | Float above center | Ephemeral retrieval visualization |
| **Bottom Telemetry** | Dock footer | Diagnostic transparency — FPS, brain state, clock |
| **Thinking Indicator** | In transcript | Honest "Titan réfléchit…" line — not bouncing dots |

---

## Panel Hierarchy

```
Workspace
├── Sidebar [PRIMARY — navigation authority]
│   ├── Logo + version
│   ├── Nav items (Chat active)
│   └── Presence block (waveform + mini core)
├── Main Column
│   ├── Topbar [SECONDARY — session summary]
│   ├── Neural Module Labels [SECONDARY — decorative orientation]
│   └── Chat Panel [PRIMARY — conversation hero]
│       └── Conversation scroll (messages + thinking indicator)
├── Orchestrator [PRIMARY — cognitive transparency]
│   ├── State orb + badge
│   ├── Plan steps
│   ├── Active tools + timeline
│   └── Neural sparkline
└── Bottom Dock
    ├── Status Cards Row [SECONDARY — subsystem glance]
    ├── Tool / Memory Status Lines [SECONDARY — ephemeral]
    ├── Composer [PRIMARY — command input]
    └── Telemetry [TERTIARY — diagnostic]
```

**Visual weight:** Conversation > Orchestrator = Sidebar > Status cards > Telemetry.

---

## Panel Specifications

### 1.1 Sidebar

| Aspect | Specification |
|--------|---------------|
| **Why** | Single navigation authority; user never hunts for "where am I" |
| **When visible** | Always on desktop/laptop; icon rail on tablet; bottom sheet on phone |
| **Contents** | Logo, nav list, presence block at bottom |
| **Active item** | Chat highlighted with red accent |
| **Animation** | Nav hover: 100ms opacity; active switch: 350ms border fade |
| **Neural** | None directly — glass panel floats above field |

### 1.2 Neural Space

| Aspect | Specification |
|--------|---------------|
| **Why** | Core product identity; user feels Titan is alive before reading text |
| **When visible** | Always — full viewport, z-index 0 |
| **Contents** | Infinite node field, connections, signals, depth layers, central core |
| **Animation** | Idle drift; intensifies on thinking, tools, memory hooks |
| **Neural** | Master state machine: BOOTING → AWAKE → IDLE ↔ THINKING ↔ WORKING |
| **Pointer events** | None — passes through to UI |

### 1.3 Neural Module Labels

| Aspect | Specification |
|--------|---------------|
| **Why** | Orient user to which cognitive region is engaged without exposing agent names |
| **When visible** | Desktop/laptop default; tablet shows active chip only; phone hidden |
| **Modules shown** | CORE, MÉMOIRE, PLANIFICATION, BROWSER, OBSIDIAN, OUTILS, COMMUNICATION, TRADING, CALENDAR |
| **States** | ACTIF (red border, pulse) / IDLE (muted, 50% opacity) |
| **Animation** | IDLE → ACTIF: 500ms border + opacity; active pulse 2.4s organic |
| **Neural** | Label ACTIF syncs with cognitive sub-state tag on canvas |

### 1.4 Topbar

| Aspect | Specification |
|--------|---------------|
| **Why** | One-line session truth above conversation |
| **When visible** | All viewports; compact on phone |
| **Contents** | Subsystem pills (Memory, Tools, Reflection) · centered presence copy · actions (info, Cerveau) |
| **Animation** | Status copy cross-fade 200ms on state change; pills pulse only when subsystem active |
| **Neural** | Reflection pill red dot intensifies during THINKING |

### 1.5 Conversation

| Aspect | Specification |
|--------|---------------|
| **Why** | Hero surface — the dialogue IS the product |
| **When visible** | Always in center column on Home / Chat |
| **Contents** | Message list (user + Titan + system + error variants); thinking indicator |
| **Max width** | 720px desktop; 840px ultrawide; centered in column |
| **Animation** | New message: fade + translateY 8px, 350ms enter; auto-scroll unless user scrolled up |
| **Streaming** | Text appends in place; optional cursor blink 530ms |
| **Neural** | THINKING state drives field intensity behind glass |

### 1.6 Cognitive Orchestrator

| Aspect | Specification |
|--------|---------------|
| **Why** | Makes cognition legible — plan, tools, state — without committee of agents |
| **When visible** | Desktop/laptop always; tablet drawer; phone sheet |
| **Sections (Chat focus)** | State · Plan steps · Tools + timeline · Neural sparkline |
| **Animation** | Step highlight sequential 300ms; orb breathe 2.4s during thinking |
| **Neural** | Sparkline reflects activity level last N seconds |

### 1.7 Status Cards

| Aspect | Specification |
|--------|---------------|
| **Why** | Peripheral awareness of subsystems without leaving conversation |
| **When visible** | Desktop/laptop full row (5 cards); tablet horizontal scroll; phone single combined chip |
| **Cards** | Mémoire Récente · Obsidian · Browser · État Cognitif · Présence |
| **Animation** | Body text cross-fade 200ms on update; presence ring arc lerps activity 0–100% |
| **Neural** | Présence card ring driven by presence engine activity target |

### 1.8 Tool Activity

| Aspect | Specification |
|--------|---------------|
| **Why** | Natural-language legibility of tool execution |
| **When visible** | When tool active — tool status line above composer; progress cards for long ops |
| **Contents** | French copy ("Exploration web…", "Consultation d'Obsidian…") |
| **Animation** | Line fade in 200ms; progress cards enter from bottom 350ms; max 3 stack; oldest dismiss first |
| **Neural** | Tool profile wave style per Animation Guide § tool table |

### 1.9 Composer

| Aspect | Specification |
|--------|---------------|
| **Why** | Perpetual command entry — text and voice |
| **When visible** | Always reachable; sticky on phone with safe-area inset |
| **Contents** | Mic button · textarea · attach · stop (hidden default) · send |
| **Animation** | Stop button fades in 200ms during thinking/streaming; mic ring when listening |
| **Neural** | Listening elevates neural attention; speaking triggers circular pulses |

### 1.10 Bottom Telemetry

| Aspect | Specification |
|--------|---------------|
| **Why** | Diagnostic transparency — not surveillance |
| **When visible** | Desktop/laptop always; tablet optional; phone hidden (available in Settings → Developer) |
| **Contents** | FPS · Brain state · Memory count · Tools active · Reflection · local clock |
| **Animation** | Numeric cross-fade 100ms; no slot-machine scroll |
| **Neural** | Brain state label mirrors master neural state enum |

---

## Animation Behavior (Home / Chat)

| Event | Behavior |
|-------|----------|
| Cold load | Launch sequence: void → neural fade → panel stagger → "Présent — en attente" |
| Message send | Presence → Thinking 700ms; neural activity ×2.15; thinking line fade in |
| Tool start | Presence → Working 650ms; directed tool waves; tool line fade in |
| Memory retrieval | Cognitive-memory mode; recall dive; memory cards stagger 80ms |
| Response complete | Thinking decay 0.0028/frame; presence → Idle 900ms |
| User stop | Immediate halt; fast transition to Idle |

---

## Neural Behavior (Home / Chat)

| Condition | Master state | Cognitive tag | Wave style |
|-----------|--------------|---------------|------------|
| Waiting for input | IDLE | idle | Ambient drift |
| Processing message | THINKING | thinking | Default radial |
| Tool executing | WORKING | tool / browser / etc. | Per tool profile |
| Memory recall | THINKING or WORKING | memory | Central convergence |
| Voice input | LISTENING | voice | Listening ripple |
| TTS output | SPEAKING | voice | Circular from core |

Active module labels sync with cognitive tag. Signals travel toward active region.

---

## Presence State (Home / Chat)

Default screen presence follows global states. Topbar center copy is authoritative user-facing status. Orchestrator badge mirrors same enum.

Priority when concurrent: Listening > Thinking > Speaking / Working > Idle.

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Launch overlay | Home / Chat | Overlay exit 400ms; panels already visible beneath |
| Other screen → Chat | Chat | Center cross-fade 350ms; orchestrator sections refocus to State/Plan/Tools |
| Chat → Other screen | Any | Conversation persists in memory; center swaps; composer may hide or adapt per target screen |

---

## Empty State

| Condition | Display |
|-----------|---------|
| No messages in session | Transcript area shows welcome block: "Titan est présent. Que veux-tu accomplir ?" — sm secondary, centered |
| No active plan | Orchestrator steps: "En attente de demande…" |
| No active tools | Orchestrator tools: "Aucun outil actif" |
| Status cards | Each card shows subsystem idle copy (e.g., "Aucune note récente") |

Neural field remains in idle profile — never static frozen.

---

## Loading State

| Condition | Display |
|-----------|---------|
| Initial session connect | Launch overlay copy sequence; no spinner |
| Awaiting first Brain response | Presence Thinking; neural intensifies; "Titan réfléchit…" in transcript |
| Status poll pending | Previous values hold; no skeleton placeholders |

---

## Error State

| Condition | Display |
|-----------|---------|
| API / Brain failure | Error message variant in transcript; semantic error badge; topbar "Problème détecté"; neural calms |
| Tool failure | Orchestrator step marked failed; tool line shows failure copy; retry if applicable |
| Auth missing | Settings prompt inline in composer area — not blocking modal stack |

Never panic red fills. Never blame user.

---

## Responsive Behavior

### Desktop (≥1280px)

Reference layout. All panels visible. Chat max-width 720px. Five status cards. Full telemetry. All module labels.

### Laptop (1024–1279px)

Orchestrator 280px min. Chat max-width 680px. Module labels reduced to core + active. Status card body text sm.

### Tablet (768–1023px)

Sidebar → 56px icon rail. Orchestrator → slide-over drawer via "Cerveau". Status cards horizontal scroll snap. Module labels hidden; active chip in topbar. Touch targets 44×44px min.

### Phone (<768px)

Single column. Composer sticky above safe area. Topbar mini one-line presence. Status cards → single combined chip. Orchestrator, telemetry, module labels → sheets only. Neural node count −30%. Display title xl not display token.

---

# 2. PROJECTS

## Purpose

Mission and project execution dashboard. Surfaces active goals, task progression, Brain involvement, and plans derived from the mission manager and project context. Answers: *"What am I building, where am I in it, and what is Titan doing about it?"*

Projects is not a generic Kanban clone — it reflects Titan's **mission-aware** cognition.

---

## Primary Panels

| Panel | Role |
|-------|------|
| **Project Dashboard** | Center column hero — active project overview |
| **Project Cards Grid** | Scannable project inventory |
| **Task Progression** | Current mission step and completion state |
| **Active Plans** | Planner output tied to active project |
| **Orchestrator (Projects focus)** | Brain involvement — agents, steps, tool chain for project work |

## Secondary Panels

| Panel | Role |
|-------|------|
| **Sidebar** | Nav with Projects active |
| **Topbar** | Project name pill + presence |
| **Neural Space** | Planning region emphasis when Brain engaged |
| **Status Cards** | Cognitive + Memory cards prioritized |
| **Composer** | Quick command scoped to active project |
| **Telemetry** | Standard diagnostic strip |

---

## Panel Hierarchy

```
Workspace
├── Sidebar [PRIMARY]
├── Main Column
│   ├── Topbar [SECONDARY — project context pill]
│   └── Projects View [PRIMARY]
│       ├── Active Project Header (title, phase, progress)
│       ├── Task Progression (mission steps)
│       ├── Active Plans (planner steps)
│       └── Project Cards Grid (secondary projects)
├── Orchestrator [PRIMARY — Brain involvement]
│   ├── State
│   ├── Mission / plan steps
│   ├── Agent activity summary (no agent personas)
│   └── Tool timeline
└── Bottom Dock
    ├── Status Cards (Cognitive, Memory prioritized)
    ├── Composer
    └── Telemetry
```

---

## Animation Behavior

| Event | Behavior |
|-------|----------|
| Enter Projects view | Center fade 350ms; PLANIFICATION module → ACTIF 500ms |
| Step completion | Strike-through fade 400ms; progress bar fill 600ms organic |
| Plan update | New steps append with 300ms sequential highlight |
| Project card select | Card border accent 200ms; dashboard cross-fade content 350ms |
| Brain starts project task | Planning animation profile; orchestrator orb intensifies |

---

## Neural Behavior

| Condition | Cognitive tag | Behavior |
|-----------|---------------|----------|
| Browsing projects idle | idle | Standard ambient |
| Brain analyzing project | planning | Structured path bursts; PLANIFICATION ACTIF |
| Tool execution for project | tool | Directed waves toward OUTILS region |
| Mission step evaluation | thinking | Moderate thinking profile |

---

## Presence State

| Context | Copy |
|---------|------|
| Idle on Projects | Présent — en attente |
| Brain working on mission | Planification or En action |
| Step completing | Brief "Étape validée" flash in topbar |

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Chat → Projects | Projects | Center swap 350ms; orchestrator adds Mission section focus |
| Projects → Chat | Chat | Project context pill persists in topbar until cleared |

---

## Empty State

| Condition | Display |
|-----------|---------|
| No active project | Dashboard: "Aucun projet actif. Décris un objectif à Titan pour commencer une mission." |
| No secondary projects | Grid hidden; single CTA block |
| No active plan | "Aucun plan en cours — envoie une instruction depuis le composer." |

---

## Loading State

| Condition | Display |
|-----------|---------|
| Mission data loading | Previous state holds; presence Idle; no skeleton |
| Plan generation in flight | Planning presence; orchestrator shows pending steps appearing sequentially |

---

## Error State

| Condition | Display |
|-----------|---------|
| Mission load failure | Inline error in dashboard header; retry action |
| Plan failure | Failed step in orchestrator; honest French explanation |

---

## Responsive Behavior

### Desktop

Full dashboard + grid side-by-side or stacked based on content width. Orchestrator shows full Brain involvement sections.

### Laptop

Project cards 2-column grid. Plan steps truncate with expand.

### Tablet

Dashboard full width. Cards single column. Orchestrator drawer. Composer retained.

### Phone

Dashboard header + current step only. Project cards → horizontal snap carousel. Grid and plans in sheet. Composer sticky.

---

# 3. MEMORY

## Purpose

Inspection and exploration of Titan's durable knowledge — conversation memory, long-term memory, retrieval history. Makes memory **legible and honest** without dumping raw JSON. Answers: *"What does Titan remember, and why?"*

User isolation (Nolan ≠ Ibrahim) is enforced in all memory views.

---

## Primary Panels

| Panel | Role |
|-------|------|
| **Memory View** | Center column hero — browse, search, filter |
| **Memory Timeline** | Chronological retrieval and write events |
| **Memory Cards** | Category-grouped note excerpts |
| **Long-term Memory Browser** | Structured browse of `users.{username}.notes` |
| **Conversation Memory** | Session-linked recall distinct from permanent notes |
| **Orchestrator (Memory focus)** | Memory activity, retrieval chain, decider rationale summary |

## Secondary Panels

| Panel | Role |
|-------|------|
| **Search Bar** | Full-width filter above memory content |
| **Filter Chips** | Category: goals, preferences, projects, notes |
| **Memory Visualization** | Neural-adjacent float layer during active recall |
| **Sidebar** | Nav with Memory active |
| **Status Cards** | Mémoire Récente card expanded emphasis |
| **Composer** | "Souviens-toi de…" / "Oublie…" commands |

---

## Panel Hierarchy

```
Workspace
├── Sidebar [PRIMARY]
├── Main Column
│   ├── Topbar [SECONDARY — user identity pill when personal data]
│   └── Memory View [PRIMARY]
│       ├── Search + Filters
│       ├── Memory Timeline (vertical)
│       ├── Memory Cards (grouped by category)
│       └── Conversation Memory section (collapsible)
├── Orchestrator [PRIMARY — memory activity]
│   ├── State
│   ├── Retrieval chain (what matched, relevance summary)
│   ├── Recent writes (decider outcomes)
│   └── Neural sparkline (recall frequency)
└── Bottom Dock
    ├── Status Cards (Mémoire Récente hero)
    ├── Memory Status Line
    ├── Composer
    └── Telemetry
```

---

## Animation Behavior

| Event | Behavior |
|-------|----------|
| Enter Memory view | MÉMOIRE module ACTIF 500ms; recall dive camera |
| Search / filter | Results cross-fade 200ms; cards stagger enter 80ms |
| Active recall | Ghost nodes +36; central wave convergence; memory cards float up 350ms |
| Timeline scroll | Parallax subtle on neural haze — disabled reduced motion |
| New memory write | Card enter from timeline anchor 350ms; category chip pulse once |

**Recall animation:** Dedicated memory retrieval sequence — camera inward scale 5.5%, ghost nodes fade 600ms organic, memory cards ephemeral float then dissolve 400ms exit when recall completes.

---

## Neural Behavior

| Condition | Cognitive tag | Behavior |
|-----------|---------------|----------|
| Memory view idle browse | memory (low intensity) | MÉMOIRE module ACTIF muted |
| Active search/recall | memory | Full recall dive; central waves; ghost nodes |
| Memory write pipeline | memory + tool | Brief central pulse on save confirmation |

Hook: `memory_retrieval` drives intensity.

---

## Presence State

| Context | Copy |
|---------|------|
| Browsing | Présent — en attente |
| Searching | Recherche en mémoire… |
| Recall complete | Mémoire consultée |
| Write pending | Mémorisation en cours… |

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Chat → Memory | Memory | Recall animation may trigger if retrieval was in-flight |
| Memory → Chat | Chat | Float memory cards dissolve; MÉMOIRE module fades IDLE 500ms |

---

## Empty State

| Condition | Display |
|-----------|---------|
| No stored notes for user | "Aucune mémoire permanente pour toi. Dis « souviens-toi de… » pour commencer." |
| Search no results | "Aucun résultat pour cette recherche." |
| Timeline empty | "Aucun événement mémoire récent." |

---

## Loading State

| Condition | Display |
|-----------|---------|
| Memory index loading | "Chargement de la mémoire…" + memory cognitive mode low intensity |
| Retrieval in flight | Memory status line + recall animation — not skeleton list |

---

## Error State

| Condition | Display |
|-----------|---------|
| Load corruption | "Impossible de lire la mémoire. Consulte les logs." + retry |
| User identity uncertain | Prompt to confirm Nolan vs Ibrahim before showing personal notes |

---

## Responsive Behavior

### Desktop

Timeline left or center; cards 2-column grid; full filters visible.

### Laptop

Single column timeline; cards 2-column narrow.

### Tablet

Timeline full width; filters in collapsible row; orchestrator drawer.

### Phone

Search sticky top. Timeline vertical only. Cards single column. Filters → sheet. Recall animation simplified (no float cards — status line only).

---

# 4. OBSIDIAN

## Purpose

Interface to the user's **existing** Obsidian vault (Titan AI) — read, search, write, edit, and visualize knowledge relationships. Obsidian is the user's personal note space, **not** Titan's brain. Answers: *"What do I know in my vault, and how can Titan help maintain it?"*

Relationship to Titan Memory: Obsidian holds user-authored notes; Titan Memory holds what Titan learned about the user. UI must never conflate the two.

---

## Primary Panels

| Panel | Role |
|-------|------|
| **Vault Browser** | Center hero — folder tree + note list |
| **Note Reader** | Read selected note with markdown structure awareness |
| **Note Editor** | Patch/update modes preserving formatting |
| **Search** | Vault-scoped search (filename, keyword, tag, folder) |
| **Recent Notes** | Quick access row |
| **Knowledge Graph** | Relationship visualization between linked notes |
| **Orchestrator (Obsidian focus)** | Tool activity, patch mode, search-before-create status |

## Secondary Panels

| Panel | Role |
|-------|------|
| **Sync Status** | Vault path validation, last sync, connector health |
| **Write Actions** | Create (confirmation-gated), patch, append — decision-engine driven |
| **Sidebar** | Nav with Obsidian active |
| **Status Cards** | Obsidian card hero emphasis |
| **Composer** | Natural language vault commands |

---

## Panel Hierarchy

```
Workspace
├── Sidebar [PRIMARY]
├── Main Column
│   ├── Topbar [SECONDARY — vault name "Titan AI"]
│   └── Obsidian View [PRIMARY]
│       ├── Recent Notes (horizontal strip)
│       ├── Split: Vault Browser | Note Reader/Editor
│       ├── Search (persistent)
│       └── Knowledge Graph (toggle panel / bottom split)
├── Orchestrator [PRIMARY]
│   ├── Obsidian connector status
│   ├── Active operation (search, read, patch)
│   ├── Decision engine outcome (CREATE vs SEARCH vs PATCH)
│   └── Tool timeline
└── Bottom Dock
    ├── Status Cards (Obsidian hero)
    ├── Tool Status Line
    ├── Composer
    └── Telemetry
```

---

## Animation Behavior

| Event | Behavior |
|-------|----------|
| Enter Obsidian | OBSIDIAN module ACTIF; geometric wave bias 500ms |
| Note select | Reader cross-fade 200ms; graph highlights node 300ms |
| Graph toggle | Panel expand 350ms enter; nodes fade in staggered 60ms |
| Patch apply | Brief confirmation pulse on saved section — not celebration confetti |
| Search results | List stagger 80ms |
| Sync refresh | Sync icon rotate 600ms once; status cross-fade |

---

## Neural Behavior

| Condition | Cognitive tag | Behavior |
|-----------|---------------|----------|
| Browsing vault | idle / obsidian | OBSIDIAN module ACTIF muted |
| Search / read | tool | Geometric wave style |
| Patch / write | tool | Sharp micro-pulse on confirmation |
| Graph view | obsidian | Distributed low-intensity signals between nodes mirroring graph edges ( decorative sync optional ) |

---

## Presence State

| Context | Copy |
|---------|------|
| Idle | Présent — en attente |
| Searching vault | Recherche dans le vault… |
| Reading | Consultation d'Obsidian |
| Writing / patch | Mise à jour du vault… |
| Sync | Synchronisation… |

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Chat → Obsidian | Obsidian | If tool was Obsidian-active, orchestrator preserves operation context |
| Obsidian → Memory | Memory | Clear vault selection; show relationship tooltip once: "Mémoire Titan ≠ Vault Obsidian" |

---

## Empty State

| Condition | Display |
|-----------|---------|
| Vault path unset | "Vault Obsidian non configuré. Définis TITAN_OBSIDIAN_VAULT_PATH dans les paramètres." |
| Vault empty | "Vault connecté — aucune note trouvée." |
| No search results | "Aucune note correspondante. Titan peut chercher avant de créer." |
| Graph no links | Graph area: "Pas encore de liens entre notes." |

---

## Loading State

| Condition | Display |
|-----------|---------|
| Vault indexing | "Indexation du vault…" + geometric neural pulse |
| Note loading | Previous note holds; subtle opacity 0.7 on reader |

---

## Error State

| Condition | Display |
|-----------|---------|
| Vault path invalid | Persistent banner in view; link to Settings → Tools |
| Patch failure | Inline error in editor; orchestrator step failed |
| Create blocked | Confirmation required message — decision engine enforced |

---

## Responsive Behavior

### Desktop

Split browser | reader; graph as toggle bottom panel (40% height).

### Laptop

Split 40/60; graph overlay modal.

### Tablet

Browser full width; reader as sheet over content; graph sheet.

### Phone

Note list only; reader full-screen sheet; graph hidden (link count in note header); search sticky.

---

# 5. EXPLORATION (Browser)

## Purpose

Web research command center. Surfaces active browser tool sessions — sources, citations, comparison, summary, and Brain state during exploration. Answers: *"What is Titan researching, from where, and what did it find?"*

Exploration is a **capability of Titan**, not a separate browser app.

---

## Primary Panels

| Panel | Role |
|-------|------|
| **Exploration View** | Center hero — active research session |
| **Research Summary** | Titan-synthesized findings |
| **Sources List** | Visited URLs with status and snippets |
| **Citations Panel** | Referenceable source citations for conversation |
| **Comparison View** | Side-by-side source comparison when multi-source |
| **Exploration Cards** | Session snapshots floating in center |
| **Orchestrator (Browser focus)** | Tool chain, fetch status, browser health |

## Secondary Panels

| Panel | Role |
|-------|------|
| **Brain State Indicator** | Topbar + orchestrator — thinking during synthesis |
| **Screenshot Preview** | Thumbnail when browser tool captures |
| **Sidebar** | Nav with Exploration active |
| **Status Cards** | Browser card hero |
| **Composer** | "Cherche…", "Compare…", "Résume…" commands |

---

## Panel Hierarchy

```
Workspace
├── Sidebar [PRIMARY]
├── Main Column
│   ├── Topbar [SECONDARY — "Exploration web" when active]
│   └── Exploration View [PRIMARY]
│       ├── Research Summary (top)
│       ├── Exploration Cards (session snapshots)
│       ├── Sources List
│       └── Comparison View (when ≥2 sources selected)
├── Orchestrator [PRIMARY]
│   ├── Browser tool status + health
│   ├── Fetch / navigation steps
│   ├── Active URLs
│   └── Tool timeline
└── Bottom Dock
    ├── Status Cards (Browser hero)
    ├── Tool Status Line ("Exploration web…")
    ├── Composer
    └── Telemetry
```

---

## Animation Behavior

| Event | Behavior |
|-------|----------|
| Enter Exploration | BROWSER module ACTIF; distributed waves 500ms |
| New source fetched | Source row enter 350ms; card fade + translateY 12px |
| Summary update | Cross-fade paragraph 200ms |
| Comparison toggle | Split animate 350ms |
| Screenshot capture | Thumbnail scale 0.96 → 1 over slow |
| Session end | Cards dissolve 400ms; module fades IDLE |

---

## Neural Behavior

| Condition | Cognitive tag | Behavior |
|-----------|---------------|----------|
| Idle on Exploration | browser (muted) | BROWSER module visible, low activity |
| Active research | browser | Distributed waves; 3 burst; 1.18× speed |
| Synthesis / summary | thinking + browser | Combined profile — thinking brightness + distributed waves |

Hook: `browser_research`.

---

## Presence State

| Context | Copy |
|---------|------|
| Idle | Présent — en attente |
| Navigating | Exploration web… |
| Extracting | Analyse de la source… |
| Synthesizing | Synthèse en cours… |

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Chat → Exploration | Exploration | If browser tool active, session context preserved |
| Exploration → Chat | Chat | Summary may inject as system context line in transcript optional |

---

## Empty State

| Condition | Display |
|-----------|---------|
| No active session | "Aucune exploration en cours. Demande une recherche à Titan." |
| No sources yet | Sources list: "En attente de la première source." |

---

## Loading State

| Condition | Display |
|-----------|---------|
| Page fetch | Tool status line + distributed neural; source row pending badge |
| Summary generation | Thinking presence; summary area shows "Synthèse en cours…" |

---

## Error State

| Condition | Display |
|-----------|---------|
| Browser connector down | Banner: "Navigateur indisponible." + health in orchestrator |
| Fetch failure | Source row error badge; retry per URL |
| Blocked URL | Honest message — no invented content |

---

## Responsive Behavior

### Desktop

Summary top; sources left list; comparison right split when active.

### Laptop

Summary + sources stacked; comparison overlay.

### Tablet

Cards horizontal scroll; sources sheet; orchestrator drawer.

### Phone

Exploration card single full-width; sources sheet; comparison full-screen sheet; summary collapsible.

---

# 6. TRADING

## Purpose

Market oversight and controlled execution interface. Surfaces overview, strategies, positions, alerts, performance, broker status, execution history, and risk boundaries. Answers: *"What are markets doing, what is my exposure, and what is Titan analyzing?"*

Trading UI defaults to **read-only / paper** posture until explicit LIVE confirmation gates pass.

---

## Primary Panels

| Panel | Role |
|-------|------|
| **Market Overview** | Center hero — indices, watchlist, key levels |
| **Strategies Panel** | Active and backtest strategy status |
| **Positions Table** | Open positions with P&L |
| **Alerts Feed** | Price, risk, and system alerts |
| **Performance Summary** | Session / period metrics |
| **Broker Status** | Connection, account mode (PAPER/LIVE), health |
| **Execution Log** | Recent orders with confirmation state |
| **Risk Panel** | Limits, exposure, blocked actions |
| **Orchestrator (Trading focus)** | Brain analysis steps, tool activity |

## Secondary Panels

| Panel | Role |
|-------|------|
| **Brain Visualization** | TRADING module + sharp neural profile during analysis |
| **Sidebar** | Nav with Trading active |
| **Status Cards** | Cognitive + custom trading chip |
| **Composer** | "Analyse…", "Position…", "Alerte si…" commands |

---

## Panel Hierarchy

```
Workspace
├── Sidebar [PRIMARY]
├── Main Column
│   ├── Topbar [SECONDARY — broker mode badge PAPER/LIVE]
│   └── Trading View [PRIMARY]
│       ├── Market Overview
│       ├── Row: Positions | Performance
│       ├── Row: Strategies | Alerts
│       └── Execution Log + Risk Panel (split bottom)
├── Orchestrator [PRIMARY]
│   ├── Brain analysis steps (market reasoning)
│   ├── Trading tool status
│   ├── Broker connector health
│   └── Tool timeline
└── Bottom Dock
    ├── Status Cards (Trading emphasis)
    ├── Tool Status Line
    ├── Composer
    └── Telemetry (numeric monospace ticks)
```

---

## Animation Behavior

| Event | Behavior |
|-------|----------|
| Enter Trading | TRADING module ACTIF; sharp wave profile |
| Price tick | Numeric cross-fade 100ms — no slot-machine |
| Alert trigger | Alert row enter 200ms; amber badge pulse once |
| LIVE mode request | Confirmation overlay — orchestrator pauses |
| Order execution | Execution row enter; risk panel recalculates 300ms |
| Analysis start | Sharp micro-pulses; "Analyse des marchés" status |

---

## Neural Behavior

| Condition | Cognitive tag | Behavior |
|-----------|---------------|----------|
| Idle on Trading | trading (muted) | TRADING module IDLE until engaged |
| Market analysis | trading | Sharp waves; 1.35× speed; controlled urgency — never strobe |
| Order pipeline | trading + tool | Sharp + directed tool signals |
| Risk block | idle | Neural calms immediately on blocked action |

---

## Presence State

| Context | Copy |
|---------|------|
| Idle | Présent — en attente |
| Analyzing | Analyse des marchés |
| Executing | Exécution en cours… (confirmation if LIVE) |
| Broker disconnected | Broker déconnecté |

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Chat → Trading | Trading | Market data poll begins; no layout jump |
| LIVE confirmation | Execution | Overlay scrim 72%; confirm/Cancel; neural pauses |

---

## Empty State

| Condition | Display |
|-----------|---------|
| No broker configured | "Trading non configuré. Connecte un broker dans Paramètres → Comptes." |
| No positions | Positions: "Aucune position ouverte." |
| No strategies | "Aucune stratégie active." |
| No alerts | "Aucune alerte." |

---

## Loading State

| Condition | Display |
|-----------|---------|
| Market data fetch | Previous tick holds; "Chargement des marchés…" |
| Broker connect | Broker status spinner replaced by presence Working — no skeleton table |

---

## Error State

| Condition | Display |
|-----------|---------|
| Broker error | Broker status error badge; orchestrator detail |
| Order rejected | Execution log failed row; risk panel explanation |
| LIVE without confirmation | Action blocked inline — never silent fail |

---

## Responsive Behavior

### Desktop

Full grid: overview top; positions + performance; strategies + alerts; execution + risk.

### Laptop

Overview + positions stacked; strategies collapsible.

### Tablet

Market overview only in center; all else in tabs (Positions, Alerts, Execution). Orchestrator drawer.

### Phone

Watchlist mini horizontal scroll; positions sheet; alerts badge count; execution sheet only; risk in Settings link.

---

# 7. CALENDAR

## Purpose

Temporal command center — agenda, upcoming tasks, scheduling, daily focus, and Brain planning mode for time-aware missions. Answers: *"What is happening when, and what should I focus on today?"*

---

## Primary Panels

| Panel | Role |
|-------|------|
| **Agenda View** | Center hero — day / week calendar grid |
| **Upcoming Tasks** | Next events and mission-linked deadlines |
| **Scheduling Panel** | Create / modify events via Brain + calendar tool |
| **Daily Focus** | Curated priority block for current day |
| **Orchestrator (Calendar focus)** | Planning mode, calendar tool steps, conflicts |

## Secondary Panels

| Panel | Role |
|-------|------|
| **Brain Planning Mode** | PLANIFICATION + CALENDAR modules dual emphasis |
| **Sidebar** | Nav with Calendar active |
| **Status Cards** | Agenda summary chip |
| **Composer** | "Planifie…", "Rappelle-moi…", "Qu'est-ce aujourd'hui?" |

---

## Panel Hierarchy

```
Workspace
├── Sidebar [PRIMARY]
├── Main Column
│   ├── Topbar [SECONDARY — date + "Aujourd'hui" pill]
│   └── Calendar View [PRIMARY]
│       ├── Daily Focus (top banner)
│       ├── Agenda (day/week toggle)
│       └── Upcoming Tasks (sidebar within center or below agenda)
├── Orchestrator [PRIMARY — planning mode]
│   ├── State (Planning when scheduling)
│   ├── Plan steps for scheduling requests
│   ├── Calendar tool status + conflicts
│   └── Tool timeline
└── Bottom Dock
    ├── Status Cards
    ├── Tool Status Line
    ├── Composer
    └── Telemetry
```

---

## Animation Behavior

| Event | Behavior |
|-------|----------|
| Enter Calendar | CALENDAR module ACTIF; circular wave 500ms |
| Day navigation | Agenda cross-fade 200ms; focus block update 350ms |
| Event create | Event block enter 350ms from slot; planning step highlight |
| Conflict detected | Conflict row amber pulse once |
| Brain planning | PLANIFICATION ACTIF; structured path bursts |

---

## Neural Behavior

| Condition | Cognitive tag | Behavior |
|-----------|---------------|----------|
| Browsing calendar | calendar (muted) | CALENDAR module low activity |
| Scheduling request | planning + calendar | Circular waves + planning paths |
| Conflict resolution | thinking | Moderate thinking profile |

---

## Presence State

| Context | Copy |
|---------|------|
| Idle | Présent — en attente |
| Loading events | Chargement de l'agenda… |
| Scheduling | Planification… |
| Sync | Synchronisation du calendrier… |

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Chat → Calendar | Calendar | Date context from message preserved if parsed |
| Calendar → Projects | Projects | Shared mission deadlines link visually once |

---

## Empty State

| Condition | Display |
|-----------|---------|
| No calendar connected | "Calendrier non connecté. Configure Google Calendar dans Paramètres." |
| No events today | Agenda: "Rien de prévu aujourd'hui." + Daily Focus suggestion |
| No upcoming tasks | "Aucune tâche à venir." |

---

## Loading State

| Condition | Display |
|-----------|---------|
| Events fetch | Previous day view holds; circular neural pulse low |
| Create in flight | Planning presence; pending event ghost block in agenda |

---

## Error State

| Condition | Display |
|-----------|---------|
| API failure | "Impossible de charger l'agenda." + retry |
| Create failure | Event ghost removed; orchestrator failed step |
| Permission denied | Link to Settings → Accounts |

---

## Responsive Behavior

### Desktop

Day/week toggle; focus banner; upcoming tasks right column within center.

### Laptop

Single column agenda; upcoming below.

### Tablet

Day view default; week in sheet; focus banner compact.

### Phone

Today only; swipe day change; upcoming as list below; week sheet; focus one-line strip.

---

# 8. VOICE

## Purpose

Immersive voice conversation mode — hands-free partnership with Titan. Full-screen emphasis on listening, speaking, interrupt, and continuous mode. Answers: *"Can I talk to Titan naturally without staring at a transcript?"*

Voice is a **first-class modality** accessible from sidebar and composer mic. The Voice screen is the dedicated immersive expression of that modality.

---

## Primary Panels

| Panel | Role |
|-------|------|
| **Voice Stage** | Center hero — waveform, presence, minimal transcript |
| **Wave Visualization** | Large central audio envelope display |
| **Conversation Mode Toggle** | Push-to-talk vs continuous listening |
| **Listening Indicator** | Full-width attention state |
| **Speaking Indicator** | Output rhythm visualization |
| **Interrupt Control** | Stop speaking / cancel listening — always reachable |
| **Minimal Transcript** | Last exchange only — not full history |

## Secondary Panels

| Panel | Role |
|-------|------|
| **Sidebar** | Nav with Voice active; may auto-collapse desktop |
| **Orchestrator (Voice focus)** | State orb enlarged emphasis; tool line if voice triggers tool |
| **Mic Status** | Composer mic mirrored large in center |
| **Composer** | Retained slim — text fallback always available |

---

## Panel Hierarchy

```
Workspace
├── Sidebar [SECONDARY — may collapse to rail]
├── Main Column
│   ├── Topbar [SECONDARY — voice mode badge]
│   └── Voice Stage [PRIMARY — immersive]
│       ├── Wave Visualization (hero)
│       ├── Presence copy (large)
│       ├── Mode toggle (push / continuous)
│       ├── Interrupt button
│       └── Minimal Transcript (last 2 turns)
├── Orchestrator [SECONDARY — slim or hidden phone]
│   └── State orb + tool line only
└── Bottom Dock
    ├── Composer slim [SECONDARY — text fallback]
    └── Telemetry optional hidden
```

**Immersive rule:** Voice Stage occupies ≥60% center column visual weight.

---

## Animation Behavior

| Event | Behavior |
|-------|----------|
| Enter Voice | Sidebar optional collapse 350ms; wave canvas expand |
| Start listening | Mic ring 900ms organic; `--tdl-voice-ripple` 0→1; LISTENING presence 500ms |
| Audio envelope | Waveform bars 60fps follow input level |
| Start speaking | Circular pulses from core 520ms; SPEAKING presence 600ms |
| Interrupt | Immediate halt — presence snap to Idle 200ms (exception to lerp for user agency) |
| Continuous mode on | Ring persistent subtle pulse; idle elevated neural |
| Exit Voice | Wave shrink 350ms exit; sidebar restore |

---

## Neural Behavior

| Condition | Master state | Behavior |
|-----------|--------------|----------|
| Listening | LISTENING | Elevated idle; ripple; activity 0.22 |
| Processing speech | THINKING | Standard thinking profile |
| Speaking | SPEAKING | Circular waves; brightness 1.07×; activity 0.76 |
| Continuous idle listen | LISTENING (low) | Ambient attention — not full thinking |

---

## Presence State

| Context | Copy |
|---------|------|
| Ready | Présent — en attente |
| Listening | À l'écoute |
| Processing | Réflexion en cours |
| Speaking | Titan parle |
| Interrupted | Interrompu — prêt |

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Chat → Voice | Voice | Mic state preserved; transcript minimized |
| Voice → Chat | Chat | Full transcript restored in conversation scroll |
| Voice + tool trigger | Working | Orchestrator slides in if hidden; tool line appears |

---

## Empty State

| Condition | Display |
|-----------|---------|
| First enter Voice | "Appuie sur le micro ou parle en mode continu." — centered below wave |
| No conversation yet | Minimal transcript hidden |

---

## Loading State

| Condition | Display |
|-----------|---------|
| Voice engine init | "Initialisation vocale…" — wave flat line |
| STT processing | Listening holds; wave frozen brief — then Thinking transition |

---

## Error State

| Condition | Display |
|-----------|---------|
| Mic permission denied | "Accès micro refusé. Autorise le micro ou utilise le texte." |
| STT failure | "Je n'ai pas compris. Réessaie." — neural calms |
| TTS failure | Text response appears in minimal transcript |

---

## Responsive Behavior

### Desktop

Full immersive stage; orchestrator slim right; sidebar may collapse for focus mode.

### Laptop

Same; wave slightly reduced height.

### Tablet

Full center; orchestrator hidden; interrupt floating button bottom-right.

### Phone

Full bleed voice stage; sidebar hidden; interrupt 56px floating; composer one-line; transcript last turn only.

---

# 9. SETTINGS

## Purpose

Configuration overlay for appearance, voice, memory, tools, accounts, security, developer diagnostics, and performance. Settings is an **overlay** — not a separate marketing page. Neural context remains visible behind scrim. Answers: *"How do I configure Titan for my environment and preferences?"*

---

## Primary Panels

| Panel | Role |
|-------|------|
| **Settings Overlay** | Scrim + large card centered or right-aligned |
| **Settings Navigation** | Section list within overlay |
| **Section Content** | Active settings group form |

## Settings Sections

| Section | Contents |
|---------|----------|
| **Appearance** | Font scale 100/112/125%; reduced motion; high contrast |
| **Voice** | Push-to-talk default; continuous mode; TTS voice selection (future) |
| **Memory** | User identity (Nolan/Ibrahim); memory path info read-only; forget commands doc |
| **Tools** | Tool runtime mode (LIVE/PAPER/SIMULATION/MOCK); per-connector toggles |
| **Accounts** | Google Calendar, Gmail, Broker, Obsidian vault path |
| **Security** | Bearer secret key; session clear; local-only reminder |
| **Developer** | Telemetry toggle; debug brain; API endpoint display |
| **Performance** | Neural density; FPS cap; adaptive quality toggle |

## Secondary Panels

| Panel | Role |
|-------|------|
| **Sidebar** | Settings nav item active; overlay dims workspace |
| **Neural Space** | Visible through scrim at 28% visibility |
| **Orchestrator** | Dimmed behind overlay — not interactive |

---

## Panel Hierarchy

```
Overlay Layer (z=100)
├── Scrim [full viewport]
└── Settings Card [PRIMARY]
    ├── Header (title + close)
    ├── Settings Navigation [SECONDARY — vertical tabs]
    └── Section Content [PRIMARY — forms]
Background (dimmed)
├── Neural Stage (visible)
└── Workspace (non-interactive)
```

---

## Animation Behavior

| Event | Behavior |
|-------|----------|
| Open Settings | Scrim fade 350ms enter; card scale 0.96→1 slow enter |
| Section switch | Content cross-fade 200ms |
| Save | Primary button brief confirm state 200ms; no toast unless error |
| Close | Card exit 350ms; scrim fade exit |
| Live setting change (font scale) | Immediate apply — no save required for a11y |

---

## Neural Behavior

| Condition | Behavior |
|-----------|----------|
| Settings open | Neural continues idle profile — never pauses |
| Performance density change | Engine adapts on next frame — smooth density lerp |
| Reduced motion toggle | Immediate: drift → 0; transitions shorten |

---

## Presence State

| Context | Copy |
|---------|------|
| Settings open | Topbar behind scrim retains last state |
| Save in progress | Button "Enregistrement…" — not global presence change |

---

## Transitions

| From | To | Behavior |
|------|-----|----------|
| Any screen → Settings | Settings | Overlay — underlying screen preserved |
| Settings → Close | Previous | Overlay exit; no screen reload |

---

## Empty State

N/A — settings sections always show current values or explicit "non configuré".

---

## Loading State

| Condition | Display |
|-----------|---------|
| Account OAuth | Section inline "Connexion…" — no full overlay spinner |
| Test connection | Button loading state 200ms minimum feedback |

---

## Error State

| Condition | Display |
|-----------|---------|
| Invalid secret | Inline field error |
| Connection test fail | Section error banner + detail |
| Save failure | "Enregistrement impossible." — field values preserved |

---

## Responsive Behavior

### Desktop

Card max-width 640px centered; scrim 72% black; vertical section nav left inside card.

### Laptop

Same; card 560px.

### Tablet

Card 90vw; section nav horizontal scroll chips top.

### Phone

Full-screen sheet slide up; section nav horizontal; close sticky top-right.

---

# Cross-Screen Architecture

## Navigation Model

| Rule | Specification |
|------|---------------|
| Single shell | Neural + sidebar + dock persist; only center primary content swaps |
| Active nav | One item highlighted; 350ms transition |
| Deep link | Each screen addressable by nav key for future routing |
| Settings | Overlay — not nav destination that destroys context |
| Voice | May be entered from nav or composer mic long-press |

## Orchestrator Refocus Matrix

| Screen | Primary orchestrator sections |
|--------|------------------------------|
| Home / Chat | State, Plan, Tools, Sparkline |
| Projects | State, Mission, Agents summary, Tools |
| Memory | State, Retrieval chain, Writes, Sparkline |
| Obsidian | Connector, Operation, Decision, Timeline |
| Exploration | Browser health, URLs, Fetch steps, Timeline |
| Trading | Analysis, Broker, Orders, Risk |
| Calendar | Planning, Conflicts, Tool status |
| Voice | State orb only (+ Tools if triggered) |
| Settings | Dimmed — frozen snapshot |

## Composer Availability

| Screen | Composer |
|--------|----------|
| Home / Chat | Full |
| Projects | Full — project-scoped |
| Memory | Full — memory commands |
| Obsidian | Full — vault commands |
| Exploration | Full — research commands |
| Trading | Full — analysis commands; LIVE gated |
| Calendar | Full — scheduling commands |
| Voice | Slim — text fallback |
| Settings | Hidden behind overlay |

## Status Cards Emphasis Matrix

| Screen | Hero card |
|--------|-----------|
| Home / Chat | Balanced all five |
| Projects | État Cognitif |
| Memory | Mémoire Récente |
| Obsidian | Obsidian |
| Exploration | Browser |
| Trading | État Cognitif + trading extension |
| Calendar | Custom agenda chip |
| Voice | Présence |
| Settings | Hidden |

## Cognitive Region Activation Matrix

| Screen | Primary module(s) |
|--------|---------------------|
| Home / Chat | CORE + dynamic per activity |
| Projects | PLANIFICATION |
| Memory | MÉMOIRE |
| Obsidian | OBSIDIAN |
| Exploration | BROWSER |
| Trading | TRADING |
| Calendar | CALENDAR + PLANIFICATION |
| Voice | CORE + COMMUNICATION |
| Settings | None active — all IDLE |

---

# Global Forbidden Patterns

| Pattern | Reason |
|---------|--------|
| Screen without neural field | Breaks identity |
| Full opaque page background | Breaks void |
| Separate app chrome per tool | Tools are limbs |
| Skeleton loading screens | Violates honest loading law |
| Agent personas in UI | Single intelligence principle |
| White/light mode | Void preservation |
| Chat bubbles candy colors | Generic chatbot |
| Obsidian as Titan memory | Product policy |
| Auto-create Obsidian vault | Product policy |
| Trading LIVE without confirmation | Safety |
| Memory mixed across Nolan/Ibrahim | User isolation |

---

# Verification Checklist

Before any screen ships:

- [ ] Purpose statement answerable in one sentence
- [ ] All primary and secondary panels documented
- [ ] Panel hierarchy respects Layout Guide z-index and weight tiers
- [ ] Animation maps to Animation Guide state — no invented motion
- [ ] Neural behavior maps to Neural Engine hooks and cognitive tags
- [ ] Presence copy in French; honest to backend state
- [ ] Empty, loading, error states defined — no lorem ipsum
- [ ] Desktop, laptop, tablet, phone behaviors specified
- [ ] Transitions preserve neural field continuity
- [ ] Constitution and UI Bible alignment verified

---

## Document Metadata

| Field | Value |
|-------|-------|
| Phase | D2 |
| Version | 1.0.0 |
| Established | 2026-07-06 |
| Authors | Titan Product (Nolan Hassing) |
| Predecessor | Phase D1 design system |
| Successor | Phase D3+ implementation phases |

---

**End of Titan Master Blueprint — Phase D2**

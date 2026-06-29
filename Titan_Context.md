# Titan Context

**Official engineering knowledge base for the Titan project.**

| Field | Value |
|-------|-------|
| Document version | 1.0.0 |
| Project version | 0.0.1 |
| Creator | Nolan Hassing |
| Primary users | Nolan Hassing, Ibrahim |
| Last inferred from repository | June 2026 |
| Runtime entry point | `python main.py` |
| Primary language | Python 3 |
| LLM provider | OpenAI (Responses API) |
| Default model | `gpt-5.2` |

This document describes everything inferable from the current Titan repository: structure, behavior, data, gaps, debt, and evolution. It is the permanent reference for engineers and AI assistants working on Titan.

Related documents:

- `Titan_Blueprint.md` — original product blueprint (partially outdated)
- `core/constitution/titan_constitution.md` — product identity and values (1,468 lines, not yet wired into runtime)
- `.cursor/rules/titan.mdc` — engineering rulebook for Cursor agents

---

# Vision

## Why Titan Exists

Titan exists because Nolan Hassing and Ibrahim need more than a generic chatbot. They need a **personal agentic AI system** that:

- Helps manage real projects over weeks and months
- Assists with learning, coding, analysis, and automation
- Eventually supports market analysis and trading automation
- Remembers what matters across sessions
- Executes multi-step missions with continuity
- Speaks as one unified intelligence while using internal specialists

Titan is explicitly **not** built as a disposable demo. The Blueprint states:

> *Titan doit être construit comme un vrai logiciel professionnel, pas comme un simple chatbot.*

Every file in the repository is intended to serve the final product. No throwaway exercises. No temporary files without a clear role.

## Long-Term Mission

The long-term mission of Titan, as defined across the Blueprint, Constitution, and runtime memory defaults, is:

1. **Transform ideas into concrete outcomes** — not just answer questions, but drive progress on projects
2. **Augment Nolan and Ibrahim intellectually and operationally** — act as co-pilot, strategist, and execution assistant
3. **Persist knowledge** — remember users, projects, decisions, preferences, and mission progress
4. **Coordinate specialists** — Brain orchestrates Coding, Research, Planning, Reasoning, and future agents (Trading, Web, Voice, Vision, Automation, Memory)
5. **Act on the world through tools** — files, Python, web, calendar, email, trading platforms, external services
6. **Evolve for years** — modular architecture that grows without rewriting foundations
7. **Maintain a single identity** — users always interact with Titan, never with raw internal agents

The Constitution's permanent guiding question:

> *"Qu'est-ce que je peux faire maintenant pour aider Nolan ou Ibrahim à avancer concrètement ?"*

This question should eventually inform Brain decisions, prompt design, and mission prioritization.

## Product Philosophy

### Titan Is Not a Chatbot

The Constitution opens with this principle. Titan is a **personal AI operating system** with:

- A Brain (conductor)
- Agents (specialists)
- Memory (selective persistence)
- Tools (external action)
- State and missions (continuity)

### Truth Over Convenience

Titan must prioritize truth, honesty about uncertainty, and long-term value over fast or flattering answers. This is defined in Constitution Articles 2, 4, and 5. Runtime LLM instructions in `brain/llm.py` reinforce clarity and step-by-step practical guidance.

### One Intelligence, Many Specialists

Users never speak to `CodingAgent` or `ResearchAgent` directly in the final product. Agents produce internal artifacts. The Brain assembles the user-facing response. Constitution Article 8.8.

### Memory Is a Privilege

Memory is selective, not exhaustive. Store what helps future assistance. Protect user separation (Nolan vs Ibrahim). Constitution Article 7.

### Tools Extend, Brain Decides

Tools execute. Brain decides. No tool makes strategic decisions alone. Constitution Articles 8.4 and 9.

### Quality Over Quantity

Every response should provide real value. Avoid filler. Constitution Articles 2.7, 4.4, 4.5.

### Planned Personality Traits

From `Titan_Blueprint.md` (personality module not yet built):

- Calm
- Intelligent
- Loyal
- Direct
- Disciplined
- Professional
- Protective
- Action-oriented

From `brain/identity.py` (exists but unwired):

- Private assistant and co-teammate inspired by an intelligent butler (Alfred)
- No ego
- Works **with** Nolan and Ibrahim, not merely **for** them

### Primary Users and Authority

| User | Role | Authority |
|------|------|-----------|
| Nolan Hassing | Creator of Titan | Principal (creator authority on vision) |
| Ibrahim | Primary user | Equal to Nolan in product terms |

Both must receive equal engagement. Personal memories must never be mixed.

---

# Current Development Status

## Current Version

**Version 0.0.1** — defined in `config/settings.py`:

```python
TITAN_NAME = "Titan"
VERSION = "0.0.1"
CREATOR = "Nolan Hassing"
```

## What Has Already Been Implemented

### Application Shell

| Component | Status | Location |
|-----------|--------|----------|
| Entry point | Complete | `main.py` |
| Titan composition root | Complete | `core/titan.py` |
| Interactive REPL session loop | Complete | `core/titan.py` → `start()` |
| Startup banner and greeting | Complete | French CLI output |
| Exit commands | Complete | `exit`, `quit`, `stop`, `bye` |
| Static configuration | Complete | `config/settings.py` |

### Brain and LLM

| Component | Status | Location |
|-----------|--------|----------|
| Brain orchestrator | Complete pipeline | `brain/brain.py` |
| OpenAI integration | Functional | `brain/llm.py` |
| GPT Responses API call | Functional | model `gpt-5.2` |
| System instructions (French) | Functional | embedded in `LLM.ask()` |
| Rich prompt assembly | Functional | context, memory, state, mission, executive analysis, user message, agent results |
| Knowledge lookup (minimal) | Functional | `brain/knowledge.py` — 3 hardcoded facts |
| Internal monologue | Template only | `brain/internal_monologue.py` |
| Reasoning | Stub | `brain/reasoning.py` |
| Planning | Stub | `brain/planning.py` |
| Decision | Minimal | `brain/decision.py` |
| Executor | Stub | `brain/executor.py` |
| Executive brain | Template formatter | `brain/executive_brain.py` |
| Task evaluator | Keyword heuristics | `brain/task_evaluator.py` |

### Memory

| Component | Status | Location |
|-----------|--------|----------|
| Short-term session memory | Functional (in-memory) | `memory/memory.py`, `memory/memory_manager.py` |
| Long-term JSON memory | Functional | `memory/long_term_memory.py` |
| Memory decider (should save?) | Functional | `memory/memory_decider.py` |
| Memory classifier | Functional | `memory/memory_classifier.py` |
| Memory retriever | Functional | `memory/memory_retriever.py` |
| Runtime data file | Populated | `data/long_term_memory.json` |

### State and Missions

| Component | Status | Location |
|-----------|--------|----------|
| State manager | Functional | `core/state_manager.py` |
| Mission manager | Functional | `core/mission_manager.py` |
| Auto-mission from message | Functional | keyword templates for trading, titan, general |
| Step completion | Functional | `brain/task_evaluator.py` + `MissionManager.complete_current_step()` |
| Runtime state file | Populated | `data/titan_state.json` |
| Runtime mission file | Active mission | `data/titan_mission.json` |

### Agents

| Component | Status | Location |
|-----------|--------|----------|
| Agent registry | Functional | `agents/agent_manager.py` |
| Agent selector | Functional | `agents/agent_selector.py` |
| Base agent | Functional | `agents/base_agent.py` |
| Coding agent | Template responses | `agents/coding_agent.py` |
| Research agent | Template responses | `agents/research_agent.py` |
| Planning agent | Template responses | `agents/planning_agent.py` |
| Reasoning agent | Template responses | `agents/reasoning_agent.py` |
| Task manager | Functional routing | `core/task_manager.py` |
| Task orchestrator | Functional | `core/task_orchestrator.py` |

### Context, Conversation, Tools

| Component | Status | Location |
|-----------|--------|----------|
| Context manager | Functional (static values) | `context/context_manager.py` |
| Conversation history | Functional (in-memory) | `core/conversation.py` |
| Tool manager | Functional | `tools/tool_manager.py` |
| Time tool | Functional | `tools/time_tool.py` |

### Documentation and Governance

| Component | Status | Location |
|-----------|--------|----------|
| Product blueprint | Exists (outdated section 5) | `Titan_Blueprint.md` |
| Constitution | Complete draft | `core/constitution/titan_constitution.md` |
| Cursor engineering rulebook | Complete | `.cursor/rules/titan.mdc` |
| This context document | Being created | `Titan_Context.md` |

### Dependencies

| Package | Purpose |
|---------|---------|
| `openai` | OpenAI Python SDK |
| `python-dotenv` | Load `OPENAI_API_KEY` from `.env` |

## What Is Partially Implemented

### Cognitive Pipeline

The Brain **runs** a full multi-stage pipeline on every turn, but most stages are **placeholders**:

- `Reasoning.analyze()` always returns the same dict with all flags `False`
- `Planning.create_plan()` always returns the same 5 generic steps
- `Decision.decide()` only detects `"bonjour"` → `"salutation"`, else `"conversation"`
- `Executor.execute()` never triggers tool/memory/clarify paths because reasoning flags are always false
- `ExecutiveBrain.analyze_mission()` formats a template; no real inference
- `InternalMonologue.think()` formats a template; no real inference

**Real intelligence today:** the OpenAI call at the end of `Brain.think()`.

### Agent System

Agents **execute** and return text, but:

- No LLM calls inside agents
- Coding agent returns a hardcoded `additionner(a, b)` example regardless of task
- Research agent has no web access
- Routing is keyword-based only (French + some English)

Agents run **twice per user turn**:

1. Inside `Brain.think()` via `TaskOrchestrator`
2. After Brain response in `Titan.start()` via `AgentManager.auto_execute()`

Two separate `AgentManager` instances exist (one in `Titan`, one in `Brain`).

### Memory System

Two parallel memory paths:

| Path | Used when | Persistence |
|------|-----------|-------------|
| `MemoryManager` → `Memory` | Titan startup only | In-memory session list |
| `LongTermMemory` | Brain `think()` pipeline | JSON file |

They are not unified. `Memory.long_term` list is never used.

Memory writes in Brain always attribute notes to `"Nolan"` hardcoded — Ibrahim not detected from context.

Retrieval uses simple word overlap (words > 3 chars), not semantic search.

### Context System

Two context implementations exist:

| Module | Used? | Format |
|--------|-------|--------|
| `context/context_manager.py` | Yes (Titan + Brain) | Formatted French text block |
| `core/context.py` | No | Python dict |

Context values are **static** (`current_user = "Nolan"`, `active_project = "Titan"`, etc.) and do not sync with `StateManager` or `MissionManager`.

### Mission System

Missions persist and advance, but:

- New mission auto-created whenever `active == False` on any message — can overwrite intent
- Step completion triggers on broad keywords (`continue`, `fait`, `terminé`, etc.) — false positives likely
- Current live mission (`data/titan_mission.json`) is a trading bot mission with 5 remaining steps

### State System

State loads, displays in prompts, and updates `last_user_message` / `last_titan_response` after each Brain response. Fields like `current_step`, `next_action`, `progress` are **not automatically updated** by Brain logic — they remain static unless manually changed in JSON.

### Constitution and Identity

- `core/constitution/titan_constitution.md` — 11 articles, ~1,468 lines — **never loaded by code**
- `brain/identity.py` — `IDENTITY` string — **never imported**

LLM instructions in `brain/llm.py` partially reflect constitution values but do not include full governance.

### Blueprint Accuracy

`Titan_Blueprint.md` Section 5 claims only startup and config are done. The repository has substantially more. Section 6 mentions connecting **Claude**; implementation uses **OpenAI GPT**.

## What Is Still Missing

### Directories Planned but Absent

| Directory | Purpose |
|-----------|---------|
| `prompts/` | Externalized prompt templates |
| `logs/` | Structured application logging |
| `tests/` | Automated test suite |

### Infrastructure

- No `__init__.py` files — not an installable Python package
- No `pyproject.toml` or `setup.py`
- No README with setup instructions
- No `.env.example`
- No logging module — extensive `print()` debug instead
- No error handling wrapper on REPL loop
- No CI/CD configuration

### Product Features (from Blueprint and Constitution)

- Logging system
- Full brain with real reasoning (not templates)
- Claude or multi-provider LLM abstraction (Blueprint mentions Claude; code uses OpenAI)
- Real tools beyond time: files, web, Python execution, calendar, email
- Trading module (active mission exists but no trading code)
- Voice identification (Constitution Article 1.5)
- User identification beyond hardcoded Nolan
- Prompts module for personality
- Memory Agent, Trading Agent, Vision Agent, Voice Agent, Web Agent, Automation Agent
- Conversation history in LLM prompts
- Project-specific memory namespaces
- Embedding-based memory retrieval
- Action manager wired to executor
- Ibrahim-aware memory writes

### Integration Gaps

- `core/action_manager.py` — stub, unused
- `core/context.py` — duplicate, unused
- `brain/identity.py` — unused
- Constitution not in LLM prompts
- `Titan.context` (ContextManager on Titan) separate from `Brain.context_manager` (second instance)
- Conversation history not passed to Brain or LLM

---

# Architecture

## Architectural Style

Titan is a **modular monolith**:

- Single Python process
- Synchronous REPL-driven execution
- Multiple domain modules with intended separation of concerns
- JSON file persistence for state, missions, and long-term memory
- Composition root at `core/titan.py` (partial — Brain re-instantiates many dependencies)

## Dependency Graph (Intended)

```
main.py
└── Titan (core/titan.py)
    ├── MemoryManager → Memory
    ├── Brain (brain/brain.py)
    │   ├── Decision, Reasoning, Planning, Knowledge, Executor
    │   ├── LLM
    │   ├── InternalMonologue, ExecutiveBrain, TaskEvaluator
    │   ├── ContextManager          [duplicate instance]
    │   ├── LongTermMemory
    │   ├── MemoryDecider, MemoryClassifier, MemoryRetriever
    │   ├── AgentManager            [duplicate instance]
    │   ├── TaskManager → AgentManager
    │   ├── TaskOrchestrator → TaskManager, AgentManager
    │   ├── StateManager
    │   └── MissionManager
    ├── ToolManager → TimeTool
    ├── ContextManager              [duplicate instance]
    ├── Conversation
    └── AgentManager                [duplicate instance]
```

## Full Execution Pipeline

### Phase 0: Application Bootstrap

**File:** `main.py`

```python
titan = Titan()
titan.start()
```

1. Python loads `core/titan.py`
2. `Titan.__init__()` constructs all top-level subsystems
3. `Titan.start()` begins the session

### Phase 1: Startup (Once Per Session)

**File:** `core/titan.py` → `Titan.start()`

| Step | Action | Component |
|------|--------|-----------|
| 1 | Set `self.status = "ONLINE"` | Titan |
| 2 | Remember startup message | MemoryManager → Memory.short_term |
| 3 | Print short-term memory | Memory.show_memory() |
| 4 | Print banner with name, version, creator, status | config/settings.py |
| 5 | Get current time | ToolManager → TimeTool |
| 6 | Get and print context | ContextManager.get_context() |
| 7 | Print French greeting to Nolan | hardcoded strings |
| 8 | Enter REPL loop | `while True` |

**Note:** Startup uses `Titan.context` (ContextManager instance #1). Brain later uses its own ContextManager instance #2 with identical static defaults.

### Phase 2: User Turn — Shell Layer

**File:** `core/titan.py` → REPL loop

| Step | Action | Component |
|------|--------|-----------|
| 1 | Read user input | `input("Toi : ")` |
| 2 | Check exit commands | case-insensitive match |
| 3 | Record user message | Conversation.add_message("Nolan", question) |
| 4 | Generate response | Brain.think(question) |
| 5 | Record Titan response | Conversation.add_message("Titan", reponse) |
| 6 | Print response | stdout |
| 7 | Run agent again | AgentManager.auto_execute(question) — **second agent pass** |
| 8 | Print agent result | stdout |
| 9 | Show full conversation history | Conversation.show_history() |

**Critical:** Speaker is always hardcoded `"Nolan"` in conversation recording regardless of actual user.

### Phase 3: Brain Pipeline — `Brain.think(message)`

**File:** `brain/brain.py`

This is the cognitive core. Exact order as implemented:

#### Stage 3.1 — Knowledge Search

```
knowledge = self.knowledge.search(message)
```

- **Class:** `Knowledge`
- **Behavior:** Lowercases question; matches French keywords `créateur`, `nom`, `version`
- **Returns:** String fact or `None`
- **Side effect:** Prints `"Recherche dans la base de connaissances..."`

#### Stage 3.2 — Context Load

```
context = self.context_manager.get_context()
```

- **Class:** `ContextManager` (Brain's instance)
- **Returns:** Formatted multi-line French text block with user, project, goal, phase

#### Stage 3.3 — Long-Term Memory Load

```
full_memory = self.long_memory.get_memory()
```

- **Class:** `LongTermMemory`
- **Returns:** Full Python dict from `data/long_term_memory.json`

#### Stage 3.4 — Memory Retrieval

```
memory = self.memory_retriever.retrieve(full_memory, message)
```

- **Class:** `MemoryRetriever`
- **Behavior:** Word overlap search across user notes, preferences, projects, titan metadata
- **Returns:** Relevant string lines or `"Aucune mémoire pertinente trouvée."`

#### Stage 3.5 — State Load

```
state = self.state_manager.get_state()
```

- **Class:** `StateManager`
- **Returns:** Dict from `data/titan_state.json`

#### Stage 3.6 — Mission Load or Create

```
if not self.mission_manager.get_mission()["active"]:
    self.mission_manager.create_mission_from_message(message)
mission = self.mission_manager.get_mission()
```

- **Class:** `MissionManager`
- **Behavior:** If no active mission, creates one from keyword templates
- **Templates:**
  - `trading` / `robot` / `bot` → 7-step trading robot mission
  - `titan` → 5-step improve Titan mission
  - default → 4-step general mission

#### Stage 3.7 — Debug Output Block 1

Prints: mission JSON, state dict, executive analysis (next stage), retrieved memory, context, knowledge.

#### Stage 3.8 — Executive Analysis

```
executive_analysis = self.executive_brain.analyze_mission(
    message, context, memory, state, mission
)
```

- **Class:** `ExecutiveBrain`
- **Returns:** Large formatted template embedding all inputs plus mission-following rules
- **Note:** Parameter named `mission` in template shadows outer mission dict inside f-string construction — still works because outer mission is interpolated before inner template assignment

#### Stage 3.9 — Internal Monologue

```
thoughts = self.monologue.think(message, context)
```

- **Class:** `InternalMonologue`
- **Returns:** Formatted template with message and context

#### Stage 3.10 — Reasoning

```
analysis = self.reasoning.analyze(message)
```

- **Class:** `Reasoning`
- **Returns:**
  ```python
  {
      "message": message,
      "goal": "Comprendre la demande de l'utilisateur",
      "needs_memory": False,
      "needs_tool": False,
      "needs_clarification": False
  }
  ```

#### Stage 3.11 — Planning

```
plan = self.planning.create_plan(message)
```

- **Class:** `Planning`
- **Returns:** List of 5 generic French steps including goal echo

#### Stage 3.12 — Execution Strategy Selection

```
action = self.executor.execute(analysis)
```

- **Class:** `Executor`
- **Returns:** One of:
  - `"Utiliser un outil"` (if needs_tool — never true today)
  - `"Consulter la mémoire"` (if needs_memory — never true today)
  - `"Poser une question"` (if needs_clarification — never true today)
  - `"Répondre directement"` (default always today)

#### Stage 3.13 — Decision Classification

```
decision = self.decision.decide(message)
```

- **Class:** `Decision`
- **Returns:** `"salutation"` if `"bonjour"` in message, else `"conversation"`
- **Note:** Decision result is printed but **not used** in prompt assembly

#### Stage 3.14 — Initial Prompt Construction

Builds prompt string with sections:

1. CONTEXTE ACTUEL
2. MÉMOIRE PERMANENTE — uses `self.long_memory.show_memory()` (full JSON dump, not just retrieved subset)
3. ÉTAT ACTUEL
4. MISSION ACTIVE
5. EXECUTIVE ANALYSIS
6. QUESTION DE L'UTILISATEUR

**Note:** Retrieved relevant memory from Stage 3.4 is shown in debug prints but the prompt uses **full memory JSON** at this stage.

#### Stage 3.15 — Memory Write Decision

```
should_save = self.memory_decider.should_remember(message)
```

If true:

1. `category = self.memory_classifier.classify(message)`
2. `self.long_memory.remember_user_note("Nolan", f"[{category}] {message}")`
3. Saves to `data/long_term_memory.json`

**Keywords triggering save:** souviens-toi, rappelle-toi, remember, note, garde en mémoire, mets en mémoire, mon objectif, ma préférence, j'aime, je préfère, important, projet, stratégie, ibrahim, nolan, titan

**Categories:** goals, preferences, projects, notes (default)

#### Stage 3.16 — Agent Orchestration

```
orchestrator_results = self.task_orchestrator.orchestrate(message)
orchestrator_summary = self.task_orchestrator.format_results(orchestrator_results)
```

See Orchestration section below.

Prompt extended with:

7. RÉSULTATS DES AGENTS

#### Stage 3.17 — LLM Call

```
reponse = self.llm.ask(prompt)
```

- **Class:** `LLM`
- **API:** `client.responses.create(model="gpt-5.2", instructions=..., input=prompt)`
- **Returns:** `response.output_text`

#### Stage 3.18 — Mission Step Evaluation

```
if self.task_evaluator.is_step_completed(message, reponse, mission):
    self.mission_manager.complete_current_step()
```

Completion triggers on keywords in user message OR LLM response, or if user says continue/prochaine étape/avance.

#### Stage 3.19 — State Update

```
self.state_manager.update_after_response(message, reponse)
```

Updates `last_user_message` and `last_titan_response` in JSON.

#### Stage 3.20 — Return

Returns `reponse` string to `Titan.start()`.

### Phase 4: Post-Brain Agent Pass (Shell Layer)

```
agent_result = self.agents.auto_execute(question)
```

- Uses `Titan.agents` (separate AgentManager instance)
- `AgentSelector.select_agent()` picks **one** agent based on keywords
- Executes single agent — **different from orchestrator multi-agent path inside Brain**

### End-to-End Flow Diagram

```
┌─────────────┐
│   main.py   │
└──────┬──────┘
       │
       ▼
┌─────────────┐     startup: memory, time, context
│    Titan    │────────────────────────────────────┐
└──────┬──────┘                                    │
       │ REPL loop                                  │
       ▼                                            │
┌─────────────┐                                    │
│Conversation │◄── record user + titan messages    │
└─────────────┘                                    │
       │                                            │
       ▼                                            │
┌─────────────────────────────────────────┐        │
│              Brain.think()               │        │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ │        │
│  │Knowledge│ │ Context  │ │ Memory   │ │        │
│  └─────────┘ └──────────┘ └──────────┘ │        │
│  ┌─────────┐ ┌──────────┐               │        │
│  │ State   │ │ Mission  │               │        │
│  └─────────┘ └──────────┘               │        │
│  ┌─────────────────────────────────────┐ │        │
│  │ Monologue → Reason → Plan → Execute │ │        │
│  │ → Decision (mostly debug output)    │ │        │
│  └─────────────────────────────────────┘ │        │
│  ┌─────────────────────────────────────┐ │        │
│  │ Memory save? → Orchestrator → LLM   │ │        │
│  └─────────────────────────────────────┘ │        │
│  ┌─────────────────────────────────────┐ │        │
│  │ TaskEvaluator → State update        │ │        │
│  └─────────────────────────────────────┘ │        │
└──────────────────┬──────────────────────┘        │
                   │ response                       │
                   ▼                                │
              print response                        │
                   │                                │
                   ▼                                │
         AgentManager.auto_execute()  ◄─────────────┘
                   │
                   ▼
         print agent result + history
```

---

## Memory Flow

### Memory Layers in Titan

| Layer | Implementation | Scope | Persisted? |
|-------|----------------|-------|------------|
| Short-term session | `Memory` via `MemoryManager` | Current session startup notes | No (RAM) |
| Conversation | `Conversation.history` | Full dialogue list | No (RAM) |
| Long-term permanent | `LongTermMemory` | Users, notes, preferences, projects, Titan meta | Yes (`data/long_term_memory.json`) |
| Operational state | `StateManager` | Project step, last messages, progress | Yes (`data/titan_state.json`) |
| Mission state | `MissionManager` | Multi-step goal tracking | Yes (`data/titan_mission.json`) |

### Long-Term Memory Schema

**File:** `data/long_term_memory.json`

```json
{
    "users": {
        "Nolan": {
            "role": "...",
            "authority": "...",
            "preferences": [],
            "projects": [],
            "notes": []
        },
        "Ibrahim": { ... }
    },
    "titan": {
        "mission": "...",
        "current_project": "...",
        "current_phase": "..."
    }
}
```

**Current live data (Nolan notes include):**

- `"Je préfère travailler la nuit."`
- `"[projects] salut titan"`
- `"[projects] Salut Titan, quelle est ta prochaine étape ?"`

### Read Path (Brain)

```
LongTermMemory.load_memory()
    → get_memory() returns dict
        → MemoryRetriever.retrieve(dict, user_message)
            → word overlap filter
                → relevant string OR "Aucune mémoire pertinente trouvée."
                    → shown in debug output
                    → full memory JSON also injected into LLM prompt via show_memory()
```

### Write Path (Brain)

```
User message
    → MemoryDecider.should_remember(message)
        → if True:
            → MemoryClassifier.classify(message)
                → LongTermMemory.remember_user_note("Nolan", "[category] message")
                    → append to users.Nolan.notes
                        → save_memory() to JSON
```

### Memory Class Details

#### Class: `Memory`

**File:** `memory/memory.py`

| Attribute | Type | Purpose |
|-----------|------|---------|
| `short_term` | list | Session notes |
| `long_term` | list | **Unused** in current flow |

| Method | Behavior |
|--------|----------|
| `remember(information)` | Appends to short_term |
| `show_memory()` | Prints all short_term items |

#### Class: `MemoryManager`

**File:** `memory/memory_manager.py`

Facade over `Memory`. Used by `Titan` at startup only.

| Method | Behavior |
|--------|----------|
| `remember(information)` | Delegates to Memory |
| `show_memory()` | Delegates to Memory |

#### Class: `LongTermMemory`

**File:** `memory/long_term_memory.py`

| Method | Behavior |
|--------|----------|
| `load_memory()` | Load JSON or return default schema with Nolan + Ibrahim |
| `save_memory()` | Write JSON with mkdir |
| `get_memory()` | Return in-memory dict |
| `remember(category, key, value)` | Generic key-value store under category |
| `show_memory()` | JSON.dumps formatted string |
| `remember_user_note(user, note)` | Append to user's notes list |

#### Class: `MemoryDecider`

**File:** `memory/memory_decider.py`

| Method | Behavior |
|--------|----------|
| `should_remember(message)` | Keyword scan → bool |
| `classify_memory(message)` | **Unused in pipeline** — returns Nolan/Ibrahim/titan/general |

#### Class: `MemoryClassifier`

**File:** `memory/memory_classifier.py`

| Method | Behavior |
|--------|----------|
| `classify(message)` | Returns goals, preferences, projects, or notes |

#### Class: `MemoryRetriever`

**File:** `memory/memory_retriever.py`

| Method | Behavior |
|--------|----------|
| `retrieve(memory, message)` | Word overlap across all users' notes, preferences, projects, and titan keys |

**Retrieval limitation:** Searches all users — no filter by current user identity.

---

## Context Flow

### What Context Means in Titan

Context is **situational metadata** about who is using Titan, on what project, with what goal, in what phase. It is distinct from long-term memory (durable facts) and state (operational continuity).

### Active Context Path

```
ContextManager.__init__()
    → static defaults:
        current_user = "Nolan"
        active_project = "Titan"
        current_goal = "Construire le meilleur assistant personnel possible."
        current_phase = "Développement"

ContextManager.get_context()
    → formatted French text block

Used by:
    - Titan.start() at startup (instance on Titan)
    - Brain.think() (separate instance inside Brain)
    - InternalMonologue.think(message, context)
    - ExecutiveBrain.analyze_mission(..., context, ...)
    - LLM prompt section CONTEXTE ACTUEL
```

### Inactive Context Path

**File:** `core/context.py` — Class `Context`

| Field | Default |
|-------|---------|
| current_user | "Nolan" |
| current_project | "Titan" |
| current_mode | "development" |
| last_action | None |

Returns Python dict, not formatted text. **Not imported anywhere.**

### Context Gaps

- Does not read from StateManager
- Does not read from MissionManager
- Does not update after responses
- Two duplicate ContextManager instances
- Conversation history not part of context
- Ibrahim never set as current_user automatically

### Target Context Flow (Future)

```
StateManager + MissionManager + user identification
    → ContextManager.update_from_state()
        → get_context() for prompts
```

---

## Mission Flow

### Mission Schema

**File:** `data/titan_mission.json`

```json
{
    "active": true,
    "title": "Créer un robot de trading",
    "objective": "Crée un robot de trading pour le NQ",
    "steps": ["...", "..."],
    "current_step": "Créer le système de backtest",
    "status": "in_progress"
}
```

### Current Live Mission State

| Field | Value |
|-------|-------|
| active | true |
| title | Créer un robot de trading |
| objective | Crée un robot de trading pour le NQ |
| current_step | Créer le système de backtest |
| remaining steps | backtest, execution, risk, logs/monitoring, paper trading |
| completed steps (inferred) | Définir le marché et la stratégie, Créer l'architecture du robot |

Steps were removed from the list as `complete_current_step()` removes current step from array.

### Mission Lifecycle

```
Brain.think(message)
    │
    ├─ mission.active == False?
    │       └─ YES → MissionManager.create_mission_from_message(message)
    │                 └─ keyword templates assign title, objective, steps
    │
    ├─ mission loaded into prompt + executive analysis
    │
    ├─ LLM generates response
    │
    └─ TaskEvaluator.is_step_completed(message, response, mission)?
            └─ YES → MissionManager.complete_current_step()
                        ├─ remove current_step from steps list
                        ├─ set current_step to steps[0] or None
                        └─ if no steps: active=False, status="completed"
```

### Class: `MissionManager`

**File:** `core/mission_manager.py`

| Method | Behavior |
|--------|----------|
| `load_mission()` | Load JSON or idle default |
| `save_mission()` | Persist to file |
| `create_mission(title, objective, steps)` | Set active mission |
| `get_mission()` | Return dict |
| `complete_current_step()` | Advance or complete |
| `show_mission()` | JSON string for display |
| `create_mission_from_message(message)` | Template-based mission creation |
| `advance_mission()` | Wrapper calling complete_current_step |

### Mission Templates

**Trading keywords** (`trading`, `robot`, `bot`):

1. Définir le marché et la stratégie
2. Créer l'architecture du robot
3. Créer le système de backtest
4. Créer le système d'exécution
5. Ajouter la gestion du risque
6. Ajouter les logs et le monitoring
7. Tester en paper trading

**Titan keywords** (`titan`):

1. Comprendre l'amélioration demandée
2. Modifier l'architecture si nécessaire
3. Ajouter ou modifier les fichiers
4. Tester le fonctionnement
5. Sauvegarder l'état du projet

**Default:**

1. Comprendre la demande
2. Créer un plan
3. Exécuter la première étape
4. Vérifier le résultat

### Executive Brain Mission Rules (Template)

Embedded in every executive analysis:

- Respect active mission
- Respond according to current step
- Do not revert to completed steps
- If user says "continue", continue current step
- Treat with logic, precision, efficiency

---

## Planning

Planning exists at **two levels** in Titan:

### Level 1: Brain Planning Module

**File:** `brain/planning.py` — Class `Planning`

| Method | Input | Output |
|--------|-------|--------|
| `create_plan(goal)` | User message string | List of 5 generic steps |

Always returns:

1. Comprendre l'objectif : {goal}
2. Identifier les informations nécessaires
3. Choisir les bons outils
4. Exécuter les actions dans le bon ordre
5. Vérifier le résultat

**Status:** Template only. Printed to console. **Not injected into LLM prompt.**

### Level 2: Planning Agent

**File:** `agents/planning_agent.py` — Class `PlanningAgent`

Returns formatted 5-step plan template for any task. Invoked by orchestrator or auto_execute.

**Status:** Template only. Results **are** injected into LLM prompt via orchestrator.

### Level 3: Mission Steps

**File:** `core/mission_manager.py`

Multi-step persisted plans for long-running goals. These **are** in the LLM prompt.

### Level 4: Task Manager Plans

**File:** `core/task_manager.py`

Decomposes message into ordered agent tasks — operational plan, not user-facing plan.

### Planning Gap

Brain's `Planning.create_plan()` output is debug-only. The LLM never sees it directly. Real planning in production today comes from mission steps + agent orchestration results + LLM's own reasoning.

---

## Reasoning

### Brain Reasoning Module

**File:** `brain/reasoning.py` — Class `Reasoning`

| Method | Output |
|--------|--------|
| `analyze(message)` | Dict with message, goal, three boolean flags (all False) |

The analysis dict feeds `Executor.execute()` but flags never enable alternate paths today.

**Status:** Stub. Printed to console. **Not in LLM prompt.**

### Reasoning Agent

**File:** `agents/reasoning_agent.py` — Class `ReasoningAgent`

Returns: `"{name} a trouvé un raisonnement pour : {task}"`

Invoked by orchestrator for most message types (default path includes reasoning + planning agents).

**Status:** Template. Result **is** in LLM prompt via orchestrator.

### Executive Brain

Strategic reasoning template combining mission, context, memory, state.

**Status:** Template in prompt.

### Real Reasoning Today

Performed by **GPT-5.2** when processing the assembled prompt. Internal Python reasoning modules are scaffolding.

---

## Execution

Execution in Titan refers to multiple distinct concepts:

### 1. Brain Executor Module

**File:** `brain/executor.py` — Class `Executor`

Maps reasoning analysis to action label:

| Condition | Return |
|-----------|--------|
| needs_tool | "Utiliser un outil" |
| needs_memory | "Consulter la mémoire" |
| needs_clarification | "Poser une question" |
| default | "Répondre directement" |

**Today:** Always returns `"Répondre directement"`.

**Not connected to ToolManager.** Tools are not invoked from Brain pipeline.

### 2. Agent Execution

**File:** `agents/agent_manager.py`

| Method | Behavior |
|--------|----------|
| `execute(agent_name, task)` | Dispatch to registered agent |
| `auto_execute(task)` | Select one agent → execute |

Agents produce text artifacts, not side effects (no file writes, no API calls).

### 3. Task Orchestrator Execution

**File:** `core/task_orchestrator.py`

Runs multiple agents sequentially for one message. Primary execution path feeding LLM.

### 4. Action Manager (Unused)

**File:** `core/action_manager.py` — Class `ActionManager`

| Method | Behavior |
|--------|----------|
| `execute(action)` | Print and return confirmation string |

Never imported. Intended future layer for discrete actions.

### 5. LLM Response Execution

The only execution that materially affects the user today: `LLM.ask()` generating natural language response.

### 6. Persistence Execution

After response:

- `StateManager.update_after_response()` writes JSON
- `MissionManager.complete_current_step()` may write JSON
- `LongTermMemory.remember_user_note()` may write JSON

---

## Orchestration

### Components

| Component | Role |
|-----------|------|
| `TaskManager` | Creates list of (agent_name, task) tuples from message keywords |
| `TaskOrchestrator` | Executes task list sequentially via AgentManager |
| `AgentManager` | Registry and dispatch |
| Individual agents | Execute task strings, return text |

### TaskManager Routing Rules

**Code keywords** (`code`, `python`, `fonction`):

1. planning → "Créer un plan pour : {message}"
2. coding → "Écrire une solution de code pour : {message}"
3. reasoning → "Vérifier la logique de la solution pour : {message}"

**Planning keywords** (`organise`, `planning`, `journée`):

1. planning → "Organiser la demande : {message}"
2. reasoning → "Vérifier si le plan est logique : {message}"

**Research keywords** (`recherche`, `internet`, `information`):

1. research → "Analyser la recherche demandée : {message}"
2. reasoning → "Résumer et vérifier les informations pour : {message}"

**Default (all other messages):**

1. reasoning → "Comprendre et analyser la demande : {message}"
2. planning → "Proposer une prochaine étape pour : {message}"

### Orchestrator Flow

```
TaskOrchestrator.orchestrate(message)
    → tasks = TaskManager.create_tasks(message)
    → for each (agent_name, task):
          result = AgentManager.execute(agent_name, task)
          append {agent, task, result} to results
    → return results

TaskOrchestrator.format_results(results)
    → single formatted string for LLM prompt
```

### AgentSelector (Separate Path)

Used only by `Titan.agents.auto_execute()` after Brain response.

Priority order: coding → research → planning → reasoning → base

Returns **one** agent name. Different from multi-agent orchestrator.

### Orchestration Problem

Two routing systems with different logic:

- `TaskManager.create_tasks()` — multi-agent
- `AgentSelector.select_agent()` — single agent

Both use overlapping but not identical keyword sets. Both run per turn.

---

## Role of Every Manager

### MemoryManager

**File:** `memory/memory_manager.py`

**Role:** Facade for in-memory session notes at startup.

**Used by:** `Titan.__init__`, `Titan.start()` only.

**Does not interact with:** LongTermMemory, Brain.

### LongTermMemory

**File:** `memory/long_term_memory.py`

**Role:** Persistent JSON storage for users, notes, preferences, projects, Titan metadata.

**Used by:** Brain pipeline (read, write, prompt injection).

### StateManager

**File:** `core/state_manager.py`

**Role:** Operational continuity across sessions.

**Fields:**

| Key | Purpose |
|-----|---------|
| active_project | Current project name |
| current_step | Development/operational step label |
| last_user_message | Previous user input |
| last_titan_response | Previous Titan output |
| next_action | Suggested next engineering action |
| progress | Progress label |

**Used by:** Brain — loaded into prompt, updated after each response.

**Not auto-updated:** current_step, next_action, progress from Brain logic.

### MissionManager

**File:** `core/mission_manager.py`

**Role:** Multi-step goal tracking with persistence.

**Used by:** Brain — create, load, advance missions; inject into prompt.

### ContextManager

**File:** `context/context_manager.py`

**Role:** Format situational context for prompts and analysis templates.

**Used by:** Titan.start(), Brain.think(), monologue, executive brain.

### AgentManager

**File:** `agents/agent_manager.py`

**Role:** Agent registry, manual execute, auto-select execute.

**Registered agents:** base, coding, research, planning, reasoning.

**Instantiated twice:** Titan.agents and Brain.agent_manager.

### TaskManager

**File:** `core/task_manager.py`

**Role:** Message → ordered agent task list.

**Used by:** TaskOrchestrator, optionally `execute_tasks()` directly.

### TaskOrchestrator

**File:** `core/task_orchestrator.py`

**Role:** Run task list, collect results, format for LLM.

**Used by:** Brain.think() only.

### ToolManager

**File:** `tools/tool_manager.py`

**Role:** Tool registry facade.

**Current tools:** TimeTool only.

**Used by:** Titan.start() for startup time display. **Not used by Brain.**

### Conversation

**File:** `core/conversation.py`

**Role:** In-session dialogue history list.

**Not a "manager" but session state.** Not passed to Brain or LLM.

### ActionManager (Unused)

**File:** `core/action_manager.py`

**Role:** Planned discrete action execution. Not wired.

---

## Role of Every Agent

### BaseAgent

**File:** `agents/base_agent.py`

**Role:** Abstract base. Default execute prints and returns completion string.

**Registered as:** `"base"` — fallback when no keyword matches in AgentSelector.

### CodingAgent

**File:** `agents/coding_agent.py`

**Role:** Code-related tasks.

**Trigger keywords:** code, python, fonction, programmer, script

**Output:** Canned Python addition function example.

**Future:** Real code generation with file context and LLM.

### ResearchAgent

**File:** `agents/research_agent.py`

**Role:** Information gathering tasks.

**Trigger keywords:** recherche, chercher, internet, google, information, actualité

**Output:** Placeholder research suggestion string.

**Future:** Web search tool integration.

### PlanningAgent

**File:** `agents/planning_agent.py`

**Role:** Organization and planning tasks.

**Trigger keywords:** plan, planning, organise, organiser, horaire, programme

**Output:** 5-step formatted plan template.

### ReasoningAgent

**File:** `agents/reasoning_agent.py`

**Role:** Logic analysis and verification.

**Trigger keywords:** pourquoi, analyse, raisonne, réfléchis, explique, logique

**Output:** Placeholder reasoning string.

**Also invoked:** By TaskManager default path and coding path.

### AgentSelector

**File:** `agents/agent_selector.py`

**Role:** Single-agent routing for auto_execute path. Not a worker agent but routing logic.

### Future Agents (Constitution Article 8.2)

Not implemented: Trading Agent, Memory Agent, Vision Agent, Voice Agent, Web Agent, Automation Agent.

---

## Complete Class Reference

Every class in the repository:

| Class | File | Instantiated by | Purpose |
|-------|------|-----------------|---------|
| `Titan` | core/titan.py | main.py | Application shell |
| `Brain` | brain/brain.py | Titan | Cognitive pipeline |
| `Decision` | brain/decision.py | Brain | Intent classification stub |
| `Reasoning` | brain/reasoning.py | Brain | Analysis dict stub |
| `Planning` | brain/planning.py | Brain | Generic plan list stub |
| `Knowledge` | brain/knowledge.py | Brain | Hardcoded fact lookup |
| `Executor` | brain/executor.py | Brain | Action label from analysis |
| `LLM` | brain/llm.py | Brain | OpenAI gateway |
| `InternalMonologue` | brain/internal_monologue.py | Brain | Template reflection |
| `ExecutiveBrain` | brain/executive_brain.py | Brain | Strategic template |
| `TaskEvaluator` | brain/task_evaluator.py | Brain | Mission step completion |
| `AgentManager` | agents/agent_manager.py | Titan, Brain | Agent registry (×2) |
| `AgentSelector` | agents/agent_selector.py | AgentManager | Single-agent routing |
| `BaseAgent` | agents/base_agent.py | AgentManager | Agent base |
| `CodingAgent` | agents/coding_agent.py | AgentManager | Code tasks |
| `ResearchAgent` | agents/research_agent.py | AgentManager | Research tasks |
| `PlanningAgent` | agents/planning_agent.py | AgentManager | Planning tasks |
| `ReasoningAgent` | agents/reasoning_agent.py | AgentManager | Reasoning tasks |
| `MemoryManager` | memory/memory_manager.py | Titan | Session memory facade |
| `Memory` | memory/memory.py | MemoryManager | Short-term list |
| `LongTermMemory` | memory/long_term_memory.py | Brain | JSON persistence |
| `MemoryDecider` | memory/memory_decider.py | Brain | Save trigger |
| `MemoryClassifier` | memory/memory_classifier.py | Brain | Note category |
| `MemoryRetriever` | memory/memory_retriever.py | Brain | Relevance filter |
| `StateManager` | core/state_manager.py | Brain | State JSON |
| `MissionManager` | core/mission_manager.py | Brain | Mission JSON |
| `TaskManager` | core/task_manager.py | Brain | Task decomposition |
| `TaskOrchestrator` | core/task_orchestrator.py | Brain | Multi-agent run |
| `Conversation` | core/conversation.py | Titan | Dialogue history |
| `ActionManager` | core/action_manager.py | **None** | Unused stub |
| `Context` | core/context.py | **None** | Unused dict context |
| `ContextManager` | context/context_manager.py | Titan, Brain | Formatted context |
| `ToolManager` | tools/tool_manager.py | Titan | Tool facade |
| `TimeTool` | tools/time_tool.py | ToolManager | Datetime string |

**Module-level constant (not a class):**

| Name | File | Used? |
|------|------|-------|
| `IDENTITY` | brain/identity.py | No |

---

# Folder Reference

## Root (`/`)

### Purpose

Application root. Entry point, configuration, documentation, runtime data, and all Python packages.

### Responsibilities

- Host `main.py` entry point
- Store product documentation (Blueprint, Context, Constitution)
- Store runtime JSON in `data/`
- Define Cursor engineering rules in `.cursor/rules/`
- Hold secrets in `.env` (not committed)

### Dependencies

- Python 3 runtime
- Packages from `requirements.txt`
- `OPENAI_API_KEY` in environment

### Future Evolution

- Add `pyproject.toml`, `README.md`, `.env.example`
- Add `tests/`, `logs/`, `prompts/`
- Possible packaging as installable CLI `titan`

---

## `config/`

### Purpose

Static, non-secret application configuration.

### Responsibilities

- Define `TITAN_NAME`, `VERSION`, `CREATOR`
- Future: default file paths, model names, feature flags, log levels

### Dependencies

- None (leaf module)

### Files

| File | Content |
|------|---------|
| `settings.py` | Three constants today |

### Future Evolution

- `MODEL_NAME = "gpt-5.2"`
- `MEMORY_PATH`, `STATE_PATH`, `MISSION_PATH`
- `DEBUG_MODE`, `LOG_LEVEL`
- Optional `settings_local.py` gitignored override

---

## `core/`

### Purpose

Application orchestration, session management, persisted operational state, missions, and product constitution.

### Responsibilities

- `Titan` class — composition root and REPL
- Conversation tracking
- Task decomposition and orchestration
- State and mission persistence
- Product constitution document storage

### Dependencies

- config/settings
- brain, memory, tools, context, agents modules

### Files

| File | Role |
|------|------|
| titan.py | Main application class |
| conversation.py | Session dialogue |
| task_manager.py | Agent task creation |
| task_orchestrator.py | Multi-agent execution |
| state_manager.py | State JSON |
| mission_manager.py | Mission JSON |
| action_manager.py | Unused |
| context.py | Unused duplicate |
| constitution/titan_constitution.md | Product governance |

### Future Evolution

- Unified dependency injection in Titan.__init__
- Wire ActionManager to Brain Executor
- Load constitution summary for prompts
- `core/logging_config.py`
- `core/exceptions.py`

---

## `brain/`

### Purpose

Cognitive center. Reasoning pipeline, LLM integration, executive analysis, mission evaluation.

### Responsibilities

- Orchestrate full think pipeline
- Assemble LLM prompts
- Connect memory, state, mission, context, agents
- Call OpenAI API
- Evaluate mission progress

### Dependencies

- openai, python-dotenv
- context, memory, core, agents modules

### Files

| File | Role |
|------|------|
| brain.py | Central orchestrator |
| llm.py | OpenAI client |
| executive_brain.py | Strategic template |
| internal_monologue.py | Reflection template |
| reasoning.py | Analysis stub |
| planning.py | Plan stub |
| decision.py | Classification stub |
| executor.py | Action label stub |
| knowledge.py | Fact lookup |
| task_evaluator.py | Step completion |
| identity.py | Unused identity text |

### Future Evolution

- Real LLM-backed reasoning/planning or pipeline simplification
- Load identity + constitution into LLM instructions
- Inject conversation history
- Connect executor to ToolManager
- Dependency injection from Titan
- Prompt builder module extraction

---

## `agents/`

### Purpose

Internal specialist workers coordinated by Brain.

### Responsibilities

- Domain-specific task execution
- Return structured text for prompt injection
- Register in AgentManager

### Dependencies

- base_agent only (currently)
- Future: tools, LLM sub-calls

### Files

| File | Role |
|------|------|
| agent_manager.py | Registry and dispatch |
| agent_selector.py | Keyword routing |
| base_agent.py | Base class |
| coding_agent.py | Code specialist |
| research_agent.py | Research specialist |
| planning_agent.py | Planning specialist |
| reasoning_agent.py | Reasoning specialist |

### Future Evolution

- LLM-powered agents with focused prompts
- Tool access per agent type
- Trading, Web, Memory, Vision, Voice, Automation agents
- Shared routing registry with TaskManager
- Single AgentManager instance

---

## `memory/`

### Purpose

Knowledge persistence and retrieval.

### Responsibilities

- Session short-term memory (startup)
- Long-term JSON memory
- Save decision, classification, retrieval

### Dependencies

- json, os standard library
- No upstream Titan imports (leaf domain)

### Files

| File | Role |
|------|------|
| memory.py | In-memory lists |
| memory_manager.py | Startup facade |
| long_term_memory.py | JSON persistence |
| memory_decider.py | Save triggers |
| memory_classifier.py | Categories |
| memory_retriever.py | Relevance search |

### Future Evolution

- Unified MemoryService facade
- User-aware writes (Nolan vs Ibrahim)
- Semantic/embedding retrieval
- Memory summarization and compaction
- Project-scoped memory namespaces
- SQLite or vector store backend

---

## `context/`

### Purpose

Situational context for prompts.

### Responsibilities

- Track current user, project, goal, phase
- Format context block for Brain and LLM

### Dependencies

- None currently (should depend on State/Mission in future)

### Files

| File | Role |
|------|------|
| context_manager.py | Active context implementation |

### Future Evolution

- Sync with StateManager and MissionManager
- Dynamic user identification
- Include recent conversation summary
- Remove duplicate core/context.py

---

## `tools/`

### Purpose

External capabilities and factual lookups.

### Responsibilities

- Register tools
- Provide ToolManager facade
- Execute bounded actions on world outside Python process

### Dependencies

- datetime (TimeTool)
- Future: requests, subprocess, filesystem

### Files

| File | Role |
|------|------|
| tool_manager.py | Registry |
| time_tool.py | Current datetime |

### Future Evolution

Per Constitution: Internet, Python execution, Files, Calendar, Email, TradingView, NinjaTrader, Discord, Notion.

- `file_tool.py`, `web_tool.py`, `python_tool.py`, `trading_tool.py`
- Plugin registration pattern
- Brain Executor integration

---

## `data/`

### Purpose

Runtime persistence. Not source code.

### Responsibilities

- Store long-term memory
- Store session state
- Store active mission

### Dependencies

- Written only through manager classes

### Files

| File | Managed by |
|------|------------|
| long_term_memory.json | LongTermMemory |
| titan_state.json | StateManager |
| titan_mission.json | MissionManager |

### Future Evolution

- Schema version fields
- Backup on corruption
- gitignore user-specific notes if needed
- Migration scripts

---

## `.cursor/rules/`

### Purpose

AI engineering governance for Cursor IDE.

### Responsibilities

- Enforce coding standards
- Document architecture rules
- Guide AI contributors

### Files

| File | Role |
|------|------|
| titan.mdc | Full engineering rulebook (1,722 lines) |

---

# Current Technical Debt

## Critical (Fix Before Scaling)

### 1. Duplicate AgentManager Instances

- `Titan.agents` and `Brain.agent_manager` are separate objects
- Separate agent registries, separate state
- **Fix:** Single instance created in Titan, injected into Brain

### 2. Double Agent Execution Per Turn

- Brain runs TaskOrchestrator (multi-agent)
- Titan runs auto_execute (single agent) after response
- Wastes compute, confuses architecture, may produce inconsistent outputs
- **Fix:** One orchestration path only

### 3. Dual Memory Systems

- MemoryManager (session) vs LongTermMemory (Brain) unconnected
- Memory.long_term list unused
- **Fix:** Unified MemoryService with short-term, long-term, conversation layers

### 4. Duplicate ContextManager Instances

- Titan.context and Brain.context_manager
- Both static, identical
- **Fix:** Single shared instance

### 5. Constitution and Identity Not Loaded

- 1,468-line constitution unused
- identity.py unused
- Product values partially in llm.py only
- **Fix:** Inject into LLM system instructions

## High (Functional Gaps)

### 6. Placeholder Cognitive Modules

- Reasoning, Planning, Decision, Executor, Monologue, ExecutiveBrain are templates
- Create illusion of pipeline without real logic
- **Fix:** LLM-back or collapse until needed

### 7. Template Agents

- Agents return canned strings, not real work
- **Fix:** LLM sub-calls with domain prompts and optional tools

### 8. Static Context

- Never updates from state/mission
- Always Nolan/Titan/development
- **Fix:** Dynamic context sync

### 9. Hardcoded Nolan in Memory Writes

```python
self.long_memory.remember_user_note("Nolan", ...)
```

- Ibrahim cannot be memory write target
- **Fix:** Use ContextManager.current_user

### 10. Mission Auto-Creation Overwrites

- Any message when mission inactive creates new mission
- **Fix:** Explicit mission commands or confirmation

### 11. TaskEvaluator False Positives

- `"continue"`, `"fait"`, `"terminé"` advance mission steps easily
- Live state shows mission advanced past architecture step on "continue"
- **Fix:** Stricter completion criteria, LLM structured output, user confirmation

### 12. Full Memory Dump in Prompt

- Prompt uses show_memory() full JSON, not retrieved subset
- Increases tokens, may include irrelevant notes
- **Fix:** Use MemoryRetriever result in prompt

### 13. Conversation Not in LLM Prompt

- History tracked but Brain never sees it
- **Fix:** Include recent N messages in prompt

### 14. State Fields Stale

- current_step, next_action, progress not updated by Brain
- **Fix:** StateManager.update_from_brain_pipeline()

## Medium (Engineering Quality)

### 15. Unused Modules

- core/action_manager.py
- core/context.py
- brain/identity.py
- MemoryDecider.classify_memory() unused

### 16. No Tests

- Zero automated tests
- **Fix:** pytest suite for managers and routing

### 17. No Logging

- Dozens of print statements in Brain
- **Fix:** logging module with levels

### 18. No Error Handling on REPL

- Brain exception crashes session
- LLM failure unhandled
- **Fix:** try/except with graceful French message

### 19. No Package Structure

- No __init__.py
- Imports assume project root
- **Fix:** pyproject.toml with package definition

### 20. Blueprint Outdated

- Section 5 understates progress
- Section 6 says Claude, code uses OpenAI
- **Fix:** Update blueprint

### 21. Two Routing Systems

- TaskManager vs AgentSelector different keyword sets
- **Fix:** Shared routing registry

### 22. Brain Planning/Decision Not in Prompt

- Computed but only printed
- Dead computation every turn
- **Fix:** Include or remove

### 23. ToolManager Not in Brain

- Executor never calls tools
- Time only shown at startup
- **Fix:** Wire tools to executor decisions

### 24. Memory Retrieval Cross-User

- Searches all users' notes
- Violates constitution separation intent
- **Fix:** Filter by current user

### 25. Indentation Inconsistency

- titan.py start() method uses inconsistent spacing
- brain.py mixed indentation in places
- **Fix:** normalize on edit

## Low (Future Cleanup)

### 26. Missing Directories

- prompts/, logs/, tests/

### 27. Missing .env.example

### 28. No README

### 29. No type hints in existing code

### 30. No CI

### 31. Model name hardcoded in llm.py

### 32. TaskManager.execute_tasks() duplicates orchestrator — dead code path

---

# Future Roadmap

## Version 1 — Solid Foundation (v0.1.x → v1.0.0)

**Goal:** One coherent, trustworthy CLI assistant with real persistence and no architectural contradictions.

### v0.1 — Consolidation

- Single AgentManager, single ContextManager injected from Titan
- Remove double agent execution
- Unified memory facade (session + long-term + conversation)
- Wire identity.py and constitution summary into LLM instructions
- Delete or integrate unused modules (action_manager, core/context.py)
- Add logging module; replace prints in Brain
- Add error handling on REPL loop and LLM calls
- Dynamic context from StateManager + MissionManager
- User-aware memory writes
- Use retrieved memory in prompt, not full dump
- Include last N conversation turns in prompt
- Add pytest for StateManager, MissionManager, MemoryRetriever, TaskManager, AgentSelector
- Add `.env.example`, README, update Blueprint

### v0.2 — Real Agents

- LLM-backed agent execution with focused sub-prompts
- Shared keyword/intent routing registry
- File read tool (read project files for coding tasks)
- Stricter mission step completion (structured LLM signal or explicit user confirm)
- Explicit mission commands: `nouvelle mission`, `statut mission`, `continuer mission`

### v0.3 — Prompts Module

- Externalize all prompts to `prompts/`
- Personality module per Blueprint
- Constitution summary prompt
- Agent-specific prompt templates

### v1.0 — Production CLI

- Stable JSON schemas with version field
- Full test coverage on managers and routing
- Clean user-facing output (debug mode flag)
- Ibrahim user switching support
- Documented setup and deployment
- Changelog and version policy

---

## Version 2 — Capable Assistant (v2.0.0)

**Goal:** Titan can act on the world through tools and maintain rich project context.

### Tools

- File tool (read/write within project bounds)
- Python execution tool (sandboxed)
- Web search tool
- Calendar and email tools (optional integrations)

### Agents

- Web Agent with search tool
- Memory Agent for summarization and compaction
- Coding Agent with file tool + LLM
- Automation Agent for scripted workflows

### Memory

- Embedding-based retrieval
- Project-scoped memory namespaces
- Memory summarization when JSON grows
- Explicit forget/remember commands

### Interfaces

- Optional API server wrapping Brain (same core)
- Improved CLI with debug/verbose flags

### Trading (Begin)

- Trading Agent stub connected to mission system
- Market data read tool
- Backtest framework skeleton (aligned with active mission)

---

## Version 3 — Autonomous Partner (v3.0.0)

**Goal:** Multi-modal, proactive, trading-capable personal AI OS.

### Multi-Modal

- Voice Agent
- Voice user identification (Constitution Article 1.5)
- Vision Agent for screenshots/documents

### Trading System

- Full NQ robot pipeline per mission template:
  - Strategy definition
  - Backtest engine
  - Execution system
  - Risk management
  - Logging and monitoring
  - Paper trading
- NinjaTrader / Tradovate / IBKR integrations (per user platform choice)

### Proactivity

- Initiative engine (Constitution Article 11)
- Risk detection alerts
- Opportunity suggestions
- Priority management across projects

### Multi-Provider LLM

- Abstract LLM interface
- Model routing (small for classify, large for synthesis)
- Optional Anthropic/other providers

### Deployment

- Desktop wrapper or always-on service
- Scheduled tasks and automations

---

## Long-Term Vision

Titan becomes a **personal AI operating system** that Nolan and Ibrahim rely on daily for years:

- Knows each user's preferences, projects, and history in isolation
- Identifies speaker by voice
- Coordinates a team of specialist agents invisibly
- Uses tools across code, web, communication, and trading platforms
- Executes multi-week missions with reliable state
- Learns from outcomes (Constitution Article 10)
- Maintains constitution-aligned personality and values
- Improves measurably with each version
- Never degrades into a generic chatbot

Constitution closing principle:

> *L'objectif est de devenir, année après année, le meilleur partenaire d'intelligence possible pour Nolan et Ibrahim.*

Engineering serves that goal.

---

# Coding Standards

## Engineering Philosophy

Derived from Blueprint rule, Constitution, and `.cursor/rules/titan.mdc`:

### Every Line Must Earn Its Place

No throwaway code. No fake exercises. Every file must serve the final Titan system.

### Modular Monolith

One process, many modules, clear boundaries, registry patterns for agents and tools.

### Brain Conducts, Agents Specialize, Tools Act

Strict separation of concerns. No agent speaks directly to user as final voice.

### Minimal Diff Discipline

Change only what the task requires. No drive-by refactors. Match existing style.

### Truth and Durability Over Shortcuts

Prefer solutions that remain maintainable for years. Avoid technical debt that contradicts constitution Article 8.7.

### Test Before Scale

New modules require tests once `tests/` exists. Managers and pure logic first.

### Secrets Never in Code

API keys in `.env` only. Never commit secrets.

### French Product, English Code Identifiers

User-facing strings French. Code comments and new identifiers English preferred.

### Persistence Through Managers

Never scatter JSON writes. Always through StateManager, MissionManager, LongTermMemory.

### Single Composition Root Target

All shared services wired in Titan.__init__, injected into Brain.

## File Conventions

- Banner header: `# =====================================`
- snake_case.py filenames
- Manager/Agent/Tool class suffixes
- 4-space indentation
- Absolute imports from project root

## Prohibited Patterns

- Duplicate subsystem instances
- Circular imports
- Bare except
- eval() on user input
- Secrets in logs or commits
- Agents importing Brain
- Memory importing agents
- Direct data/*.json writes outside managers

---

# Things Cursor Must Always Remember

Permanent knowledge for any AI engineer working on Titan:

## Identity

1. **Titan is not a chatbot** — it is a personal agentic AI system for Nolan Hassing and Ibrahim.
2. **Creator:** Nolan Hassing. **Version:** 0.0.1. **Entry:** `python main.py`.
3. **Users speak to Titan**, never to internal agents directly in the final product.

## Architecture

4. **Brain.think()** is the cognitive entry point. Real responses come from **LLM.ask()** at end of pipeline.
5. **Composition root** is `core/titan.py` class `Titan`.
6. **Dependency direction:** main → Titan → Brain → (memory, agents, core managers). Memory and tools do not import Brain.
7. **Known bugs to not replicate:** two AgentManager instances, double agent execution per turn, two memory systems, two ContextManager instances.

## Data Files

8. **`data/long_term_memory.json`** — Nolan and Ibrahim user data, notes. Sensitive.
9. **`data/titan_state.json`** — last messages, project step, progress.
10. **`data/titan_mission.json`** — active mission; currently trading robot for NQ with backtest step active.
11. **Never corrupt JSON schemas** without migration.

## Memory Rules

12. **Never mix Nolan and Ibrahim personal memory.**
13. Memory writes go through MemoryDecider → MemoryClassifier → LongTermMemory.
14. Currently all saves hardcoded to user `"Nolan"` — known debt.

## LLM

15. **OpenAI Responses API**, model `gpt-5.2`, key from `OPENAI_API_KEY`.
16. **All LLM calls through brain/llm.py** only.
17. **Constitution and identity.py not yet loaded** — partial instructions in llm.py.
18. **French responses**, tutoiement, step-by-step, practical.

## Agents

19. **Five agents registered:** base, coding, research, planning, reasoning.
20. **Agents are templates today** — no real LLM inside agents yet.
21. **TaskOrchestrator** runs multi-agent inside Brain. **auto_execute** runs single agent after response — redundant.

## Missions

22. **Mission auto-created** when inactive on any message.
23. **TaskEvaluator** advances steps on keywords like `continue`, `terminé`, `fait` — easy false positives.
24. **Executive brain template** enforces mission-step-aware responses in prompt.

## Context

25. **ContextManager** returns static formatted block. Not synced with state/mission.
26. **Conversation history** stored but not sent to Brain/LLM.

## Tools

27. **Only TimeTool exists.** ToolManager not used in Brain pipeline.
28. **Executor never triggers tools** because reasoning flags always false.

## Unused Code

29. **Do not extend without integrating:** core/action_manager.py, core/context.py, brain/identity.py (unless wiring task).
30. **Constitution file** is product law but not runtime code yet.

## Documentation

31. **Titan_Blueprint.md** is partially outdated.
32. **`.cursor/rules/titan.mdc`** is engineering rulebook (1,722 lines).
33. **This file (Titan_Context.md)** is official knowledge base.

## Engineering Behavior

34. **Read full files and callers before editing.**
35. **Minimal scope diffs.** No unrelated changes.
36. **Do not commit unless user asks.**
37. **Do not create markdown files unless user asks** (this file was explicitly requested).
38. **Do not add tests unless requested or tests/ infrastructure exists and change requires them.**
39. **Run from project root** — no __init__.py packages yet.

## Product Values (from Constitution)

40. **Truth before convenience.**
41. **Quality before quantity.**
42. **Long-term over shortcuts.**
43. **Honesty about uncertainty.**
44. **Tools extend capability; Brain decides.**
45. **Memory is selective privilege, not total recording.**

## Guiding Question

46. Before any change, ask: **"Does this help Nolan or Ibrahim advance concretely?"**

47. Before any new file, ask: **"Does this belong in the final Titan system?"**

48. Before any refactor, ask: **"Am I fixing duplicate subsystems or creating a third parallel path?"**

---

# Appendix A: Runtime JSON Snapshots

## long_term_memory.json (summary)

- Nolan: creator, notes include night work preference and project-tagged messages
- Ibrahim: equal authority, empty notes/projects
- Titan meta: mission to help build/organize/automate projects, current project Titan, phase memory system development

## titan_state.json (summary)

- active_project: Titan
- current_step: Développement du State Manager
- last_user_message: continue
- next_action: Connecter le State Manager au Brain
- progress: En développement

## titan_mission.json (summary)

- Active trading robot mission for NQ
- current_step: Créer le système de backtest
- 5 steps remaining after prior completions

---

# Appendix B: LLM System Instructions (Current)

From `brain/llm.py`:

- Titan, private assistant of Nolan and Ibrahim
- French, tutoiement
- Clear, direct, practical
- Short responses unless asked otherwise
- One step at a time
- No large code blocks without exact context
- When Nolan builds Titan: precise file, location, copy-paste code
- Broad requests: propose simple plan first

---

# Appendix C: Import Graph (All Project Imports)

```
main.py
  └── core.titan

core.titan
  ├── config.settings
  ├── memory.memory_manager → memory.memory
  ├── brain.brain
  ├── tools.tool_manager → tools.time_tool
  ├── context.context_manager
  ├── core.conversation
  └── agents.agent_manager
        ├── agents.base_agent
        ├── agents.coding_agent → base_agent
        ├── agents.research_agent → base_agent
        ├── agents.planning_agent → base_agent
        ├── agents.reasoning_agent → base_agent
        └── agents.agent_selector

brain.brain
  ├── brain.decision
  ├── brain.reasoning
  ├── brain.planning
  ├── brain.knowledge
  ├── brain.executor
  ├── brain.llm → openai, dotenv
  ├── context.context_manager
  ├── brain.internal_monologue
  ├── memory.long_term_memory
  ├── memory.memory_decider
  ├── memory.memory_classifier
  ├── memory.memory_retriever
  ├── core.task_manager
  ├── core.task_orchestrator
  ├── agents.agent_manager (full tree again)
  ├── core.state_manager
  ├── brain.executive_brain
  ├── brain.task_evaluator
  └── core.mission_manager
```

**Modules with zero importers (orphans):**

- core.action_manager
- core.context
- brain.identity

---

# Appendix D: Constitution Structure (Reference)

`core/constitution/titan_constitution.md` — Version 1.0 Draft

| Article | Topic |
|---------|-------|
| Préambule | Nature and purpose |
| 1 | Identity — name, creator, users, voice recognition future |
| 2 | Fundamental philosophy — truth, reflection, long-term |
| 3 | Personality — tone, loyalty, humility, initiative |
| 4 | Core values — truth, honesty, logic, utility, quality |
| 5 | Decision making — understand, verify, explain, say no |
| 6 | Communication — clarity, tutoiement, technical code rules |
| 7 | Memory — layers, isolation, what to remember |
| 8 | Intelligent architecture — Brain, agents, tools, modularity |
| 9 | Tool usage — philosophy, verification, Brain decides |
| 10 | Learning and evolution |
| 11 | Initiative and proactivity |

Not loaded at runtime. Engineering should treat as product requirements source.

---

**End of Titan Context Document**

# Titan Brain System Audit

**Audit date:** 2026-06-23  
**Scope:** All files under `brain/`, `agents/`, `memory/`, `context/`, and `core/`  
**Method:** Full source read of every module in scope; import graph analysis; runtime path tracing from `main.py` → `Titan.start()` → `Brain.think()`  
**Constraint:** Read-only audit — no code was modified.

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [Responsibilities of Every Class](#2-responsibilities-of-every-class)
3. [Data Flow](#3-data-flow)
4. [Decision Flow](#4-decision-flow)
5. [Memory Flow](#5-memory-flow)
6. [Execution Flow](#6-execution-flow)
7. [Context Flow](#7-context-flow)
8. [Missing Implementations](#8-missing-implementations)
9. [Duplicate Logic](#9-duplicate-logic)
10. [Dead Code](#10-dead-code)
11. [Circular Dependencies](#11-circular-dependencies)
12. [Technical Debt](#12-technical-debt)
13. [Potential Bugs](#13-potential-bugs)
14. [Future Improvements](#14-future-improvements)
15. [Priority Order for Improvements](#15-priority-order-for-improvements)

---

## 1. Current Architecture

### 1.1 High-Level Overview

Titan is a **modular monolith**: a single Python process with a REPL entry point (`main.py`), an application shell (`core/titan.py`), and a central cognitive pipeline (`brain/brain.py`). Users interact only with **Titan** (one voice); agents are internal specialists whose outputs are injected into the Brain's LLM prompt.

The Brain is **not** a thin LLM wrapper. It orchestrates many subsystems in a fixed pipeline: knowledge lookup, context, long-term memory retrieval, state, missions, executive framing, internal monologue, reasoning, planning, execution classification, decision classification, memory writes, agent orchestration, prompt assembly, LLM call, mission step evaluation, and state update.

However, several pipeline stages are **placeholders** (template strings or static logic) and their outputs are **not all wired into the final LLM prompt**. The actual intelligence of user-facing responses comes primarily from **OpenAI `gpt-5.2`** via `brain/llm.py`, fed with a subset of assembled context.

### 1.2 Layer Diagram

```
main.py
  └── core/titan.py (Titan — composition root, REPL loop)
        ├── config/settings.py (name, version, creator)
        ├── memory/memory_manager.py → memory/memory.py (short-term, in-process)
        ├── brain/brain.py (Brain — cognitive pipeline)
        │     ├── brain/* (decision, reasoning, planning, knowledge, executor, llm, monologue, executive, task_evaluator)
        │     ├── context/context_manager.py
        │     ├── memory/* (long_term, decider, classifier, retriever)
        │     ├── core/* (task_manager, task_orchestrator, state_manager, mission_manager)
        │     └── agents/agent_manager.py (+ embedded TaskManager/Orchestrator deps)
        ├── tools/tool_manager.py (used at startup only from Titan shell)
        ├── context/context_manager.py (duplicate instance — startup display only)
        ├── core/conversation.py (in-session history — not fed to Brain)
        └── agents/agent_manager.py (duplicate instance — post-response auto_execute)
```

### 1.3 Module Inventory (Audited Files)

| Directory | Files | Role |
|-----------|-------|------|
| `brain/` | 11 Python modules | Cognitive pipeline, LLM gateway, identity (unwired) |
| `agents/` | 7 Python modules | Registry, routing, specialist workers |
| `memory/` | 6 Python modules | Short-term (unused by Brain), long-term JSON, read/write helpers |
| `context/` | 1 Python module | Static situational context for prompts |
| `core/` | 8 Python modules + constitution markdown | App shell, orchestration, persistence, legacy duplicates |

### 1.4 Persistence

| File | Manager | Used by Brain |
|------|---------|---------------|
| `data/long_term_memory.json` | `LongTermMemory` | Yes — read, write, prompt |
| `data/titan_state.json` | `StateManager` | Yes — read, partial write |
| `data/titan_mission.json` | `MissionManager` | Yes — read, write, auto-create |

Short-term memory (`Memory` / `MemoryManager`) lives **only in RAM** and is wired to `Titan` startup, not to `Brain.think()`.

### 1.5 External Dependencies (Brain Path)

- **OpenAI API** via `brain/llm.py` (`OPENAI_API_KEY` from `.env`)
- **Tools** (`TimeTool`) — available in `Titan` but **not** invoked from `Brain.think()` despite `Executor` having a `"Utiliser un outil"` branch

---

## 2. Responsibilities of Every Class

### 2.1 `brain/` — Cognitive Layer

| Class / Symbol | File | Responsibility | Wired to Runtime? |
|----------------|------|----------------|-------------------|
| `Brain` | `brain.py` | Central `think()` orchestrator; owns all subsystems; assembles prompt; calls LLM; updates mission/state | **Yes** — primary entry |
| `Decision` | `decision.py` | Keyword-based intent label (`salutation` vs `conversation`) | Partial — printed to console only, **not in LLM prompt** |
| `Reasoning` | `reasoning.py` | Returns static analysis dict with boolean flags (`needs_memory`, `needs_tool`, `needs_clarification`) — all default `False` | Partial — feeds `Executor` only |
| `Planning` | `planning.py` | Returns generic 5-step plan template for any goal | Partial — printed only, **not in LLM prompt** |
| `Knowledge` | `knowledge.py` | In-memory facts (creator, name, version); keyword search | Partial — printed only, **not in LLM prompt** |
| `Executor` | `executor.py` | Maps reasoning flags to action label string | Partial — printed only, **not in LLM prompt** |
| `LLM` | `llm.py` | OpenAI client; system instructions; `ask(prompt)` → response text | **Yes** — final synthesis |
| `InternalMonologue` | `internal_monologue.py` | Template "reflection" string | Partial — printed only, **not in LLM prompt** |
| `ExecutiveBrain` | `executive_brain.py` | Formats strategic framing text from inputs (not LLM-backed) | **Yes** — included in prompt |
| `TaskEvaluator` | `task_evaluator.py` | Keyword detection for mission step completion | **Yes** — can advance mission |
| `IDENTITY` | `identity.py` | Product identity prose for Titan | **No** — never imported |

### 2.2 `agents/` — Specialist Workers

| Class | File | Responsibility |
|-------|------|----------------|
| `AgentManager` | `agent_manager.py` | Registry of agents; `execute(name, task)`; `auto_execute(task)` via selector |
| `AgentSelector` | `agent_selector.py` | Single-agent keyword routing → `coding`, `research`, `planning`, `reasoning`, or `base` |
| `BaseAgent` | `base_agent.py` | Abstract contract; generic completion message |
| `CodingAgent` | `coding_agent.py` | Returns templated Python `additionner` example for any coding task |
| `ResearchAgent` | `research_agent.py` | Returns placeholder research suggestion string |
| `PlanningAgent` | `planning_agent.py` | Returns generic 5-step plan template |
| `ReasoningAgent` | `reasoning_agent.py` | Returns placeholder reasoning completion string |

Agents **do not** call the LLM, tools, or persistence layers directly.

### 2.3 `memory/` — Memory Layer

| Class | File | Responsibility | Used by Brain? |
|-------|------|----------------|----------------|
| `Memory` | `memory.py` | In-memory `short_term` list | No (via MemoryManager in Titan only) |
| `MemoryManager` | `memory_manager.py` | Facade over `Memory` | No |
| `LongTermMemory` | `long_term_memory.py` | JSON load/save; `get_memory`, `show_memory`, `remember`, `remember_user_note` | **Yes** |
| `MemoryDecider` | `memory_decider.py` | `should_remember(message)` keyword gate; unused `classify_memory()` | Partial |
| `MemoryClassifier` | `memory_classifier.py` | Category: `goals`, `preferences`, `projects`, `notes` | **Yes** |
| `MemoryRetriever` | `memory_retriever.py` | Keyword relevance filter over user notes/preferences/projects + titan block | **Yes** (then overwritten — see bugs) |

### 2.4 `context/` — Situational Context

| Class | File | Responsibility |
|-------|------|----------------|
| `ContextManager` | `context_manager.py` | Static fields: `current_user`, `active_project`, `current_goal`, `current_phase`; returns formatted French block |

Does **not** sync with `StateManager` or `MissionManager`.

### 2.5 `core/` — Application & Orchestration

| Class | File | Responsibility | Used by Brain? |
|-------|------|----------------|----------------|
| `Titan` | `titan.py` | Composition root; REPL; wires Brain, duplicate managers | Indirect — calls `brain.think()` |
| `TaskManager` | `task_manager.py` | Multi-agent task list from keywords; `create_tasks`, unused `execute_tasks` | **Yes** (via orchestrator) |
| `TaskOrchestrator` | `task_orchestrator.py` | Runs task pipeline sequentially; `format_results` for prompt | **Yes** |
| `StateManager` | `state_manager.py` | JSON state: project, step, last messages, progress | **Yes** |
| `MissionManager` | `mission_manager.py` | JSON mission: steps, current_step, auto-create from message | **Yes** |
| `Conversation` | `conversation.py` | In-memory dialogue history | No (Titan only) |
| `ActionManager` | `action_manager.py` | Placeholder action executor | **No** — dead |
| `Context` | `context.py` | Legacy dict-based context | **No** — dead duplicate |

---

## 3. Data Flow

### 3.1 Per-Turn Data Flow (Canonical)

```
User input (str)
    │
    ▼
Brain.think(message)
    │
    ├─► Knowledge.search(message) ──────────────► str | None (console only)
    ├─► ContextManager.get_context() ───────────► formatted str
    ├─► LongTermMemory.get_memory() ──────────► dict (full JSON structure)
    ├─► MemoryRetriever.retrieve(dict, msg) ──► relevant str (discarded later)
    ├─► StateManager.get_state() ───────────────► dict
    ├─► MissionManager.get_mission() ───────────► dict
    │       └─ if not active: create_mission_from_message(message)
    ├─► ExecutiveBrain.analyze_mission(...) ────► formatted str
    ├─► InternalMonologue.think(...) ─────────► formatted str (console only)
    ├─► Reasoning.analyze(message) ─────────────► dict
    ├─► Planning.create_plan(message) ──────────► list[str] (console only)
    ├─► Executor.execute(analysis) ─────────────► str (console only)
    ├─► Decision.decide(message) ───────────────► str (console only)
    │
    ├─► LongTermMemory.show_memory() ───────────► full JSON string (replaces retrieved memory in prompt)
    ├─► StateManager.get_state() ───────────────► dict (re-read)
    │
    ├─► MemoryDecider.should_remember(message)
    │       └─ if True: MemoryClassifier.classify → LongTermMemory.remember_user_note("Nolan", note)
    │
    ├─► TaskOrchestrator.orchestrate(message) ──► list[{agent, task, result}]
    │       └─ format_results → str
    │
    ├─► LLM.ask(prompt) ────────────────────────► str (user-facing response)
    │
    ├─► TaskEvaluator.is_step_completed(...) ─────► bool → MissionManager.complete_current_step()
    └─► StateManager.update_after_response(msg, response)
            │
            ▼
        return response to Titan REPL
            │
            ▼
Titan: Conversation.add_message; print response
Titan: AgentManager.auto_execute(question) ───────► str (console only, NOT in LLM)
Titan: Conversation.show_history()
```

### 3.2 Prompt Payload (What the LLM Actually Sees)

The final prompt includes:

1. `CONTEXTE ACTUEL` — from `ContextManager`
2. `MÉMOIRE PERMANENTE` — **full** JSON dump via `show_memory()`, not retrieved subset
3. `ÉTAT ACTUEL` — raw Python dict stringification of state
4. `MISSION ACTIVE` — raw Python dict stringification of mission
5. `EXECUTIVE ANALYSIS` — template from `ExecutiveBrain`
6. `QUESTION DE L'UTILISATEUR` — user message
7. `RÉSULTATS DES AGENTS` — orchestrator formatted output

**Excluded from prompt:** knowledge hits, internal monologue, reasoning analysis, plan steps, executor action, decision label, conversation history, identity/constitution, retrieved memory subset.

### 3.3 JSON Schema Summary

**Long-term memory (`data/long_term_memory.json`):**
```json
{
  "users": {
    "<name>": {
      "role", "authority", "preferences", "projects", "notes"
    }
  },
  "titan": { "mission", "current_project", "current_phase" }
}
```

**State (`data/titan_state.json`):**
```json
{
  "active_project", "current_step", "last_user_message",
  "last_titan_response", "next_action", "progress"
}
```

**Mission (`data/titan_mission.json`):**
```json
{
  "active", "title", "objective", "steps", "current_step", "status"
}
```

---

## 4. Decision Flow

Decision-making in Titan is **distributed and mostly non-executing** — many "decision" modules produce labels or text that do not gate downstream behavior.

### 4.1 Decision Points Map

```
┌─────────────────────────────────────────────────────────────────┐
│                     Brain.think() Decision Graph                 │
└─────────────────────────────────────────────────────────────────┘

[1] Mission active?
    NO  → create_mission_from_message(message)  [keyword heuristics]
    YES → use existing mission

[2] MemoryDecider.should_remember(message)?
    YES → classify + remember_user_note (always user "Nolan")
    NO  → skip write

[3] TaskManager.create_tasks(message)  [keyword routing]
    → fixed agent pipeline (1–3 agents)

[4] Reasoning.analyze → Executor.execute
    → action label (never acted upon)

[5] Decision.decide(message)
    → "salutation" | "conversation" (never acted upon)

[6] LLM.ask(prompt)
    → final natural language response (actual user-facing decision)

[7] TaskEvaluator.is_step_completed(message, response, mission)?
    YES → complete_current_step() [mutates mission JSON]
    NO  → unchanged

[8] Titan.start() after Brain returns:
    AgentSelector.select_agent(message) → single agent auto_execute
    (parallel decision path, not coordinated with orchestrator)
```

### 4.2 Agent Routing Decisions (Two Independent Systems)

| Trigger keywords | `AgentSelector` (single) | `TaskManager` (multi) |
|------------------|--------------------------|------------------------|
| code, python, fonction | coding | planning → coding → reasoning |
| recherche, internet | research | research → reasoning |
| plan, organise | planning | planning → reasoning |
| pourquoi, analyse | reasoning | reasoning → planning (default) |
| default | base | reasoning → planning |

These systems **disagree** on which agents run and **both execute** in a single user turn (orchestrator inside Brain, `auto_execute` in Titan afterward).

### 4.3 Mission Creation Heuristics

`MissionManager.create_mission_from_message()`:

- Contains `trading`, `robot`, or `bot` → 7-step trading robot mission
- Contains `titan` → 5-step Titan improvement mission
- Else → 4-step generic mission

Any message matching these keywords when **no mission is active** creates a persisted multi-step mission.

---

## 5. Memory Flow

### 5.1 Read Path

```
LongTermMemory.load_memory()  [on Brain init + after each save]
        │
        ▼
get_memory() → full dict
        │
        ▼
MemoryRetriever.retrieve(full_dict, user_message)
        │
        ├─ Scan all users' notes, preferences, projects
        ├─ Match words in message (len > 3) against item text
        ├─ Match titan block keys/values against message
        │
        ▼
relevant string OR "Aucune mémoire pertinente trouvée."
        │
        ▼
Used in ExecutiveBrain template + console print
        │
        ▼
*** OVERWRITTEN before prompt ***
show_memory() → entire JSON serialized into prompt
```

### 5.2 Write Path

```
User message
    │
    ▼
MemoryDecider.should_remember(message)
    │  keyword list: "souviens-toi", "projet", "nolan", "titan", etc.
    │
    ▼ (if True)
MemoryClassifier.classify(message)
    │  → goals | preferences | projects | notes
    │
    ▼
LongTermMemory.remember_user_note("Nolan", f"[{category}] {message}")
    │
    ▼
Append to users.Nolan.notes[] → save_memory() → data/long_term_memory.json
```

### 5.3 Memory Isolation

| Concern | Current behavior |
|---------|------------------|
| Nolan vs Ibrahim | Retrieval scans **both** users; writes **always** go to `"Nolan"` |
| User detection | `MemoryDecider.classify_memory()` exists but is **unused** |
| Short-term vs long-term | Two separate systems; Brain never reads short-term |
| Context `current_user` | Static `"Nolan"` — not passed to memory write path |

### 5.4 Short-Term Memory (Parallel, Disconnected)

```
Titan.__init__ → MemoryManager → Memory.short_term[]
Titan.start() → remember("Titan a démarré...") → show_memory() at boot only
Conversation history is separate (Conversation.history) — also not in Brain prompt
```

---

## 6. Execution Flow

### 6.1 Full Session Lifecycle

```
python main.py
    │
    ▼
Titan.__init__()
    • Instantiates Brain (which creates its OWN AgentManager, ContextManager, etc.)
    • Instantiates SEPARATE MemoryManager, ContextManager, AgentManager
    │
    ▼
Titan.start()
    • status = ONLINE
    • short-term memory note
    • print banner, time from ToolManager, context from Titan's ContextManager
    • greet Nolan (hardcoded)
    │
    └── REPL loop ──────────────────────────────────────────────┐
            │                                                    │
            input("Toi : ")                                      │
            │                                                    │
            if exit → break                                      │
            │                                                    │
            conversation.add_message("Nolan", question)          │
            │                                                    │
            response = brain.think(question)  ◄── MAIN PIPELINE  │
            │                                                    │
            conversation.add_message("Titan", response)          │
            print(response)                                      │
            │                                                    │
            agent_result = agents.auto_execute(question)  ◄── DUPLICATE PATH
            print(agent_result)                                  │
            │                                                    │
            conversation.show_history()                          │
            └────────────────────────────────────────────────────┘
```

### 6.2 Agent Execution Inside Brain

```
TaskOrchestrator.orchestrate(message)
    │
    ▼
TaskManager.create_tasks(message) → [(agent_name, task), ...]
    │
    ▼
For each task sequentially:
    AgentManager.execute(agent_name, task)
        → agent.execute(task) → templated string
    │
    ▼
format_results → injected into LLM prompt BEFORE llm.ask()
```

**Important:** Agent results influence the LLM response because they are in the prompt. The second `auto_execute` in `Titan.start()` runs **after** the LLM already responded — those results are only printed to console.

### 6.3 Executor / Tools Gap

`Executor.execute()` can return `"Utiliser un outil"`, but:

- `Reasoning.analyze()` never sets `needs_tool=True`
- Brain never calls `ToolManager`
- `ActionManager` is unwired

Tool execution is **non-functional** in the cognitive pipeline.

---

## 7. Context Flow

### 7.1 Context Sources

| Source | Fields | Synced? | In LLM Prompt? |
|--------|--------|---------|----------------|
| `ContextManager` | current_user, active_project, current_goal, current_phase | Static defaults | Yes |
| `StateManager` | active_project, current_step, last_*, next_action, progress | Updated after each response | Yes (raw dict) |
| `MissionManager` | title, objective, steps, current_step, status | Updated on step completion | Yes (raw dict) |
| `Conversation` | speaker, message pairs | Grows each turn | **No** |
| `core/context.py` `Context` | current_user, project, mode, last_action | **Dead code** | No |

### 7.2 Context Duplication

Three context-like constructs exist:

1. **`context/context_manager.py`** — formatted string, used by Brain
2. **`core/context.py`** — dict-based legacy, unused
3. **`StateManager.state["active_project"]`** — may diverge from `ContextManager.active_project`

`Titan` creates its own `ContextManager` for startup display; `Brain` creates another independent instance. Changes in one are never reflected in the other.

### 7.3 Context vs Memory Boundary

| Context (situational now) | Memory (durable facts) |
|---------------------------|------------------------|
| Static goal/phase strings | User notes, preferences, projects |
| State last messages | Classified note append |
| Mission steps | Titan mission metadata in JSON |

No automatic propagation: completing a mission step does not update `ContextManager.current_phase`.

---

## 8. Missing Implementations

### 8.1 Brain Pipeline Gaps

| Expected capability | Status |
|---------------------|--------|
| LLM-backed reasoning, planning, executive analysis | Template/print only |
| Wire knowledge, monologue, plan, decision into prompt | Not implemented |
| Use retrieved memory in prompt (not full dump) | Retrieval done then discarded |
| `brain/identity.py` + constitution in system prompt | Not loaded |
| Conversation history in prompt | Not implemented |
| Tool execution from Executor decision | Not wired |
| User-aware memory writes (Nolan/Ibrahim) | Hardcoded Nolan |
| Dependency injection from `Titan` composition root | Brain self-instantiates everything |
| Error handling / retry on LLM failure | Not implemented |
| Structured logging | Extensive `print()` only |
| Tests for brain pipeline | No `tests/` coverage observed |

### 8.2 Agent Gaps

| Expected | Status |
|----------|--------|
| LLM-backed agent execution | Static templates |
| Tool access (web, files, code) | None |
| Agent prompts externalized | Inline f-strings |
| Real research or coding capability | Placeholder strings |

### 8.3 Memory Gaps

| Expected | Status |
|----------|--------|
| Unified memory facade | Two parallel systems |
| Embedding / semantic retrieval | Keyword match only |
| Explicit forget / edit commands | Not implemented |
| `classify_memory()` for user routing | Method exists, unused |
| Category-specific storage (goals vs notes paths) | All go to `notes[]` with prefix tag |

### 8.4 Core Gaps

| Expected | Status |
|----------|--------|
| Single orchestration entry for agents | Dual paths |
| `ActionManager` integration | Unwired |
| Context sync with state/mission | Not implemented |
| Multi-user session (Ibrahim) | Hardcoded Nolan in REPL and memory |
| REPL error wrapper around `brain.think()` | Not implemented |

---

## 9. Duplicate Logic

### 9.1 Duplicate Manager Instances

| Manager | Instance 1 | Instance 2 |
|---------|------------|------------|
| `AgentManager` | `Titan.agents` | `Brain.agent_manager` |
| `ContextManager` | `Titan.context` | `Brain.context_manager` |

Separate instances mean separate state (though ContextManager is currently static).

### 9.2 Duplicate Agent Execution

Every user turn with default flow:

1. **Inside Brain:** `TaskOrchestrator` runs 1–3 agents → results in LLM prompt
2. **Inside Titan REPL:** `agents.auto_execute()` runs 1 agent → console output only

This violates the engineering rule: **one orchestration entry point per turn**.

### 9.3 Duplicate Agent Routing Logic

Keyword routing is implemented independently in:

- `agents/agent_selector.py` — single agent selection
- `core/task_manager.py` — multi-agent task lists

Overlapping keyword sets (`code`, `python`, `recherche`, `plan`, etc.) with **different** routing outcomes.

### 9.4 Duplicate Context Implementations

- `context/context_manager.py` — active, string formatter
- `core/context.py` — legacy dict context, same conceptual role

### 9.5 Duplicate Memory Systems

- `Memory` / `MemoryManager` — ephemeral list
- `LongTermMemory` — JSON persistence used by Brain

No unified API despite overlapping "remember" naming.

### 9.6 Duplicate Planning

- `brain/planning.py` — `Planning.create_plan()`
- `agents/planning_agent.py` — separate plan template
- `TaskManager` may also invoke planning agent

Three plan generators, none coordinated.

### 9.7 Duplicate User Classification

- `MemoryDecider.classify_memory()` — Nolan/Ibrahim/titan/general
- `MemoryClassifier.classify()` — goals/preferences/projects/notes

Both exist; only classifier is used, and only for category not user.

---

## 10. Dead Code

### 10.1 Entire Modules (Never Imported)

| Module | Contents |
|--------|----------|
| `core/action_manager.py` | `ActionManager.execute()` |
| `core/context.py` | `Context` class |
| `brain/identity.py` | `IDENTITY` string constant |

### 10.2 Unused Methods

| Location | Method | Notes |
|----------|--------|-------|
| `core/task_manager.py` | `execute_tasks()` | Orchestrator duplicates this logic |
| `memory/memory_decider.py` | `classify_memory()` | User routing never called |
| `core/mission_manager.py` | `advance_mission()` | Wrapper around `complete_current_step`; unused |
| `core/state_manager.py` | `update_state()`, `show_state()` | Only `update_after_response` used by Brain |
| `long_term_memory.py` | `remember(category, key, value)` | Generic writer; Brain uses `remember_user_note` only |

### 10.3 Partially Dead Pipeline Outputs

These run every turn but outputs are **console-only** (no effect on LLM or state):

- `Knowledge.search()`
- `InternalMonologue.think()`
- `Planning.create_plan()`
- `Executor.execute()`
- `Decision.decide()`
- `MemoryRetriever.retrieve()` result (before overwrite)

### 10.4 Disconnected Subsystems

- `MemoryManager` — only Titan startup
- `Conversation` — stored but never fed to Brain
- `ToolManager` — startup time only

---

## 11. Circular Dependencies

### 11.1 Import Graph (Audited Modules)

```
main → core.titan
core.titan → brain.brain, memory.*, context.*, agents.*, tools.*, config

brain.brain → brain.*, context.*, memory.*, core.task_*, core.state_*, core.mission_*, agents.*

agents.* → agents.* only
memory.* → memory.* only (stdlib json/os)
context.* → no internal imports
core.task_* → no brain/memory imports
core.state/mission/conversation/action/context → no brain imports
```

### 11.2 Verdict

**No circular import cycles detected** among audited modules.

Dependency direction is mostly correct per rulebook:

- `brain` → `agents`, `memory`, `context`, `core` ✅
- `agents` ↛ `brain` ✅
- `memory` ↛ `brain`, `agents` ✅

**Architectural cycle (runtime, not import):** `Titan` creates `Brain`, and `Brain` creates its own copy of managers also owned by `Titan` — composition duplication rather than import cycle.

---

## 12. Technical Debt

| ID | Item | Severity | Notes |
|----|------|----------|-------|
| TD-1 | Duplicate `AgentManager` | High | Two registries, double execution |
| TD-2 | Dual memory systems | High | MemoryManager vs LongTermMemory |
| TD-3 | Duplicate context modules | Medium | `core/context.py` vs `context/context_manager.py` |
| TD-4 | Brain self-wiring | High | No injection from composition root |
| TD-5 | Placeholder brain stages | High | Reasoning, planning, executive don't analyze |
| TD-6 | Prompt assembly incomplete | High | Many pipeline stages excluded |
| TD-7 | Identity/constitution unwired | Medium | Product governance not in LLM instructions |
| TD-8 | Static ContextManager | Medium | Doesn't reflect state/mission |
| TD-9 | `print()` debug everywhere | Medium | No logging module |
| TD-10 | No automated tests | High | Rulebook requires tests |
| TD-11 | Hardcoded user "Nolan" | Medium | Multi-user product requirement violated |
| TD-12 | Raw dict in prompt | Low | Mission/state as Python repr, not formatted JSON |
| TD-13 | Model name in code | Low | `gpt-5.2` hardcoded in `llm.py`, not `settings.py` |
| TD-14 | Indentation inconsistency | Low | `titan.py`, `brain.py`, `mission_manager.py` mixed spacing |
| TD-15 | Missing `__init__.py` packages | Low | Implicit namespace imports rely on PYTHONPATH |
| TD-16 | `Executor` missing file banner | Low | Style inconsistency vs other brain modules |

---

## 13. Potential Bugs

### 13.1 High Impact

| Bug | Location | Description |
|-----|----------|-------------|
| **Mission auto-creation on casual messages** | `brain.py` L61–62, `mission_manager.py` | When `active=False`, **every** message creates a new mission. Keyword `"titan"` in any message triggers Titan improvement mission. |
| **TaskEvaluator false positives** | `task_evaluator.py` | Keywords `"continue"`, `"fait"`, `"done"`, `"terminé"`, `"avance"`, `"prochaine étape"` auto-complete mission steps. User saying "continue" (observed in `titan_state.json`) advances mission incorrectly. |
| **Retrieved memory discarded** | `brain.py` L56–59 vs L130 | Relevant memory computed then prompt uses `show_memory()` full dump — wastes retrieval and may overload tokens. |
| **Double agent execution** | `titan.py` L61–67 + `brain.py` L191–203 | Agents run in orchestrator (affects LLM) and again in REPL (wasted work, confusing debug output). |
| **Memory always saved to Nolan** | `brain.py` L184–186 | Ibrahim's statements stored under Nolan's profile when decider triggers. |
| **No LLM error handling** | `llm.py` | API failures will crash REPL with unhandled exception. |

### 13.2 Medium Impact

| Bug | Location | Description |
|-----|----------|-------------|
| **Mission in prompt is raw dict** | `brain.py` L159 | `str(dict)` is not human-readable JSON; may confuse model. |
| **State fields never updated semantically** | `state_manager.py` | `current_step`, `next_action`, `progress` static after init — only last messages update. |
| **CodingAgent irrelevant output** | `coding_agent.py` | Always returns `additionner` example — pollutes agent section of prompt for real coding tasks. |
| **Over-broad memory decider** | `memory_decider.py` | Keywords `"titan"`, `"projet"`, `"note"` cause many messages to persist (see polluted notes in JSON). |
| **Mission step removal mutates list** | `mission_manager.py` L55–56 | `list.remove(current)` loses step history permanently. |

### 13.3 Low Impact

| Bug | Location | Description |
|-----|----------|-------------|
| **Variable reuse `memory`** | `brain.py` | `memory` holds retrieved str, then reassigned to full JSON string — confusing maintenance. |
| **ExecutiveBrain parameter shadowing** | `executive_brain.py` L15 | Local `mission` variable shadows parameter name (works in Python f-string but fragile). |
| **Reasoning flags never True** | `reasoning.py` | Executor branches for tool/memory/clarify never trigger. |

---

## 14. Future Improvements

### 14.1 Architecture

- **Composition root injection:** `Titan` constructs single shared instances; pass into `Brain.__init__(...)`.
- **Single agent orchestration path:** Remove `auto_execute` from REPL or move all agent work post-Brain with results fed back (pick one).
- **Unified memory facade:** One `MemoryService` wrapping short-term, long-term, retrieval, decider, classifier.
- **Retire legacy modules:** Delete or merge `core/context.py`, wire or delete `ActionManager`.

### 14.2 Brain Pipeline

- **Prompt builder class:** Explicit assembly of all relevant sections with truncation/token budget.
- **Use retrieval in prompt:** Replace full dump with `MemoryRetriever` output + optional small global summary.
- **Wire identity + constitution:** Load `IDENTITY` and constitution summary into `LLM.instructions`.
- **Conversation window:** Inject last N turns from `Conversation` into prompt.
- **Real executive/reasoning:** LLM or structured classifiers with tests; or collapse placeholders to reduce noise.

### 14.3 Memory

- User detection on write using `classify_memory()` or explicit session user.
- Store by category in schema (`goals[]`, not only prefixed `notes[]`).
- Commands: "oublie X", "souviens-toi de X".
- Embedding-based retrieval when note count grows.

### 14.4 Agents

- LLM-backed agents with focused system prompts in `prompts/`.
- Tool-scoped capabilities (coding agent → file read; research → web tool).
- Shared routing table used by both selector and task manager.

### 14.5 Mission & State

- Explicit mission commands vs automatic creation from keywords.
- TaskEvaluator upgrade: structured user confirmation or LLM evaluator with strict schema.
- Sync `ContextManager` fields from `StateManager` and active mission step.
- Preserve step history (mark completed, don't delete from list).

### 14.6 Operations

- Structured logging (`logging` module, `logs/titan.log`).
- REPL exception handler around `brain.think()`.
- LLM retry with backoff (max 2).
- pytest suite mirroring managers and brain prompt builder.

---

## 15. Priority Order for Improvements

Ordered by **risk reduction × foundation value**. Complete higher items before building features on top.

| Priority | Item | Rationale |
|----------|------|-----------|
| **P0** | Fix double agent execution (TD-1) | Wasted compute, confusing behavior, violates core invariant |
| **P0** | Fix TaskEvaluator false positives | Corrupts mission state on common words like "continue" |
| **P0** | Add REPL + LLM error handling | Prevents session crashes |
| **P1** | Shared dependency injection from `Titan` | Enables all consolidation work |
| **P1** | Use retrieved memory in prompt (not full dump) | Token cost, relevance, retrieval purpose |
| **P1** | Fix memory user attribution (Nolan/Ibrahim) | Data integrity / privacy |
| **P1** | Mission creation gating | Stop auto-missions on casual chat |
| **P2** | Unify agent routing (single keyword registry) | DRY, predictable behavior |
| **P2** | Wire identity + constitution into LLM | Product alignment |
| **P2** | Sync context with state/mission | Accurate situational awareness |
| **P2** | Collapse or implement placeholder brain stages | Reduce noise or add real value |
| **P3** | Unified memory facade | Clean API for future features |
| **P3** | Conversation history in prompt | Multi-turn coherence |
| **P3** | Delete dead modules (`action_manager`, `core/context`, unused methods) | Reduce confusion |
| **P3** | Scaffold `tests/` with manager + routing tests | Regression safety |
| **P4** | Structured logging | Operability |
| **P4** | LLM-backed agents + tools | Capability expansion |
| **P4** | Semantic memory retrieval | Scale past keyword matching |
| **P5** | Mission step history preservation | Auditing and UX |
| **P5** | Move model name to `config/settings.py` | Configuration hygiene |

---

## Appendix A: File-by-File Quick Reference

| Path | Lines (approx) | Runtime role |
|------|----------------|----------------|
| `brain/brain.py` | 225 | Cognitive orchestrator |
| `brain/llm.py` | 35 | OpenAI gateway |
| `brain/executive_brain.py` | 53 | Template strategic block |
| `brain/task_evaluator.py` | 37 | Mission step completion |
| `brain/internal_monologue.py` | 29 | Template reflection |
| `brain/knowledge.py` | 29 | Static facts lookup |
| `brain/planning.py` | 18 | Generic plan template |
| `brain/reasoning.py` | 18 | Static analysis dict |
| `brain/decision.py` | 14 | Greeting vs conversation |
| `brain/executor.py` | 16 | Action label from reasoning |
| `brain/identity.py` | 19 | **Unwired** identity text |
| `agents/agent_manager.py` | 47 | Agent registry + dispatch |
| `agents/agent_selector.py` | 62 | Single-agent routing |
| `agents/base_agent.py` | 13 | Agent contract |
| `agents/coding_agent.py` | 44 | Template coding response |
| `agents/planning_agent.py` | 43 | Template plan response |
| `agents/reasoning_agent.py` | 16 | Placeholder reasoning |
| `agents/research_agent.py` | 16 | Placeholder research |
| `memory/long_term_memory.py` | 78 | JSON persistence |
| `memory/memory_retriever.py` | 46 | Keyword retrieval |
| `memory/memory_decider.py` | 47 | Remember gate + unused user classify |
| `memory/memory_classifier.py` | 19 | Category classification |
| `memory/memory_manager.py` | 17 | Short-term facade |
| `memory/memory.py` | 17 | In-memory list |
| `context/context_manager.py` | 35 | Static context formatter |
| `core/titan.py` | 74 | App shell + REPL |
| `core/task_orchestrator.py` | 60 | Multi-agent sequential run |
| `core/task_manager.py` | 51 | Task list creation |
| `core/state_manager.py` | 48 | State JSON |
| `core/mission_manager.py` | 117 | Mission JSON |
| `core/conversation.py` | 19 | Dialogue history |
| `core/action_manager.py` | 11 | **Dead** |
| `core/context.py` | 22 | **Dead** duplicate |

---

## Appendix B: Canonical `think()` Pipeline Order (As Implemented)

1. Knowledge search  
2. Context load  
3. Long-term memory load + retrieval  
4. State load  
5. Mission load / auto-create  
6. Executive analysis  
7. Internal monologue *(console)*  
8. Reasoning *(console + executor)*  
9. Planning *(console)*  
10. Executor action label *(console)*  
11. Decision classification *(console)*  
12. Memory write decision  
13. Task orchestration (agents)  
14. Prompt assembly + LLM call  
15. Task evaluation / mission step advance  
16. State update after response  

*Stages 7–11 and parts of 3 are executed but largely disconnected from the LLM prompt.*

---

**End of Brain Audit**

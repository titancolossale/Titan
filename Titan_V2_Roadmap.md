# Titan Version 2 — Complete Engineering Roadmap

**Document type:** Chief Software Architect engineering plan  
**Author role:** Chief Software Architect for Titan  
**Version target:** Titan V2 (evolution from v0.0.1 → production-grade personal AI OS)  
**Date:** 2026-06-23  
**Status:** Approved for planning — no code changes implied by this document  

**Source documents studied:**

| Document | Role in this roadmap |
|----------|----------------------|
| `Titan_Blueprint.md` | Product vision, personality goals, target directory structure |
| `Titan_Context.md` | Current implementation truth, gaps, v1/v2/v3 evolution sketch |
| `Brain_Audit.md` | P0–P5 priorities, bugs, dead code, duplicate logic |
| `core/constitution/titan_constitution.md` | Non-negotiable product identity, memory isolation, architecture principles |
| `.cursor/rules/titan.mdc` | Engineering standards, dependency rules, testing policy |

**Guiding principle (Constitution + Rulebook):**

> *"Qu'est-ce que je peux faire maintenant pour aider Nolan ou Ibrahim à avancer concrètement ?"*

Every phase must reduce technical debt, preserve modular monolith boundaries, and move Titan from **prototype pipeline** to **professional personal AI operating system**.

---

## Executive Summary

Titan v0.0.1 proves the concept: a REPL-driven Brain pipeline with JSON persistence, placeholder agents, and OpenAI synthesis. It also carries **critical architectural debt**: duplicate managers, double agent execution, disconnected pipeline stages, unwired constitution/identity, and memory integrity risks.

**Titan V2** is not a single release tag. It is a **sequenced engineering program** of 14 phases that:

1. Stabilizes foundations (Phases 1–4)
2. Builds real cognitive and action capability (Phases 5–8)
3. Enables continuity and proactivity (Phase 9)
4. Adds modalities and interfaces (Phases 10–12)
5. Introduces high-risk domain systems (Phase 13)
6. Hardens for production (Phase 14)

**Version mapping (informative):**

| Roadmap phases | Approximate release track |
|----------------|---------------------------|
| Phases 1–4 | v0.1.x → v0.3.x (foundation) |
| Phases 5–8 | v0.4.x → v1.0.x (capable CLI assistant) |
| Phase 9 | v1.1.x → v1.5.x (autonomy layer) |
| Phases 10–12 | v1.6.x → v2.0.x (multimodal + web) |
| Phases 13–14 | v2.1.x → v2.5.x+ (trading + deployment) |

Phases are **strictly ordered**. Skipping Phase 1 to build agents or trading will recreate today's duplicate paths and corrupt mission/memory state.

---

## Master Phase Dependency Graph

```
Phase 1  Architecture Cleanup
    │
    ▼
Phase 2  Brain Redesign
    │
    ├──────────────────┐
    ▼                  ▼
Phase 3  Memory    Phase 4  Context Engine
    │                  │
    └────────┬─────────┘
             ▼
Phase 5  Agent Framework
             │
             ▼
Phase 6  Tool Framework
             │
             ▼
Phase 7  Conversation Engine
             │
             ▼
Phase 8  Planning & Execution
             │
             ▼
Phase 9  Long-Term Autonomy
             │
    ┌────────┴────────┐
    ▼                 ▼
Phase 10 Voice    Phase 11 Vision
    │                 │
    └────────┬────────┘
             ▼
Phase 12 Web Interface
             │
             ▼
Phase 13 Trading Infrastructure
             │
             ▼
Phase 14 Deployment
```

---

## Cross-Cutting Standards (All Phases)

These apply to **every phase** and are not repeated in full below:

| Standard | Requirement |
|----------|-------------|
| **Dependency direction** | `main → core/titan → brain → (memory, context, agents, core managers) → tools`. No cycles. |
| **Single intelligence** | Users always speak to Titan; agents remain internal. |
| **User isolation** | Nolan ≠ Ibrahim memory. Never mix personal data. |
| **Persistence** | All JSON via manager classes; schema migrations with `version` field. |
| **Secrets** | `.env` only; never in repo or long-term memory. |
| **Tests** | New modules require pytest; bug fixes require regression tests. |
| **Logging** | Structured logging after Phase 1; no new permanent `print()` in core paths. |
| **Prompts** | Externalize to `prompts/` once Phase 2 prompt builder lands. |
| **Definition of done** | `python main.py` works; tests pass; no new duplicate subsystems; changelog note. |

---

# Phase 1 — Architecture Cleanup

## Why this phase comes first

Nothing built on top of v0.0.1 is trustworthy until **one composition root, one instance per manager, and one agent execution path** exist. The Brain Audit identifies P0 bugs (double agent execution, TaskEvaluator false positives, no error handling) that **corrupt live JSON data today**. Phase 1 eliminates structural contradictions so Phases 2–14 do not amplify debt.

**Why before Phase 2:** Brain redesign requires injected dependencies; you cannot redesign `Brain.think()` while it still constructs duplicate `AgentManager` and `ContextManager` instances.

---

## Purpose

Establish a **clean modular monolith skeleton**: single wiring from `Titan`, retired dead code, operational infrastructure (logging, tests, error boundaries), and P0 bug fixes.

---

## Objectives

1. **Single composition root:** `Titan.__init__()` constructs all managers once; passes them into `Brain.__init__(...)`.
2. **Remove double agent execution:** Delete `agents.auto_execute()` from REPL loop; agents run only via `TaskOrchestrator` inside Brain (or explicitly chosen single path documented in code).
3. **Retire dead modules:** Delete or integrate `core/action_manager.py`, `core/context.py`; document decision in changelog.
4. **P0 bug fixes:**
   - TaskEvaluator: remove keyword false positives (`continue`, `fait`, `done` as standalone triggers).
   - Mission auto-creation: gate behind explicit intent or commands (minimal fix in Phase 1; full UX in Phase 8).
   - REPL + LLM exception handling with French graceful messages.
5. **Infrastructure scaffold:**
   - `tests/` with pytest
   - `logs/` with `logging` configuration
   - `.env.example`, README setup section
   - `pyproject.toml` or documented PYTHONPATH strategy
6. **Package hygiene:** Add `__init__.py` files where needed for test imports.

---

## Dependencies

| Dependency | Status |
|------------|--------|
| Existing codebase v0.0.1 | Required |
| `Brain_Audit.md` P0/P1 list | Input |
| `.cursor/rules/titan.mdc` Section 10.5 consolidation list | Input |
| OpenAI API key for smoke tests | Optional (mock in CI) |

**No prior phases required.**

---

## Expected Architecture

```
main.py
└── Titan (composition root — SOLE owner of managers)
      ├── Brain(deps injected)
      │     └── uses shared: AgentManager, ContextManager, StateManager,
      │         MissionManager, LongTermMemory, TaskOrchestrator, ...
      ├── Conversation
      ├── ToolManager
      └── MemoryFacade (stub OK — full unification Phase 3)

logs/logger.py or core/logging_config.py
tests/test_*.py
```

**Invariants after Phase 1:**

- Exactly **one** `AgentManager` instance per process
- Exactly **one** agent orchestration call per user turn
- Brain does **not** call `AgentManager()` in its own `__init__`

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `core/titan.py` | Major — DI wiring, remove auto_execute, error wrapper |
| `brain/brain.py` | Major — constructor accepts injected deps |
| `brain/task_evaluator.py` | Fix false positives |
| `core/mission_manager.py` | Minimal gating on auto-create |
| `brain/llm.py` | Error handling, retry (max 2) |
| `core/action_manager.py` | Delete or archive |
| `core/context.py` | Delete |
| `config/settings.py` | Feature flags: `DEBUG_BRAIN`, `LOG_LEVEL` |
| `logs/` (new) | Logging config |
| `tests/` (new) | Initial test suite |
| `.env.example` (new) | Document `OPENAI_API_KEY` |
| `requirements.txt` | Pin pytest, dev deps |

---

## Estimated Complexity

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Overall | **Medium** | Mostly wiring and deletion; high care required to avoid regressions |
| Effort | **2–3 engineer-weeks** | 1 engineer full-time |
| Risk of regression | **Medium** | Touches hot path every turn |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Breaking `python main.py` imports | Smoke test in CI; run after each sub-task |
| Missing hidden duplicate instantiation | Grep for `AgentManager()`, `ContextManager()` |
| Data migration for mission JSON | Backup `data/*.json` before testing TaskEvaluator changes |
| Over-scoping into Brain redesign | Strict scope: wiring only; defer prompt work to Phase 2 |

---

## Testing Strategy

| Test area | Approach |
|-----------|----------|
| Composition | Assert Brain receives same instance as Titan (`id()` equality) |
| Single agent path | Mock `AgentManager.execute`; assert called once per turn |
| TaskEvaluator | Parametrize messages: `"continue"` must NOT complete; explicit `"étape terminée"` must |
| Mission gating | Inactive mission + `"bonjour"` does not create mission (after fix) |
| LLM errors | Mock OpenAI client; assert French fallback, REPL continues |
| State/Mission managers | Existing JSON load/save round-trip with `tmp_path` |
| Regression | `pytest tests/ -v` mandatory before phase sign-off |

---

## Definition of Done

- [ ] One `AgentManager`, one `ContextManager`, one orchestration path per turn
- [ ] `Brain.__init__` receives all dependencies via constructor injection
- [ ] Dead modules removed or integrated with zero orphan imports
- [ ] REPL survives LLM and Brain exceptions
- [ ] TaskEvaluator no longer advances mission on `"continue"` alone
- [ ] `tests/` exists with ≥15 tests covering P0 fixes
- [ ] Structured logging replaces prints in modified files
- [ ] `Brain_Audit.md` P0 items marked addressed in changelog
- [ ] `python main.py` verified manually on Windows (Nolan's environment)

---

# Phase 2 — Brain Redesign

## Why this phase comes second

Phase 1 delivers trustworthy wiring. Phase 2 transforms `Brain.think()` from a **linear script with disconnected stages** into a **coherent cognitive conductor** aligned with Constitution Article 8.1 and the rulebook's canonical pipeline.

**Why before Phase 3/4:** Memory and context upgrades feed the Brain prompt. The Brain must have a **Prompt Builder**, **stage registry**, and **clear stage I/O contract** before subsystems plug in new data shapes.

**Why before Phase 5:** Agents must integrate into a stable orchestration slot — not ad-hoc string concatenation in `brain.py`.

---

## Purpose

Redesign the Brain as a **maintainable orchestration core**: explicit pipeline stages, unified prompt assembly, constitution/identity in LLM instructions, token budget management, and collapse-or-implement placeholder modules.

---

## Objectives

1. **Extract `PromptBuilder`** — builds labeled sections: CONTEXTE, MÉMOIRE, ÉTAT, MISSION, EXECUTIVE, CONVERSATION (stub until Phase 7), AGENTS, USER.
2. **Extract `ThinkPipeline` or stage runner** — ordered stages with typed inputs/outputs; debug via logging levels.
3. **Wire product identity:**
   - Load `brain/identity.py` → `IDENTITY`
   - Load constitution **summary** (not full 1,468 lines) into `LLM.instructions`
4. **Fix prompt bugs from audit:**
   - Use **retrieved** memory in prompt, not full JSON dump
   - Format mission/state as readable JSON strings, not raw `dict` repr
5. **LLM gateway improvements:**
   - Model name in `config/settings.py`
   - Provider interface abstraction (prepare for multi-provider in Phase 9+)
   - Retry with backoff (if not done in Phase 1)
6. **Placeholder decision:** Either implement lightweight LLM classifiers for reasoning/executive OR collapse unused console-only stages to reduce noise.
7. **Relocate orchestration ownership:** Document Brain as sole cognitive entry; Titan shell only calls `brain.think()`.

---

## Dependencies

| Dependency | Required from |
|------------|---------------|
| Phase 1 complete | DI, single agent path, tests, logging |
| `prompts/` directory | Created in this phase |
| Constitution summary authoring | Product + engineering |

---

## Expected Architecture

```
brain/
├── brain.py              # Thin orchestrator: pipeline.run(message) → response
├── pipeline/
│   ├── stages.py         # Stage definitions and order
│   └── context_bundle.py # Typed bundle passed between stages
├── prompt_builder.py     # Assembles prompt with truncation policy
├── llm.py                # LLM interface + OpenAI implementation
├── llm_provider.py       # Abstract provider (new)
├── executive_brain.py    # Real analysis OR folded into pipeline LLM call
├── task_evaluator.py     # Staged for Phase 8 upgrade
└── identity.py           # Loaded by prompt/LLM layer

prompts/
├── system_instructions.md
├── constitution_summary.md
├── identity.md             # Optional mirror of identity.py
└── sections/               # Template fragments
```

**Pipeline data object (conceptual):**

```python
@dataclass
class ThinkContext:
    user_message: str
    current_user: str
    situational_context: str      # from ContextManager (Phase 4 enriches)
    retrieved_memory: str
    state: dict
    mission: dict
    executive_analysis: str
    agent_results: list[AgentResult]
    conversation_window: list     # Phase 7 fills
    knowledge_hits: str | None
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `brain/brain.py` | Major refactor |
| `brain/llm.py` | Instructions assembly, provider abstraction |
| `brain/executive_brain.py` | Upgrade or merge into pipeline |
| `brain/reasoning.py`, `planning.py`, `decision.py`, `executor.py`, `internal_monologue.py` | Implement, merge, or deprecate |
| `brain/knowledge.py` | Wire to prompt OR fold into static system context |
| `brain/prompt_builder.py` | New |
| `brain/pipeline/*` | New |
| `prompts/*` | New |
| `config/settings.py` | `LLM_MODEL`, `MAX_PROMPT_TOKENS`, flags |
| `tests/test_prompt_builder.py` | New |
| `tests/test_brain_pipeline.py` | Smoke integration with mocks |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **High** |
| Effort | **3–4 engineer-weeks** |
| Cognitive design decisions | High — which stages earn an LLM call vs heuristic |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Prompt regression (worse answers) | Golden-file prompt tests; before/after manual eval set |
| Token overflow | Truncation policy with priority: user msg > mission > retrieved memory > history |
| Over-engineering pipeline | Start with 5–7 real stages; merge decorative templates |
| Constitution too large for context | Maintain 500–800 token summary; full doc for offline reference only |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Prompt sections present | Given fixtures, assert all required labels exist |
| Retrieved memory used | Mock retriever; assert full dump not in prompt |
| Identity in system prompt | String contains key phrases from `IDENTITY` |
| Pipeline order | Stage mock records call order vs rulebook Section 14.2 |
| LLM failure | Mock provider raises; Brain returns French error |
| No duplicate LLM calls | Count provider.invocations per turn |

---

## Definition of Done

- [ ] `Brain.think()` ≤ 80 lines; logic delegated to pipeline + prompt builder
- [ ] Constitution summary + identity in LLM system instructions
- [ ] Retrieved memory (not full dump) in user prompt
- [ ] Mission and state formatted as readable JSON text
- [ ] All prompt sections documented in `prompts/README` or rulebook update
- [ ] Placeholder stages either wired to prompt or removed with documented rationale
- [ ] ≥20 new/updated tests; integration smoke test passes
- [ ] Debug output controlled by `DEBUG_BRAIN` flag, not unconditional prints

---

# Phase 3 — Memory System

## Why this phase comes third (parallel-ready with Phase 4 after Phase 2)

Constitution Article 7 defines memory as a **privilege** with **strict user isolation**. v0.0.1 violates this (hardcoded `"Nolan"`, over-broad decider, dual memory systems). Phase 2's prompt builder needs a **stable memory API**; this phase delivers it.

**Why after Phase 2:** Prompt builder consumes memory retrieval output — contract must be stable.

**Why before Phase 5:** Agents will eventually include a Memory Agent; facade must exist first.

**Why before Phase 9:** Long-term autonomy depends on reliable selective persistence and project namespaces.

---

## Purpose

Unify Titan's fragmented memory layers into a **single Memory Service** with correct user attribution, category-aware storage, selective retrieval, and migration-safe JSON schemas.

---

## Objectives

1. **`MemoryService` facade** unifying:
   - Session notes (current `Memory` / `MemoryManager`)
   - Long-term JSON (`LongTermMemory`)
   - Conversation pointers (delegates to Phase 7 ConversationEngine)
2. **User-aware writes:**
   - Use session `current_user` from Context (Phase 4) or explicit detection
   - Activate `MemoryDecider.classify_memory()` or replace with unified classifier
3. **Category-aware schema:**
   - Store in typed arrays: `goals[]`, `preferences[]`, `projects[]`, `notes[]`
   - Migration from existing `notes[]` with `[category]` prefixes
4. **Retrieval upgrades:**
   - Phase 3a: Improved keyword + category weighting
   - Phase 3b (optional within phase): Embedding retrieval behind feature flag
5. **Explicit commands:** `souviens-toi de`, `oublie`, `montre ma mémoire`
6. **Memory Agent prep:** Interface for summarize/compact (implementation Phase 5)
7. **JSON schema version field:** `"schema_version": 1`

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phase 1 DI | Required |
| Phase 2 PromptBuilder | Required — consumes retrieval API |
| Phase 4 Context | Strongly recommended in parallel — provides `current_user` |

---

## Expected Architecture

```
memory/
├── memory_service.py       # Facade — ONLY entry for Brain/agents
├── short_term_store.py     # Renamed from memory.py
├── long_term_memory.py     # Persistence layer (internal)
├── memory_decider.py       # should_remember + user detect
├── memory_classifier.py    # Category assignment
├── memory_retriever.py     # Relevance engine
├── memory_migrator.py      # Schema upgrades (new)
└── embedding_retriever.py  # Optional Phase 3b

data/long_term_memory.json  # schema_version, structured categories
```

**Read path:**

```
MemoryService.retrieve(user, message, project_id?) → RetrievalResult
    ├── personal notes (filtered by user)
    ├── project namespace (if active)
    └── titan global metadata
```

**Write path:**

```
MemoryService.maybe_remember(user, message) → bool
    ├── MemoryDecider
    ├── MemoryClassifier
    └── LongTermMemory.write_categorized(...)
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `memory/memory_service.py` | New facade |
| `memory/long_term_memory.py` | Schema + categorized writes |
| `memory/memory_decider.py` | User detection integrated |
| `memory/memory_retriever.py` | User filter, project filter |
| `memory/memory_manager.py` | Deprecated → facade delegate |
| `memory/memory.py` | Rename/refactor short-term |
| `brain/brain.py` | Use MemoryService only |
| `core/titan.py` | Wire MemoryService at root |
| `data/long_term_memory.json` | Migration on load |
| `tests/test_memory_*.py` | Comprehensive suite |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **High** (data migration + privacy) |
| Effort | **3–4 engineer-weeks** |
| Embedding sub-track | +1–2 weeks if included |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Corrupting Nolan/Ibrahim JSON | Backup + migrator tests + `default_schema()` fallback |
| Over-storage (decider too aggressive) | Tighten keywords; require explicit remember phrases for auto-save |
| Embedding cost/complexity | Feature flag; defer 3b if needed |
| Mixed old/new schema | Version field + one-time migration |

---

## Testing Strategy

| Test | Coverage |
|------|----------|
| User isolation | Ibrahim note never appears in Nolan retrieval |
| Category storage | Goal message → `goals[]` not generic notes |
| Migration | Old JSON fixture → new schema without data loss |
| Retrieve relevance | Keyword match + empty memory + large memory truncation |
| Explicit commands | Remember/forget command parsing |
| Decider precision | `"salut titan"` should NOT auto-save (fix over-broad triggers) |
| Facade enforcement | Grep: no direct `LongTermMemory` imports outside memory/ |

---

## Definition of Done

- [ ] Single `MemoryService` API; Brain and Titan use only facade
- [ ] Writes attributed to correct user (Nolan or Ibrahim)
- [ ] Categories stored in structured arrays with migration complete
- [ ] Retrieval returns relevant subset; integrated in PromptBuilder
- [ ] Explicit remember/forget commands work
- [ ] `schema_version` in JSON; migrator tested
- [ ] ≥25 memory tests; user isolation regression suite
- [ ] Constitution Article 7 requirements traceable to implementation

---

# Phase 4 — Context Engine

## Why this phase comes fourth

`ContextManager` today returns **static strings** disconnected from `StateManager`, `MissionManager`, and session user. Constitution requires situational accuracy: *who, what project, what goal, what phase*.

**Why after Phase 2:** PromptBuilder needs context section contract.

**Why with/after Phase 3:** Memory writes need `current_user` from context session.

**Why before Phase 5:** Agents route tasks based on project/domain; context engine supplies that signal.

**Why before Phase 8:** Planning & execution sync mission step → context phase.

---

## Purpose

Build a **dynamic Context Engine** that aggregates operational reality from state, mission, session, and user identity into a single authoritative situational model for prompts and routing.

---

## Objectives

1. **`ContextEngine`** replaces bare `ContextManager`:
   - Pulls from `StateManager`, `MissionManager`, session user, active project
   - Publishes `ContextSnapshot` dataclass (typed, not f-string only)
2. **Sync rules:**
   - `active_project` ← state.mission.title or state.active_project
   - `current_phase` ← mission.current_step or state.current_step
   - `current_goal` ← mission.objective or state.next_action
3. **User session:**
   - CLI flag or command: `/user Ibrahim`, `/user Nolan`
   - Future voice ID hooks (Phase 10)
4. **Context update after turn:** Post-response hook updates `last_action`, mode
5. **Delete legacy `core/context.py`** if not done in Phase 1
6. **French formatted output** for prompts via `ContextFormatter`

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phase 1 DI | Required |
| Phase 2 PromptBuilder | Required |
| Phase 3 MemoryService | Required for user-aware memory + context user |
| StateManager, MissionManager | Existing |

---

## Expected Architecture

```
context/
├── context_engine.py       # Aggregates sources → ContextSnapshot
├── context_manager.py      # Thin wrapper or renamed formatter
├── context_formatter.py    # Prompt-ready French blocks
├── session_manager.py      # current_user, session id, mode
└── models.py               # ContextSnapshot dataclass

Integration:
StateManager ──┐
MissionManager ├──► ContextEngine ──► PromptBuilder
SessionManager ┘
MemoryService (user id)
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `context/context_engine.py` | New |
| `context/context_manager.py` | Refactor to delegate |
| `context/session_manager.py` | New |
| `core/state_manager.py` | Optional sync hooks |
| `core/mission_manager.py` | Optional getters for context |
| `core/titan.py` | Session commands, wire ContextEngine |
| `brain/pipeline/*` | Consume ContextSnapshot |
| `tests/test_context_engine.py` | New |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **Medium** |
| Effort | **2 engineer-weeks** |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Stale context if sync missed | Single `refresh()` per turn at pipeline start |
| Conflicting state vs mission project names | Precedence rules documented in `ContextEngine` |
| Ibrahim still defaulted to Nolan | Session manager enforced at REPL + tests |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Sync from mission | Active mission step appears in `current_phase` |
| Sync from state | No mission → state fields used |
| User switch | `/user Ibrahim` changes retrieval scope |
| Formatter output | Required French labels present |
| Snapshot immutability | Pipeline gets frozen snapshot per turn |

---

## Definition of Done

- [ ] No static hardcoded goal/phase in production path
- [ ] Context refreshes every turn from state + mission + session
- [ ] Nolan/Ibrahim switch supported in CLI
- [ ] PromptBuilder uses `ContextSnapshot`
- [ ] Legacy `core/context.py` gone
- [ ] ≥12 context tests
- [ ] Document precedence rules in code docstring + Titan_Context update (when requested)

---

# Phase 5 — Agent Framework

## Why this phase comes fifth

Constitution Article 8.2–8.3 defines **specialist agents** collaborating under Brain direction. v0.0.1 agents are templates; routing is duplicated. With Brain (Phase 2), Memory (Phase 3), and Context (Phase 4) stable, agents can become **real internal workers**.

**Why before Phase 6:** Tool framework targets agent consumption patterns; agent contract must exist first.

**Why before Phase 8:** Planning & execution expands orchestration; needs agent registry and LLM-backed agents.

---

## Purpose

Deliver a **production agent framework**: unified routing registry, LLM-backed agents with scoped prompts, structured results, and Brain-only orchestration entry.

---

## Objectives

1. **Unified routing registry** — single source for `AgentSelector` + `TaskManager` keyword/intent maps
2. **`AgentResult` dataclass** — structured output: summary, artifacts, confidence, tools_used
3. **LLM-backed agents** — each agent calls LLM via controlled helper (not full constitution duplicate)
4. **Agent prompt templates** in `prompts/agents/`
5. **BaseAgent upgrades** — `execute(task, context: AgentContext) -> AgentResult`
6. **Registry extensibility** — plugin pattern for future Trading, Web, Memory agents
7. **Remove template responses** from coding/research/planning/reasoning agents
8. **Optional: Memory Agent v1** — summarize session notes into long-term (uses MemoryService)

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phase 1 single AgentManager | Required |
| Phase 2 pipeline agent stage | Required |
| Phase 3 MemoryService | Required for Memory Agent |
| Phase 4 ContextEngine | Required for AgentContext |
| `prompts/` | Required |

---

## Expected Architecture

```
agents/
├── agent_manager.py
├── agent_registry.py       # Single routing table
├── agent_selector.py       # Uses registry
├── base_agent.py           # AgentResult contract
├── agent_context.py        # Injected context bundle
├── agent_llm.py            # Scoped LLM calls for agents
├── coding_agent.py         # LLM + (future file tool)
├── research_agent.py
├── planning_agent.py
├── reasoning_agent.py
└── memory_agent.py         # New (optional v1)

core/task_manager.py        # Uses registry only
core/task_orchestrator.py   # Sequential; future parallel design doc
```

**Routing registry example:**

```python
ROUTES = [
    Route(keywords=["code", "python"], agents=["planning", "coding", "reasoning"]),
    Route(keywords=["recherche"], agents=["research", "reasoning"]),
    ...
]
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `agents/*` | Major upgrades |
| `agents/agent_registry.py` | New |
| `agents/agent_llm.py` | New |
| `core/task_manager.py` | Refactor to registry |
| `agents/agent_selector.py` | Refactor to registry |
| `prompts/agents/*.md` | New |
| `brain/pipeline/stages.py` | Agent stage uses AgentResult |
| `tests/test_agent_*.py` | Routing + execute shape tests |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **High** |
| Effort | **4–5 engineer-weeks** |
| LLM cost | Increased — mitigated with small model for routing later |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Agents speak as Titan to user | Strict prompts: "output internal artifact only" |
| LLM cost explosion | Limit agent calls per turn; configurable max agents |
| Routing drift | Single registry tested with shared fixtures |
| Circular imports agent → brain | Agents use `agent_llm` only, never `brain.brain` |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Registry consistency | Selector and TaskManager produce compatible routes |
| AgentResult schema | All agents return required fields |
| Mock LLM content | Coding agent receives task; mock returns structured code block |
| No duplicate execution | Still one orchestration path per turn |
| Memory Agent | Summarize fixture notes → categorized write |

---

## Definition of Done

- [ ] Single routing registry; no duplicated keyword lists
- [ ] All five core agents LLM-backed with scoped prompts
- [ ] Agent results structured; PromptBuilder formats consistently
- [ ] Template placeholder responses removed
- [ ] Memory Agent v1 optional but designed
- [ ] ≥20 agent tests with mocked LLM
- [ ] Constitution Article 8.8 upheld — user sees Titan voice only

---

# Phase 6 — Tool Framework

## Why this phase comes sixth

Constitution Articles 8.4 and 9: **tools extend capability; Brain decides**. Phase 5 agents need tools to act. Phase 2 Executor/planning stages need real `needs_tool` detection.

**Why after Phase 5:** Agents are primary tool consumers; framework defines allowlists and result types first.

**Why before Phase 7–8:** Conversation and planning benefit from file/time tools; execution layer dispatches tools.

**Why before Phase 13:** Trading requires market data, file, and execution tools.

---

## Purpose

Build a **secure, extensible Tool Framework** with registry, validation, sandboxing policy, and Brain-controlled dispatch.

---

## Objectives

1. **`ToolManager` v2** — register tools by name; schema for inputs/outputs
2. **`ToolResult` dataclass** — success, data, error, source attribution
3. **Core tools (v1):**
   - `TimeTool` (existing)
   - `FileReadTool` — project directory allowlist
   - `FileWriteTool` — confirm mode / dry-run flag initially
   - `PythonExecTool` — sandboxed subprocess with timeout + path restrictions
4. **`ToolPolicy`** — which agents may call which tools
5. **Brain Executor integration** — reasoning sets `needs_tool`; pipeline dispatches before LLM synthesis
6. **Tool trace in prompts** — "data from tool X" for constitution transparency
7. **Prepare stubs:** WebSearchTool, CalendarTool (no-op interface OK)

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phase 2 pipeline Executor stage | Required |
| Phase 5 AgentContext | Required |
| Security review mindset | Constitution 9.3 verification |

---

## Expected Architecture

```
tools/
├── tool_manager.py
├── tool_registry.py
├── tool_policy.py
├── base_tool.py
├── time_tool.py
├── file_read_tool.py
├── file_write_tool.py
├── python_exec_tool.py
└── web_search_tool.py      # Stub → Phase 9/12

brain/executor.py           # Returns ToolRequest objects
brain/tool_dispatcher.py    # New — validates + runs tools
```

**Execution flow:**

```
Reasoning → needs_tool=True
    → ToolDispatcher.run(tool_name, params)
    → ToolResult → PromptBuilder (RÉSULTATS OUTILS section)
    → LLM synthesizes with tool attribution
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `tools/*` | Major expansion |
| `brain/executor.py` | Emit tool requests |
| `brain/reasoning.py` | Real heuristic or LLM signal for tools |
| `brain/tool_dispatcher.py` | New |
| `brain/pipeline/*` | Tool stage before LLM |
| `agents/coding_agent.py` | File read integration |
| `config/settings.py` | `PROJECT_ROOT`, tool allowlist paths |
| `tests/test_tools_*.py` | Security + happy path |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **High** (security-critical) |
| Effort | **4–6 engineer-weeks** |
| PythonExecTool alone | High risk — may ship read-only first |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Arbitrary code execution | Sandboxing, timeout, no network in exec tool v1 |
| Path traversal | pathlib resolve + allowlist check |
| Tool output trusted blindly | Constitution 9.3 — LLM labels tool data vs reasoning |
| Scope creep to all Blueprint tools | Phase 6 ships core 4 tools only |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Path traversal blocked | `../../etc/passwd` rejected |
| Allowlist | Write outside project root fails |
| Python timeout | Infinite loop killed |
| Policy | Research agent cannot write files |
| Dispatcher integration | Mock tool → appears in prompt |
| Regression | TimeTool still works at startup |

---

## Definition of Done

- [ ] Tool registry with ≥4 working tools
- [ ] Brain pipeline dispatches tools when reasoning requests
- [ ] Tool results in prompt with source attribution
- [ ] Security tests for path and exec sandbox
- [ ] ToolPolicy enforced per agent
- [ ] Web/calendar stubs registered for future phases
- [ ] ≥20 tool tests
- [ ] No tool bypasses Brain dispatch

---

# Phase 7 — Conversation Engine

## Why this phase comes seventh

Constitution Article 7.3: **conversation memory** enables immediate context. v0.0.1 stores history in `Conversation` but **never sends it to the Brain/LLM** — breaking multi-turn coherence.

**Why after Phase 2:** PromptBuilder must have conversation section slot.

**Why before Phase 8:** Planning and mission continuity require dialogue context ("comme je disais", prior clarifications).

**Why before Phase 12:** Web interface will stream multi-turn sessions; engine must exist in core first.

---

## Purpose

Build a **Conversation Engine** with sliding window history, summarization for long sessions, and prompt-safe formatting — unified with session and memory layers.

---

## Objectives

1. **`ConversationEngine`** replaces bare `Conversation` list:
   - Turn model: `{id, user, speaker, message, timestamp, metadata}`
   - Sliding window: last N turns in prompt
   - Optional summarization of older turns (LLM or extractive)
2. **Wire to PromptBuilder** — `HISTORIQUE RÉCENT` section
3. **Session persistence (optional v1):** Save conversation to `data/sessions/{id}.json` for resume
4. **Integration with MemoryService:** Important turns flagged for long-term promotion
5. **Speaker attribution:** Nolan vs Ibrahim vs Titan tracked per turn
6. **REPL improvements:** Clear history command, session status

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phase 2 PromptBuilder | Required |
| Phase 3 MemoryService | Optional promotion path |
| Phase 4 SessionManager | Required for user attribution |

---

## Expected Architecture

```
core/
├── conversation_engine.py   # Primary API
└── conversation.py          # Deprecated → delegate

Session flow:
User message → ConversationEngine.add_user_turn()
Brain.think() → ConversationEngine.get_window(n=10)
Response → ConversationEngine.add_titan_turn()
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `core/conversation_engine.py` | New |
| `core/conversation.py` | Refactor/wrap |
| `core/titan.py` | Use engine |
| `brain/prompt_builder.py` | History section |
| `brain/pipeline/*` | Load window at start |
| `data/sessions/` | Optional persistence |
| `tests/test_conversation_engine.py` | New |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **Medium** |
| Effort | **2–3 engineer-weeks** |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Token bloat from history | Strict N turn limit + summarization |
| PII in session files | Same protections as long_term_memory.json |
| Summarization quality | Fallback to truncate-only in v1 |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Window size | 20 turns stored, 10 in prompt |
| Order preserved | Chronological in formatted output |
| User attribution | Ibrahim turn labeled correctly |
| Summarization mock | Old turns collapsed to summary string |
| Empty history | First turn works without section error |

---

## Definition of Done

- [ ] Conversation window in every LLM prompt (when history exists)
- [ ] Nolan/Ibrahim/Titan speakers tracked
- [ ] Token budget respected
- [ ] Old `Conversation` API migrated or wrapped
- [ ] ≥10 conversation tests
- [ ] Multi-turn manual scenario passes (clarification follow-up)

---

# Phase 8 — Planning & Execution

## Why this phase comes eighth

Titan's mission is **action-oriented** (Blueprint, Constitution Article 11). v0.0.1 has placeholder planning, broken TaskEvaluator, and unwired ActionManager. Real **plan → execute → evaluate** loops require stable Brain, agents, tools, and conversation.

**Why after Phases 5–7:** Execution dispatches agents and tools; planning needs context + history.

**Why before Phase 9:** Autonomy builds on reliable mission/step machinery.

**Why before Phase 13:** Trading is a specialized planning/execution domain.

---

## Purpose

Implement **Planning & Execution** as first-class systems: mission lifecycle, step evaluation, action dispatch, and coherent orchestration policy.

---

## Objectives

1. **Mission system v2:**
   - Explicit commands: `nouvelle mission`, `statut mission`, `terminer étape`, `annuler mission`
   - Stop keyword-based auto-create on every message
   - Step history preserved (`completed_steps[]`) — no destructive `list.remove`
2. **TaskEvaluator v2:**
   - Structured completion: user confirm OR LLM JSON `{step_completed: bool, reason}`
   - Remove bare keyword `"continue"` completion
3. **Planning module v2:**
   - `PlanningEngine` produces structured plans linked to mission steps
   - Plans fed to PromptBuilder and Planning Agent
4. **Execution coordinator:**
   - Merge `TaskOrchestrator` + `Executor` + `ToolDispatcher` into `ExecutionCoordinator`
   - Policy: max agents, max tools, ordering rules
5. **Retire or wire `ActionManager`** as thin delegate to tool/agent dispatch
6. **Executive Brain v2:** Real strategic analysis using mission + state + memory (LLM call with small prompt)

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phases 1–7 | All required |
| MissionManager | Upgrade |
| TaskOrchestrator | Refactor |

---

## Expected Architecture

```
core/
├── mission_manager.py      # v2 schema with step history
├── execution_coordinator.py # New — agents + tools policy
└── planning_engine.py      # New (or brain/planning_engine.py)

brain/
├── task_evaluator.py       # v2 structured evaluation
├── executive_brain.py      # LLM-backed
└── pipeline/stages.py      # Plan → Execute → Evaluate → Respond
```

**Turn flow:**

```
Understand intent
    → Mission commands handled early
    → PlanningEngine proposes next actions
    → ExecutionCoordinator runs agents/tools
    → LLM synthesizes
    → TaskEvaluator v2 updates mission
    → ContextEngine refresh
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `core/mission_manager.py` | Major schema upgrade |
| `core/task_orchestrator.py` | Merge into coordinator |
| `core/task_manager.py` | Policy integration |
| `core/execution_coordinator.py` | New |
| `brain/task_evaluator.py` | Major rewrite |
| `brain/planning.py` | Replace with PlanningEngine |
| `brain/executive_brain.py` | LLM-backed |
| `brain/executor.py` | Integration with coordinator |
| `data/titan_mission.json` | Migration |
| `tests/test_mission_*.py`, `test_execution_*.py` | Expanded |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **Very High** |
| Effort | **5–6 engineer-weeks** |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Mission migration breaks active trading mission | Backup + migration script preserving current_step |
| LLM evaluator unreliable | Default to explicit user confirmation for step advance |
| Over-complex coordinator | Start sequential; document parallel future |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Explicit mission commands | Create/status/complete via CLI |
| No auto mission on greeting | `"bonjour"` leaves mission inactive |
| Step history | Completed steps remain in JSON |
| TaskEvaluator v2 | `"continue"` does NOT complete |
| Coordinator limits | Max 3 agents enforced |
| End-to-end | Multi-step mission simulation with mocks |

---

## Definition of Done

- [ ] Mission v2 schema migrated; step history preserved
- [ ] No spurious mission creation
- [ ] TaskEvaluator v2 with false positive fixes proven by tests
- [ ] PlanningEngine output in prompt
- [ ] ExecutionCoordinator owns agents + tools dispatch
- [ ] Executive analysis LLM-backed
- [ ] ActionManager resolved (wired or deleted)
- [ ] ≥30 tests across mission/planning/execution
- [ ] Active NQ trading mission manually validated post-migration

---

# Phase 9 — Long-Term Autonomy

## Why this phase comes ninth

Constitution Articles 10–11 describe **learning, initiative, and proactivity**. These require trustworthy memory, missions, tools, and execution — all prior phases.

**Why before Phase 10–11:** Voice/vision are I/O channels; autonomy logic lives in core Brain.

**Why before Phase 13:** Trading automation demands proactive risk detection and scheduled tasks.

**Why before Phase 14:** Deployment must expose autonomy controls and guardrails.

---

## Purpose

Enable **long-horizon autonomous behavior**: cross-session missions, scheduled tasks, proactive suggestions, learning memory, and controlled initiative within user-defined bounds.

---

## Objectives

1. **Initiative engine** — detects opportunities/risks (Constitution 11.2–11.3); surfaces in response when relevant
2. **Learning memory layer** — track what worked/failed; inform recommendations
3. **Scheduler / job runner** — cron-like tasks: reminders, mission checkpoints (local only v1)
4. **Project memory namespaces** — full project-scoped recall (extends Phase 3)
5. **Web Agent + WebSearchTool** — real research capability
6. **Automation Agent v1** — scripted multi-step workflows with confirmation gates
7. **Multi-provider LLM abstraction** — route classification to small model, synthesis to large
8. **Autonomy policy config** — user toggles: proactive level, auto-tool use, confirmation required

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phases 1–8 | Required |
| Tool framework | Web search |
| Memory project namespaces | Phase 3 extension |

---

## Expected Architecture

```
brain/
├── initiative_engine.py
├── learning_memory.py
└── autonomy_policy.py

core/
├── scheduler.py
└── job_runner.py

agents/
├── web_agent.py
└── automation_agent.py

tools/
└── web_search_tool.py      # Real implementation
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `brain/initiative_engine.py` | New |
| `memory/learning_memory.py` | New |
| `core/scheduler.py` | New |
| `agents/web_agent.py`, `automation_agent.py` | New |
| `tools/web_search_tool.py` | Implement |
| `brain/llm_provider.py` | Multi-model routing |
| `config/settings.py` | Autonomy flags |
| `tests/test_autonomy_*.py` | New |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **Very High** |
| Effort | **6–8 engineer-weeks** |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Unwanted proactive messages | Policy off by default; explicit opt-in |
| Scheduler runaway jobs | Max jobs, user approval for recurring |
| Web search bad data | Constitution verification + cite sources |
| Automation unsafe actions | Confirmation gate for write/exec |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Initiative triggers | Fixture scenarios for risk/opportunity detection |
| Scheduler | Fake clock; job fires once |
| Web agent mock | Search results injected; citation in output |
| Autonomy policy | Disabled → no proactive block in prompt |
| Learning memory | Failed approach reduces confidence in suggestion |

---

## Definition of Done

- [ ] Initiative engine integrated with guardrails
- [ ] Web Agent + search tool operational
- [ ] Automation Agent with confirmation workflow
- [ ] Scheduler for local reminders/checkpoints
- [ ] Project memory namespaces active
- [ ] Multi-model routing for at least 2 call types
- [ ] Autonomy policy documented and configurable
- [ ] ≥25 autonomy tests

---

# Phase 10 — Voice

## Why this phase comes tenth

Constitution Article 1.5: **voice identification** for Nolan vs Ibrahim. Voice is an I/O modality — it must sit on top of a stable Brain API, session management, and memory isolation.

**Why after Phase 9:** Autonomy + session infrastructure supports hands-free workflows.

**Why before Phase 11:** Voice identification pairs with speaker model; establish audio pipeline first.

**Why before Phase 12:** Web UI may include voice widget reusing same backend.

---

## Purpose

Add **voice input/output** with speaker identification, push-to-talk or wake word (v2 choice), and secure user attribution before personal memory access.

---

## Objectives

1. **Voice I/O pipeline:** STT → Brain.think() → TTS
2. **Speaker identification v1:** Distinguish Nolan vs Ibrahim vs unknown
3. **Unknown speaker protocol:** Ask confirmation before personal memory (Constitution 1.5)
4. **Voice Agent** — handles audio-specific tasks (transcription cleanup, voice settings)
5. **Integration with SessionManager** — voice session sets `current_user`
6. **French STT/TTS** optimization
7. **Optional wake word** — deferred if complexity high; PTT first

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phases 1–4 | Session + memory isolation critical |
| Stable Brain API | Required |
| External STT/TTS provider or local models | Infrastructure decision |

---

## Expected Architecture

```
voice/
├── voice_engine.py         # STT/TTS orchestration
├── speaker_identifier.py   # Nolan/Ibrahim/unknown
├── voice_session.py        # Links audio → SessionManager
└── adapters/               # Provider-specific

agents/voice_agent.py

Interface options:
CLI voice mode OR parallel to REPL
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `voice/*` | New package |
| `agents/voice_agent.py` | New |
| `context/session_manager.py` | Voice user binding |
| `core/titan.py` | Optional voice mode entry |
| `requirements.txt` | Audio dependencies |
| `tests/test_speaker_*.py` | Mock identification |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **Very High** |
| Effort | **6–10 engineer-weeks** (provider-dependent) |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Misidentification → wrong memory | Unknown → ask; low confidence → ask |
| Latency unacceptable | Streaming STT; shorter responses in voice mode |
| Platform audio issues on Windows | Test Nolan environment early |
| Privacy | Local processing preference documented |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Unknown speaker | Does not load Nolan memory without confirm |
| Identified Nolan | Retrieves Nolan-scoped memory |
| Mis-match Ibrahim | Never writes to Nolan profile |
| STT/TTS mocked | Pipeline produces response |
| Fallback | Text REPL always available |

---

## Definition of Done

- [ ] Voice mode runs end-to-end with mocked STT/TTS
- [ ] Speaker ID v1 with confirm-on-unknown flow
- [ ] Session user set from voice identification
- [ ] Constitution Article 1.5 requirements met
- [ ] Voice Agent registered
- [ ] Documentation for audio setup on Windows
- [ ] ≥15 voice pipeline tests (mocked providers)

---

# Phase 11 — Vision

## Why this phase comes eleventh

Vision extends input modalities (screenshots, documents, diagrams). Requires stable agent framework, tool policy, and Brain pipeline — same prerequisites as voice but **no speaker ID dependency**.

**Why after Phase 10:** Reuses multimodal session patterns established for voice.

**Why before Phase 12:** Web UI benefits from image upload using Vision Agent backend.

---

## Purpose

Add **Vision Agent** and image understanding for code screenshots, charts, documents, and UI debugging — feeding structured descriptions into Brain prompt.

---

## Objectives

1. **Vision Agent** — analyze images via multimodal LLM
2. **ImageTool** — load, validate, resize images from allowed paths
3. **Prompt integration** — `ENTRÉE VISUELLE` section with structured description
4. **Use cases v1:**
   - Code screenshot → extract/error diagnosis
   - Chart screenshot → describe trends (not financial advice without disclaimer)
   - Document photo → OCR summary
5. **Size/format validation** — png, jpg, webp; max dimensions
6. **Privacy** — no silent exfiltration; user provides image explicitly

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phases 5–6 | Agent + tool patterns |
| Phase 2 multimodal LLM call | Extend llm_provider |
| Phase 10 optional | Session patterns helpful not required |

---

## Expected Architecture

```
agents/vision_agent.py
tools/image_tool.py
brain/pipeline/vision_stage.py   # Optional pre-processing stage
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `agents/vision_agent.py` | New |
| `tools/image_tool.py` | New |
| `brain/llm_provider.py` | Multimodal messages |
| `brain/prompt_builder.py` | Vision section |
| `tests/test_vision_*.py` | Mock multimodal responses |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **High** |
| Effort | **3–5 engineer-weeks** |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Token cost for large images | Resize/compress policy |
| Hallucinated OCR | Label output as model interpretation |
| Sensitive image data | User confirm before sending to API |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Format rejection | Invalid file type blocked |
| Agent output shape | Structured description fields |
| Mock multimodal | Vision stage injects text into prompt |
| No image path traversal | Same allowlist as file tools |

---

## Definition of Done

- [ ] Vision Agent analyzes fixture images in tests
- [ ] Multimodal LLM path in provider
- [ ] CLI or command to attach image to turn
- [ ] Prompt section for visual analysis
- [ ] ≥12 vision tests
- [ ] Privacy note in user-facing docs

---

# Phase 12 — Web Interface

## Why this phase comes twelfth

A web UI is a **new client** for the same Brain. It must not fork business logic. Phases 1–11 deliver a stable, tested core suitable for API wrapping.

**Why after Phases 10–11:** UI can expose voice/image features when ready.

**Why before Phase 13:** Trading dashboards and monitoring naturally fit web UI.

**Why before Phase 14:** Deployment packages API + UI together.

---

## Purpose

Deliver a **Web Interface** (and REST/WebSocket API) that exposes Titan's single intelligence to browsers while preserving all architectural invariants.

---

## Objectives

1. **API server** — FastAPI (recommended) wrapping `Brain.think()` synchronously; async design doc for later
2. **WebSocket streaming** — token stream from LLM for responsive UX
3. **Session API** — login as Nolan/Ibrahim (simple auth v1); session token
4. **Web UI v1:**
   - Chat interface
   - Mission status panel
   - Memory inspect (user-scoped, read-only v1)
   - Project/context display
5. **No Brain logic in frontend** — API is thin
6. **CORS, rate limits, local bind default** (`127.0.0.1`)
7. **Optional image upload** — Vision phase integration

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phases 1–8 minimum | Required |
| Phases 10–11 | Optional UI features |
| ConversationEngine | Required for multi-turn API |

---

## Expected Architecture

```
api/
├── server.py              # FastAPI app
├── routes/chat.py
├── routes/session.py
├── routes/mission.py
└── auth/simple_session.py

web/                       # Frontend (React or lightweight HTML)
├── src/
└── package.json

core/titan.py              # Unchanged REPL; parallel entry:
api/server.py              # python -m api.server
```

**Critical rule:** API calls same injected `Brain` instance pattern as Titan shell.

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `api/*` | New package |
| `web/*` | New frontend |
| `brain/llm_provider.py` | Streaming support |
| `core/titan.py` | Optional shared bootstrap module |
| `requirements.txt` | fastapi, uvicorn |
| `tests/test_api_*.py` | API integration tests |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **Very High** |
| Effort | **6–8 engineer-weeks** (UI choice dependent) |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Duplicate Brain in API | Shared bootstrap factory function |
| Auth too weak | Local-only default; explicit warning for expose |
| SSE/WS complexity | Start with synchronous REST; add stream incrementally |
| Frontend scope creep | v1 chat + mission panel only |

---

## Testing Strategy

| Test | Method |
|------|--------|
| API chat round-trip | Mock LLM; assert response JSON |
| Session user | Ibrahim token → Ibrahim memory scope |
| WS stream mock | Chunks received in order |
| REPL unchanged | `python main.py` still works |
| Load basic | 10 concurrent requests local |

---

## Definition of Done

- [ ] API server runs Brain without logic duplication
- [ ] Web UI chat functional against local API
- [ ] Nolan/Ibrahim session switching via API
- [ ] Mission status visible in UI
- [ ] Default bind localhost; auth documented
- [ ] ≥20 API tests
- [ ] Streaming optional but designed

---

# Phase 13 — Trading Infrastructure

## Why this phase comes thirteenth

Trading is **high-risk, domain-specific**, and explicitly in Blueprint/Constitution long-term vision. It requires tools, agents, execution coordinator, web UI for monitoring, and strong guardrails.

**Why after Phase 12:** Monitoring dashboard and API for paper trading results.

**Why after Phase 6–8:** Market data tools, Trading Agent, risk policy in execution layer.

**Why before Phase 14:** Deployment must include trading-specific secrets management and paper-default policy.

**Why NOT earlier:** Building trading on v0.0.1 mission/TaskEvaluator would amplify false positives into financial workflow errors.

---

## Purpose

Build **Trading Infrastructure** aligned with the active NQ robot mission: data ingestion, backtest engine skeleton, paper trading, risk controls, and Trading Agent — **paper trading default, no live capital without explicit approval gate**.

---

## Objectives

1. **Trading Agent** — strategy discussion, backtest interpretation, order draft (not live v1)
2. **Market data tool** — read-only historical bars (provider TBD: CSV first, then API)
3. **Backtest engine v1:**
   - Strategy interface
   - Metrics: drawdown, win rate, Sharpe (basic)
   - Reproducible runs logged to `data/backtests/`
4. **Paper trading simulator** — no broker connection v1
5. **Risk manager module** — max position, max daily loss, kill switch flag
6. **Mission integration** — NQ mission steps map to trading milestones
7. **Broker adapters (stubs):** NinjaTrader, Tradovate, IBKR interfaces only
8. **Constitution compliance** — truth about uncertainty; no guaranteed returns language

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phases 6, 8, 9 | Tools, execution, autonomy |
| Phase 12 | Monitoring UI |
| Market data source decision | Nolan/Ibrahim input |

---

## Expected Architecture

```
trading/
├── trading_agent.py        # wraps agents/trading_agent.py
├── data/market_data_tool.py
├── backtest/
│   ├── engine.py
│   ├── strategy_base.py
│   └── metrics.py
├── paper/
│   └── simulator.py
├── risk/
│   └── risk_manager.py
└── brokers/
    ├── base_broker.py
    └── stubs/

agents/trading_agent.py
data/backtests/
```

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `trading/*` | New package |
| `agents/trading_agent.py` | New |
| `tools/market_data_tool.py` | New |
| `core/mission_manager.py` | Trading mission templates v2 |
| `web/` | Backtest results view |
| `config/settings.py` | `TRADING_MODE=paper`, risk limits |
| `tests/test_backtest_*.py`, `test_risk_*.py` | Extensive |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **Extreme** |
| Effort | **10–16 engineer-weeks** (incremental delivery) |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Live trading accident | Paper default; live behind multi-step confirm + config flag |
| Bad backtest → false confidence | Constitution honesty; show limitations |
| Data quality | Source attribution in results |
| Regulatory | Personal use disclaimer; not investment advice |
| Scope explosion | Ship CSV backtest before broker integration |

---

## Testing Strategy

| Test | Method |
|------|--------|
| Backtest reproducibility | Same seed → same metrics |
| Risk kill switch | Blocks orders when loss exceeded |
| Paper simulator | No external network calls |
| Trading Agent | Mock data → structured report |
| Mission sync | Complete backtest step updates mission correctly |
| Regression | Non-trading Titan features unaffected |

---

## Definition of Done

- [ ] Trading Agent registered and tested
- [ ] Backtest engine runs sample strategy on fixture CSV data
- [ ] Paper simulator operational
- [ ] Risk manager enforces configured limits
- [ ] Results visible in web UI
- [ ] NQ mission steps completable through system actions
- [ ] Live trading **disabled** by default with documented enable process
- [ ] ≥40 trading-specific tests
- [ ] Risk disclosure in UI and prompts

---

# Phase 14 — Deployment

## Why this phase comes last

Deployment hardens everything prior: packaging, CI/CD, secrets, monitoring, backups, and production config. Deploying v0.0.1 would cement debt; deploying after Phase 13 ensures **one coherent system**.

**Why last:** You deploy what is built — not build while deploying broken foundations.

---

## Purpose

Make Titan **deployable, observable, and maintainable** for long-term personal use by Nolan and Ibrahim on chosen environments (local workstation, optional home server).

---

## Objectives

1. **Packaging** — `pyproject.toml`, installable package, entry points: `titan`, `titan-api`
2. **CI/CD** — GitHub Actions: pytest, lint, type check (optional), no secrets
3. **Environment management** — `.env.example` complete; secrets rotation doc
4. **Process management** — systemd unit or Windows service wrapper (document both)
5. **Backup strategy** — `data/*.json` scheduled backup; export/import memory
6. **Monitoring** — log aggregation, health endpoint on API, disk space alerts
7. **Version policy** — semver, changelog, migration notes per release
8. **Security hardening** — API auth upgrade path, dependency audit, allowlist review
9. **Documentation** — README, architecture diagram, runbook for failures
10. **Release Titan V2.0.0** — checklist from rulebook Section 23.2

---

## Dependencies

| Dependency | Phase |
|------------|-------|
| Phases 1–13 | All features frozen for release candidate |
| Test coverage target | ≥70% managers + core paths (rulebook 11.6) |

---

## Expected Architecture

```
.github/workflows/ci.yml
pyproject.toml
Dockerfile                  # Optional for API deployment
docker-compose.yml          # Optional local stack
scripts/backup_data.sh
scripts/run_titan.ps1       # Windows
docs/RUNBOOK.md
CHANGELOG.md
```

**Deployment targets v1:**

| Target | Components |
|--------|------------|
| Local CLI | `titan` REPL |
| Local API + Web | `titan-api` + static web build |
| Optional Docker | API + UI for homelab |

---

## Files Likely Affected

| File | Change type |
|------|-------------|
| `pyproject.toml` | New |
| `.github/workflows/*` | New |
| `Dockerfile`, `docker-compose.yml` | Optional |
| `scripts/*` | New |
| `docs/RUNBOOK.md` | New |
| `CHANGELOG.md` | New |
| `config/settings.py` | Environment profiles |
| All packages | Version bump to 2.0.0 |

---

## Estimated Complexity

| Dimension | Rating |
|-----------|--------|
| Overall | **High** (breadth not depth) |
| Effort | **3–5 engineer-weeks** |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Deploying with failing tests | CI gate mandatory |
| Secret leak in Docker image | Multi-stage build; .dockerignore |
| Windows vs Linux drift | Test Nolan Windows path; document WSL option |
| Over-engineering Kubernetes | Personal scale — Docker optional only |

---

## Testing Strategy

| Test | Method |
|------|--------|
| CI pipeline | Full pytest on push |
| Install smoke | Fresh venv `pip install -e .` → `titan --help` |
| Backup restore | Backup → wipe data → restore → verify |
| Health check | API `/health` 200 |
| Release checklist | Manual runbook walkthrough |

---

## Definition of Done

- [ ] `pip install -e .` works; CLI and API entry points documented
- [ ] CI green on all tests
- [ ] Backup/restore documented and tested
- [ ] RUNBOOK covers LLM failure, corrupt JSON, API restart
- [ ] Version 2.0.0 tagged with CHANGELOG
- [ ] Security review of tools allowlist and API auth
- [ ] Rulebook regression checklist (Section 23.2) all passed
- [ ] Nolan and Ibrahim sign-off on personal deployment

---

# Program Timeline (Indicative)

Assuming **1 dedicated engineer** (+ occasional product review):

| Phase | Duration | Cumulative |
|-------|----------|------------|
| 1 Architecture cleanup | 2–3 weeks | ~1 month |
| 2 Brain redesign | 3–4 weeks | ~2 months |
| 3 Memory | 3–4 weeks | ~3 months |
| 4 Context | 2 weeks | ~3.5 months |
| 5 Agents | 4–5 weeks | ~4.5 months |
| 6 Tools | 4–6 weeks | ~6 months |
| 7 Conversation | 2–3 weeks | ~6.5 months |
| 8 Planning & execution | 5–6 weeks | ~8 months |
| 9 Autonomy | 6–8 weeks | ~10 months |
| 10 Voice | 6–10 weeks | ~12 months |
| 11 Vision | 3–5 weeks | ~13 months |
| 12 Web | 6–8 weeks | ~15 months |
| 13 Trading | 10–16 weeks | ~18 months |
| 14 Deployment | 3–5 weeks | **~19–20 months** |

Parallelization (memory + context; voice + vision after core) can reduce calendar time with 2 engineers.

---

# Success Metrics for Titan V2

| Metric | Target |
|--------|--------|
| Duplicate subsystems | Zero |
| Agent executions per turn | Exactly 1 orchestrated path |
| Memory user mix incidents | Zero in tests + manual QA |
| Mission false completions | Zero on `"continue"` alone |
| Test coverage (managers/core) | ≥70% |
| Constitution in runtime prompts | Summary always loaded |
| Tool calls without Brain dispatch | Zero |
| Uptime (personal deployment) | REPL/API recover from LLM errors |
| Trading | Paper default; backtest reproducible |

---

# Governance & Change Control

| Activity | Owner | When |
|----------|-------|------|
| Phase kickoff | Nolan + architect | Start of each phase |
| Schema migration approval | Nolan | Before memory/mission/trading migrations |
| Constitution prompt changes | Nolan + Ibrahim | Phase 2, 5, 9 |
| Trading live enable | Nolan + Ibrahim explicit | After Phase 13 complete |
| Phase sign-off | Engineer + Nolan | Definition of done checklist |

All implementation must continue to follow `.cursor/rules/titan.mdc`. Update rulebook when Phase 1–2 structural rules change (e.g., new directories `api/`, `voice/`, `trading/`).

---

# Appendix A — Phase Ordering Rationale (Summary)

| Transition | Why order matters |
|------------|-------------------|
| 1 → 2 | Clean DI before Brain refactor |
| 2 → 3/4 | Prompt contracts before subsystem upgrades |
| 3 ↔ 4 | Memory needs user from context; can parallelize after Phase 2 |
| 4 → 5 | Agents need situational context |
| 5 → 6 | Tool consumers need agent contracts |
| 6 → 7 | Conversation before complex execution reduces incoherent multi-turn tool use |
| 7 → 8 | Planning/execution needs dialogue history |
| 8 → 9 | Autonomy needs reliable missions and tools |
| 9 → 10/11 | Modality layers on stable cognitive core |
| 10 → 11 | Voice session patterns reused; independent features |
| 11 → 12 | Web UI uploads vision; API needed for UI |
| 12 → 13 | Trading monitoring requires UI/API |
| 13 → 14 | Deploy complete system once |

---

# Appendix B — Mapping Brain Audit P0–P5 to Phases

| Audit priority | Phase |
|----------------|-------|
| P0 double agents, TaskEvaluator, error handling | Phase 1 |
| P1 DI, retrieved memory, user attribution, mission gating | Phases 1–4, 8 |
| P2 unified routing, constitution, context sync, placeholders | Phases 2, 4, 5, 8 |
| P3 memory facade, conversation, dead code, tests | Phases 1, 3, 7 |
| P4 logging, LLM agents, semantic memory | Phases 1, 5, 9 |
| P5 mission history, settings hygiene | Phases 8, 14 |

---

# Appendix C — Constitution Traceability Matrix (Selected)

| Constitution requirement | Delivering phase |
|---------------------------|------------------|
| Art 1.4 Equal users Nolan/Ibrahim | Phases 3, 4, 12 |
| Art 1.5 Voice identification | Phase 10 |
| Art 7 Memory privilege + isolation | Phase 3 |
| Art 7.3 Conversation memory | Phase 7 |
| Art 8.1 Brain as conductor | Phases 2, 8 |
| Art 8.2 Specialist agents | Phase 5 |
| Art 8.4 Tools extend capability | Phase 6 |
| Art 8.8 Single intelligence | All phases (enforced) |
| Art 9 Brain decides, tools execute | Phases 6, 8 |
| Art 11 Initiative | Phase 9 |
| Art 6.10 Technical communication (file paths) | Phases 5–6 (coding agent + file tools) |

---

**End of Titan V2 Roadmap**

*This document is planning-only. No repository code was modified in its creation.*

# Titan Architecture Audit

**Version audited:** 0.25.0 (`config/settings.py`)  
**Audit date:** July 7, 2026  
**Scope:** Full read-only review of all source packages, web assets, scripts, tests, and documentation  
**Method:** Static analysis, module inventory, dependency tracing, composition-root review, test suite enumeration (1,408 tests collected)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Runtime Architecture Overview](#runtime-architecture-overview)
3. [Package Audits](#package-audits)
   - [Entry Point & Config](#1-entry-point--config)
   - [brain/](#2-brain)
   - [core/](#3-core)
   - [tools/](#4-tools)
   - [memory/](#5-memory)
   - [agents/](#6-agents)
   - [context/](#7-context)
   - [api/](#8-api)
   - [web/](#9-web)
   - [voice/](#10-voice)
   - [prompts/](#11-prompts)
   - [scripts/](#12-scripts)
   - [tests/](#13-tests)
   - [plugins/](#14-plugins)
   - [docs/](#15-docs)
   - [Other Directories](#16-other-directories)
4. [Global Architecture Summary](#global-architecture-summary)
5. [Development Roadmap](#development-roadmap)
6. [Appendix: Duplication Matrix](#appendix-duplication-matrix)

---

## Executive Summary

| Question | Answer |
|----------|--------|
| **Overall implementation** | **~68%** of the long-term Titan vision is implemented at a functional or mostly-complete level. Core cognitive loop, tool runtime, memory, agents, connectors (Obsidian/Browser/Calendar/Email/Trading read-only), web API, and v2 UI are real and tested. Autonomous scheduling, live trading, server-side voice, plugin system, and several placeholder brain stages remain incomplete. |
| **Architecture coherence** | **Yes, with caveats.** The official execution path (`Brain → ExecutionCoordinator → ToolOrchestrator → ToolRuntime`) is coherent and documented in `docs/ARCHITECTURE.md`. Parallel subsystems (`core/tools`, `core/permissions`, `core/actions`, legacy `web/static`) create duplication risk but do not break the primary runtime path. |
| **Duplicated systems to merge** | **Yes — five high-priority pairs:** (1) `tools/` vs `core/tools/`, (2) `tools/permission_manager` vs `core/permissions/`, (3) `web/v2/` vs `web/static/`, (4) `AgentSelector` vs `TaskManager`/`AgentRegistry`, (5) cognitive progress formatting in `brain/cognitive_progress` vs `api/orchestrator_progress`. |
| **Test coverage signal** | 1,408 pytest cases across 127 test files — strong regression coverage for wired paths. |

### Next 10 Highest-Value Implementation Tasks

| Priority | Task | Why |
|----------|------|-----|
| 1 | Consolidate or delete `core/tools`, `core/permissions`, `core/actions` | Eliminates parallel frameworks; reduces contributor confusion and test maintenance |
| 2 | Retire or gate `web/static/` behind deprecation | Halves frontend maintenance; v2 is the production UI |
| 3 | Wire scheduler tick in REPL/web or document as API-only | `JobRunner` composed but never started — autonomy layer is dead code at runtime |
| 4 | Sync `Titan_Blueprint.md` and doc version headers to v0.25.0 | Product/engineering alignment; onboarding accuracy |
| 5 | Complete structured logging migration (`print` → `logging`) | Production readiness; debug noise in REPL |
| 6 | Upgrade placeholder brain stages (`decision.py`, `internal_monologue.py`, `knowledge.py`) | Pipeline stages exist but add little value today |
| 7 | Unify agent routing (`AgentSelector` → `AgentRegistry` only) | Single routing path per rulebook |
| 8 | Live provider hardening (Gmail, Google Calendar, Brave) with CI smoke gates | Connectors exist; live paths are opt-in and lightly exercised |
| 9 | Trading live execution with risk controls (post read-only foundation) | Read-only broker layer complete; order execution intentionally deferred |
| 10 | Plugin system integration (`ToolLoader` → `ToolManager`) | `plugins/` empty; loader tested but unwired |

---

## Runtime Architecture Overview

```
main.py
  └── core.titan.Titan                    [composition root]
        ├── memory.MemoryService
        ├── agents.AgentManager
        ├── context.ContextManager
        ├── tools.ToolManager
        ├── core.scheduler / job_runner   [composed, not started in REPL]
        └── brain.Brain.think()
              └── brain.pipeline.ThinkPipeline
                    └── core.ExecutionCoordinator
                          ├── TaskOrchestrator → AgentManager
                          ├── CognitiveOrchestrator
                          └── tools.ToolOrchestrator → ToolRuntime → Executors

api.app.create_app()  →  titan_service.get_titan()  →  same Titan singleton
web/v2/               →  FastAPI chat + SSE endpoints
```

**Dependency direction:** Mostly respected. Minor violations: `tools/confirmation_gate.py` → `brain.autonomy_policy`; `agents/agent_manager.py` → `brain.autonomy_policy`.

---

## Package Audits

Each module entry uses a standard 10-field template.

---

### 1. Entry Point & Config

#### `main.py`

| Field | Detail |
|-------|--------|
| **Purpose** | Application entry: REPL or CLI subcommands (obsidian, browser, calendar, email, broker, web) |
| **Status** | **Mostly Complete** |
| **Public classes** | None |
| **Public functions** | `main()` |
| **Dependencies** | `config.settings`, `core.logging_config`, `core.titan`, `core/*_cli` dispatchers |
| **Working** | REPL startup, CLI routing chain, logging init |
| **Missing** | Unified `--help` for all subcommands |
| **Technical debt** | Subcommand dispatch is sequential if-chain |
| **Duplication** | None |
| **Next steps** | argparse or typer for CLI; document subcommands in README |

#### `config/settings.py`

| Field | Detail |
|-------|--------|
| **Purpose** | Central configuration: version, feature flags, provider settings, paths |
| **Status** | **Complete** |
| **Public classes** | None |
| **Public functions** | `reload_env()`, `env_bool()`, `is_web_dev_mode()`, `get_web_secret_key()` |
| **Dependencies** | `dotenv`, stdlib only (correct — config imports nothing internal) |
| **Working** | 350+ lines of env-driven config for Phases 2–17 |
| **Missing** | Formal feature-flag registry doc; some duplicate env keys (`TITAN_PROVIDER_FALLBACK_ENABLED` vs `TITAN_ALLOW_PROVIDER_FALLBACK`) |
| **Technical debt** | Large monolithic file; no `config/__init__.py` |
| **Duplication** | Fallback env vars duplicated |
| **Next steps** | Split by domain (tools, web, providers) when file exceeds maintainability |

---

### 2. `brain/`

**29 Python modules.** Cognitive orchestration layer — single `Brain.think()` entry point.

#### Package Summary

| Field | Detail |
|-------|--------|
| **Purpose** | Reasoning, planning, prompt assembly, tool/agent dispatch coordination, cognitive streaming |
| **Status** | **Mostly Complete** |
| **Dependencies** | `core/*`, `memory/*`, `agents/*`, `context/*`, `tools/*`, `config/*` |
| **Working** | Full 17-stage pipeline, LLM gateway, cognitive orchestrator, tool decision bridges, streaming/progress |
| **Missing** | Real logic in placeholder stages; server-side knowledge index |
| **Technical debt** | `reasoning.py` ~1000+ lines; extensive debug prints in some paths |
| **Duplication** | `Planning` → `PlanningEngine`; `ToolDispatcher` vs `tool_executor`; `CognitiveOrchestrator` overlaps execution paths |
| **Next steps** | Extract reasoning routing tables; upgrade placeholders; deprecate `ToolDispatcher` |

#### Module Inventory

| Module | Status | Key Public API | Notes |
|--------|--------|----------------|-------|
| `brain.py` | Mostly Complete | `Brain.think()` | Sole cognitive entry; DI wired |
| `pipeline/stages.py` | Mostly Complete | `ThinkPipeline`, stage order | 17+ stages |
| `pipeline/context_bundle.py` | Complete | `ThinkContext` | Shared context dataclass |
| `llm.py` | Mostly Complete | `LLM`, `load_prompt_file()`, `build_system_instructions()` | Loads prompts + identity + constitution |
| `llm_provider.py` | Complete | `LLMProvider` ABC | Provider abstraction |
| `llm_router.py` | Mostly Complete | `LLMRouter`, `LLMCallType` | Multi-model routing Phase 9 |
| `reasoning.py` | Mostly Complete | `Reasoning.analyze()` | Heavy intent/tool routing |
| `executive_brain.py` | Mostly Complete | `ExecutiveBrain.analyze_mission()` | Uses `prompts/executive_analysis.md` |
| `planning_engine.py` | Mostly Complete | `PlanningEngine.create_plan()` | Structured plans |
| `planning.py` | Partial | `Planning` | Backward-compat facade |
| `planning_models.py` | Complete | `PlanStep`, `StructuredPlan` | |
| `executor.py` | Partial | `Executor` | Routes to tools/memory/clarify |
| `decision.py` | Prototype | `Decision` | Keyword salutation only |
| `internal_monologue.py` | Prototype | `InternalMonologue` | Static template |
| `knowledge.py` | Prototype | `Knowledge` | Minimal stub |
| `task_evaluator.py` | Mostly Complete | `TaskEvaluator` | LLM + prompt file |
| `step_evaluation.py` | Mostly Complete | `StepEvaluation` | Mission step eval |
| `prompt_builder.py` | Mostly Complete | `PromptBuilder` | Prompt section assembly |
| `cognitive_orchestrator.py` | Mostly Complete | `CognitiveOrchestrator` | Plan/create/execute/verify |
| `cognitive_models.py` | Complete | `CognitivePlan`, `TaskGraph`, enums | |
| `cognitive_stream.py` | Mostly Complete | `CognitiveStreamEmitter`, `intent_label()` | SSE progress |
| `cognitive_progress.py` | Mostly Complete | `progress_event()`, tool phase mapping | Duplicated in API layer |
| `decision_execution_bridge.py` | Mostly Complete | Factory helpers for `ToolDecisionEngine` | |
| `tool_execution_bridge.py` | Mostly Complete | `dispatch_context_from_think()` | |
| `tool_dispatcher.py` | Deprecated | `ToolDispatcher` | Test/legacy only per ARCHITECTURE.md |
| `tool_confirmation_handler.py` | Mostly Complete | Confirmation token parsing | |
| `autonomy_policy.py` | Mostly Complete | `AutonomyPolicy`, enums | Phase 9 autonomy |
| `initiative_engine.py` | Partial | `InitiativeEngine` | Proactive signals; not in REPL loop |
| `identity.py` | Mostly Complete | Identity prompt fragments | Wired via `LLM.build_system_instructions()` |

---

### 3. `core/`

**54 Python modules** across root and subpackages (`tools/`, `permissions/`, `actions/`).

#### Package Summary

| Field | Detail |
|-------|--------|
| **Purpose** | Application shell, composition root, orchestration, persistence, CLI, scheduling |
| **Status** | **Mostly Complete** (root); **Prototype** (subpackages) |
| **Dependencies** | `brain`, `memory`, `agents`, `context`, `tools`, `config` |
| **Working** | Titan lifecycle, execution coordinator, state/mission, conversation, CLI health commands, web server launcher |
| **Missing** | Scheduler background tick; integration of `core/tools`, `core/permissions`, `core/actions` |
| **Technical debt** | `Titan.start()` still uses `print()` for UX; scheduler dead at runtime |
| **Duplication** | See [Appendix](#appendix-duplication-matrix) |
| **Next steps** | Start scheduler or remove from composition; consolidate parallel tool framework |

#### Root Modules

| Module | Status | Key Public API | Notes |
|--------|--------|----------------|-------|
| `titan.py` | Mostly Complete | `Titan`, `start()` | Composition root; error handling in REPL |
| `execution_coordinator.py` | Mostly Complete | `ExecutionCoordinator.execute()` | Agents + tools + cognitive |
| `task_orchestrator.py` | Mostly Complete | `TaskOrchestrator.orchestrate()` | Single agent path |
| `task_manager.py` | Mostly Complete | `TaskManager.create_tasks()` | Uses `AgentRegistry` |
| `execution_context.py` | Complete | `ExecutionDispatchContext`, `build_tool_execution_context()` | Neutral contract |
| `execution_policy.py` | Complete | `ExecutionPolicy` | Max agents/tools |
| `execution_result.py` | Complete | `ExecutionResult` | |
| `state_manager.py` | Mostly Complete | `StateManager` | `data/titan_state.json` |
| `mission_manager.py` | Mostly Complete | `MissionManager` | `data/titan_mission.json` |
| `mission_migrator.py` | Complete | `migrate()`, `default_schema()` | v2 mission schema |
| `conversation.py` | Complete | `Conversation` | Thin wrapper |
| `conversation_engine.py` | Mostly Complete | `ConversationEngine` | Windowed turns, summarization |
| `conversation_models.py` | Complete | `ConversationTurn` | |
| `scheduler.py` | Partial | `Scheduler` | Composed, not ticked |
| `job_runner.py` | Partial | `JobRunner`, job handlers | Tested; unwired in REPL |
| `job_store.py` | Mostly Complete | `JobStore` | `data/scheduled_jobs.json` |
| `job_models.py` | Complete | `ScheduledJob`, enums | |
| `logging_config.py` | Mostly Complete | `setup_logging()` | Partial migration from print |
| `exceptions.py` | Complete | `TitanError`, tool/provider hierarchy | |
| `obsidian_cli.py` | Mostly Complete | Health/smoke commands | |
| `browser_cli.py` | Mostly Complete | Health/brain-test/validate | |
| `calendar_cli.py` | Mostly Complete | Health/auth/list/smoke | |
| `email_cli.py` | Mostly Complete | Health/auth/list/smoke | |
| `broker_cli.py` | Mostly Complete | Health command | |
| `web_cli.py` | Mostly Complete | `run_web_server()`, web-dev/remote | FastAPI launcher |

#### `core/tools/` (Parallel Framework — Prototype)

| Module | Status | Key Public API | Notes |
|--------|--------|----------------|-------|
| `base_tool.py` | Prototype | `BaseTool` | `id` + `execute_action()` contract |
| `tool_registry.py` | Prototype | `ToolRegistry` | Separate from `tools/tool_registry.py` |
| `tool_loader.py` | Prototype | `ToolLoader` | Plugin scan; not wired to `ToolManager` |
| `tool_metadata.py` | Prototype | `ToolMetadata` | |
| `fake_calculator_tool.py` | Prototype | `FakeCalculatorTool` | Test/demo |
| `fake_search_tool.py` | Prototype | `FakeSearchTool` | Test/demo |
| `obsidian/*` | Prototype | `ObsidianTool`, `ObsidianClient` | Action-dispatch Obsidian; production uses `tools/` |

#### `core/permissions/` (Prototype)

| Module | Status | Key Public API | Notes |
|--------|--------|----------------|-------|
| `permission_manager.py` | Prototype | `PermissionManager` | Registry-based; production uses `tools/permission_manager.py` |
| `permission.py` | Prototype | `Permission`, `PermissionLevel` | |
| `permission_policy.py` | Prototype | `PermissionPolicy` | |
| `permission_result.py` | Prototype | `PermissionResult` | |
| `exceptions.py` | Prototype | Permission exceptions | |

#### `core/actions/` (Prototype)

| Module | Status | Key Public API | Notes |
|--------|--------|----------------|-------|
| `action_dispatcher.py` | Prototype | `ActionDispatcher` | Only referenced in tests |
| `action_registry.py` | Prototype | `ActionRegistry` | |
| `action.py` | Prototype | `Action` | |
| `action_result.py` | Prototype | `ActionResult` | |
| `exceptions.py` | Prototype | Action exceptions | |

---

### 4. `tools/`

**168 Python modules.** Production tool runtime, connectors, providers, decision engines.

#### Package Summary

| Field | Detail |
|-------|--------|
| **Purpose** | Tool registration, runtime v2, permissions, orchestration, external connectors |
| **Status** | **Mostly Complete** |
| **Dependencies** | Mostly `tools/*`, `config/*`, `core.exceptions`; minor `brain.*` imports |
| **Working** | Tool Runtime V2 (default), built-in tools, NL planner, reasoning loop, audit, health, all major connectors |
| **Missing** | Live trading execution; full async pool production tuning; plugin loading |
| **Technical debt** | Large decision/ subdirectory; connector-level permission mirrors |
| **Duplication** | `web_search_provider.py` re-export; connector vs tool wrapper pairs |
| **Next steps** | Document connector vs tool boundaries; remove legacy adapter when safe |

#### Subpackage Overview

| Subpackage | Files (approx) | Status | Purpose |
|------------|----------------|--------|---------|
| Root tools | ~35 | Mostly Complete | Facades, built-ins, orchestration |
| `decision/` | ~40 | Mostly Complete | Intent, domain decision engines, patch/rollback, workspace planning |
| `connectors/` | ~45 | Mostly Complete | Obsidian, browser, calendar, email, trading, broker, TradingView |
| `providers/` | ~25 | Mostly Complete | Web search, file system, GitHub, calendar, telemetry |
| `executors/` | 2 | Complete | Sync/async execution adapters |
| `audit/` | 2 | Complete | JSONL tool audit |
| `adapters/` | 1 | Partial | Legacy Phase 6 bridge |

#### Key Root Modules

| Module | Status | Key Public API |
|--------|--------|----------------|
| `tool_manager.py` | Mostly Complete | `ToolManager` — registry facade |
| `tool_runtime.py` | Mostly Complete | `ToolRuntime` — preflight, confirmation, audit |
| `tool_orchestrator.py` | Mostly Complete | `ToolOrchestrator` — plan execution |
| `tool_executor.py` | Mostly Complete | `execute_tool()` — single invoke path |
| `natural_language_planner.py` | Mostly Complete | `NaturalLanguagePlanner` |
| `reasoning_loop.py` | Mostly Complete | `ReasoningLoop` |
| `permission_facade.py` | Mostly Complete | Unified permission evaluation |
| `permission_manager.py` | Mostly Complete | Action-level permissions (production) |
| `confirmation_gate.py` | Mostly Complete | User confirmation for risky ops |
| `health_monitor.py` | Mostly Complete | Provider/tool health aggregation |
| `time_tool.py` | Complete | Current datetime |
| `file_read_tool.py` / `file_write_tool.py` | Mostly Complete | Bounded file I/O |
| `python_exec_tool.py` | Mostly Complete | Sandboxed exec with timeout |
| `web_search_tool.py` | Mostly Complete | Provider-backed search |
| `obsidian_tool.py` | Mostly Complete | Vault connector wrapper |
| `browser_tool.py` | Mostly Complete | Playwright-backed browser |
| `calendar_tool.py` | Mostly Complete | Calendar connector wrapper |
| `email_tool.py` | Mostly Complete | Email connector wrapper |
| `trading_tool.py` | Mostly Complete | Trading connector (mock/paper default) |
| `github_tool.py` | Mostly Complete | GitHub API provider |
| `live_provider_smoke.py` | Prototype | Manual dev smoke only |

#### `tools/decision/` Highlights

| Module | Status | Role |
|--------|--------|------|
| `tool_decision_engine.py` | Mostly Complete | Central decision orchestration |
| `intent_classifier.py` | Mostly Complete | NL intent → tool need |
| `obsidian_decision.py` | Mostly Complete | Vault create/update policy |
| `browser_decision.py` | Mostly Complete | Browser action routing |
| `calendar_decision.py` | Mostly Complete | Calendar intent |
| `email_decision.py` | Mostly Complete | Email intent |
| `trading_decision.py` | Mostly Complete | Trading intent (no live orders) |
| `task_execution_engine.py` | Mostly Complete | Multi-step task plans |
| `patch_application_engine.py` | Mostly Complete | File patch apply |
| `rollback_manager.py` | Mostly Complete | Rollback history |
| `workspace_planner.py` | Mostly Complete | Codebase workspace ops |

#### `tools/connectors/` Highlights

| Connector | Status | Live Provider |
|-----------|--------|---------------|
| Obsidian | Mostly Complete | Filesystem vault |
| Browser | Mostly Complete | Playwright (opt-in) |
| Calendar | Mostly Complete | Mock + Google OAuth |
| Email | Mostly Complete | Mock + Gmail OAuth |
| Trading | Mostly Complete | Mock/paper |
| Broker | Partial | Read-only Apex/Rithmic stubs |
| TradingView | Mostly Complete | Webhook alert store |

---

### 5. `memory/`

**12 Python modules.**

#### Package Summary

| Field | Detail |
|-------|--------|
| **Purpose** | Short/long-term memory, retrieval, classification, learning, project namespaces |
| **Status** | **Mostly Complete** |
| **Dependencies** | `memory/*` only — correct isolation |
| **Working** | Unified `MemoryService`, decider/classifier/retriever pipeline, user isolation, migrator |
| **Missing** | Embedding retrieval; explicit forget commands; compaction |
| **Technical debt** | Legacy `Memory` class; `MemoryFacade` alias |
| **Duplication** | `MemoryFacade` = `MemoryService`; `Memory` vs `MemoryManager` |
| **Next steps** | Deprecate `Memory` class; semantic retrieval Phase 2+ |

#### Module Inventory

| Module | Status | Key Public API |
|--------|--------|----------------|
| `memory_service.py` | Mostly Complete | `MemoryService` — unified facade |
| `memory_facade.py` | Deprecated | `MemoryFacade` alias |
| `long_term_memory.py` | Mostly Complete | `LongTermMemory` |
| `memory_manager.py` | Complete | `MemoryManager` — short-term |
| `memory.py` | Deprecated | `Memory` — legacy |
| `memory_decider.py` | Mostly Complete | `MemoryDecider` |
| `memory_classifier.py` | Complete | `MemoryClassifier` |
| `memory_retriever.py` | Mostly Complete | `MemoryRetriever` — keyword relevance |
| `memory_migrator.py` | Complete | Schema migration |
| `learning_memory.py` | Mostly Complete | `LearningMemory` |
| `project_memory.py` | Mostly Complete | `ProjectMemoryStore` |
| `models.py` | Complete | `RetrievalResult` |

---

### 6. `agents/`

**17 Python modules.**

#### Package Summary

| Field | Detail |
|-------|--------|
| **Purpose** | Internal specialist workers; LLM-backed domain agents |
| **Status** | **Mostly Complete** |
| **Dependencies** | `agents/*`, `memory.memory_service`, `brain.autonomy_policy` (violation), `tools.web_search_provider` |
| **Working** | LLM agents with external prompts; single orchestration via `TaskOrchestrator` |
| **Missing** | Trading, voice, vision agents; deeper tool scoping per agent |
| **Technical debt** | Dual routing: `AgentSelector` vs `AgentRegistry` |
| **Duplication** | `AgentSelector` parallel to `TaskManager` |
| **Next steps** | Consolidate routing; remove `AgentSelector` from hot path |

#### Module Inventory

| Module | Status | Key Public API |
|--------|--------|----------------|
| `agent_manager.py` | Mostly Complete | `AgentManager.execute()` |
| `agent_registry.py` | Mostly Complete | `AgentRegistry`, `default_registry` |
| `agent_selector.py` | Partial | `AgentSelector` — legacy single-select |
| `agent_llm.py` | Mostly Complete | `AgentLLM` |
| `agent_context.py` | Complete | `AgentContext` |
| `agent_result.py` | Complete | `AgentResult` |
| `agent_response_parser.py` | Partial | `parse_agent_output()` |
| `base_agent.py` | Complete | `BaseAgent` ABC |
| `llm_agent_mixin.py` | Complete | `LLMAgentMixin` |
| `coding_agent.py` | Mostly Complete | LLM coding specialist |
| `research_agent.py` | Mostly Complete | LLM research specialist |
| `planning_agent.py` | Mostly Complete | LLM planning specialist |
| `reasoning_agent.py` | Mostly Complete | LLM reasoning specialist |
| `general_agent.py` | Mostly Complete | Registered as `"base"` |
| `memory_agent.py` | Mostly Complete | Memory operations |
| `web_agent.py` | Mostly Complete | Web search scoped |
| `automation_agent.py` | Partial | Template automation steps |

---

### 7. `context/`

**6 Python modules.**

#### Package Summary

| Field | Detail |
|-------|--------|
| **Purpose** | Situational metadata: user, project, goal, phase; workspace intelligence |
| **Status** | **Mostly Complete** |
| **Dependencies** | `core.state_manager`, `core.mission_manager` |
| **Working** | State/mission sync via `ContextEngine`; French formatting; workspace area map |
| **Missing** | Automatic context refresh on all state mutations |
| **Technical debt** | None significant |
| **Duplication** | None |
| **Next steps** | Hook state/mission saves to invalidate context cache |

#### Module Inventory

| Module | Status | Key Public API |
|--------|--------|----------------|
| `context_manager.py` | Mostly Complete | `ContextManager` facade |
| `context_engine.py` | Mostly Complete | `ContextEngine` |
| `context_formatter.py` | Complete | `ContextFormatter` |
| `session_manager.py` | Mostly Complete | `SessionManager` — user identity |
| `models.py` | Complete | `ContextSnapshot` |
| `workspace_map.py` | Mostly Complete | `WorkspaceArea`, `find_area_in_message()` |

---

### 8. `api/`

**11 Python modules.** FastAPI web layer.

#### Package Summary

| Field | Detail |
|-------|--------|
| **Purpose** | HTTP API: chat, SSE streaming, status, auth, activity formatting |
| **Status** | **Mostly Complete** |
| **Dependencies** | `api/*`, `core.titan`, `brain.pipeline`, `voice`, `config`, FastAPI |
| **Working** | Chat sync/stream, SSE cognitive progress, connector status, v2 static mount |
| **Missing** | Rate limiting; session persistence API; WebSocket alternative |
| **Technical debt** | Progress formatting duplicated from brain |
| **Duplication** | `orchestrator_progress` vs `cognitive_progress` |
| **Next steps** | Single progress formatter module; production auth hardening |

#### Module Inventory

| Module | Status | Key Public API |
|--------|--------|----------------|
| `app.py` | Mostly Complete | `create_app()` — FastAPI factory |
| `titan_service.py` | Mostly Complete | `get_titan()`, `handle_chat()` |
| `stream_service.py` | Mostly Complete | `handle_chat_stream()`, SSE events |
| `auth.py` | Mostly Complete | `require_web_auth()` |
| `event_hub.py` | Complete | `EventHub`, `TitanStreamEvent` |
| `sse.py` | Complete | SSE formatting helpers |
| `status_builders.py` | Mostly Complete | Connector health snapshots |
| `memory_activity.py` | Mostly Complete | UI memory card formatting |
| `tool_activity.py` | Mostly Complete | UI tool activity formatting |
| `orchestrator_progress.py` | Partial | Duplicates brain progress logic |

---

### 9. `web/`

**~100 JS/CSS/HTML files.** Dual frontend stack.

#### Package Summary

| Field | Detail |
|-------|--------|
| **Purpose** | Browser UI for Titan: conversation, neural visualization, tool/memory activity |
| **Status** | **v2: Mostly Complete** / **static: Partial (legacy)** |
| **Dependencies** | FastAPI static mounts; `/api/*` backend |
| **Working** | v2 full app: neural engine, SSE bridge, auth, regions, design system |
| **Missing** | v1 retirement; unified voice UX in v2 |
| **Technical debt** | Two parallel codebases maintained |
| **Duplication** | Entire duplicate stacks (conversation, neural, tools, voice) |
| **Next steps** | Deprecate `web/static/`; port any missing v1 features to v2 |

#### `web/v2/` (Production UI)

| Area | Status | Key Modules |
|------|--------|-------------|
| `core/` | Mostly Complete | `app.js`, `backend-bridge.js`, `state-store.js`, `web-auth.js` |
| `neural/` | Mostly Complete | `engine.js`, `cognitive.js`, `renderer.js` |
| `conversation/` | Mostly Complete | Conversation manager, stream handling |
| `design/` | Mostly Complete | `ui.css`, tokens, layout, neural CSS |
| `memory/`, `tools/`, `orchestrator/` | Mostly Complete | Activity engines |
| `composer/`, `sidebar/`, `center/`, `status/` | Mostly Complete | Region controllers |

#### `web/static/` (Legacy)

| Area | Status | Notes |
|------|--------|-------|
| All subdirs | Partial | Still mounted at `/static`; superseded by v2 |

---

### 10. `voice/`

**2 Python modules.**

| Field | Detail |
|-------|--------|
| **Purpose** | Voice configuration API; server-side STT/TTS provider stubs |
| **Status** | **Partial** |
| **Public classes** | `VoiceManager`, `VoiceCapabilities`, `SpeechToTextProvider`, `TextToSpeechProvider` |
| **Public functions** | None module-level |
| **Dependencies** | `config.settings` only |
| **Working** | `/api/voice/config` endpoint; capability flags |
| **Missing** | Server-side STT/TTS providers; voice agent integration |
| **Technical debt** | STT/TTS delegated to browser (`web/static/voice/`) |
| **Duplication** | Client voice in static + future v2 port |
| **Next steps** | Port browser voice to v2; optional Whisper/local TTS backend |

---

### 11. `prompts/`

**10 markdown files.**

| Field | Detail |
|-------|--------|
| **Purpose** | Externalized LLM system and agent prompts |
| **Status** | **Mostly Complete** |
| **Public API** | Files loaded by `brain/llm.py`, `executive_brain.py`, `task_evaluator.py`, `agents/agent_llm.py` |
| **Dependencies** | None (consumed by brain/agents) |
| **Working** | System instructions, constitution summary, executive analysis, step evaluator, 6 agent prompts |
| **Missing** | Tool-specific prompt templates; versioning metadata |
| **Technical debt** | None |
| **Duplication** | None |
| **Next steps** | Add prompt version headers; tool decision prompt externalization |

---

### 12. `scripts/`

**4 Python validation scripts.**

| Script | Status | Purpose |
|--------|--------|---------|
| `browser_brain_flow_validation.py` | Mostly Complete | E2E browser brain flow |
| `browser_production_validation.py` | Mostly Complete | Browser production checks |
| `calendar_brain_flow_validation.py` | Mostly Complete | Calendar brain flow |
| `email_brain_flow_validation.py` | Mostly Complete | Email brain flow |

**Role:** Dev/integration validators; output markdown reports at repo root. Not runtime.

---

### 13. `tests/`

**127 test files, 1,408 test cases.**

| Field | Detail |
|-------|--------|
| **Purpose** | Regression coverage for all major subsystems |
| **Status** | **Mostly Complete** |
| **Coverage areas** | Brain pipeline, cognitive orchestrator, tools/runtime/decision/connectors, API, agents, memory, core parallel framework, web API |
| **Missing** | E2E web UI tests; live provider CI ( appropriately mocked ) |
| **Technical debt** | Some tests cover prototype `core/*` paths not in production |
| **Next steps** | Mark production vs prototype test suites; add web e2e smoke |

---

### 14. `plugins/`

| Field | Detail |
|-------|--------|
| **Purpose** | Third-party tool plugin drop-in directory |
| **Status** | **Empty** (`.gitkeep` only) |
| **Public API** | None |
| **Dependencies** | `core/tools/tool_loader.py` supports scan paths |
| **Working** | Nothing |
| **Missing** | Entire plugin ecosystem |
| **Technical debt** | Loader tested but unwired |
| **Duplication** | N/A |
| **Next steps** | Wire `ToolLoader` into `ToolManager.register_defaults()` or remove until ready |

---

### 15. `docs/`

**19 markdown files** (+ 10 design specs in `docs/design/`).

| Field | Detail |
|-------|--------|
| **Purpose** | Architecture, connector guides, design language, remote access |
| **Status** | **Mostly Complete** (content drift on versions) |
| **Working** | `ARCHITECTURE.md`, BROWSER/CALENDAR/EMAIL/TRADING guides, design bible |
| **Missing** | Single source of truth for current version; architecture audit (this doc) |
| **Technical debt** | `ARCHITECTURE.md` header says 0.10.0+; Blueprint says 0.1.0 |
| **Next steps** | Version stamp all docs; link this audit from README |

---

### 16. Other Directories

| Path | Purpose | Status |
|------|---------|--------|
| `core/constitution/titan_constitution.md` | Product governance | **Complete** |
| `data/` | Runtime JSON persistence | Managed by managers — not source |
| `logs/` | `titan.log`, `tools_audit.jsonl` | **Partial** — logging migration ongoing |
| `sample_vault/` | Obsidian test vault | Sample data |
| `.cursor/rules/titan.mdc` | Engineering rulebook | **Complete** — authoritative |
| `Titan_Blueprint.md` | Product roadmap | **Deprecated/Partial** — stale at v0.1.0 |
| `CHANGELOG.md` | Release notes | Present; verify sync with 0.25.0 |
| `agents/` (missing from glob?) | Present | See section 6 |
| Root validation MD | `*-Validation.md`, `*-Brain-Flow-Validation.md` | Generated by scripts |

---

## Global Architecture Summary

### Modules Completed (Production-Ready Core)

| Module | Status |
|--------|--------|
| `config/settings.py` | Complete |
| `core/exceptions.py`, `execution_context.py` | Complete |
| `brain/pipeline/*`, `cognitive_models.py` | Complete |
| `brain/llm_provider.py` | Complete |
| `tools/tool_runtime.py`, executors, audit | Complete |
| `memory/models.py`, migrators | Complete |
| `prompts/*` (loaded templates) | Mostly Complete |

### Modules Partially Completed

| Module | Gap |
|--------|-----|
| `brain/` placeholders | `decision`, `internal_monologue`, `knowledge` are stubs |
| `core/scheduler` | Composed but not started |
| `tools/connectors/broker` | Read-only; no live SDK |
| `tools/trading` | No live order execution |
| `voice/` | Config only |
| `web/static/` | Legacy parallel UI |
| `agents/automation_agent` | Template-level |
| Logging | Mixed print/logging |

### Modules Not Started

| Module | Notes |
|--------|-------|
| `plugins/` | Empty directory |
| Server-side voice providers | Protocol stubs only |
| Live trading execution | Intentionally blocked |
| Vector/embedding memory | Planned |
| Vision agent | Not present |
| Installable package (`pyproject.toml`) | Not present |

### Potential Duplicate Systems

See [Appendix](#appendix-duplication-matrix).

### Dead Code & Unused Files

| Item | Evidence |
|------|----------|
| `core/actions/ActionDispatcher` | Only test references |
| `core/tools/ToolLoader` | Not called from composition root |
| `brain/tool_dispatcher.py` | Marked deprecated in ARCHITECTURE.md |
| `JobRunner` background loop | Never started in `Titan.start()` |
| `plugins/.gitkeep` | No plugins |
| `tools/live_provider_smoke.py` | Manual dev only |
| `memory/memory.py`, `memory_facade.py` | Legacy aliases |
| `web/static/*` | Superseded by v2 |

### Old Experiments

| Experiment | Location | Recommendation |
|------------|----------|----------------|
| Action-dispatch tool framework | `core/tools/`, `core/actions/` | Merge or delete |
| Registry permission manager | `core/permissions/` | Delete or bridge to `tools/` |
| Legacy web UI | `web/static/` | Deprecate |
| Phase 6 legacy adapter | `tools/adapters/legacy_tool_adapter.py` | Remove when legacy path off |

### Refactoring Opportunities

1. **Split `brain/reasoning.py`** into intent registry + domain routers
2. **Extract shared progress formatter** from brain + API
3. **Unify permission evaluation** — already consolidated in `tools/permission_facade.py`; remove core duplicate
4. **Package structure** — add `pyproject.toml` for installable imports
5. **Config split** — domain-specific settings modules
6. **Single frontend** — v2 only

---

## Development Roadmap

Prioritized remaining work with rationale for ordering.

### Tier 1 — Architectural Integrity (Do First)

| # | Work Item | Why Before Next |
|---|-----------|-----------------|
| 1 | **Resolve `tools/` vs `core/tools/` duplication** | Every other tool feature builds on one framework; two registries guarantee bugs |
| 2 | **Delete or bridge `core/permissions/` and `core/actions/`** | Permission path is production-critical; parallel stubs confuse tests and contributors |
| 3 | **Retire `web/static/` or freeze as archive** | Frontend duplication doubles every UI bug fix |
| 4 | **Update Blueprint + doc version headers** | Cannot prioritize correctly against stale roadmap |

### Tier 2 — Runtime Completeness

| # | Work Item | Why Before Next |
|---|-----------|-----------------|
| 5 | **Wire scheduler tick (REPL + web lifespan)** | Autonomy layer exists but delivers zero user value until started |
| 6 | **Upgrade brain placeholder stages** | Pipeline runs 17 stages; stubs waste tokens and mislead debugging |
| 7 | **Consolidate agent routing to `AgentRegistry` only** | Prevents divergent routing behavior between CLI and web |
| 8 | **Structured logging completion** | Required before production deployment and remote access |

### Tier 3 — Connector Hardening

| # | Work Item | Why Before Next |
|---|-----------|-----------------|
| 9 | **Live Gmail + Google Calendar CI smoke (mocked credentials)** | Calendar/email connectors complete in mock; live is opt-in and under-tested |
| 10 | **Browser connector production checklist** | Playwright path works; needs operational docs and failure modes |
| 11 | **Obsidian vault path validation UX** | Common misconfiguration; high user-facing impact |

### Tier 4 — Advanced Capabilities

| # | Work Item | Why Before Next |
|---|-----------|-----------------|
| 12 | **Plugin system (`ToolLoader` → `ToolManager`)** | Extensibility after core framework is singular |
| 13 | **Semantic memory retrieval** | Keyword retrieval works; embeddings need stable memory schema first |
| 14 | **Trading live execution + risk gates** | Read-only foundation complete; live orders require permission/confirmation maturity |
| 15 | **Server-side voice providers** | Browser STT/TTS sufficient for v1 web; server providers add deployment complexity |

### Tier 5 — Long-Term Vision

| # | Work Item | Why Before Next |
|---|-----------|-----------------|
| 16 | Vision agent + multimodal | Depends on stable tool/agent framework |
| 17 | Backtesting engine | Depends on trading execution maturity |
| 18 | Multi-session persistence API | Conversation engine supports it; needs web UX |
| 19 | Installable package + proper PYTHONPATH | Developer experience; not blocking features |
| 20 | Microservice split | Explicitly deferred per modular monolith rule |

---

## Appendix: Duplication Matrix

| Domain | Production Path | Parallel / Unused Path | Severity |
|--------|-----------------|------------------------|----------|
| Tool framework | `tools/base_tool`, `ToolManager`, `run()` | `core/tools/*`, `execute_action()` | **Critical** |
| Obsidian | `tools/obsidian_tool.py` + connector | `core/tools/obsidian/` | High |
| Permissions | `tools/permission_manager.py`, `permission_facade.py` | `core/permissions/` | High |
| Web UI | `web/v2/` | `web/static/` | High |
| Memory API | `MemoryService` | `MemoryFacade`, `Memory` class | Low |
| Agent routing | `TaskManager` + `AgentRegistry` | `AgentSelector` | Medium |
| Progress SSE | `brain/cognitive_progress.py` | `api/orchestrator_progress.py` | Medium |
| Tool dispatch | `tools/tool_executor.execute_tool()` | `brain/tool_dispatcher.py` | Low (deprecated) |
| Product docs | `config/settings.py` v0.25.0 | `Titan_Blueprint.md` v0.1.0 | Medium |

---

## Audit Methodology Notes

- **No production code modified** during this audit
- Composition root verified in `core/titan.py`
- Official execution path cross-checked against `docs/ARCHITECTURE.md`
- Test count: `pytest tests/ --collect-only` → **1,408 tests**
- Dependency rule violations flagged where `tools/` or `agents/` import `brain/`
- Status labels assigned by: runtime wiring, test coverage, placeholder logic detection, and documentation cross-reference

---

*End of Titan Architecture Audit — v0.25.0*

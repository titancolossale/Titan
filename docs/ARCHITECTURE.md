# Titan Architecture — Execution Path (Phase 12.8+)

**Version:** 0.39.0  
**Last updated:** July 13, 2026

This document describes the **official runtime execution path** after Phase 12.8 Core Consolidation Sprint, updated for Natural Language Orchestrator V1. It supersedes stale descriptions in `Brain_Audit.md` and rulebook Section 14.2 for tool routing.

---

## Layer Responsibilities

| Layer | Module | Owns | Must NOT own |
|-------|--------|------|--------------|
| **Natural Language Orchestrator** | `brain/natural_language_orchestrator.py` | NL intent → Brain system routing; `process_request` front door | Tool I/O, code edits, permission bypass |
| **Reasoning Engine** | `brain/reasoning_engine.py` | Multi-step structured thinking before planning/execution | Tool execution, mission mutation, code edits |
| **Brain** | `brain/brain.py`, `brain/pipeline/stages.py` | Cognitive pipeline, prompt assembly, final LLM synthesis | Direct tool I/O, permission rules |
| **Execution Coordinator** | `core/execution_coordinator.py` | Agent + tool dispatch policy, result formatting | Tool registration, runtime gates |
| **Natural Language Planner** | `tools/natural_language_planner.py` | NL → structured `PlannerResult` | Execution, permission enforcement |
| **Reasoning Loop** | `tools/reasoning_loop.py` | Plan review, safe optimization, clarification | Tool invocation |
| **Tool Orchestrator** | `tools/tool_orchestrator.py` | Permission pre-check, plan step ordering, dispatch | Registry, audit, provider routing |
| **Permission Facade** | `tools/permission_facade.py` | Unified caller + action permission (single evaluation in runtime) | Tool execution |
| **Tool Manager** | `tools/tool_manager.py` | Registry facade, default tool registration | Strategic planning |
| **Tool Runtime** | `tools/tool_runtime.py` | Preflight gates, confirmation, audit, execution | Intent analysis |
| **Tool Executor** | `tools/tool_executor.py` | Single invoke path (runtime v2 or legacy) | Permission policy definition |

**Neutral contracts (no Brain import):**

- `core/execution_context.py` — `ExecutionDispatchContext`, `build_tool_execution_context`
- `tools/default_tools.py` — central built-in tool registration

---

## Official High-Level Request Path (NLO V1)

```
User natural language
  → Brain.process_request(message)          ← canonical Brain front door
  → NaturalLanguageOrchestrator
       ├── Reasoning Engine (awareness)      ← structured thinking first
       │     └── Cognitive Context Builder   ← unified context assembly
       ├── Intent analysis
       ├── Conversation awareness
       │     (Context / Workspace / Memory / Missions /
       │      Development Session / Executive Function)
       └── Delegate to existing Brain systems (examples):
             ├── Brain.think()                    [conversation / question]
             ├── LongTermPlanner                  [planning]
             ├── ProjectIntelligence              [architecture]
             ├── CodeIntelligence                 [code explanation]
             ├── DeveloperWorkflow                [dev continuation]
             ├── CodeModificationPlanner          [code planning]
             ├── CodeGenerationEngine             [generation — no apply]
             ├── CodeEditorTool                   [controlled patch]
             └── ToolIntelligence → execute_request()  [research / tools]
  → OrchestrationResult (intent, systems, confidence, response)
```

No existing subsystem changes its responsibilities. NLO only selects and orders them.

## Official Tool Execution Path

```
User message
  → Brain.process_request()  [or Brain.think() for direct conversation]
       └── (tool intents) Brain.execute_request()
             └── ToolIntelligence.plan() → ToolExecutionEngine.execute()
  → Brain.think() path (conversation / ThinkPipeline):
  → ThinkPipeline (stages)
  → ExecutionCoordinator.execute()
       ├── Reasoning.analyze() → ToolDecisionReport
       ├── NaturalLanguagePlanner.plan() → PlannerResult
       ├── ReasoningLoop.review() → ReviewedPlannerResult
       ├── TaskOrchestrator.orchestrate() [agents]
       └── Tool path (one of):
             ├── ToolOrchestrator.orchestrate_plan()     [structured plan]
             ├── ToolOrchestrator.orchestrate_requests() [ad-hoc requests]
             └── TaskExecutionEngine + orchestrator invoke [multi-step task plan]
                   └── ToolOrchestrator.orchestrate_requests()  [per step]
                         ├── PermissionFacade.evaluate_action_only()
                         └── tools/tool_executor.execute_tool()
                               └── ToolRuntime.invoke()
                                     ├── PermissionFacade.evaluate() [preflight]
                                     ├── ConfirmationGate [if needed]
                                     └── SyncExecutor / AsyncExecutor
  → Prompt assembly → LLM → state/mission update
```

**Deprecated / test-only paths:**

- `ToolDispatcher.dispatch()` — thin wrapper over `execute_tool`; used in tests and legacy invoke overrides only.
- `TaskExecutionEngine` + raw `ToolDispatcher` — replaced by orchestrator invoke in production.

---

## Official Agent Execution Path

```
ExecutionCoordinator._run_agents()
  → TaskOrchestrator.orchestrate(message, max_agents=policy.max_agents)
       → TaskManager.create_tasks()
       → AgentManager.execute() [sequential, per task]
```

`TaskOrchestrator.orchestrate()` is the **single source of truth** for agent dispatch (Phase 12.8 — R-01).

---

## Permission Flow (Post-12.8)

1. **Orchestrator pre-flight:** `PermissionFacade.evaluate_action_only()` before execution.
2. **Runtime preflight:** `PermissionFacade.evaluate()` — caller allowlist + action level in one call.
3. **Confirmation:** `ConfirmationGate` when action requires user approval; `PermissionFacade` reused for confirmation check (no separate manager re-evaluation in preflight).

`PermissionEngine` and `PermissionManager` remain accessible on runtime for backward-compatible tests; new code should use `PermissionFacade`.

---

## Tool Registration (Post-12.8)

All built-in tools register through `tools/default_tools.py`:

```
register_default_tools()
  → TimeTool, FileReadTool, FileWriteTool, PythonExecTool,
     WebSearchTool, CalendarTool, GitHubTool, ObsidianTool
```

New external tools should extend this registry and add permission actions in `PermissionManager` — future work will reduce touchpoints further (R-10 complete for defaults).

---

## Browser Readiness

After Phase 12.8:

- **Single tool execution path** — Browser can register once and flow through orchestrator → executor → runtime.
- **Layer boundaries** — `tools/` no longer imports `brain/` for dispatch context.
- **Permission facade** — Browser actions can add rules in one coordinated place.

Still required before Browser: intent classification, Browser tool implementation, sandbox design, permission action entries.

---

## Development Session Runtime (V1)

Persistent coding-session context lives in `brain/development_session.py` and is
wired on `Brain` (`start/update/pause/resume/end/summarize_development_session`).
It **tracks** feature progress, plans, and patch proposals only — it does not
execute tools or apply patches by itself. See `docs/DEVELOPMENT_SESSION.md`.

## Controlled Patch Application (V1)

Generated patches are applied only through `core/tools/code_editor/` after
explicit human approval and `confirmed=True`. Brain exposes thin facades
(`validate_generated_patch`, `preview_generated_patch`, `apply_generated_patch`,
`rollback_patch`) and delegates filesystem mutation to the tool. Backups live
under `.titan/backups/<transaction_id>/`. See `docs/CONTROLLED_PATCH_APPLICATION.md`.

## Long-Term Planning Engine (V1)

High-level objective → structured multi-level `GoalPlan` lives in
`brain/long_term_planner.py` and is wired on `Brain`
(`plan_goal`, `expand_goal`, `review_plan`, `recalculate_plan`).

It **produces plans only** — never executes tools, never edits code, never
starts missions. Reuses Workspace Awareness, Executive Function, Project
Intelligence, Developer Workflow, Mission Runtime (read-only proposals),
Memory, and Context. Executive Function may recommend next work from a
`GoalPlan` without modifying it. See `docs/LONG_TERM_PLANNER.md`.

## Natural Language Orchestrator (V1)

High-level NL routing lives in `brain/natural_language_orchestrator.py` and is
exposed as `Brain.process_request(message)`. It is the **canonical front door**
of the Brain: every high-level request should flow through this layer for
intent → system selection → delegation. See `docs/NATURAL_LANGUAGE_ORCHESTRATOR.md`.

## Voice Runtime (V1)

Real-time spoken conversation lives in `voice/` and is **an external interface**
to the Brain — it never bypasses `Brain.process_request()`.

```
Microphone → STT provider → Brain.process_request() → TTS provider → Speaker
```

- `voice/voice_runtime.py` — sessions, state machine, interruptions, latency logging
- Provider registries in `voice/speech_to_text.py` and `voice/text_to_speech.py`
- Persistent sessions in `data/voice_sessions.json`
- Modes: single-shot, continuous, push-to-talk; wake-word reserved
- Reuses Brain front door only — NLO, Memory, Missions, Tools unchanged

See `docs/VOICE_RUNTIME.md`.

## Web Runtime (V1)

**Visual law:** All future frontend work must follow
`docs/TITAN_DESIGN_CONSTITUTION.md` (Titan Design Constitution V1). That document
is the single source of truth for artistic identity and visual language; this
architecture doc does not restate it.

The production web interface (`web/v2/`) connects to the shared Brain through the
existing FastAPI Web API. All chat paths delegate to `Brain.process_request()` —
never a per-request Brain, never raw `think()` as the web front door.

```
web/v2 → POST /api/chat/message | POST /chat/stream
  → api/chat_service.process_chat_message()
  → get_titan() singleton
  → Brain.process_request()
  → NaturalLanguageOrchestrator → existing systems
  → structured JSON / SSE → web/v2 UI
```

- `web/static/` is **legacy/deprecated**; do not extend.
- Auth: shared-secret Bearer (`TITAN_WEB_SECRET_KEY`); dev bypass via `web-dev`.
- Streaming: SSE stage events (V1); LLM token streaming deferred to Web Runtime V2.
- Cloud deployment (Phase 10.1–10.2): production entrypoint `python main.py web-prod`,
  probes `/health` and `/ready`, env config in `config/deployment.py`,
  Railway packaging in `railway.json`. See `docs/RAILWAY_DEPLOYMENT.md`.

See `docs/WEB_RUNTIME.md`.

### Web App Finalization — Layout Foundation (Sprint 1)

The production frontend (`web/v2/`) is being evolved **in place** into a premium
futuristic OS shell (single frontend, no duplication). Sprint 1 delivers the
five-region layout foundation only — Brain, Cognitive OS, and reasoning systems
are untouched.

- **Mounts:** `web/v2/` is the **canonical** production frontend at **`/app/`**
  (also aliased at `/v2/`). Root `/` redirects to `/app/`. Legacy V1
  (`web/static/`) is available only under `/static/` — never the default app.
- **Regions:** Top Bar, Left Sidebar (collapsed icon rail), Main Workspace
  (living neural core), Right Context Panel (additive resizable drawer, hidden
  by default), Bottom Status Bar.
- **Design language:** pure black + subtle red accent, unified with the
  already-red neural core; new shell styling isolated in `web/v2/design/shell.css`.

See `docs/WEB_APP_LAYOUT.md` and the canonical reconstruction record in
`docs/TITAN_FINAL_REFERENCE_IMPLEMENTATION.md` (single `/app` frontend root;
`web/v2/design/canonical-final.css` is visual authority).

### Web App Finalization — Living Neural Core V1 (Sprint 2)

The Main Workspace became Titan's living neural core — a frontend-only evolution
that reuses the **existing** Canvas 2D neural engine (`web/v2/neural/`); no second
renderer was introduced.

- **Overlay:** a thin DOM layer adds the dominant Titan Core label, a ring of
  interactive **cognitive satellites** (Memory, Reasoning, Planning, Knowledge,
  World Model, Tools, Communication, Workflow), and SVG neural links to the core.
- **State adaptation:** the pure `NeuralStatusAdapter` maps the existing
  `StateStore` onto six behavior modes (IDLE / LISTENING / THINKING / EXECUTING /
  ERROR / OFFLINE) and per-satellite status (IDLE / ACTIVE / WAITING), always
  falling back to IDLE. Satellites are presentation-only — **no backend state is
  mutated**.
- **Interaction:** subtle pointer parallax, hover/focus emphasis, tooltips, and a
  `titan:satellite-select` event for future panels; reduced-motion respected.

See `docs/WEB_APP_NEURAL_CORE.md`.

### Web App Finalization — Living Neural Intelligence (Sprint 2.3)

Frontend-only evolution of the same Canvas 2D neural engine into a living organic
cognitive organism: denser irregular neuron clusters, stronger Titan Core
hierarchy, volumetric atmosphere (haze, dust, vignette, restrained bloom),
selected-path impulses that can converge to the core, and cognitive satellites
joined by curved axons with floating labels. Adaptive density and reduced-motion
support are preserved.

See `docs/LIVING_NEURAL_INTELLIGENCE.md`.

### Web App Finalization — Neural Organism Composition (Sprint 2.4)

Composition redesign of the Living Neural Field to match the reference artwork:
eliminates graph / starburst / radial-hub reading; Titan Core becomes a dense
cortical yarn-ball of microscopic filaments; procedural field tissue fills the
entire canvas; depth bands (far→mid→near→core) carry different opacity and motion.
Frontend-only — no layout, panel, API, or Brain changes.

See `docs/LIVING_NEURAL_INTELLIGENCE.md`.

### Web App Finalization — Premium Command Center (Sprint 2.2)

Frontend-only polish of the production shell into a quieter premium command
center. Darker glass, refined typography, sidebar/topbar/orchestrator/composer
chrome, and minimal status-card indicators. No Brain or API changes.

See `docs/WEB_APP_PREMIUM_COMMAND_CENTER.md`.

## Capability Registry (V1)

Dynamic tool discovery lives in `core/tools/capability_registry.py` and extends the
existing core tool stack — no second Tool Runtime, loader, or registry.

```
ToolLoader → ToolRegistry → CapabilityRegistry
                ↓
         ToolIntelligence → Brain capability APIs
                ↓
         ToolExecutionEngine (unchanged execution path)
```

- Every `BaseTool` under `core/tools/` self-describes via `CapabilityRecord` metadata.
- Adding `core/tools/slack/` (or similar) auto-registers without Brain changes.
- Brain APIs: `list_capabilities`, `search_capabilities`, `find_tools_for_task`,
  `describe_tool`, `summarize_installed_tools`.
- `export()` provides JSON for a future Settings UI (installed tools, risk, permissions).

See `docs/CAPABILITY_REGISTRY.md`.

## Reasoning Engine (V1)

Structured multi-step thinking lives in `brain/reasoning_engine.py` and is wired on
`Brain` (`reason`, `compare_options`, `evaluate_request`, `detect_missing_information`,
`recommend_strategy`, `reason_about_project`).

It **analyzes only** — never executes tools. Runs before Executive Function in the
NLO awareness phase; Executive Function and Long-Term Planner consume
`ReasoningResult` instead of duplicating general reasoning.

Context is assembled exclusively via **Cognitive Context Builder** into one
`CognitiveContext` object — Reasoning Engine does not query Memory, Knowledge,
World Model, or Project Intelligence directly.

Reuses Cognitive Context Builder (which aggregates Workspace Awareness, Memory,
Mission Runtime, Development Session, Project Intelligence, Code Intelligence,
and Capability Registry via Tool Intelligence).

See `docs/REASONING_ENGINE.md` and `docs/COGNITIVE_CONTEXT.md`.

## Proactive Intelligence (V1)

Ranked attention recommendations live in `brain/proactive_intelligence.py` and are
wired on `Brain` (`evaluate_proactive_context`, `get_proactive_digest`,
`get_attention_items`, lifecycle APIs).

It **analyzes only** — never executes tools, never mutates missions or files.
Reuses Executive Function, Workspace Awareness, Development Session, Memory,
Reasoning Engine, Cognitive Loop (read-only observations), and Confirmation Gate.

NLO intent `PROACTIVE_ATTENTION` routes attention queries to Proactive Intelligence.

See `docs/PROACTIVE_INTELLIGENCE.md`.

## Knowledge & Learning Engine (V1)

Titan's first true learning subsystem lives in `brain/knowledge_learning_engine.py` and is
wired on `Brain` (`learn_from_*`, `approve_knowledge`, `search_knowledge`, etc.).

It **extracts reusable knowledge from experience** — lessons, patterns, workflows,
successful/failed strategies — and stores them as scored candidates awaiting verification.

```
Experience (interaction, execution, feedback, code, project)
  → KnowledgeLearningEngine.learn_from_*()
  → KnowledgeItem (candidate)
  → approve_knowledge() / reject_knowledge()
  → verified knowledge → optional future reasoning input
```

- **Not a memory database** — Memory stores facts; Learning generalizes from experience.
- **Proposes only** — never auto-modifies behavior, missions, or files.
- Reuses Memory, Project Intelligence, Code Intelligence, Mission Runtime,
  Developer Workflow, Reasoning Engine, Executive Function, and Learning Memory.
- Persisted in `data/knowledge_learning.json`.

See `docs/KNOWLEDGE_LEARNING_ENGINE.md`.

## World Model (V1)

Titan's internal belief about the current environment lives in
`brain/world_model.py` and is wired on `Brain` (`build_world_model`,
`refresh_world_model`, `get_world_model_snapshot`, `get_project_state`,
`get_workspace_state`, `get_world_blockers`, `get_world_opportunities`,
`get_world_dependencies`, `get_world_active_focus`, `export_world_model`).

It **represents state only** — never executes tools, never mutates missions
or memory, and never runs reasoning. Aggregates read-only signals from
Project Intelligence, Mission Runtime, Developer Workflow, Knowledge Learning
Engine, Memory, Code Intelligence, Executive Function, Proactive Intelligence,
Workspace Awareness, and Tool Intelligence into a single `WorldModelSnapshot`.

- **Not memory** — Memory stores durable facts; World Model is an ephemeral snapshot.
- **Not knowledge** — Knowledge generalizes experience; World Model describes now.
- **Not reasoning** — Reasoning analyzes requests; World Model reports believed reality.

See `docs/WORLD_MODEL.md`.

## Cognitive Context Builder (V1)

Unified read-only context assembly lives in `brain/cognitive_context_builder.py`
and is wired on `Brain` (`build_cognitive_context`, `build_cognitive_context_for_request`,
`build_cognitive_context_for_project`, `build_cognitive_context_for_code_task`,
`build_cognitive_context_for_mission`, `get_last_cognitive_context`,
`export_cognitive_context`).

It **assembles context only** — never mutates memory, knowledge, or missions, and
never executes tools. Combines memories, verified knowledge, World Model snapshot,
missions, workspace, executive priorities, proactive recommendations, tools, runtime
state, and conversation into one `CognitiveContext` object.

Reasoning Engine consumes **only** `CognitiveContext` via
`CognitiveContextBuilder.build_for_request()` — it no longer queries Memory,
Knowledge, World Model, or Project Intelligence directly.

See `docs/COGNITIVE_CONTEXT.md`.

## Meta-Cognition Engine (V1)

Titan's self-evaluation layer lives in `brain/meta_cognition.py` and is wired on
`Brain` (`evaluate_reasoning_quality`, `evaluate_cognitive_context_quality`,
`evaluate_response_quality`, `meta_cognition_requires_clarification`,
`meta_cognition_confidence`, `export_meta_cognition_report`).

It **evaluates only** — never generates answers, never mutates reasoning, memory,
knowledge, or missions. Assesses confidence, uncertainty, ambiguity, missing
information, unsupported assumptions, conflicting evidence, and hallucination risk
before a response is finalized.

```
ReasoningResult / CognitiveContext / candidate response
  → MetaCognitionEngine.evaluate_*()
  → MetaCognitionReport (advisory)
```

Reuses Reasoning Engine, Cognitive Context Builder, Knowledge Learning Engine,
World Model, Executive Function, and Memory (read-only via assembled artifacts).

V1 does not block or alter responses — future versions may influence behavior.

See `docs/META_COGNITION.md`.

## Autonomous Workflow Engine (V1)

Generic multi-step workflow orchestration lives in
`brain/autonomous_workflow_engine.py` and is wired on `Brain`
(`create_workflow`, `start_workflow`, `pause_workflow`, `resume_workflow`,
`cancel_workflow`, `get_workflow`, `list_workflows`, `export_workflow`).

It **orchestrates existing cognitive systems** — it does not replace Reasoning,
Executive Function, Meta-Cognition, or tool execution.

```
High-level objective
  → Cognitive Context Builder → Reasoning Engine → Executive Function
  → Meta-Cognition (confirmation gate)
  → Cognitive Orchestrator (plan → execute → verify)
  → Knowledge Learning Engine (outcomes)
```

Workflow states: `created`, `analyzing`, `planning`, `awaiting_confirmation`,
`executing`, `validating`, `completed`, `failed`, `cancelled`, `paused`.

See `docs/AUTONOMOUS_WORKFLOW_ENGINE.md`.

## Cognitive Operating System (V1)

The central cognitive coordination layer lives in
`brain/cognitive_operating_system.py` and is wired on `Brain`
(`run_cognitive_cycle`, `build_cognitive_execution_plan`,
`execute_cognitive_plan`, `cancel_cognitive_execution`,
`get_cognitive_execution_trace`, `get_cognitive_execution_metrics`,
`export_cognitive_execution`).

It **orchestrates the full cognitive lifecycle** — it does not replace
Reasoning, Executive Function, Meta-Cognition, Memory, or tool execution.

```
High-level request
  → CognitiveOperatingSystem
       receive → context → reason → evaluate → plan
       → confirm → execute → learn → complete
       ├── Cognitive Context Builder, World Model, Memory
       ├── Reasoning Engine, Executive Function, Meta-Cognition
       ├── Project Intelligence, Developer Workflow (code domains)
       ├── Cognitive Orchestrator OR Autonomous Workflow Engine
       └── Knowledge Learning Engine
  → ExecutionPlan + ExecutionTrace + ExecutionMetrics
```

`Brain.process_request()` (NLO) remains the NL front door — unchanged.
`Brain.run_cognitive_cycle()` is the COS entry for full lifecycle orchestration.

See `docs/COGNITIVE_OPERATING_SYSTEM.md`.

## Core System Validation (V1)

Integration validation for the complete cognitive stack is documented in
`docs/CORE_SYSTEM_VALIDATION.md` (July 2026 sprint). Confirms:

- Shared `CognitiveOrchestrator` wiring via `ExecutionCoordinator`
- Six official lifecycle flows (informational, ambiguous, workflow, project-aware, failure, cancel)
- Confirmation gate guarantees and JSON-serializable exports for Web App APIs
- **Web App Finalization readiness: approved**

See also `docs/ROADMAP.md` for phase status.

## Related Documents

- `docs/TITAN_DESIGN_CONSTITUTION.md` — Titan Design Constitution V1 (visual law for all future UI)
- `docs/CORE_SYSTEM_VALIDATION.md` — Core Integration & System Validation V1
- `docs/ROADMAP.md` — phase status and milestones
- `.cursor/rules/titan.mdc` — engineering rulebook
- `CHANGELOG.md` — release notes
- `docs/NATURAL_LANGUAGE_ORCHESTRATOR.md` — Natural Language Orchestrator V1
- `docs/DEVELOPMENT_SESSION.md` — Development Session Runtime V1
- `docs/CONTROLLED_PATCH_APPLICATION.md` — Controlled Patch Application V1
- `docs/LONG_TERM_PLANNER.md` — Long-Term Planning Engine V1
- `docs/VOICE_RUNTIME.md` — Voice Runtime V1
- `docs/CAPABILITY_REGISTRY.md` — Capability Registry & Dynamic Tool Discovery V1
- `docs/REASONING_ENGINE.md` — Reasoning Engine V1
- `docs/PROACTIVE_INTELLIGENCE.md` — Proactive Intelligence V1
- `docs/KNOWLEDGE_LEARNING_ENGINE.md` — Knowledge & Learning Engine V1
- `docs/WORLD_MODEL.md` — World Model V1
- `docs/COGNITIVE_CONTEXT.md` — Cognitive Context Builder V1
- `docs/META_COGNITION.md` — Meta-Cognition Engine V1
- `docs/AUTONOMOUS_WORKFLOW_ENGINE.md` — Autonomous Workflow Engine V1

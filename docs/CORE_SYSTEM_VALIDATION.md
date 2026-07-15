# Titan Core System Validation

**Version:** 0.39.0  
**Last updated:** July 13, 2026  
**Sprint:** Core Integration & System Validation V1

This document records the validated integration of Titan's complete cognitive architecture as one coherent system. It is the authoritative reference for request/workflow lifecycles, initialization order, safety guarantees, and Web App readiness.

---

## Validated Architecture

The cognitive stack is wired through a single composition root (`core/titan.py`) into one `Brain` instance. No duplicate managers or parallel orchestration paths were found during this sprint.

```
core/titan.py (Titan)
  └── brain/brain.py (Brain)
        ├── think()                         → ThinkPipeline (conversation + LLM synthesis)
        ├── process_request()               → NaturalLanguageOrchestrator (NL front door)
        └── run_cognitive_cycle()           → CognitiveOperatingSystem (full lifecycle)
              ├── Cognitive Context Builder  (read-only assembly)
              ├── Reasoning Engine           (structured thinking only)
              ├── Executive Function         (mission/focus evaluation)
              ├── Meta-Cognition Engine      (confidence / clarification gate)
              ├── World Model                (read-only environment snapshot)
              ├── Project / Code Intelligence (domain analysis)
              ├── Developer Workflow         (dev continuation plans)
              ├── Cognitive Orchestrator     (task graph plan → execute → verify)
              ├── Autonomous Workflow Engine   (multi-step objectives)
              ├── Knowledge Learning Engine  (outcome extraction)
              └── Tool path via ExecutionCoordinator → ToolOrchestrator → Tool Runtime
```

**Shared orchestrator contract:** `CognitiveOrchestrator` is constructed once inside `ExecutionCoordinator` and injected into both `AutonomousWorkflowEngine` and `CognitiveOperatingSystem` via `execution_coordinator.cognitive_orchestrator`.

**Validated subsystems (present, wired, tested):**

| Subsystem | Module | Brain entry |
|-----------|--------|-------------|
| Natural Language Orchestrator | `brain/natural_language_orchestrator.py` | `process_request()` |
| Cognitive Operating System | `brain/cognitive_operating_system.py` | `run_cognitive_cycle()` |
| Cognitive Context Builder | `brain/cognitive_context_builder.py` | `build_cognitive_context_*()` |
| Reasoning Engine | `brain/reasoning_engine.py` | `reason()` |
| Executive Function | `brain/executive_function.py` | `evaluate_missions()` |
| Meta-Cognition Engine | `brain/meta_cognition.py` | `evaluate_reasoning_quality()` |
| World Model | `brain/world_model.py` | `refresh_world_model()` |
| Knowledge Learning Engine | `brain/knowledge_learning_engine.py` | `learn_from_*()` |
| Autonomous Workflow Engine | `brain/autonomous_workflow_engine.py` | `create_workflow()` / `start_workflow()` |
| Proactive Intelligence | `brain/proactive_intelligence.py` | `evaluate_proactive_context()` |
| Project Intelligence | `brain/project_intelligence.py` | `analyze_project()` |
| Code Intelligence | `brain/code_intelligence.py` | `explain_module()` |
| Developer Workflow | `brain/developer_workflow.py` | `plan_development_workflow()` |
| Mission Runtime | `core/mission_runtime.py` | via `MissionManager` |
| Tool execution | `core/execution_coordinator.py` → `tools/tool_orchestrator.py` | `execute_request()` |

---

## Official Request Lifecycle (NLO)

```
User message
  → Brain.process_request(message)
  → NaturalLanguageOrchestrator.process()
       1. Request analysis (tokens, user, project, developer mode)
       2. Reasoning Engine (awareness — structured thinking first)
       3. Awareness pass (context, workspace, memory, missions, dev session, executive)
       4. Intent detection + pipeline decision
       5. Delegate to existing Brain systems (no logic duplication)
  → OrchestrationResult
       (intent, systems_used, confidence, final_response, artifacts)
```

**Conversation intents** still call `Brain.think()` internally — NLO does not replace the ThinkPipeline.

**Tool intents** route through `Brain.execute_request()` → Tool Intelligence → Tool Execution Engine.

---

## Official Workflow Lifecycle (COS + AWE)

### Cognitive Operating System (single request)

```
Brain.run_cognitive_cycle(message, confirmed=False)
  → CognitiveOperatingSystem.process_request()
       RECEIVE   — register execution, assign execution_id
       CONTEXT   — CognitiveContextBuilder + WorldModel + Memory retrieve
       REASON    — ReasoningEngine.reason()
       EVALUATE  — ExecutiveFunction + MetaCognitionEngine
       PLAN      — CognitiveOrchestrator.create_plan() [+ Project/Code for code domains]
       CONFIRM   — meta-cognition / open questions / plan confirmation / pending tool gates
       EXECUTE   — CognitiveOrchestrator OR AutonomousWorkflowEngine (multi-step)
       LEARN     — KnowledgeLearningEngine (success or failure)
       COMPLETE  — terminal status + trace + metrics
  → CognitiveProcessResult
```

Terminal statuses: `completed`, `failed`, `cancelled`, `awaiting_confirmation`.

### Autonomous Workflow Engine (multi-step objective)

```
Brain.create_workflow(objective)
  → AutonomousWorkflowEngine.create_workflow()
Brain.start_workflow(workflow_id, confirmed=False)
  → context → reason → evaluate → confirm → plan → execute → verify → learn
  → WorkflowRunResult
```

Workflow statuses: `created`, `analyzing`, `planning`, `awaiting_confirmation`, `executing`, `validating`, `completed`, `failed`, `cancelled`, `paused`.

COS auto-selects the workflow engine when a cognitive plan has more than two task-graph nodes (`use_workflow_engine=None` heuristic).

---

## Initialization Order

### Titan composition root (`core/titan.py`)

1. Config / identity
2. `LongTermMemory` → `MemoryService`
3. `AutonomyPolicy`, `LearningMemory`
4. `AgentManager` (shared)
5. `StateManager`, `MissionManager`
6. `ContextManager` (state + mission injected)
7. `ToolManager`, `JobStore`, `Scheduler`, `JobRunner`
8. `ConversationEngine` → `Conversation`
9. **`Brain`** (all shared managers injected)

### Brain cognitive stack (`brain/brain.py`)

1. Micro-brains: Decision, Reasoning, Planning, Knowledge, Executor
2. Tool layer: ToolDispatcher, CoreToolRuntime, ToolIntelligence, permissions
3. LLM, LLMRouter, AutonomyPolicy, LearningMemory, InitiativeEngine
4. WorkspaceAwareness → ExecutiveFunction → ProjectIntelligence → CodeIntelligence → DeveloperWorkflow → planning/code engines
5. ReasoningEngine, ProactiveIntelligence, KnowledgeLearningEngine, WorldModel
6. CognitiveContextBuilder → ReasoningEngine.attach_context_builder() → MetaCognitionEngine
7. TaskManager → TaskOrchestrator → **ExecutionCoordinator** (builds CognitiveOrchestrator)
8. AutonomousWorkflowEngine (shared orchestrator)
9. CognitiveOperatingSystem (shared orchestrator + workflow engine)
10. ThinkPipeline, NaturalLanguageOrchestrator (last — holds Brain back-reference)

Later subsystems must not initialize before their dependencies. The Reasoning Engine requires CognitiveContextBuilder to be attached before `reason()` is called in production paths.

---

## Subsystem Ownership Boundaries

| Layer | Owns | Must NOT own |
|-------|------|--------------|
| NLO | Intent routing, system ordering, awareness assembly | Tool I/O, code edits, permission bypass |
| COS / AWE | Lifecycle coordination, traces, metrics | Reasoning logic, tool execution internals |
| Reasoning Engine | Structured analysis, open questions | Tool execution, persistence mutation |
| Meta-Cognition | Confidence, clarification advisory | Answer generation, state mutation |
| World Model | Environment snapshot (read-only) | Memory writes, tool calls |
| Cognitive Context Builder | Context assembly (read-only) | Memory/knowledge/mission mutation |
| Proactive Intelligence | Attention recommendations (advisory) | Tool execution, file/mission mutation |
| Knowledge Learning Engine | Candidate extraction from outcomes | Auto-approval, behavior mutation |
| Cognitive Orchestrator | Task graph plan/execute/verify | NL routing, LLM synthesis |
| ExecutionCoordinator | Agent + tool dispatch policy | Tool registration |
| ThinkPipeline | Prompt assembly + LLM call | Direct tool I/O |

**Approved orchestration paths only.** Cognitive modules must not bypass NLO (for NL routing), COS (for full lifecycle), or ToolOrchestrator (for tool execution).

---

## Confirmation and Safety Guarantees

Validated behaviors (see `tests/test_workflow_safety_end_to_end.py`):

1. **Meta-cognition clarification** — ambiguous or low-confidence requests stop at `awaiting_confirmation`; `execute_plan` is not called.
2. **Open questions** — Reasoning Engine open questions block execution until resolved or `confirmed=True`.
3. **Plan confirmation** — `CognitivePlan.requires_confirmation=True` blocks orchestrator execution without user approval.
4. **Tool confirmation gate** — pending confirmations in `ConfirmationGate` block COS execution.
5. **`confirmed=True` bypass** — explicit user approval skips meta-cognition and plan confirmation gates (not tool LIVE gates outside COS scope).
6. **Failure visibility** — verification failures set `failed` status, populate `error_message`, preserve trace, and invoke learning (no silent failure).
7. **Cancellation** — `cancel_cognitive_execution()` / `cancel_workflow()` set terminal `cancelled` status, invoke `cancel_plan`, and reject re-execution.

---

## Graceful Degradation

When optional subsystems fail, the system continues with degraded awareness — never inventing data:

| Failure | Behavior |
|---------|----------|
| Workspace refresh error (NLO) | `systems_used.skipped` records workspace; response still returned |
| Reasoning Engine error (NLO) | Reasoning skipped; downstream routing continues |
| Memory retrieve empty | Context proceeds without memory block |
| Learning stage error (COS) | Execution may still complete; learning stage marked failed in trace |
| LLM unavailable (ThinkPipeline) | French graceful error message; REPL continues |

Optional systems (`workspace_awareness`, `confirmation_gate`) may be `None` — COS checks before use.

---

## Known Limitations

1. **Two orchestrators by name** — `NaturalLanguageOrchestrator` (routing) vs `CognitiveOrchestrator` (task graph). Documentation and logs use distinct prefixes (`NLO`, `cos_`, `wf_`).
2. **Brain facade surface** — `brain/brain.py` exposes ~100 delegating methods; large import surface is accepted technical debt until prompt externalization lands.
3. **Confirmation gate introspection** — COS reads `ConfirmationGate._pending` (private attribute); fragile if gate internals change.
4. **MissionManager reach-through** — facade calls `MissionRuntime` private sync methods; coupling documented in architecture audit.
5. **Workflow auto-selection heuristic** — COS selects AWE when task graph has >2 nodes; explicit `use_workflow_engine=True` overrides.
6. **Meta-cognition V1 advisory only** — does not block ThinkPipeline responses; blocks COS/AWE execution paths only.
7. **Constitution not yet loaded into LLM system prompt** — tracked technical debt (rulebook §26.5 item 4).
8. **Dual memory facade** — `MemoryFacade` partial unification; long-term path stable via `MemoryService`.

---

## Web App Integration Readiness

**Status: Ready for Titan Web App Finalization phase.**

Evidence from this sprint:

| Requirement | Status |
|-------------|--------|
| Canonical API entry `Brain.process_request()` | Validated — used by `api/chat_service.py` |
| JSON-serializable exports (COS, AWE, NLO) | Validated — `export_*` and `to_dict()` pass `json.dumps` |
| Structured orchestration response | Validated — `OrchestrationResult.to_dict()` |
| SSE / approval flow hooks | Existing — `tests/test_web_runtime.py` |
| Single Brain instance at composition root | Validated — `tests/test_composition.py` |
| No duplicate agent execution per turn | Validated — Phase 1 consolidation guards |
| Cognitive lifecycle API for future UI | Available — `run_cognitive_cycle`, workflow APIs, trace/metrics export |

**Recommended Web App integration points:**

- **Chat messages:** `Brain.process_request(message, stream=...)`
- **Full cognitive cycle (future UI):** `Brain.run_cognitive_cycle(message, confirmed=...)`
- **Workflow panel (future):** `create_workflow` / `start_workflow` / `export_workflow`
- **Debug / telemetry panel:** `export_cognitive_execution`, `get_cognitive_execution_trace`

---

## Test Coverage

| Test file | Scope |
|-----------|-------|
| `tests/test_core_system_integration.py` | Composition wiring, shared orchestrator, JSON exports, graceful degradation |
| `tests/test_cognitive_lifecycle_end_to_end.py` | Six official validation flows |
| `tests/test_workflow_safety_end_to_end.py` | Confirmation gates, failure traces, cancellation |
| `tests/test_composition.py` | DI guards (shared managers) |
| `tests/test_cognitive_operating_system.py` | COS unit coverage |
| `tests/test_autonomous_workflow_engine.py` | AWE unit coverage |
| `tests/test_natural_language_orchestrator.py` | NLO routing coverage |

Run integration validation:

```powershell
python -m pytest tests/test_core_system_integration.py tests/test_cognitive_lifecycle_end_to_end.py tests/test_workflow_safety_end_to_end.py -v
```

---

## Related Documents

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — official execution paths
- [`docs/ROADMAP.md`](ROADMAP.md) — phase status and next milestones
- [`docs/COGNITIVE_OPERATING_SYSTEM.md`](COGNITIVE_OPERATING_SYSTEM.md)
- [`docs/AUTONOMOUS_WORKFLOW_ENGINE.md`](AUTONOMOUS_WORKFLOW_ENGINE.md)
- [`docs/NATURAL_LANGUAGE_ORCHESTRATOR.md`](NATURAL_LANGUAGE_ORCHESTRATOR.md)

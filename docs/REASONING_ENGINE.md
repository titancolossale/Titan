# Reasoning Engine V1

The Reasoning Engine teaches Titan **structured multi-step thinking** before planning or execution.

It is **analysis only**.

> Never executes tools. Never replaces Executive Function. Never duplicates Project Intelligence, Code Intelligence, or Workspace Awareness.

## Architecture

```
Brain.process_request(message) / Brain.reason(message)
    ↓
Natural Language Orchestrator
    ↓
ReasoningEngine.reason()          ← structured thinking (6 stages)
    ├── WorkspaceAwareness          (context)
    ├── MemoryService               (context)
    ├── MissionRuntime              (read-only)
    ├── DevelopmentSession          (read-only)
    ├── ProjectIntelligence         (architecture input — not duplicated)
    ├── CodeIntelligence            (symbol/module input — not duplicated)
    └── ToolIntelligence            (tool recommendations only — never executed)
    ↓
ReasoningResult
    ↓
ExecutiveFunction.evaluate_missions(reasoning_result=...)
    ↓
LongTermPlanner.plan_goal(reasoning_result=...)   [optional]
    ↓
ToolIntelligence → Tool Runtime                   [execution layer — separate]
```

No second Brain. No duplicate reasoning in Executive Function when `ReasoningResult` is supplied.

## Responsibilities

| Does | Does not |
|------|----------|
| Analyze requests | Execute tools |
| Identify ambiguities | Edit code |
| Decompose complex goals | Replace Executive Function |
| Compare approaches | Parse code directly (delegates to Code Intelligence) |
| Surface risks, assumptions, open questions | Duplicate architectural analysis |
| Recommend tools (metadata only) | Run Natural Language Planner or ReasoningLoop |

## Six-stage pipeline

1. **Understand** — objective, constraints, urgency, domain, requested output
2. **Context** — reuse Workspace, Memory, Missions, Dev Session, Project/Code Intelligence, Capability Registry
3. **Decompose** — logical reasoning units (`ReasoningStep`)
4. **Alternatives** — candidate strategies with tradeoffs (`ReasoningAlternative`)
5. **Evaluate** — rank by risk, complexity, tool availability, mission relevance, maintainability
6. **Recommend** — one strategy with supporting arguments, confidence, assumptions, open questions

## Models

| Model | Purpose |
|-------|---------|
| `RequestUnderstanding` | Stage 1 parsed semantics |
| `ReasoningStep` | Decomposed reasoning unit |
| `ReasoningAlternative` | Candidate strategy with scores |
| `ReasoningRisk` | Identified risk + mitigation |
| `ReasoningAssumption` | Explicit assumption |
| `ReasoningQuestion` | Missing information / clarification |
| `ReasoningRecommendation` | Final recommended strategy |
| `ReasoningSummary` | Aggregate confidence, quality, completeness |
| `ReasoningResult` | Full serializable output |

All models expose `to_dict()`. `ReasoningResult.format_for_prompt()` supports LLM injection.

### Scoring

- **confidence_score** — recommendation strength
- **reasoning_quality_score** — depth of alternatives and decomposition
- **completeness_score** — context coverage minus open-question penalty

## Brain integration

| API | Description |
|-----|-------------|
| `Brain.reason(message)` | Full six-stage pipeline |
| `Brain.compare_options(message, options=...)` | Compare explicit or generated options |
| `Brain.evaluate_request(message)` | Holistic evaluation alias |
| `Brain.detect_missing_information(message)` | Open questions only |
| `Brain.recommend_strategy(message)` | Recommendation only |
| `Brain.reason_about_project(message)` | Architecture-focused reasoning |

`Brain.plan_goal()` runs reasoning first, then passes `ReasoningResult` to Executive Function and Long-Term Planner.

## Natural Language Orchestrator integration

Every `process_request()` call:

1. Runs `Brain.reason()` in awareness phase
2. Passes `ReasoningResult` to `evaluate_missions()`
3. Stores serialized reasoning in `OrchestrationResult.artifacts["reasoning"]`
4. Enriches `reasoning_summary` for web UI

## Executive Function integration

`ExecutiveFunction.evaluate_missions(..., reasoning_result=...)` reuses the Reasoning Engine recommendation in focus reasoning instead of recreating general analysis.

Mission ranking logic is unchanged; reasoning provides strategic context.

## Long-Term Planner integration

`LongTermPlanner.plan_goal(..., reasoning_result=...)` optionally enriches:

- `context_summary` with reasoning strategy and confidence
- `recommendations` rationale with Reasoning Engine advice
- `sources["reasoning_engine"]` flag

Planner ownership of decomposition and `GoalPlan` structure is unchanged.

## Web compatibility

`ReasoningResult.to_dict()` is stable JSON for future UI:

```
Reasoning → Alternatives → Recommendation → Confidence → Questions
```

No backend changes required when the web layer adds a reasoning panel.

## Distinction from other “reasoning” modules

| Module | Role |
|--------|------|
| `brain/reasoning.py` `Reasoning` | Tool intent routing for ExecutionCoordinator |
| `tools/reasoning_loop.py` | Plan review before tool orchestration |
| `brain/executive_function.py` | Mission focus ranking |
| **`brain/reasoning_engine.py`** | **General structured thinking before planning** |

## Future roadmap

- LLM-assisted alternative generation (optional, routed via `LLMRouter`)
- Reasoning artifact persistence in Development Session
- ThinkPipeline prompt injection of `ReasoningResult`
- Semantic contradiction detection against memory embeddings
- User-facing reasoning panel in Web Runtime V2

## Related documents

- `docs/ARCHITECTURE.md`
- `docs/NATURAL_LANGUAGE_ORCHESTRATOR.md`
- `docs/LONG_TERM_PLANNER.md`
- `CHANGELOG.md`

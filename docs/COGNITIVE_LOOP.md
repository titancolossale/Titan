# Titan Cognitive Loop V1

## Purpose

The Cognitive Loop is Titan's first **continuous reasoning cycle**. It answers one question per turn:

> What should I think about right now?

It is **not** autonomous execution, **not** a scheduler, and **not** a background timer. It only produces structured cognition: observations, thoughts, and recommendations.

Tool execution remains the responsibility of `ToolExecutionEngine`, `ExecutionCoordinator`, and the main `Brain.think()` pipeline.

## Architecture

```
User message
    ↓
Brain.generate_thoughts(message)
    ↓
WorkspaceAwareness.refresh()        → workspace snapshot (explicit)
    ↓
ExecutiveFunction.evaluate_missions()   → focus ranking (read-only)
    ↓
CognitiveLoop.run()
    ├── MemoryService.retrieve()      → memory observations
    ├── session notes / context       → session observations
    ├── WorkspaceAwareness snapshot   → workspace observations
    ├── ToolIntelligence.plan()       → tool observations (no execution)
    ├── Executive evaluation          → focus observations
    └── Mission Runtime               → active mission observations
    ↓
Thought prioritization + deduplication
    ↓
Recommendations
```

### Reused components

| Component | Role in Cognitive Loop |
|-----------|------------------------|
| `Brain` | Public API: `generate_thoughts(message)` |
| `WorkspaceAwareness` | On-demand workspace snapshot before cognition |
| `ExecutiveFunction` | Ranks missions / recommends focus before cognition |
| `CognitiveLoop` | Core cognition engine |
| `MemoryService` | Retrieves relevant long-term memory |
| `ToolIntelligence` | Recommends tools via metadata — never executes |
| `ContextManager` | User, project, goal, phase context |
| `MissionManager` | Active mission observations |

No second Brain, no new orchestration framework, no duplicate tool registry.

## Data model

### Observation

A factual signal from current inputs.

| Field | Description |
|-------|-------------|
| `id` | Unique identifier |
| `source` | `message`, `memory`, `session`, `context`, `workspace`, `tool_intelligence`, `executive_function`, `mission` |
| `summary` | Short description |
| `detail` | Supporting detail |
| `importance` | Score 0.0–1.0 |
| `timestamp` | UTC ISO timestamp |

### Thought

An evaluated cognitive unit.

| Field | Description |
|-------|-------------|
| `id` | Unique identifier |
| `source` | Originating subsystem |
| `priority` | `LOW`, `NORMAL`, `HIGH`, `CRITICAL` |
| `confidence` | Score 0.0–1.0 |
| `summary` | Human-readable thought |
| `reasoning` | Why this thought was generated |
| `recommended_action` | Suggested next step (cognition only) |
| `requires_tools` | Tool ids that may be needed later |
| `timestamp` | UTC ISO timestamp |

### Recommendation

Actionable guidance derived from prioritized thoughts.

| Field | Description |
|-------|-------------|
| `id` | Unique identifier |
| `thought_id` | Source thought |
| `summary` | Short label |
| `action` | Recommended action text |
| `priority` | Inherited priority |
| `confidence` | Inherited confidence |
| `requires_tools` | Tool ids referenced |

## Examples

### Session open

```
Observation: Unread session notes detected.
Thought:     Review latest project notes.
Priority:    HIGH
```

### ORR question

```
Observation: Relevant Obsidian notes may exist.
Thought:     Use Obsidian before answering.
Tools:       obsidian
```

### FastAPI documentation

```
Observation: Official documentation likely required.
Thought:     Browser should retrieve official docs.
Tools:       browser
```

### Greeting

```
Observation: Conversation-only request detected.
Thought:     No action needed. Conversation only.
Priority:    LOW
Tools:       (none)
```

## API

```python
from brain.brain import Brain

result = brain.generate_thoughts("Compare my ORR notes with FastAPI docs")

for observation in result.observations:
    print(observation.summary, observation.importance)

for thought in result.thoughts:
    print(thought.priority, thought.summary, thought.requires_tools)

for recommendation in result.recommendations:
    print(recommendation.action)
```

`CognitiveLoopResult.to_dict()` returns a JSON-serializable payload for API or logging layers.

## Logging

The loop logs at `INFO`:

- observation id, source, importance, summary
- thought id, priority, confidence, summary, tools
- recommendation id, priority, confidence, action

No secrets or full memory dumps are written to logs.

## Boundaries

| Allowed | Forbidden |
|---------|-----------|
| Observe message, memory, context | Execute tools |
| Recommend Obsidian / Browser | Call `ToolExecutionEngine` |
| Influence priority from memory | Background loops or timers |
| Deduplicate similar thoughts | Autonomous mission execution |

## Tests

Run:

```bash
pytest tests/test_cognitive_loop.py -v
```

Coverage includes:

- Conversation-only turns
- Obsidian recommendations
- Browser recommendations
- Mixed compare reasoning
- Priority ordering
- Confidence scoring
- Memory influence
- Duplicate thought prevention
- `Brain.generate_thoughts()` integration

## Future integration

V1 exposes cognition through `Brain.generate_thoughts()` only. Future phases may:

- Inject sanitized thought summaries into `ThinkPipeline` before `create_plan`
- Emit SSE events via `CognitiveStreamEmitter`
- Surface recommendations in the web UI neural panel

Those integrations must preserve the rule: **cognition first, execution separately**.

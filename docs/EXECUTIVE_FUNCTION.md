# Executive Function V1

Executive Function is Titan's **mission attention layer**. It decides which mission deserves focus before cognition and tool execution begin.

It is **not** a second Brain, **not** a Cognitive Loop, and **not** a tool runner.

> Rank missions. Recommend focus. Never execute. Never mutate.

## Architecture

```
User message / attention cycle
    ↓
Brain.get_current_focus()
Brain.evaluate_missions(message)
Brain.recommend_focus(message)
    ↓
ExecutiveFunction (read-only)
    ├── MissionRuntime.list_active_missions()
    ├── MissionRuntime.get_active_mission()
    ├── MemoryService.retrieve()   (relevance only)
    └── WorkspaceAwareness snapshot (optional relevance / summary)
    ↓
ExecutiveEvaluation
    ├── current_mission
    ├── ranked_missions (+ priority scores)
    ├── blocked / idle detections
    ├── FocusRecommendation
    └── workspace_summary
    ↓
CognitiveLoop (observes recommendation; still no tools)
```

### Reused components

| Component | Role |
|-----------|------|
| **Mission Runtime** | Source of active missions, state, progress, timestamps |
| **Memory** | Retrieval text used only for request/mission relevance |
| **Workspace Awareness** | Optional project/module context for relevance scoring |
| **Cognitive Loop** | Consumes executive observations/thoughts before deeper cognition |
| **Brain** | Public API surface |

No parallel mission store. No background scheduler. No tool calls.

### Distinct from ExecutiveBrain

| Module | Responsibility |
|--------|----------------|
| `ExecutiveFunction` | Multi-mission ranking and focus recommendation (deterministic) |
| `ExecutiveBrain` | LLM strategic analysis of the single loaded mission dict in `ThinkPipeline` |

Do not merge these modules.

## Responsibilities

| Does | Does not |
|------|----------|
| Evaluate all active missions | Execute tools |
| Rank by priority factors | Run Cognitive Loop cognition |
| Detect blocked / idle missions | Modify mission persistence |
| Recommend mission switching | Change `active_mission_id` |
| Expose scores + reasoning | Schedule autonomous work |

## Priority factors

Each active mission receives a composite **priority score** from:

| Factor | Signal |
|--------|--------|
| Mission priority | `LOW` / `NORMAL` / `HIGH` / `CRITICAL` |
| Mission age | Hours since `created_at` (capped) |
| Mission progress | Momentum + near-completion finish boost |
| Mission state | `BLOCKED` > `RUNNING` > `WAITING` / `READY` / … |
| User request relevance | Token overlap with title/objective/steps + memory hits |
| Blocked duration | Hours since blocked transition / tool failure |

Terminal missions (`COMPLETED`, `FAILED`, `CANCELLED`) are ignored because Mission Runtime excludes them from `list_active_missions()`.

**Tie-break order:** higher score → higher relevance → older age → stable mission id.

## Data model

### `MissionEvaluation`

Per-mission scored snapshot: id, title, state, priority, progress, `priority_score`, blocked/idle flags, relevance, reasoning, factor breakdown.

### `FocusRecommendation`

| Field | Meaning |
|-------|---------|
| `recommended_mission_id` | Top-ranked mission |
| `recommended_title` | Human label |
| `current_mission_id` | Current Mission Runtime focus |
| `should_switch` | True when top rank ≠ current focus |
| `reasoning` | Why this recommendation |
| `priority_score` | Top mission score |

### `ExecutiveEvaluation`

Full cycle result: current mission, ranked list, recommendation, overall reasoning, blocked/idle subsets.

## Brain API

```python
focus = brain.get_current_focus()

evaluation = brain.evaluate_missions("Continue trading bot work")
print(evaluation.current_mission)
print(evaluation.ranked_missions)
print(evaluation.reasoning)
print(evaluation.recommended_next_mission.priority_score)

recommendation = brain.recommend_focus("Continue trading bot work")
print(recommendation.should_switch, recommendation.recommended_title)
```

`Brain.generate_thoughts()` runs Executive Function first, then passes the evaluation into the Cognitive Loop so focus recommendations appear as `executive_function` observations/thoughts.

## Integration rules

1. **Mission Runtime** — read via `list_active_missions()` / `get_active_mission()` only.
2. **Cognitive Loop** — may observe and think about the recommendation; must not call tools.
3. **Memory** — used for relevance scoring only; no memory writes from Executive Function.
4. **Tool Intelligence / Tool Execution Engine** — never invoked here.

Switching focus remains an explicit Mission Runtime / Brain API action (`resume_mission`). Executive Function only *recommends*.

## Tests

```bash
pytest tests/test_executive_function.py -v
```

Coverage:

- Mission ranking by priority
- Blocked mission detection and switch recommendation
- Completed missions ignored
- Priority ties (age + relevance)
- Recommendation generation
- Idle mission detection
- Brain API integration (read-only guarantee)

## Files

| Path | Responsibility |
|------|----------------|
| `brain/executive_function.py` | Ranking engine + result models |
| `brain/brain.py` | `get_current_focus`, `evaluate_missions`, `recommend_focus` |
| `brain/cognitive_loop.py` | Executive observations/thoughts |
| `docs/EXECUTIVE_FUNCTION.md` | This document |
| `tests/test_executive_function.py` | Unit + Brain integration tests |

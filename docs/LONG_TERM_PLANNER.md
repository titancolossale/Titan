# Long-Term Planning Engine V1

Long-Term Planning teaches Titan how to turn a **high-level objective** into a complete, structured, multi-level project plan.

It is **planning only**.

> Never executes tools. Never edits code. Never starts missions. Never generates patches.

Mission Runtime may **later** adopt proposed missions. Executive Function may **recommend** next work from a `GoalPlan` without modifying it.

## Architecture

```
Brain.plan_goal(goal) / expand_goal / review_plan / recalculate_plan
    ↓
WorkspaceAwareness.refresh()
ExecutiveFunction.evaluate_missions()
    ↓
LongTermPlanner.plan_goal()
    ├── WorkspaceSnapshot          (feasibility / modules / docs)
    ├── ExecutiveEvaluation        (mission focus — read-only)
    ├── ProjectIntelligence        (existing / missing / conflicts)
    ├── DeveloperWorkflow          (docs → tests → validation → review gates)
    ├── MemoryService              (optional hints)
    └── Mission Runtime            (read-only; proposals only)
    ↓
GoalPlan
    ├── ProjectPlan[]
    │     └── Milestone[]
    │           └── Task[] → SubTask[]
    ├── Dependency[]
    ├── PlanningRisk[]
    ├── PlanningRecommendation[]   (planner + Executive Function)
    ├── PlanningSummary            (confidence, complexity, critical path, …)
    ├── MissionProposal[]          (compatible with create_mission — not applied)
    └── success_criteria / required_tools
```

### Reused components

| Component | Role |
|-----------|------|
| **Brain** | Public API: `plan_goal`, `expand_goal`, `review_plan`, `recalculate_plan` |
| **Workspace Awareness** | Avoid impossible work; project/module/docs context |
| **Executive Function** | Mission ranking + `recommend_next_from_goal_plan` (read-only) |
| **Mission Runtime** | Active mission overlap detection; optional future adoption of proposals |
| **Project Intelligence** | Existing features, missing systems, architecture conflicts |
| **Developer Workflow** | Quality gates: documentation, tests, validation, review before implementation |
| **Memory / ContextManager** | User/project context and optional retrieval hints |
| **Tool Execution Engine** | **Not called** |
| **Code Generation / Patch** | **Not called** |

No second Brain. No duplicate Mission Runtime, Executive Function, Workspace Awareness, Developer Workflow, Cognitive Loop, or Tool Execution Engine.

## Responsibilities

| Does | Does not |
|------|----------|
| Decompose goals → projects → milestones → tasks → subtasks | Execute tools |
| Build dependency graphs & critical path | Edit files or generate code |
| Score confidence, complexity, risk, duration | Start or mutate missions |
| Recommend tools and next work | Apply patches |
| Propose mission shapes for later adoption | Bypass quality gates |

## Planning pipeline

1. **Normalize goal** and classify domain (trading, automation, integration, software, …).
2. **Refresh context** — workspace, executive evaluation, project architecture, memory hints.
3. **Decompose** into one or more `ProjectPlan` streams (large goals get nested projects).
4. **Build milestones** in quality-first order: documentation → research → architecture → implementation → testing → review → (deployment when relevant).
5. **Expand tasks** with tools, success conditions, difficulty, duration; optionally nest `SubTask`s (`expand_goal`).
6. **Annotate graph** — dependencies, parallel groups, critical path, blocked/ready status.
7. **Score** confidence, complexity, overall risk, estimated implementation time.
8. **Recommend** next work (planner + Executive Function). Emit `MissionProposal`s without creating missions.

## Models

| Model | Purpose |
|-------|---------|
| `GoalPlan` | Top-level plan for one objective |
| `ProjectPlan` | Project stream under the goal |
| `Milestone` | Ordered delivery checkpoint |
| `Task` | Executable-sized work item (plan only) |
| `SubTask` | Finest nested unit |
| `Dependency` | `from_id` → `to_id` finish-to-start edge |
| `PlanningRisk` | Advisory risk with mitigation |
| `PlanningRecommendation` | Next-work advice (never mutates the plan) |
| `PlanningSummary` | Confidence, complexity, critical path, kind buckets |
| `MissionProposal` | Shape compatible with `MissionRuntime.create_mission` |

### Task fields

Each `Task` includes: `id`, `title`, `description`, `priority`, `difficulty`, `estimated_duration`, `dependencies`, `required_tools`, `success_conditions`, `blocked_by`, `status`, plus kind flags (`is_parallel_safe`, `is_critical_path`, `is_quick_win`, `is_high_risk`, `is_low_risk`).

### Planner intelligence

Automatically detects / labels:

- Parallel vs sequential tasks
- Critical path
- High-risk / low-risk tasks
- Quick wins
- Research, implementation, testing, documentation, deployment tasks

## Brain API

```python
plan = brain.plan_goal("Automate my ORR strategy")
deep = brain.expand_goal("Automate my ORR strategy")
reviewed = brain.review_plan(plan)
fresh = brain.recalculate_plan(plan)
```

| Method | Behavior |
|--------|----------|
| `plan_goal(goal)` | Full multi-level `GoalPlan` |
| `expand_goal(goal)` | Deeper plan with nested subtasks |
| `review_plan(plan)` | New plan with extra risks / adjusted confidence — input unchanged |
| `recalculate_plan(plan)` | Rebuild from goal with fresh workspace / architecture |

## Integration details

### Executive Function

`ExecutiveFunction.recommend_next_from_goal_plan(plan)` consumes a `GoalPlan` and returns a `PlanningRecommendation`. It never modifies the plan and never starts missions. Current mission focus is mentioned in the rationale only.

### Mission Runtime

`GoalPlan.mission_proposals` are advisory. Adoption is explicit:

```python
proposal = plan.mission_proposals[0]
mission = brain.mission_manager.runtime.create_mission(**proposal.to_create_kwargs())
```

The planner itself never calls `create_mission`.

### Workspace Awareness

Plans include workspace project name, language, and module counts. Missing documentation and active-mission overlap feed risks and duplicate-work warnings.

### Project Intelligence

Surfaces existing features (catalog hits), missing systems, and boundary conflicts so the plan does not propose duplicate subsystems.

### Developer Workflow

Quality gates are ordered **before** implementation: document → test plan → validate → review. Optional workflow hints (doc/test recommendations) are attached when Developer Workflow is wired.

## Example

**User:** `"Automate my ORR strategy."`

**Titan produces** a trading-domain `GoalPlan` with projects such as:

1. Research & Strategy Spec  
2. Execution & Broker Integration  
3. Validation & Monitoring  

Each project has milestones and tasks with dependencies, required tools (`python`, `terminal`, `trading`, …), success criteria, estimated duration, and risks (e.g. LIVE trading remains opt-in). Executive Function recommends the first ready quick-win / critical-path task. Mission proposals are listed but **not** started.

## Limitations (V1)

- Heuristic domain templates — not LLM-authored plans yet
- Duration estimates are coarse (hours/days/weeks)
- Feature overlap detection is keyword/catalog based
- Does not persist plans to disk (caller may store via Development Session later)
- Does not auto-convert proposals into missions

## Future expansion

- Persist `GoalPlan` artifacts alongside Development Sessions
- LLM-assisted decomposition with the same frozen model contract
- Explicit “adopt proposal → Mission Runtime” Brain facade with confirmation
- Cross-goal portfolio ranking in Executive Function
- Tighter coupling to Code Modification Planner for implementation milestones only (still plan-before-execute)

## Related documents

- `docs/DEVELOPER_WORKFLOW.md`
- `docs/PROJECT_INTELLIGENCE.md`
- `docs/WORKSPACE_AWARENESS.md`
- `docs/ARCHITECTURE.md`
- `tests/test_long_term_planner.py`

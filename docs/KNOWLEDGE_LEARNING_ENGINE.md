# Knowledge & Learning Engine V1

**Version:** 0.40.0  
**Module:** `brain/knowledge_learning_engine.py`

## Purpose

The Knowledge & Learning Engine is Titan's first true **learning** subsystem. It transforms experiences — interactions, executions, feedback, code changes, and project analysis — into **generalized, reusable knowledge** that can improve future reasoning.

It answers questions like:

- "What did we learn from past failures?"
- "What patterns keep recurring?"
- "Which strategies worked for similar tasks?"
- "What corrections has the user repeated?"

The engine **proposes knowledge only**. It never automatically modifies Titan behavior, missions, memory, or files. Existing reasoning and human approval decide whether to use verified knowledge.

## Architecture

```
Experience signals (read-only inputs)
  ├── Interactions          → learn_from_interaction()
  ├── Project Intelligence  → learn_from_project()
  ├── Mission / Tool runs   → learn_from_execution()
  ├── Code changes          → learn_from_code_change()
  ├── User feedback         → learn_from_feedback()
  ├── Developer Workflow    → learn_from_workflow()
  ├── Reasoning Engine      → learn_from_reasoning()
  ├── Memory Service        → context for extraction
  └── Learning Memory       → outcome records (execution path)
        ↓
KnowledgeLearningEngine
  ├── extract lessons / patterns / workflows
  ├── detect repeated corrections
  ├── score confidence + evidence
  ├── deduplicate by fingerprint
  └── persist candidates + verified knowledge
        ↓
KnowledgeItem (candidate | verified | rejected)
        ↓
Brain APIs → Reasoning / Executive Function / prompts (optional, explicit)
```

No second Brain, memory system, cognitive loop, or orchestrator is created.

## Memory vs Learning

| Dimension | Memory (`memory/`) | Learning (`brain/knowledge_learning_engine.py`) |
|-----------|-------------------|------------------------------------------------|
| Stores | Facts, notes, preferences | Generalized lessons from experience |
| Nature | What the user said or asked to remember | What Titan inferred from patterns |
| Lifecycle | Written when decider triggers | Candidate → verified/rejected |
| Confidence | Implicit (retrieval relevance) | Explicit score + evidence count |
| Verification | None required | Human promotion required |
| Auto-behavior | Injected when retrieved | Never auto-applied |

`memory/learning_memory.py` (Phase 9) records **approach outcomes** (success/failure per domain). The Knowledge Learning Engine **synthesizes** those signals into structured `KnowledgeItem` entries with categories, fingerprints, and verification history.

## Knowledge lifecycle

```
Experience
  → extract signal
  → generate_candidate_knowledge() / learn_from_*()
  → KnowledgeItem (status: candidate)
        ├── approve_candidate()  → verified (confidence floor 0.75)
        ├── reject_candidate()   → rejected (confidence 0.0)
        └── merge_duplicate_knowledge() → consolidated entry
  → search_knowledge() / list_verified_knowledge()
  → optional prompt injection via format_for_prompt()
```

Persisted in `data/knowledge_learning.json` (configurable via `TITAN_KNOWLEDGE_LEARNING_PATH`).

## Knowledge model

| Field | Purpose |
|-------|---------|
| `id` | Stable UUID |
| `title` | Short label |
| `category` | `lesson`, `correction`, `pattern`, `workflow`, `strategy_success`, `strategy_failure`, `preference`, `convention` |
| `description` | Full knowledge text |
| `source` | Origin subsystem (`interaction`, `project`, `execution`, …) |
| `confidence` | 0.0–1.0 score |
| `evidence_count` | Number of supporting observations |
| `created_at` / `updated_at` | Timestamps |
| `verified` | Whether human-approved |
| `verification_history` | Approve/reject/merge audit trail |
| `tags` | Search keywords |
| `related_projects` / `related_files` / `related_tools` | Scope links |
| `status` | `candidate`, `verified`, `rejected` |
| `fingerprint` | Deduplication hash |

## Candidate promotion

1. Engine creates or updates a **candidate** when evidence arrives.
2. Repeated identical signals increase `evidence_count` and `confidence`.
3. User corrections tracked separately; after **2+ repeats**, category upgrades to `pattern`.
4. Human calls `approve_knowledge(id)` → status `verified`, `verified=True`, confidence floor applied.
5. Human calls `reject_knowledge(id)` → status `rejected`, excluded from search (unless explicitly queried).

Titan **never** auto-promotes candidates.

## Confidence system

| State | Formula |
|-------|---------|
| New candidate | `0.30` base |
| + evidence | `+0.08` per observation (cap `0.90`) |
| Verified | floor `0.75`, scales with evidence |
| Rejected | `0.0` |

`update_knowledge_confidence()` supports manual adjustment for future calibration loops.

## Signal sources

| Source | Method | Extracts |
|--------|--------|----------|
| Interactions | `learn_from_interaction()` | Lessons, outcomes, preference phrases |
| Project Intelligence | `learn_from_project()` | Architecture insights, feature locations |
| Executions | `learn_from_execution()` | Success/failure strategies, mission blockers |
| Code changes | `learn_from_code_change()` | Conventions, module patterns |
| Feedback | `learn_from_feedback()` | Corrections, recurring preferences |
| Developer Workflow | `learn_from_workflow()` | Reusable step sequences |
| Reasoning Engine | `learn_from_reasoning()` | Recommended strategies, risks |

## Brain APIs

```python
brain.learn_from_interaction(user_message, assistant_response="", ...)
brain.learn_from_project(message="")
brain.learn_from_execution(mission_id=None, tool_name="", success=True, ...)
brain.learn_from_code_change(files_changed=[], change_summary="", ...)
brain.learn_from_feedback(feedback, context="")
brain.generate_candidate_knowledge(title="", description="", ...)
brain.approve_knowledge(knowledge_id, note="")
brain.reject_knowledge(knowledge_id, note="")
brain.list_knowledge_candidates(category=None)
brain.list_verified_knowledge(category=None)
brain.search_knowledge(query, verified_only=False, limit=20)
brain.update_knowledge_confidence(knowledge_id, delta=0.0, ...)
brain.merge_duplicate_knowledge(primary_id, duplicate_id)
```

## Integration boundaries

| Subsystem | Integration | Writes? |
|-----------|-------------|---------|
| Memory Service | Context for extraction | No |
| Learning Memory | Outcome records on execution | Via existing API only |
| Project Intelligence | `analyze_project`, `find_feature` | No |
| Code Intelligence | `summarize_module` | No |
| Mission Runtime | Read mission state on failure | No |
| Developer Workflow | Plan structure for workflows | No |
| Reasoning Engine | `ReasoningResult` strategies/risks | No |
| Executive Function | Available for future context | No |
| Proactive Intelligence | Independent; may consume verified knowledge later | No |

## Future self-improvement roadmap

1. **V1 (current)** — Extract, score, verify knowledge; manual promotion.
2. **V2** — Inject verified knowledge into Reasoning Engine and Executive Function context blocks.
3. **V3** — Embedding-based similarity for `merge_duplicate_knowledge` and cross-project transfer.
4. **V4** — Calibration loop: compare predicted strategy success vs actual execution outcomes.
5. **V5** — User-facing knowledge review UI (approve/reject/merge) in Web Runtime Settings.
6. **V6** — Federated learning across Nolan/Ibrahim profiles with strict isolation boundaries.

## Related documents

- `docs/ARCHITECTURE.md` — official execution path
- `docs/REASONING_ENGINE.md` — structured thinking consumer (future)
- `docs/PROACTIVE_INTELLIGENCE.md` — attention recommendations (complementary)
- `memory/learning_memory.py` — approach outcome store (Phase 9)

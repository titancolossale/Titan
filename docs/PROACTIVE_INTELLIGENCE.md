# Proactive Intelligence V1

**Version:** 0.39.0  
**Module:** `brain/proactive_intelligence.py`

## Purpose

Proactive Intelligence analyzes Titan's **existing context** — missions, workspace,
development sessions, memory, approvals, and recent execution state — to produce a
concise ranked digest of what deserves Nolan or Ibrahim's attention.

It answers questions like:

- "What deserves my attention right now?"
- "Is anything blocked?"
- "What did I leave unfinished?"

Recommendations are **advisory only**. Titan never silently executes actions.

## Architecture

```
Existing signals (read-only)
  ├── Executive Function  → blocked / idle / priority missions
  ├── Workspace Awareness → documentation / module changes
  ├── Development Session → paused sessions, pending patches, stale plans
  ├── Cognitive Loop      → high-confidence cognition (optional input)
  ├── Reasoning Engine    → risks, clarification, quick wins (optional)
  ├── Memory Service      → recent user priorities
  └── Confirmation Gate   → pending tool approvals
        ↓
ProactiveIntelligence.evaluate()
  ├── collect signals
  ├── rank + confidence filter
  ├── deduplicate fingerprints
  ├── lifecycle filter (dismiss / snooze / acknowledge / cooldown)
  └── cap digest (default: 5)
        ↓
ProactiveDigest + AttentionItems
```

Proactive Intelligence does **not** create a parallel Brain, scheduler, cognitive
loop, or executive system. It consumes outputs from existing subsystems.

## Signal sources

| Source | Signals |
|--------|---------|
| Executive Function | `blocked_missions`, `idle_missions`, focus switch |
| Workspace Awareness | `WorkspaceRecommendation` entries |
| Development Session | paused + pending tasks, unapplied patches, stale plans |
| Cognitive Loop | high-confidence `Recommendation` artifacts (read-only) |
| Reasoning Engine | risks, clarification required, strategy suggestions |
| Memory Service | notes matching priority/goal keywords |
| Confirmation Gate | pending tool approval count |

No signal source is duplicated — data is read through existing managers and APIs.

## Ranking

Recommendations are scored using:

- category weight (blocked > approval > patch review > dev continuation …)
- `ThoughtPriority` (reused from Cognitive Loop — LOW/NORMAL/HIGH/CRITICAL)
- signal `importance` and derived `confidence`
- executive mission priority and blocked duration
- duplicate fingerprint suppression

Low-confidence items below `MIN_CONFIDENCE` (default `0.35`) are omitted.

## Confidence

Confidence is derived from signal importance, category urgency, and executive
metadata (e.g. blocked hours). Titan prefers **silence** over weak suggestions.

## Recommendation lifecycle

Persisted in `data/proactive_intelligence.json` (configurable `file_path` for tests).

| Operation | Brain API | Effect |
|-----------|-----------|--------|
| Acknowledge | `brain.acknowledge_recommendation(id)` | Cooldown (default 24h) |
| Dismiss | `brain.dismiss_recommendation(id)` | Permanent suppression by fingerprint |
| Snooze | `brain.snooze_recommendation(id, until)` | Hidden until `until` (default +4h) |
| Complete | `brain.complete_recommendation(id)` | Treated as resolved |

Statuses: `active`, `acknowledged`, `dismissed`, `snoozed`, `completed`, `expired`.

## Duplicate suppression and fatigue control

- Deterministic **fingerprints** (`sha256` of stable seed per signal type)
- In-digest deduplication by fingerprint
- Lifecycle suppression for dismissed / snoozed / acknowledged / completed
- Optional `expires_at` on time-bound recommendations
- **Maximum 5** recommendations per digest (configurable)

No background notification loop is started.

## Brain APIs

```python
brain.evaluate_proactive_context(message="")
brain.get_proactive_digest()
brain.get_attention_items()
brain.acknowledge_recommendation(recommendation_id)
brain.dismiss_recommendation(recommendation_id)
brain.snooze_recommendation(recommendation_id, until=None)
brain.complete_recommendation(recommendation_id)
```

## Natural Language Orchestrator integration

Intent `PROACTIVE_ATTENTION` routes to `SystemName.PROACTIVE_INTELLIGENCE`.

Trigger examples:

- "What should I focus on?"
- "What needs my attention?"
- "Is anything blocked?"
- "Give me a quick status."
- "Quoi prioriser?"

Normal conversation intents are unchanged.

## Cognitive Loop integration

`CognitiveLoop.run(..., proactive_signals=...)` may observe proactive signals as
read-only `Observation` entries (`source=proactive_intelligence`). The Cognitive
Loop does **not** rank or generate proactive recommendations.

## Safety boundaries

Proactive Intelligence must **never**:

- execute tools
- start or resume missions
- apply patches or modify files
- send notifications or emails
- approve actions or bypass permissions
- run background schedulers

It only creates serializable recommendations with `requires_confirmation=True`.

## Future integration

- **Notifications:** a future scheduler may *read* `get_proactive_digest()` and
  surface items — Proactive Intelligence will not push autonomously.
- **Web UI:** `ProactiveDigest.to_dict()` is API-ready for an attention panel.
- **Voice Runtime:** proactive queries flow through `Brain.process_request()` like
  any other NL request.

## Related documents

- `docs/ARCHITECTURE.md`
- `docs/NATURAL_LANGUAGE_ORCHESTRATOR.md`
- `docs/REASONING_ENGINE.md`
- `brain/executive_function.py`
- `brain/cognitive_loop.py`

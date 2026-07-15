# Meta-Cognition Engine V1

**Version:** 0.42.0  
**Module:** `brain/meta_cognition.py`

## Purpose

The Meta-Cognition Engine is Titan's **self-evaluation layer**. It assesses the quality of reasoning, assembled context, and candidate responses **before** they are finalized for the user.

It answers questions like:

- "How confident should Titan be in this answer?"
- "Is the reasoning complete enough to proceed?"
- "What information is missing?"
- "Are there unsupported assumptions or conflicting evidence?"
- "What is the hallucination risk?"
- "Should Titan ask for clarification instead of answering?"

The Meta-Cognition Engine **never generates answers** and **never modifies** reasoning, memory, knowledge, missions, or responses. V1 is **evaluation-only** — future versions may influence behavior (e.g. blocking low-confidence responses or triggering clarification flows).

## Architecture

```
Read-only inputs
  ├── Reasoning Engine        → ReasoningResult (steps, risks, assumptions, questions)
  ├── Cognitive Context Builder → CognitiveContext (memory, knowledge, world model)
  ├── Knowledge Learning Engine → verified knowledge presence (via context)
  ├── World Model               → blockers, opportunities (via context snapshot)
  ├── Executive Function        → blocked missions, focus conflicts
  └── Memory Service            → retrieval coverage (via context)
        ↓
MetaCognitionEngine
  ├── evaluate_reasoning()
  ├── evaluate_context()
  └── evaluate_response()
        ↓
MetaCognitionReport
  ├── confidence_score
  ├── uncertainty_score
  ├── ambiguity_score
  ├── missing_information
  ├── assumptions
  ├── conflicting_evidence
  ├── hallucination_risk
  ├── clarification_required
  ├── reasoning_quality
  └── recommendation
        ↓
Brain APIs → prompts, NLO, future UI (advisory only in V1)
```

No second Brain, memory system, planner, runtime, or reasoning engine is created.

## Evaluation pipeline

### 1. Evaluate reasoning (`evaluate_reasoning`)

Consumes a `ReasoningResult` and optionally `CognitiveContext` and `ExecutiveEvaluation`.

| Signal | Source |
|--------|--------|
| Base confidence | `ReasoningSummary.confidence_score` |
| Completeness | `ReasoningSummary.completeness_score` |
| Missing information | `ReasoningQuestion` entries |
| Assumptions | Unvalidated `ReasoningAssumption` entries |
| Conflicts | Near-equal alternatives, high risk + high confidence |
| Context penalty | Missing world model, memory, or knowledge in context |
| Executive penalty | Blocked missions from Executive Function |

### 2. Evaluate context (`evaluate_context`)

Consumes a `CognitiveContext` and optionally a `WorldModelSnapshot`.

| Signal | Source |
|--------|--------|
| Missing items | Absent world model, memory retrieval, verified knowledge, architecture |
| Uncertainty | Context assembly gaps (no executive eval, no snapshot) |
| Conflicts | World Model blockers coexisting with opportunities |
| Hallucination risk | Proceeding without grounded memory or knowledge |

### 3. Evaluate response (`evaluate_response`)

Consumes candidate response text plus optional `ReasoningResult` and `CognitiveContext`.

| Signal | Detection |
|--------|-----------|
| Hedging language | "maybe", "perhaps", "peut-être", etc. |
| Absolute claims | "always", "never", "guaranteed", etc. |
| Specific facts without grounding | Dates, percentages, versions without context |
| Reasoning mismatch | Clarification flagged but response produced |
| Brief responses | Short answer to long/complex request |

## Confidence scoring

Confidence is a **0.0–1.0** composite score:

```
confidence = base_score
           - (open_questions × weight)
           - (unvalidated_assumptions × weight)
           - (conflicting_evidence × weight)
           - (context_penalty × weight)
```

Clamped to `[0.0, 1.0]`. Higher is better.

`MetaCognitionEngine.confidence()` returns the score from the last or supplied report.

## Uncertainty detection

Uncertainty score (`uncertainty_score`) rises when:

- Multiple open questions remain unresolved
- Unvalidated assumptions accumulate
- Risks are identified but not mitigated in reasoning
- Alternative strategies have near-equal confidence
- Cognitive context lacks world model, memory, or executive signals
- Response text uses hedging or vague generalizations

Uncertainty and confidence are **inversely related** but not identical — uncertainty captures epistemic gaps; confidence captures overall proceed-worthiness.

## Ambiguity detection

Ambiguity score (`ambiguity_score`) rises when:

- Request objective is underspecified
- Domain is `general` without constraints
- Vague response patterns detected ("it depends", "en général")
- Mission-related requests lack active mission context

## Hallucination risk

Classified as `low`, `medium`, or `high` based on:

- Unvalidated assumptions count
- Specific factual claims without grounded context
- Absolute certainty language
- High recommendation confidence with thin reasoning steps
- Missing `context_sources` in reasoning output

V1 uses **deterministic heuristics** — no LLM self-critique loop.

## Clarification gate

`clarification_required` is `true` when any of:

- Reasoning summary already flagged clarification
- Confidence falls below 0.55 (reasoning/context) or 0.5 (response)
- Two or more missing-information items
- Hallucination risk score exceeds threshold
- Response evaluation detects reasoning/response mismatch

`requires_clarification()` exposes this as a boolean API.

## Reasoning quality

Mapped from reasoning or context quality scores:

| Score range | Label |
|-------------|-------|
| ≥ 0.85 | `excellent` |
| ≥ 0.65 | `good` |
| ≥ 0.45 | `fair` |
| < 0.45 | `poor` |

## Recommendation

`MetaCognitionRecommendation` includes:

- `strength`: `weak`, `moderate`, `strong`
- `summary`: human-readable advisory text
- `factors`: supporting evaluation factors
- `proceed`: whether V1 advises continuing (advisory only — not enforced)

When clarification is required, strength is always `weak` and `proceed` is `false`.

## Meta-Cognition vs Reasoning Engine

| Dimension | Reasoning Engine | Meta-Cognition Engine |
|-----------|------------------|----------------------|
| Purpose | Structured thinking about a request | Quality evaluation of thinking/answers |
| Output | Steps, alternatives, strategy | Scores, risks, proceed/clarify advice |
| Generates content | Yes (analysis artifacts) | No |
| Executes tools | No | No |
| Mutates state | No | No |

Reasoning **produces** analysis; Meta-Cognition **judges** it.

## Meta-Cognition vs Cognitive Context Builder

| Dimension | Cognitive Context Builder | Meta-Cognition Engine |
|-----------|---------------------------|----------------------|
| Purpose | Assemble read-only context | Evaluate context sufficiency |
| Output | `CognitiveContext` | `MetaCognitionReport` |
| Queries subsystems | Yes (read-only) | No — consumes assembled artifacts |

## Brain APIs

| Method | Purpose |
|--------|---------|
| `brain.evaluate_reasoning_quality(message)` | Run reasoning + meta-evaluate |
| `brain.evaluate_cognitive_context_quality(message)` | Evaluate assembled context |
| `brain.evaluate_response_quality(response, message)` | Evaluate candidate response |
| `brain.meta_cognition_requires_clarification(report)` | Clarification gate |
| `brain.meta_cognition_confidence(report)` | Confidence accessor |
| `brain.export_meta_cognition_report(report)` | JSON export |
| `brain.get_last_meta_cognition_report()` | Last report cache |

Direct engine APIs on `MetaCognitionEngine`:

- `evaluate_reasoning()`
- `evaluate_context()`
- `evaluate_response()`
- `requires_clarification()`
- `confidence()`
- `export_report()`

## Future roadmap

| Phase | Capability |
|-------|------------|
| **V1 (current)** | Deterministic evaluation; advisory reports only |
| **V2** | Optional LLM-assisted critique with bounded token budget |
| **V3** | Integration into `ThinkPipeline` pre-LLM gate |
| **V4** | Auto-clarification prompts when `clarification_required` |
| **V5** | Confidence-weighted response synthesis (with user consent) |
| **V6** | Learning loop — meta-cognition outcomes feed Knowledge Learning Engine |

V1 deliberately does **not** block responses or alter Brain behavior — reports are available for logging, UI, and future gates.

## Related documents

- `docs/ARCHITECTURE.md` — official execution path
- `docs/REASONING_ENGINE.md` — upstream reasoning artifacts
- `docs/COGNITIVE_CONTEXT.md` — upstream context assembly
- `docs/CAPABILITY_REGISTRY.md` — cognitive capability cross-reference

## Tests

```bash
pytest tests/test_meta_cognition.py -v
```

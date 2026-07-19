# =====================================
# Titan Natural Language Orchestrator
# =====================================

"""Natural Language Orchestrator V1 — Brain front door for NL routing.

Transforms a natural-language request into the correct sequence of existing
Brain systems. Orchestration only: never executes tools itself, never edits
code, never bypasses permissions, never mutates the repository.

Architecture::

    Natural language
      → Intent analysis
      → Conversation awareness (session / missions / workspace / memory)
      → Pipeline decision
      → Delegated Brain systems (in order)
      → Structured OrchestrationResult

Does not replace CognitiveOrchestrator, NaturalLanguagePlanner, Tool
Orchestrator, or ThinkPipeline — those remain the tool/cognitive execution
layers. This module only decides *which* Brain systems participate.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from brain.chat_fast_path import is_simple_conversational_request, run_fast_path
from brain.request_deadline import (
    BrainTimeoutError,
    RequestCancelledError,
    check_deadline,
    get_request_deadline,
)

if TYPE_CHECKING:
    from brain.brain import Brain

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç_]{2,}", re.IGNORECASE)
_CLASS_NAME_RE = re.compile(
    r"\b(?:class|classe)\s+([A-Z][A-Za-z0-9_]*)\b"
    r"|\bexplain(?:\s+this)?\s+(?:class|classe)\s+([A-Z][A-Za-z0-9_]*)\b"
    r"|\b(?:class|classe)\s+([A-Z][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)
_FUNCTION_NAME_RE = re.compile(
    r"\b(?:function|fonction|method|méthode|def)\s+([A-Za-z_][A-Za-z0-9_]*)\b"
    r"|\bexplain(?:\s+this)?\s+(?:function|fonction|method|méthode)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)
_SYMBOL_FALLBACK_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\b")
_MODULE_NAME_RE = re.compile(
    r"\b(?:module|package)\s+([A-Za-z_][A-Za-z0-9_./]*)\b"
    r"|\bexplain(?:\s+the)?\s+module\s+([A-Za-z_][A-Za-z0-9_./]*)\b",
    re.IGNORECASE,
)


class DetectedIntent(str, Enum):
    """High-level request classification for Brain system routing."""

    CONVERSATION = "conversation"
    QUESTION = "question"
    RESEARCH = "research"
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    PROJECT_ANALYSIS = "project_analysis"
    CODE_EXPLANATION = "code_explanation"
    CODE_PLANNING = "code_planning"
    CODE_GENERATION = "code_generation"
    PATCH_PREVIEW = "patch_preview"
    PATCH_APPLICATION = "patch_application"
    WORKSPACE_QUERY = "workspace_query"
    MISSION_MANAGEMENT = "mission_management"
    MEMORY = "memory"
    TOOL_REQUEST = "tool_request"
    DEVELOPMENT_CONTINUATION = "development_continuation"
    PROACTIVE_ATTENTION = "proactive_attention"


class SystemName(str, Enum):
    """Canonical Brain systems the orchestrator may select."""

    REASONING_ENGINE = "reasoning_engine"
    WORKSPACE_AWARENESS = "workspace_awareness"
    MEMORY = "memory"
    CONTEXT_MANAGER = "context_manager"
    MISSION_RUNTIME = "mission_runtime"
    EXECUTIVE_FUNCTION = "executive_function"
    LONG_TERM_PLANNER = "long_term_planner"
    PROJECT_INTELLIGENCE = "project_intelligence"
    CODE_INTELLIGENCE = "code_intelligence"
    DEVELOPER_WORKFLOW = "developer_workflow"
    TOOL_INTELLIGENCE = "tool_intelligence"
    CODE_MODIFICATION_PLANNER = "code_modification_planner"
    CODE_GENERATION_ENGINE = "code_generation_engine"
    CONTROLLED_PATCH = "controlled_patch"
    DEVELOPMENT_SESSION = "development_session"
    TOOL_EXECUTION_ENGINE = "tool_execution_engine"
    BRAIN_THINK = "brain_think"
    PROACTIVE_INTELLIGENCE = "proactive_intelligence"


# Ordered pipeline templates per intent (conversation awareness prepended at runtime).
_INTENT_PIPELINE: dict[DetectedIntent, tuple[SystemName, ...]] = {
    DetectedIntent.CONVERSATION: (SystemName.BRAIN_THINK,),
    DetectedIntent.QUESTION: (SystemName.BRAIN_THINK,),
    DetectedIntent.RESEARCH: (
        SystemName.TOOL_INTELLIGENCE,
        SystemName.TOOL_EXECUTION_ENGINE,
    ),
    DetectedIntent.PLANNING: (SystemName.LONG_TERM_PLANNER,),
    DetectedIntent.ARCHITECTURE: (SystemName.PROJECT_INTELLIGENCE,),
    DetectedIntent.PROJECT_ANALYSIS: (SystemName.PROJECT_INTELLIGENCE,),
    DetectedIntent.CODE_EXPLANATION: (SystemName.CODE_INTELLIGENCE,),
    DetectedIntent.CODE_PLANNING: (
        SystemName.CODE_MODIFICATION_PLANNER,
    ),
    DetectedIntent.CODE_GENERATION: (
        SystemName.CODE_MODIFICATION_PLANNER,
        SystemName.CODE_GENERATION_ENGINE,
    ),
    DetectedIntent.PATCH_PREVIEW: (SystemName.CONTROLLED_PATCH,),
    DetectedIntent.PATCH_APPLICATION: (SystemName.CONTROLLED_PATCH,),
    DetectedIntent.WORKSPACE_QUERY: (SystemName.WORKSPACE_AWARENESS,),
    DetectedIntent.MISSION_MANAGEMENT: (
        SystemName.MISSION_RUNTIME,
        SystemName.EXECUTIVE_FUNCTION,
    ),
    DetectedIntent.MEMORY: (
        SystemName.MEMORY,
        SystemName.TOOL_INTELLIGENCE,
    ),
    DetectedIntent.TOOL_REQUEST: (
        SystemName.TOOL_INTELLIGENCE,
        SystemName.TOOL_EXECUTION_ENGINE,
    ),
    DetectedIntent.DEVELOPMENT_CONTINUATION: (
        SystemName.DEVELOPMENT_SESSION,
        SystemName.DEVELOPER_WORKFLOW,
    ),
    DetectedIntent.PROACTIVE_ATTENTION: (SystemName.PROACTIVE_INTELLIGENCE,),
}

_DEVELOPER_ENRICHMENT: tuple[SystemName, ...] = (
    SystemName.WORKSPACE_AWARENESS,
    SystemName.PROJECT_INTELLIGENCE,
    SystemName.CODE_INTELLIGENCE,
    SystemName.EXECUTIVE_FUNCTION,
    SystemName.DEVELOPER_WORKFLOW,
)

_DEVELOPER_INTENTS = frozenset(
    {
        DetectedIntent.ARCHITECTURE,
        DetectedIntent.PROJECT_ANALYSIS,
        DetectedIntent.CODE_EXPLANATION,
        DetectedIntent.CODE_PLANNING,
        DetectedIntent.CODE_GENERATION,
        DetectedIntent.PATCH_PREVIEW,
        DetectedIntent.PATCH_APPLICATION,
        DetectedIntent.DEVELOPMENT_CONTINUATION,
        DetectedIntent.WORKSPACE_QUERY,
    }
)

_AWARENESS_SYSTEMS: tuple[SystemName, ...] = (
    SystemName.REASONING_ENGINE,
    SystemName.CONTEXT_MANAGER,
    SystemName.WORKSPACE_AWARENESS,
    SystemName.MEMORY,
    SystemName.MISSION_RUNTIME,
    SystemName.DEVELOPMENT_SESSION,
    SystemName.EXECUTIVE_FUNCTION,
)

# (intent, patterns, weight) — first strong match wins after scoring.
_INTENT_PATTERNS: tuple[tuple[DetectedIntent, tuple[str, ...], float], ...] = (
    (
        DetectedIntent.PROACTIVE_ATTENTION,
        (
            r"\bwhat\s+(?:should|deserves?)\s+(?:i|my|nolan'?s?)\s+(?:focus|attention)\b",
            r"\bwhat\s+needs?\s+(?:my\s+)?attention\b",
            r"\bwhat\s+did\s+i\s+leave\s+unfinished\b",
            r"\bis\s+anything\s+blocked\b",
            r"\bgive\s+me\s+a\s+quick\s+status\b",
            r"\bremind\s+me\s+what\s+i\s+was\s+working\s+on\b",
            r"\bquoi\s+(?:faire|prioriser|mérite)\b",
            r"\bqu'?est[- ]ce\s+qui\s+(?:bloque|mérite)\b",
            r"\bstatut\s+rapide\b",
            r"\bce\s+qui\s+mérite\s+(?:mon\s+)?attention\b",
        ),
        0.94,
    ),
    (
        DetectedIntent.PATCH_APPLICATION,
        (
            r"\bapply\b.+\b(?:approved\s+)?patch\b",
            r"\bapplique\b.+\bpatch\b",
            r"\bapply\s+the\s+approved\s+patch\b",
            r"\brollback\b.+\bpatch\b",
        ),
        0.95,
    ),
    (
        DetectedIntent.PATCH_PREVIEW,
        (
            r"\bpreview\b.+\bpatch\b",
            r"\bvalidate\b.+\bpatch\b",
            r"\bshow\b.+\bpatch\b",
            r"\bprévisualis",
        ),
        0.92,
    ),
    (
        DetectedIntent.CODE_GENERATION,
        (
            r"\bgenerate\s+code\b",
            r"\bgénérer?\s+(?:du\s+)?code\b",
            r"\bimplement\b.+\b(?:feature|function|class|module)\b",
            r"\bwrite\s+(?:the\s+)?(?:code|implementation)\b",
        ),
        0.93,
    ),
    (
        DetectedIntent.CODE_PLANNING,
        (
            r"\bplan\b.+\b(?:code|change|modification|refactor|implementation)\b",
            r"\bcode\s+plan\b",
            r"\bplanifier?\b.+\b(?:code|changement|modification)\b",
            r"\bhow\s+(?:should|would)\s+(?:i|we)\s+(?:change|modify|implement)\b",
        ),
        0.9,
    ),
    (
        DetectedIntent.CODE_EXPLANATION,
        (
            r"\bexplain\b.+\b(?:class|function|method|module|symbol|this)\b",
            r"\bexplique\b.+\b(?:classe|fonction|méthode|module)\b",
            r"\bwhat\s+does\b.+\b(?:class|function|method)\b",
            r"\bfind\s+(?:symbol|callers|definition)\b",
        ),
        0.9,
    ),
    (
        DetectedIntent.DEVELOPMENT_CONTINUATION,
        (
            r"\bcontinue\b.+\b(?:titan|development|dev|coding|session|feature)\b",
            r"\bcontinue\s+titan\b",
            r"\breprendre\b.+\b(?:dev|développement|session)\b",
            r"\bresume\b.+\b(?:development|session|coding)\b",
            r"\bwhere\s+(?:was|were)\s+(?:i|we)\b",
        ),
        0.92,
    ),
    (
        DetectedIntent.PLANNING,
        (
            r"\bplan\b.+\b(?:orr|automation|strategy|project|goal|roadmap)\b",
            r"\bplan\s+the\b",
            r"\blong[- ]?term\s+plan\b",
            r"\bplanifier?\b",
            r"\bexpand\s+(?:the\s+)?goal\b",
            r"\broadmap\b",
        ),
        0.88,
    ),
    (
        DetectedIntent.ARCHITECTURE,
        (
            r"\barchitecture\b",
            r"\barchitectural\b",
            r"\bdependency\s+graph\b",
            r"\bproject\s+structure\b",
        ),
        0.88,
    ),
    (
        DetectedIntent.PROJECT_ANALYSIS,
        (
            r"\banalyze\s+(?:the\s+)?project\b",
            r"\banalyse\s+(?:le\s+)?projet\b",
            r"\bfind\s+feature\b",
            r"\bexplain\s+(?:the\s+)?module\b",
            r"\bchange\s+impact\b",
            r"\bimpact\s+analysis\b",
        ),
        0.88,
    ),
    (
        DetectedIntent.WORKSPACE_QUERY,
        (
            r"\bworkspace\b",
            r"\bwhat\s+(?:project|repo|files?)\b",
            r"\bopen\s+files?\b",
            r"\bcurrent\s+(?:project|workspace)\b",
            r"\bespace\s+de\s+travail\b",
        ),
        0.85,
    ),
    (
        DetectedIntent.MISSION_MANAGEMENT,
        (
            r"\bmission\b",
            r"\bcreate\s+mission\b",
            r"\blist\s+(?:active\s+)?missions?\b",
            r"\bresume\s+mission\b",
            r"\bcomplete\s+mission\b",
            r"\bcurrent\s+focus\b",
        ),
        0.9,
    ),
    (
        DetectedIntent.MEMORY,
        (
            r"\bremember\b",
            r"\bsouviens[- ]?toi\b",
            r"\bmy\s+(?:notes?|memory|memories)\b",
            r"\bread\s+my\b.+\bnotes?\b",
            r"\bmes\s+notes?\b",
            r"\bobsidian\b",
            r"\bvault\b",
            r"\blong[- ]?term\s+memory\b",
        ),
        0.88,
    ),
    (
        DetectedIntent.RESEARCH,
        (
            r"\bsearch\b.+\b(?:docs?|documentation|web|internet|fastapi|api)\b",
            r"\brecherche\b",
            r"\blook\s+up\b",
            r"\bbrowse\b",
            r"\bopen\s+(?:page|url|website)\b",
            r"\bfastapi\s+docs\b",
        ),
        0.87,
    ),
    (
        DetectedIntent.TOOL_REQUEST,
        (
            r"\brun\s+(?:pytest|tests?|command|terminal)\b",
            r"\bgit\s+(?:status|diff|log|commit)\b",
            r"\buse\s+(?:the\s+)?(?:browser|terminal|github|obsidian|calendar|email)\b",
            r"\bexecute\b.+\b(?:python|script|command)\b",
            r"\blist\s+(?:emails?|events?|notes?|repos?)\b",
        ),
        0.86,
    ),
    (
        DetectedIntent.CONVERSATION,
        (
            r"^(?:hi|hello|hey|bonjour|salut|coucou|yo|thanks|thank you|merci)\b",
            r"^(?:how are you|comment (?:vas|ça va))",
        ),
        0.8,
    ),
    (
        DetectedIntent.QUESTION,
        (
            r"^(?:what|why|how|when|where|who|which|est[- ]ce|pourquoi|comment|quand)\b",
            r"\?$",
        ),
        0.55,
    ),
)


@dataclass(frozen=True)
class RequestAnalysis:
    """Normalized view of the incoming request before routing."""

    request: str
    normalized: str
    tokens: tuple[str, ...]
    user: str | None = None
    project_id: str | None = None
    has_active_mission: bool = False
    has_development_session: bool = False
    developer_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "normalized": self.normalized,
            "tokens": list(self.tokens),
            "user": self.user,
            "project_id": self.project_id,
            "has_active_mission": self.has_active_mission,
            "has_development_session": self.has_development_session,
            "developer_mode": self.developer_mode,
        }


@dataclass(frozen=True)
class PipelineDecision:
    """Ordered systems selected for this request."""

    intent: DetectedIntent
    systems: tuple[SystemName, ...]
    awareness_systems: tuple[SystemName, ...]
    developer_mode: bool = False
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "systems": [s.value for s in self.systems],
            "awareness_systems": [s.value for s in self.awareness_systems],
            "developer_mode": self.developer_mode,
            "rationale": self.rationale,
        }


@dataclass
class SystemsUsed:
    """Systems actually invoked during orchestration (may be a subset)."""

    planned: tuple[SystemName, ...] = ()
    invoked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def mark_invoked(self, system: SystemName) -> None:
        name = system.value
        if name not in self.invoked:
            self.invoked.append(name)

    def mark_skipped(self, system: SystemName, reason: str = "") -> None:
        label = system.value if not reason else f"{system.value} ({reason})"
        if label not in self.skipped:
            self.skipped.append(label)

    def to_dict(self) -> dict[str, Any]:
        return {
            "planned": [s.value for s in self.planned],
            "invoked": list(self.invoked),
            "skipped": list(self.skipped),
        }


@dataclass
class OrchestrationResult:
    """Full structured result of ``process_request``."""

    request_analysis: RequestAnalysis
    detected_intent: DetectedIntent
    pipeline_decision: PipelineDecision
    systems_used: SystemsUsed
    reasoning_summary: str
    confidence: float
    final_response: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_analysis": self.request_analysis.to_dict(),
            "detected_intent": self.detected_intent.value,
            "pipeline_decision": self.pipeline_decision.to_dict(),
            "systems_used": self.systems_used.to_dict(),
            "reasoning_summary": self.reasoning_summary,
            "confidence": round(self.confidence, 3),
            "final_response": self.final_response,
            "artifacts": dict(self.artifacts),
            "duration_seconds": round(self.duration_seconds, 4),
        }


class NaturalLanguageOrchestrator:
    """Route natural-language requests to existing Brain systems.

    Holds a Brain reference solely for delegation. Does not reimplement
    planning, tool execution, code generation, or patch application.
    """

    def __init__(self, brain: Brain) -> None:
        self._brain = brain
        self._active_stream: Any = None

    def process(self, message: str, *, stream=None) -> OrchestrationResult:
        """Analyze *message*, select systems, delegate, return structured result."""
        started = time.perf_counter()
        request = (message or "").strip()
        analysis = self._analyze_request(request)
        intent, confidence, intent_reason = self._detect_intent(analysis)
        decision = self._build_pipeline(intent, analysis, intent_reason)
        systems_used = SystemsUsed(planned=decision.systems)
        self._active_stream = stream
        deadline = get_request_deadline()
        request_id = deadline.request_id if deadline else "-"

        logger.info(
            "NLO request=%r intent=%s confidence=%.3f systems=%s",
            _safe_log_text(request),
            intent.value,
            confidence,
            [s.value for s in decision.systems],
        )

        artifacts: dict[str, Any] = {"awareness": {}}
        reasoning_result = None

        # Phase 11.4 — simple conversational fast path (real LLM, no agents/tools).
        if is_simple_conversational_request(request):
            logger.info(
                "CHAT_FAST_PATH_SELECTED request_id=%s elapsed_ms=%s "
                "remaining_budget_ms=%s stage=fast_path model=%s attempt=1",
                request_id,
                deadline.elapsed_ms() if deadline else 0,
                deadline.remaining_ms() if deadline else None,
                getattr(getattr(self._brain, "llm", None), "model", None),
            )
            # Skip awareness/reasoning/planner systems explicitly.
            for system in decision.systems:
                if system != SystemName.BRAIN_THINK:
                    systems_used.mark_skipped(system, "fast_path")
            systems_used.mark_invoked(SystemName.BRAIN_THINK)
            try:
                check_deadline("fast_path")
                fast = run_fast_path(self._brain, request)
                response = fast["response"]
                artifacts["fast_path"] = {
                    "selected": True,
                    "planner_skipped": True,
                    "tools_skipped": True,
                    "agents_skipped": True,
                    "prompt_chars": fast.get("prompt_chars"),
                    "prompt_tokens_est": fast.get("prompt_tokens_est"),
                    "model": fast.get("model"),
                }
                artifacts["awareness"] = {
                    "user": analysis.user,
                    "fast_path": True,
                }
                if deadline is not None:
                    deadline.mark_stage("provider_end")
            except BrainTimeoutError as exc:
                response = (
                    "Titan n’a pas pu terminer sa réponse dans le délai prévu."
                )
                artifacts["error"] = "brain_timeout"
                artifacts["last_completed_stage"] = exc.last_completed_stage
                logger.warning(
                    "CHAT_TIMEOUT request_id=%s elapsed_ms=%s "
                    "remaining_budget_ms=0 stage=%s code=brain_timeout",
                    request_id,
                    deadline.elapsed_ms() if deadline else 0,
                    exc.last_completed_stage or "fast_path",
                )
            except RequestCancelledError as exc:
                response = "Requête annulée."
                artifacts["error"] = "cancelled"
                artifacts["last_completed_stage"] = exc.last_completed_stage
                logger.info(
                    "CHAT_CANCELLED request_id=%s elapsed_ms=%s stage=%s",
                    request_id,
                    deadline.elapsed_ms() if deadline else 0,
                    exc.last_completed_stage or "fast_path",
                )
            except Exception as exc:
                logger.exception("NLO fast-path failure")
                response = (
                    "Désolé, une erreur interne s'est produite pendant "
                    f"l'orchestration ({type(exc).__name__}). On peut réessayer."
                )
                artifacts["error"] = str(exc)

            duration = time.perf_counter() - started
            reasoning = (
                "Fast path conversationnel : planner/outils/agents ignorés; "
                "appel modèle principal uniquement."
            )
            result = OrchestrationResult(
                request_analysis=analysis,
                detected_intent=DetectedIntent.CONVERSATION,
                pipeline_decision=PipelineDecision(
                    intent=DetectedIntent.CONVERSATION,
                    systems=(SystemName.BRAIN_THINK,),
                    awareness_systems=(),
                    developer_mode=False,
                    rationale="simple conversational fast path",
                ),
                systems_used=systems_used,
                reasoning_summary=reasoning,
                confidence=max(confidence, 0.9),
                final_response=response,
                artifacts=artifacts,
                duration_seconds=duration,
            )
            self._active_stream = None
            return result

        logger.info(
            "CHAT_COMPLEX_PATH_SELECTED request_id=%s elapsed_ms=%s "
            "remaining_budget_ms=%s stage=complex intent=%s attempt=1",
            request_id,
            deadline.elapsed_ms() if deadline else 0,
            deadline.remaining_ms() if deadline else None,
            intent.value,
        )

        try:
            check_deadline("reasoning")
            logger.info(
                "CHAT_PLANNER_START request_id=%s elapsed_ms=%s "
                "remaining_budget_ms=%s stage=reasoning attempt=1",
                request_id,
                deadline.elapsed_ms() if deadline else 0,
                deadline.remaining_ms() if deadline else None,
            )
            reasoning_result = self._run_reasoning(
                analysis,
                systems_used,
                artifacts,
            )
            if deadline is not None:
                deadline.mark_stage("reasoning")
            logger.info(
                "CHAT_PLANNER_END request_id=%s elapsed_ms=%s "
                "remaining_budget_ms=%s stage=reasoning attempt=1",
                request_id,
                deadline.elapsed_ms() if deadline else 0,
                deadline.remaining_ms() if deadline else None,
            )
            check_deadline("context")
            logger.info(
                "CHAT_CONTEXT_START request_id=%s elapsed_ms=%s "
                "remaining_budget_ms=%s stage=context attempt=1",
                request_id,
                deadline.elapsed_ms() if deadline else 0,
                deadline.remaining_ms() if deadline else None,
            )
            awareness = self._run_awareness(
                analysis,
                systems_used,
                artifacts,
                reasoning_result=reasoning_result,
            )
            artifacts["awareness"] = awareness
            if deadline is not None:
                deadline.mark_stage("context")
            logger.info(
                "CHAT_CONTEXT_END request_id=%s elapsed_ms=%s "
                "remaining_budget_ms=%s stage=context attempt=1",
                request_id,
                deadline.elapsed_ms() if deadline else 0,
                deadline.remaining_ms() if deadline else None,
            )

            check_deadline("pipeline")
            response = self._run_pipeline(
                request,
                analysis,
                intent,
                decision,
                systems_used,
                artifacts,
                stream=stream,
            )
        except BrainTimeoutError as exc:
            response = (
                "Titan n’a pas pu terminer sa réponse dans le délai prévu."
            )
            artifacts["error"] = "brain_timeout"
            artifacts["last_completed_stage"] = exc.last_completed_stage
            logger.warning(
                "CHAT_TIMEOUT request_id=%s elapsed_ms=%s "
                "remaining_budget_ms=0 stage=%s code=brain_timeout",
                request_id,
                deadline.elapsed_ms() if deadline else 0,
                exc.last_completed_stage or "pipeline",
            )
        except RequestCancelledError as exc:
            response = "Requête annulée."
            artifacts["error"] = "cancelled"
            artifacts["last_completed_stage"] = exc.last_completed_stage
            logger.info(
                "CHAT_CANCELLED request_id=%s elapsed_ms=%s stage=%s",
                request_id,
                deadline.elapsed_ms() if deadline else 0,
                exc.last_completed_stage or "pipeline",
            )
        except Exception as exc:
            logger.exception("NLO pipeline failure intent=%s", intent.value)
            response = (
                "Désolé, une erreur interne s'est produite pendant "
                f"l'orchestration ({type(exc).__name__}). On peut réessayer."
            )
            artifacts["error"] = str(exc)

        duration = time.perf_counter() - started
        reasoning = self._build_reasoning(
            intent=intent,
            decision=decision,
            confidence=confidence,
            intent_reason=intent_reason,
            systems_used=systems_used,
            reasoning_result=reasoning_result,
        )
        result = OrchestrationResult(
            request_analysis=analysis,
            detected_intent=intent,
            pipeline_decision=decision,
            systems_used=systems_used,
            reasoning_summary=reasoning,
            confidence=confidence,
            final_response=response,
            artifacts=artifacts,
            duration_seconds=duration,
        )
        logger.info(
            "NLO done intent=%s confidence=%.3f duration=%.4fs "
            "invoked=%s skipped=%s",
            intent.value,
            confidence,
            duration,
            systems_used.invoked,
            systems_used.skipped,
        )
        self._active_stream = None
        return result

    # ------------------------------------------------------------------
    # Analysis & routing
    # ------------------------------------------------------------------

    def _analyze_request(self, request: str) -> RequestAnalysis:
        normalized = " ".join(request.lower().split())
        tokens = tuple(
            t for t in _TOKEN_RE.findall(normalized) if len(t) >= 2
        )
        user = getattr(self._brain.context_manager, "current_user", None)
        project_id = getattr(self._brain.context_manager, "active_project", None) or None
        has_mission = False
        try:
            active = self._brain.list_active_missions()
            has_mission = bool(active)
        except Exception:
            logger.debug("NLO mission awareness failed", exc_info=True)
        has_dev_session = self._brain.get_development_session() is not None
        # "titan" alone (e.g. "Bonjour Titan") must not force developer mode.
        developer_tokens = (
            "code",
            "class",
            "function",
            "module",
            "patch",
            "refactor",
            "implement",
            "sprint",
            "test",
            "architecture",
            "workspace",
            "dev",
            "development",
        )
        developer_mode = has_dev_session or any(t in tokens for t in developer_tokens)
        if (
            not developer_mode
            and "titan" in tokens
            and any(
                t in tokens
                for t in ("continue", "reprendre", "resume", "code", "dev")
            )
        ):
            developer_mode = True
        return RequestAnalysis(
            request=request,
            normalized=normalized,
            tokens=tokens,
            user=user,
            project_id=project_id,
            has_active_mission=has_mission,
            has_development_session=has_dev_session,
            developer_mode=developer_mode,
        )

    def _detect_intent(
        self,
        analysis: RequestAnalysis,
    ) -> tuple[DetectedIntent, float, str]:
        text = analysis.normalized
        if not text:
            return DetectedIntent.CONVERSATION, 0.4, "empty request"

        best_intent = DetectedIntent.QUESTION
        best_score = 0.0
        best_reason = "default question fallback"

        for intent, patterns, weight in _INTENT_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    score = weight
                    if intent in _DEVELOPER_INTENTS and analysis.developer_mode:
                        score = min(0.99, score + 0.03)
                    if analysis.has_development_session and intent in (
                        DetectedIntent.DEVELOPMENT_CONTINUATION,
                        DetectedIntent.CODE_PLANNING,
                        DetectedIntent.CODE_GENERATION,
                    ):
                        score = min(0.99, score + 0.02)
                    if score > best_score:
                        best_score = score
                        best_intent = intent
                        best_reason = f"matched /{pattern}/"
                    break

        # Soft boosts for continuation when session/mission active.
        if (
            best_intent in (DetectedIntent.QUESTION, DetectedIntent.CONVERSATION)
            and analysis.has_development_session
            and any(t in analysis.tokens for t in ("continue", "reprendre", "resume"))
        ):
            return (
                DetectedIntent.DEVELOPMENT_CONTINUATION,
                0.85,
                "active development session + continue language",
            )

        if best_score < 0.5 and analysis.has_active_mission and any(
            t in analysis.tokens for t in ("continue", "next", "focus", "mission")
        ):
            return (
                DetectedIntent.MISSION_MANAGEMENT,
                0.7,
                "active mission + continuation cues",
            )

        return best_intent, round(best_score or 0.5, 3), best_reason

    def _build_pipeline(
        self,
        intent: DetectedIntent,
        analysis: RequestAnalysis,
        intent_reason: str,
    ) -> PipelineDecision:
        core = list(_INTENT_PIPELINE.get(intent, (SystemName.BRAIN_THINK,)))
        developer_mode = intent in _DEVELOPER_INTENTS or (
            analysis.developer_mode
            and intent
            in (
                DetectedIntent.PLANNING,
                DetectedIntent.TOOL_REQUEST,
                DetectedIntent.RESEARCH,
            )
        )

        ordered: list[SystemName] = []
        # Conversation awareness always considered first (read-only).
        for system in _AWARENESS_SYSTEMS:
            if system not in ordered:
                ordered.append(system)

        if developer_mode:
            for system in _DEVELOPER_ENRICHMENT:
                if system not in ordered:
                    ordered.append(system)

        for system in core:
            if system not in ordered:
                ordered.append(system)

        # Development continuation always includes workspace + executive + missions.
        if intent == DetectedIntent.DEVELOPMENT_CONTINUATION:
            for system in (
                SystemName.WORKSPACE_AWARENESS,
                SystemName.MISSION_RUNTIME,
                SystemName.EXECUTIVE_FUNCTION,
                SystemName.DEVELOPER_WORKFLOW,
            ):
                if system not in ordered:
                    ordered.append(system)

        rationale = (
            f"Intent {intent.value} ({intent_reason}); "
            f"developer_mode={developer_mode}; "
            f"pipeline={[s.value for s in ordered]}"
        )
        return PipelineDecision(
            intent=intent,
            systems=tuple(ordered),
            awareness_systems=_AWARENESS_SYSTEMS,
            developer_mode=developer_mode,
            rationale=rationale,
        )

    # ------------------------------------------------------------------
    # Awareness & pipeline execution
    # ------------------------------------------------------------------

    def _run_reasoning(
        self,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> Any | None:
        """Run Reasoning Engine before Executive Function — structured thinking only."""
        try:
            result = self._brain.reason(analysis.request)
            systems_used.mark_invoked(SystemName.REASONING_ENGINE)
            artifacts["reasoning"] = result.to_dict()
            return result
        except Exception:
            logger.debug("NLO reasoning engine failed", exc_info=True)
            systems_used.mark_skipped(SystemName.REASONING_ENGINE, "error")
            return None

    def _run_awareness(
        self,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
        *,
        reasoning_result: Any | None = None,
    ) -> dict[str, Any]:
        awareness: dict[str, Any] = {
            "user": analysis.user,
            "project_id": analysis.project_id,
        }

        systems_used.mark_invoked(SystemName.CONTEXT_MANAGER)
        try:
            ctx = self._brain.context_manager.get_context()
            awareness["context"] = ctx if isinstance(ctx, str) else str(ctx)
        except Exception:
            logger.debug("NLO context load failed", exc_info=True)
            systems_used.mark_skipped(SystemName.CONTEXT_MANAGER, "error")

        try:
            workspace = self._brain.refresh_workspace()
            systems_used.mark_invoked(SystemName.WORKSPACE_AWARENESS)
            awareness["workspace"] = {
                "project_name": getattr(workspace, "project_name", None),
                "root": str(getattr(workspace, "workspace_root", "") or ""),
                "modules": list(getattr(workspace, "detected_modules", ()) or ())[:12],
            }
        except Exception:
            logger.debug("NLO workspace refresh failed", exc_info=True)
            systems_used.mark_skipped(SystemName.WORKSPACE_AWARENESS, "error")

        try:
            user = analysis.user or "Nolan"
            memory_result = self._brain.memory_service.retrieve(
                user,
                analysis.request,
                project_id=analysis.project_id,
            )
            systems_used.mark_invoked(SystemName.MEMORY)
            awareness["memory"] = str(getattr(memory_result, "text", memory_result))[:500]
        except Exception:
            logger.debug("NLO memory retrieve failed", exc_info=True)
            systems_used.mark_skipped(SystemName.MEMORY, "error")

        try:
            missions = self._brain.list_active_missions()
            systems_used.mark_invoked(SystemName.MISSION_RUNTIME)
            awareness["missions"] = [
                {
                    "id": getattr(m, "mission_id", None) or getattr(m, "id", None),
                    "title": getattr(m, "title", ""),
                    "state": str(getattr(m, "state", "")),
                }
                for m in missions[:8]
            ]
        except Exception:
            logger.debug("NLO mission list failed", exc_info=True)
            systems_used.mark_skipped(SystemName.MISSION_RUNTIME, "error")

        try:
            session = self._brain.get_development_session()
            systems_used.mark_invoked(SystemName.DEVELOPMENT_SESSION)
            if session is not None:
                awareness["development_session"] = {
                    "session_id": getattr(session, "session_id", None),
                    "feature": getattr(session, "feature", None),
                    "state": str(getattr(session, "state", "")),
                }
            else:
                awareness["development_session"] = None
        except Exception:
            logger.debug("NLO development session read failed", exc_info=True)
            systems_used.mark_skipped(SystemName.DEVELOPMENT_SESSION, "error")

        try:
            evaluation = self._brain.evaluate_missions(
                analysis.request,
                reasoning_result=reasoning_result,
            )
            systems_used.mark_invoked(SystemName.EXECUTIVE_FUNCTION)
            recommendation = getattr(evaluation, "recommendation", None)
            current = getattr(evaluation, "current_mission", None)
            awareness["executive"] = {
                "focus": (
                    getattr(recommendation, "recommended_title", None)
                    if recommendation is not None
                    else getattr(current, "title", None)
                ),
                "summary": str(getattr(evaluation, "reasoning", "") or "")[:400],
            }
            if reasoning_result is not None:
                awareness["reasoning_summary"] = {
                    "strategy": getattr(
                        getattr(reasoning_result, "recommendation", None),
                        "strategy",
                        None,
                    ),
                    "confidence": getattr(
                        getattr(reasoning_result, "summary", None),
                        "confidence_score",
                        None,
                    ),
                    "domain": getattr(
                        getattr(reasoning_result, "summary", None),
                        "domain",
                        None,
                    ),
                }
        except Exception:
            logger.debug("NLO executive evaluation failed", exc_info=True)
            systems_used.mark_skipped(SystemName.EXECUTIVE_FUNCTION, "error")

        return awareness

    def _run_pipeline(
        self,
        request: str,
        analysis: RequestAnalysis,
        intent: DetectedIntent,
        decision: PipelineDecision,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
        *,
        stream: Any = None,
    ) -> str:
        # Developer enrichment (advisory reads) when flagged.
        if decision.developer_mode:
            self._run_developer_enrichment(
                request,
                analysis,
                systems_used,
                artifacts,
            )

        handlers = {
            DetectedIntent.CONVERSATION: self._handle_conversation,
            DetectedIntent.QUESTION: self._handle_conversation,
            DetectedIntent.RESEARCH: self._handle_toolish,
            DetectedIntent.PLANNING: self._handle_planning,
            DetectedIntent.ARCHITECTURE: self._handle_architecture,
            DetectedIntent.PROJECT_ANALYSIS: self._handle_project_analysis,
            DetectedIntent.CODE_EXPLANATION: self._handle_code_explanation,
            DetectedIntent.CODE_PLANNING: self._handle_code_planning,
            DetectedIntent.CODE_GENERATION: self._handle_code_generation,
            DetectedIntent.PATCH_PREVIEW: self._handle_patch_preview,
            DetectedIntent.PATCH_APPLICATION: self._handle_patch_application,
            DetectedIntent.WORKSPACE_QUERY: self._handle_workspace_query,
            DetectedIntent.MISSION_MANAGEMENT: self._handle_mission,
            DetectedIntent.MEMORY: self._handle_memory,
            DetectedIntent.TOOL_REQUEST: self._handle_toolish,
            DetectedIntent.DEVELOPMENT_CONTINUATION: self._handle_development_continuation,
            DetectedIntent.PROACTIVE_ATTENTION: self._handle_proactive,
        }
        handler = handlers.get(intent, self._handle_conversation)
        if handler is self._handle_conversation:
            return handler(request, analysis, systems_used, artifacts, stream=stream)
        return handler(request, analysis, systems_used, artifacts)

    def _run_developer_enrichment(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> None:
        enrichment: dict[str, Any] = {}
        # Project intelligence — lightweight architecture glance.
        if SystemName.PROJECT_INTELLIGENCE.value not in systems_used.invoked:
            try:
                summary = self._brain.analyze_project()
                systems_used.mark_invoked(SystemName.PROJECT_INTELLIGENCE)
                modules = getattr(summary, "modules", ()) or ()
                module_names = []
                for mod in list(modules)[:8]:
                    module_names.append(
                        getattr(mod, "name", None) or getattr(mod, "path", str(mod))
                    )
                enrichment["architecture"] = {
                    "project": getattr(summary, "project_name", None),
                    "modules": module_names,
                    "summary": str(getattr(summary, "summary", "") or "")[:300],
                }
            except Exception:
                logger.debug("NLO project enrichment failed", exc_info=True)
                systems_used.mark_skipped(SystemName.PROJECT_INTELLIGENCE, "enrichment")

        # Code intelligence — only when a symbol-like token is present.
        symbol = _extract_symbol(request)
        if symbol and SystemName.CODE_INTELLIGENCE.value not in systems_used.invoked:
            try:
                locations = self._brain.find_symbol(symbol)
                systems_used.mark_invoked(SystemName.CODE_INTELLIGENCE)
                enrichment["symbol_hint"] = {
                    "symbol": symbol,
                    "hits": len(locations) if locations is not None else 0,
                }
            except Exception:
                logger.debug("NLO code enrichment failed", exc_info=True)
                systems_used.mark_skipped(SystemName.CODE_INTELLIGENCE, "enrichment")

        if SystemName.DEVELOPER_WORKFLOW.value not in systems_used.invoked:
            # Defer full workflow plan to handlers that need it; mark planned only.
            pass

        artifacts["developer_enrichment"] = enrichment

    # ------------------------------------------------------------------
    # Intent handlers (delegation only)
    # ------------------------------------------------------------------

    def _handle_conversation(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
        *,
        stream: Any = None,
    ) -> str:
        systems_used.mark_invoked(SystemName.BRAIN_THINK)
        response = self._brain.think(request, stream=stream)
        artifacts["think_response"] = True
        return response

    def _handle_planning(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.LONG_TERM_PLANNER)
        plan = self._brain.plan_goal(request)
        artifacts["goal_plan"] = _safe_artifact(plan)
        return _format_goal_plan(plan)

    def _handle_architecture(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.PROJECT_INTELLIGENCE)
        summary = self._brain.analyze_project()
        artifacts["architecture"] = _safe_artifact(summary)
        return _format_architecture(summary)

    def _handle_project_analysis(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.PROJECT_INTELLIGENCE)
        module = _extract_module(request)
        feature = _extract_after_keywords(
            request,
            ("find feature", "feature", "fonctionnalité"),
        )
        if module:
            desc = self._brain.explain_module(module)
            artifacts["module"] = _safe_artifact(desc)
            return _format_module(desc)
        if feature:
            loc = self._brain.find_feature(feature)
            artifacts["feature"] = _safe_artifact(loc)
            return _format_feature(loc)
        impact_target = _extract_after_keywords(
            request,
            ("impact of", "impact", "change impact"),
        )
        if impact_target:
            impact = self._brain.analyze_change_impact(impact_target)
            artifacts["impact"] = _safe_artifact(impact)
            return _format_impact(impact)
        summary = self._brain.analyze_project()
        artifacts["architecture"] = _safe_artifact(summary)
        return _format_architecture(summary)

    def _handle_code_explanation(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.CODE_INTELLIGENCE)
        class_name = _extract_class_name(request)
        func_name = _extract_function_name(request)
        if class_name:
            summary = self._brain.explain_class(class_name)
            artifacts["class_summary"] = _safe_artifact(summary)
            return _format_class(summary)
        if func_name:
            summary = self._brain.explain_function(func_name)
            artifacts["function_summary"] = _safe_artifact(summary)
            return _format_function(summary)
        symbol = _extract_symbol(request)
        if symbol:
            # Prefer class, then function, then symbol locations.
            try:
                summary = self._brain.explain_class(symbol)
                if getattr(summary, "found", True) is not False and getattr(
                    summary, "name", None
                ):
                    artifacts["class_summary"] = _safe_artifact(summary)
                    return _format_class(summary)
            except Exception:
                logger.debug("NLO explain_class fallback failed", exc_info=True)
            try:
                summary = self._brain.explain_function(symbol)
                artifacts["function_summary"] = _safe_artifact(summary)
                return _format_function(summary)
            except Exception:
                locations = self._brain.find_symbol(symbol)
                artifacts["symbol_locations"] = _safe_artifact(locations)
                return _format_symbols(symbol, locations)
        systems_used.mark_skipped(SystemName.CODE_INTELLIGENCE, "no symbol")
        return (
            "Je n'ai pas trouvé de symbole (classe/fonction) à expliquer. "
            "Précise un nom, par exemple « Explain class Brain »."
        )

    def _handle_code_planning(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.CODE_MODIFICATION_PLANNER)
        plan = self._brain.plan_code_change(request)
        artifacts["code_plan"] = _safe_artifact(plan)
        return _format_code_plan(plan)

    def _handle_code_generation(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.CODE_MODIFICATION_PLANNER)
        plan = self._brain.plan_code_change(request)
        artifacts["code_plan"] = _safe_artifact(plan)
        approved = plan.with_approval(True)
        systems_used.mark_invoked(SystemName.CODE_GENERATION_ENGINE)
        patch = self._brain.generate_code(approved)
        artifacts["generated_patch"] = _safe_artifact(patch)
        # Never apply — generation only.
        systems_used.mark_skipped(SystemName.CONTROLLED_PATCH, "generation only")
        return _format_generated_patch(plan, patch)

    def _handle_patch_preview(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.CONTROLLED_PATCH)
        patch = self._resolve_session_patch(artifacts)
        if patch is None:
            systems_used.mark_skipped(SystemName.CONTROLLED_PATCH, "no patch")
            return (
                "Aucun patch en session de développement. "
                "Génère d'abord du code, puis demande un aperçu."
            )
        preview = self._brain.preview_generated_patch(patch)
        artifacts["patch_preview"] = _safe_artifact(preview)
        return _format_patch_preview(preview)

    def _handle_patch_application(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.CONTROLLED_PATCH)
        patch = self._resolve_session_patch(artifacts)
        if patch is None:
            systems_used.mark_skipped(SystemName.CONTROLLED_PATCH, "no patch")
            return (
                "Aucun patch approuvé trouvé en session. "
                "Impossible d'appliquer sans GeneratedPatch."
            )
        if not getattr(patch, "approved", False):
            systems_used.mark_skipped(SystemName.CONTROLLED_PATCH, "not approved")
            return (
                "Le patch existe mais n'est pas marqué approuvé. "
                "Approuve-le explicitement avant application."
            )
        # User NL request to apply counts as confirmation for Controlled Patch.
        result = self._brain.apply_generated_patch(patch, confirmed=True)
        artifacts["patch_application"] = _safe_artifact(result)
        if getattr(result, "success", False):
            return (
                f"Patch appliqué (transaction {getattr(result, 'transaction_id', '')}). "
                f"{getattr(result, 'message', '')}"
            ).strip()
        return (
            f"Application refusée ou échouée: {getattr(result, 'message', result)}"
        )

    def _handle_workspace_query(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.WORKSPACE_AWARENESS)
        workspace = self._brain.get_workspace()
        artifacts["workspace"] = _safe_artifact(workspace)
        return _format_workspace(workspace)

    def _handle_mission(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.MISSION_RUNTIME)
        systems_used.mark_invoked(SystemName.EXECUTIVE_FUNCTION)
        missions = self._brain.list_active_missions()
        focus = self._brain.get_current_focus()
        evaluation = self._brain.evaluate_missions(request)
        artifacts["missions"] = [_safe_artifact(m) for m in missions]
        artifacts["focus"] = _safe_artifact(focus)
        artifacts["executive"] = _safe_artifact(evaluation)
        lines = ["Missions actives:"]
        if not missions:
            lines.append("- aucune mission active")
        else:
            for mission in missions[:10]:
                title = getattr(mission, "title", "")
                state = getattr(mission, "state", "")
                mid = getattr(mission, "id", "") or getattr(mission, "mission_id", "")
                lines.append(f"- [{state}] {title} ({mid})")
        if focus is not None:
            lines.append(f"Focus actuel: {getattr(focus, 'title', focus)}")
        recommendation = getattr(evaluation, "recommendation", None)
        if recommendation is not None and getattr(
            recommendation, "recommended_title", None
        ):
            lines.append(
                f"Recommandation: {recommendation.recommended_title} "
                f"({recommendation.reasoning})"
            )
        reasoning = getattr(evaluation, "reasoning", "")
        if reasoning:
            lines.append(f"Executive Function: {reasoning}")
        return "\n".join(lines)

    def _handle_memory(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.MEMORY)
        user = analysis.user or "Nolan"
        retrieved = self._brain.memory_service.retrieve(
            user,
            request,
            project_id=analysis.project_id,
        )
        mem_text = str(getattr(retrieved, "text", retrieved))
        artifacts["memory"] = mem_text[:1000]

        # Obsidian / notes → Tool Intelligence plan (and optional read execution).
        systems_used.mark_invoked(SystemName.TOOL_INTELLIGENCE)
        plan = self._brain.plan_tool_execution(request)
        artifacts["tool_plan"] = _safe_artifact(plan)

        lower = analysis.normalized
        should_execute = any(
            k in lower for k in ("read", "lire", "search", "cherche", "notes", "obsidian")
        )
        tool_result_text = ""
        if should_execute and getattr(plan, "requires_tools", True):
            systems_used.mark_invoked(SystemName.TOOL_EXECUTION_ENGINE)
            execution = self._brain.execute_request(request)
            artifacts["tool_execution"] = _safe_artifact(execution)
            tool_result_text = getattr(execution, "summary_message", "") or str(
                getattr(execution, "execution", "")
            )
        else:
            systems_used.mark_skipped(
                SystemName.TOOL_EXECUTION_ENGINE,
                "plan only",
            )

        parts = ["Mémoire / notes:"]
        if mem_text.strip():
            parts.append(mem_text[:800])
        else:
            parts.append("(aucun souvenir pertinent)")
        if tool_result_text:
            parts.append("")
            parts.append("Outils (Obsidian/notes):")
            parts.append(tool_result_text[:800])
        elif getattr(plan, "selected_tools", None):
            names = []
            for item in plan.selected_tools:
                names.append(
                    getattr(item, "tool_name", None)
                    or getattr(item, "name", None)
                    or str(item)
                )
            parts.append(
                f"Plan outils: {', '.join(str(n) for n in names[:6]) or 'aucun'}"
            )
        return "\n".join(parts)

    def _handle_toolish(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.TOOL_INTELLIGENCE)
        plan = self._brain.plan_tool_execution(request)
        artifacts["tool_plan"] = _safe_artifact(plan)
        systems_used.mark_invoked(SystemName.TOOL_EXECUTION_ENGINE)
        # Delegate execution — permissions / confirmation stay in Tool Execution Engine.
        execution = self._brain.execute_request(request)
        artifacts["tool_execution"] = _safe_artifact(execution)
        summary = getattr(execution, "summary_message", None)
        if not summary and hasattr(execution, "execution"):
            summary = getattr(execution.execution, "summary_message", None)
        return summary or str(execution)

    def _handle_development_continuation(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.WORKSPACE_AWARENESS)
        workspace = self._brain.refresh_workspace()
        artifacts["workspace"] = _safe_artifact(workspace)

        systems_used.mark_invoked(SystemName.MISSION_RUNTIME)
        missions = self._brain.list_active_missions()
        artifacts["missions"] = [_safe_artifact(m) for m in missions]

        systems_used.mark_invoked(SystemName.EXECUTIVE_FUNCTION)
        evaluation = self._brain.evaluate_missions(request)
        artifacts["executive"] = _safe_artifact(evaluation)

        systems_used.mark_invoked(SystemName.DEVELOPMENT_SESSION)
        session = self._brain.get_development_session()
        session_summary = None
        if session is not None:
            session_summary = self._brain.summarize_development_session()
            artifacts["session_summary"] = _safe_artifact(session_summary)
        else:
            systems_used.mark_skipped(SystemName.DEVELOPMENT_SESSION, "none active")

        systems_used.mark_invoked(SystemName.DEVELOPER_WORKFLOW)
        workflow = self._brain.plan_development_workflow(request)
        artifacts["developer_workflow"] = _safe_artifact(workflow)

        return _format_continuation(
            workspace=workspace,
            missions=missions,
            evaluation=evaluation,
            session_summary=session_summary,
            workflow=workflow,
        )

    def _handle_proactive(
        self,
        request: str,
        analysis: RequestAnalysis,
        systems_used: SystemsUsed,
        artifacts: dict[str, Any],
    ) -> str:
        systems_used.mark_invoked(SystemName.PROACTIVE_INTELLIGENCE)
        evaluation = self._brain.evaluate_proactive_context(request)
        artifacts["proactive"] = evaluation.to_dict()
        return _format_proactive_digest(evaluation.digest)

    def _resolve_session_patch(self, artifacts: dict[str, Any]) -> Any | None:
        """Best-effort: recover last GeneratedPatch from active development session."""
        session = self._brain.get_development_session()
        if session is None:
            return None
        patches = getattr(session, "patches", None) or []
        if not patches:
            return None
        last = patches[-1]
        # Session may store dict artifacts — try to rebuild via code generation models.
        if hasattr(last, "files") or hasattr(last, "approved"):
            return last
        artifacts["session_patch_raw"] = _safe_artifact(last)
        return None

    def _build_reasoning(
        self,
        *,
        intent: DetectedIntent,
        decision: PipelineDecision,
        confidence: float,
        intent_reason: str,
        systems_used: SystemsUsed,
        reasoning_result: Any | None = None,
    ) -> str:
        base = (
            f"Detected intent={intent.value} ({intent_reason}) "
            f"confidence={confidence:.2f}. "
            f"Selected systems={list(systems_used.invoked)}. "
            f"Skipped={list(systems_used.skipped)}. "
            f"{decision.rationale}"
        )
        if reasoning_result is None:
            return base
        summary = getattr(reasoning_result, "summary", None)
        recommendation = getattr(reasoning_result, "recommendation", None)
        if summary is None or recommendation is None:
            return base
        domain = getattr(summary, "domain", None)
        domain_value = domain.value if hasattr(domain, "value") else str(domain)
        return (
            f"{base} Reasoning: domain={domain_value} "
            f"strategy={getattr(recommendation, 'strategy', '')[:120]} "
            f"confidence={getattr(summary, 'confidence_score', 0.0):.2f}."
        )


# ------------------------------------------------------------------
# Helpers — extraction & formatting (no side effects)
# ------------------------------------------------------------------


def _safe_log_text(text: str, limit: int = 120) -> str:
    cleaned = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+", r"\1=***", text)
    return cleaned[:limit]


def _safe_artifact(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            pass
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_artifact(v) for k, v in list(obj.items())[:40]}
    if isinstance(obj, (list, tuple)):
        return [_safe_artifact(item) for item in list(obj)[:40]]
    return str(obj)[:500]


def _extract_class_name(request: str) -> str | None:
    match = _CLASS_NAME_RE.search(request)
    if not match:
        return None
    for group in match.groups():
        if group:
            return group
    return None


def _extract_function_name(request: str) -> str | None:
    match = _FUNCTION_NAME_RE.search(request)
    if not match:
        return None
    for group in match.groups():
        if group:
            return group
    return None


def _extract_symbol(request: str) -> str | None:
    class_name = _extract_class_name(request)
    if class_name:
        return class_name
    func_name = _extract_function_name(request)
    if func_name:
        return func_name
    # Quoted identifier
    quoted = re.search(r"['\"`]([A-Za-z_][A-Za-z0-9_]*)['\"`]", request)
    if quoted:
        return quoted.group(1)
    match = _SYMBOL_FALLBACK_RE.search(request)
    if match:
        return match.group(1)
    return None


def _extract_module(request: str) -> str | None:
    match = _MODULE_NAME_RE.search(request)
    if not match:
        return None
    for group in match.groups():
        if group:
            return group.strip("./")
    return None


def _extract_after_keywords(request: str, keywords: tuple[str, ...]) -> str | None:
    lower = request.lower()
    for keyword in keywords:
        idx = lower.find(keyword)
        if idx >= 0:
            rest = request[idx + len(keyword) :].strip(" :,-")
            if rest:
                # Take first token-ish chunk
                token = re.split(r"[\s,.;!?]+", rest, maxsplit=1)[0]
                if token:
                    return token.strip("'\"`")
    return None


def _format_goal_plan(plan: Any) -> str:
    goal = getattr(plan, "goal", "") or getattr(plan, "request", "")
    summary = getattr(plan, "summary", None)
    confidence = getattr(summary, "confidence", None) if summary else getattr(
        plan, "confidence", None
    )
    projects = getattr(plan, "projects", ()) or ()
    lines = [
        f"Plan long terme pour: {goal}",
        f"Confiance: {confidence if confidence is not None else 'n/a'}",
        f"Projets: {len(projects)}",
    ]
    for project in list(projects)[:5]:
        title = getattr(project, "title", None) or getattr(project, "name", project)
        lines.append(f"- {title}")
    if hasattr(plan, "format_for_prompt"):
        return plan.format_for_prompt()
    return "\n".join(lines)


def _format_architecture(summary: Any) -> str:
    if hasattr(summary, "format_for_prompt"):
        return summary.format_for_prompt()
    name = getattr(summary, "project_name", "project")
    text = getattr(summary, "summary", "") or str(summary)
    return f"Architecture ({name}):\n{text}"


def _format_module(desc: Any) -> str:
    if hasattr(desc, "format_for_prompt"):
        return desc.format_for_prompt()
    return str(desc)


def _format_feature(loc: Any) -> str:
    if hasattr(loc, "format_for_prompt"):
        return loc.format_for_prompt()
    return str(loc)


def _format_impact(impact: Any) -> str:
    if hasattr(impact, "format_for_prompt"):
        return impact.format_for_prompt()
    return str(impact)


def _format_class(summary: Any) -> str:
    if hasattr(summary, "format_for_prompt"):
        return summary.format_for_prompt()
    name = getattr(summary, "name", "class")
    purpose = getattr(summary, "purpose", "") or getattr(summary, "summary", "")
    return f"Classe {name}:\n{purpose}"


def _format_function(summary: Any) -> str:
    if hasattr(summary, "format_for_prompt"):
        return summary.format_for_prompt()
    name = getattr(summary, "name", "function")
    purpose = getattr(summary, "purpose", "") or getattr(summary, "summary", "")
    return f"Fonction {name}:\n{purpose}"


def _format_symbols(symbol: str, locations: Any) -> str:
    lines = [f"Symboles pour « {symbol} »:"]
    for loc in list(locations or [])[:10]:
        path = getattr(loc, "path", None) or getattr(loc, "file_path", loc)
        lines.append(f"- {path}")
    if len(lines) == 1:
        lines.append("- aucun résultat")
    return "\n".join(lines)


def _format_code_plan(plan: Any) -> str:
    if hasattr(plan, "format_for_prompt"):
        return plan.format_for_prompt()
    return str(plan)


def _format_generated_patch(plan: Any, patch: Any) -> str:
    lines = [
        "Code généré (proposition uniquement — non appliqué).",
        f"Plan: {getattr(plan, 'request', '') or getattr(plan, 'goal', '')}",
        f"Patch approuvé (plan): {getattr(patch, 'plan_approved', False)}",
        f"Patch appliqué: non",
    ]
    files = getattr(patch, "files", None) or getattr(patch, "file_patches", None) or ()
    if files:
        lines.append("Fichiers proposés:")
        for item in list(files)[:12]:
            path = getattr(item, "path", None) or getattr(item, "file_path", item)
            lines.append(f"- {path}")
    if hasattr(patch, "format_for_prompt"):
        lines.append(patch.format_for_prompt())
    return "\n".join(lines)


def _format_patch_preview(preview: Any) -> str:
    if hasattr(preview, "format_for_prompt"):
        return preview.format_for_prompt()
    return (
        f"Aperçu patch: +{getattr(preview, 'additions', 0)} "
        f"-{getattr(preview, 'deletions', 0)}; "
        f"fichiers={list(getattr(preview, 'affected_files', ()) or [])}"
    )


def _format_workspace(workspace: Any) -> str:
    if hasattr(workspace, "format_for_prompt"):
        return workspace.format_for_prompt()
    name = getattr(workspace, "project_name", "")
    root = getattr(workspace, "workspace_root", "")
    modules = list(getattr(workspace, "detected_modules", ()) or ())[:15]
    lines = [
        f"Workspace: {name}",
        f"Root: {root}",
        f"Modules: {', '.join(str(m) for m in modules) or 'aucun'}",
    ]
    return "\n".join(lines)


def _format_continuation(
    *,
    workspace: Any,
    missions: list[Any],
    evaluation: Any,
    session_summary: Any,
    workflow: Any,
) -> str:
    lines = ["Reprise du développement:"]
    project = getattr(workspace, "project_name", None)
    if project:
        lines.append(f"- projet: {project}")
    if missions:
        lines.append("- missions:")
        for mission in missions[:5]:
            lines.append(f"  - {getattr(mission, 'title', mission)}")
    recommendation = getattr(evaluation, "recommendation", None)
    if recommendation is not None and getattr(
        recommendation, "recommended_title", None
    ):
        lines.append(f"- focus: {recommendation.recommended_title}")
    elif getattr(evaluation, "current_mission", None) is not None:
        current = evaluation.current_mission
        lines.append(f"- focus: {getattr(current, 'title', current)}")
    if session_summary is not None:
        if hasattr(session_summary, "format_for_prompt"):
            lines.append(session_summary.format_for_prompt())
        else:
            lines.append(f"- session: {session_summary}")
    if workflow is not None:
        if hasattr(workflow, "format_for_prompt"):
            lines.append(workflow.format_for_prompt())
        else:
            goal = getattr(workflow, "goal", "")
            next_steps = getattr(workflow, "next_steps", ()) or ()
            lines.append(f"- workflow goal: {goal}")
            for step in list(next_steps)[:5]:
                lines.append(f"  - {step}")
    return "\n".join(lines)


def _format_proactive_digest(digest: Any) -> str:
    """Format proactive digest for user-facing NLO response."""
    recommendations = getattr(digest, "recommendations", ()) or ()
    if not recommendations:
        return (
            "Rien d'urgent ne ressort pour l'instant. "
            "Aucune recommandation proactive pertinente — c'est une bonne chose."
        )

    lines = ["Voici ce qui mérite ton attention:"]
    for idx, rec in enumerate(recommendations, start=1):
        title = getattr(rec, "title", "") or getattr(rec, "summary", "")
        summary = getattr(rec, "summary", "")
        priority = getattr(rec, "priority", None)
        priority_label = getattr(priority, "value", priority) if priority else "NORMAL"
        confidence = getattr(rec, "confidence", 0.0)
        action = getattr(rec, "recommended_action", None)
        action_label = getattr(action, "label", "") if action else ""
        lines.append(f"{idx}. [{priority_label}] {title}")
        if summary and summary != title:
            lines.append(f"   {summary}")
        if action_label:
            lines.append(f"   → Suggestion: {action_label} (confirmation requise)")
        lines.append(f"   Confiance: {confidence:.0%}")
    return "\n".join(lines)

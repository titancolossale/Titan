# =====================================
# Titan Knowledge Learning Engine
# =====================================

"""Knowledge & Learning Engine V1 — extract reusable knowledge from experience.

Transforms interactions, executions, feedback, and project signals into
generalized knowledge candidates. Proposes knowledge only — never mutates
Titan behavior, missions, memory, or files automatically.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.settings import KNOWLEDGE_LEARNING_PATH

if TYPE_CHECKING:
    from brain.code_intelligence import CodeIntelligence
    from brain.developer_workflow import DeveloperWorkflow, DeveloperWorkflowPlan
    from brain.executive_function import ExecutiveEvaluation, ExecutiveFunction
    from brain.project_intelligence import ProjectIntelligence
    from brain.reasoning_engine import ReasoningEngine
    from brain.reasoning_models import ReasoningResult
    from context.context_manager import ContextManager
    from core.mission_manager import MissionManager
    from memory.learning_memory import LearningMemory, LearningOutcome
    from memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_STORE_PATH = str(KNOWLEDGE_LEARNING_PATH)
MIN_CANDIDATE_CONFIDENCE = 0.25
VERIFIED_CONFIDENCE_FLOOR = 0.75
CORRECTION_REPEAT_THRESHOLD = 2
_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç_]{3,}", re.IGNORECASE)

_CORRECTION_MARKERS = (
    "non",
    "pas ça",
    "pas ca",
    "incorrect",
    "wrong",
    "corrige",
    "correction",
    "plutôt",
    "plutot",
    "instead",
    "should be",
    "ne fais pas",
    "don't",
    "do not",
    "erreur",
    "mistake",
)

_SUCCESS_MARKERS = (
    "success",
    "réussi",
    "reussi",
    "worked",
    "completed",
    "terminé",
    "termine",
    "done",
    "ok",
)

_FAILURE_MARKERS = (
    "fail",
    "échoué",
    "echoue",
    "error",
    "erreur",
    "broken",
    "blocked",
    "timeout",
)


class KnowledgeCategory(str, Enum):
    """Classification of learned knowledge."""

    LESSON = "lesson"
    CORRECTION = "correction"
    PATTERN = "pattern"
    WORKFLOW = "workflow"
    STRATEGY_SUCCESS = "strategy_success"
    STRATEGY_FAILURE = "strategy_failure"
    PREFERENCE = "preference"
    CONVENTION = "convention"


class KnowledgeStatus(str, Enum):
    """Lifecycle state for a knowledge entry."""

    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"


class KnowledgeSource(str, Enum):
    """Origin subsystem for a knowledge entry."""

    INTERACTION = "interaction"
    PROJECT = "project"
    EXECUTION = "execution"
    CODE_CHANGE = "code_change"
    FEEDBACK = "feedback"
    REASONING = "reasoning"
    MEMORY = "memory"
    WORKFLOW = "workflow"
    MANUAL = "manual"


@dataclass(frozen=True)
class VerificationRecord:
    """One verification or rejection event."""

    action: str
    actor: str
    note: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "actor": self.actor,
            "note": self.note,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationRecord:
        return cls(
            action=str(data.get("action", "")),
            actor=str(data.get("actor", "")),
            note=str(data.get("note", "")),
            timestamp=_parse_datetime(data.get("timestamp")),
        )


@dataclass
class KnowledgeItem:
    """One unit of proposed or verified knowledge."""

    id: str
    title: str
    category: KnowledgeCategory
    description: str
    source: KnowledgeSource
    confidence: float
    evidence_count: int
    created_at: datetime
    updated_at: datetime
    verified: bool
    verification_history: list[VerificationRecord] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    related_projects: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    related_tools: list[str] = field(default_factory=list)
    status: KnowledgeStatus = KnowledgeStatus.CANDIDATE
    fingerprint: str = ""
    last_verified_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category.value,
            "description": self.description,
            "source": self.source.value,
            "confidence": round(self.confidence, 3),
            "evidence_count": self.evidence_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "verified": self.verified,
            "verification_history": [v.to_dict() for v in self.verification_history],
            "tags": list(self.tags),
            "related_projects": list(self.related_projects),
            "related_files": list(self.related_files),
            "related_tools": list(self.related_tools),
            "status": self.status.value,
            "fingerprint": self.fingerprint,
            "last_verified_at": (
                self.last_verified_at.isoformat() if self.last_verified_at else None
            ),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeItem:
        return cls(
            id=str(data["id"]),
            title=str(data.get("title", "")),
            category=KnowledgeCategory(data.get("category", KnowledgeCategory.LESSON.value)),
            description=str(data.get("description", "")),
            source=KnowledgeSource(data.get("source", KnowledgeSource.MANUAL.value)),
            confidence=float(data.get("confidence", 0.0)),
            evidence_count=int(data.get("evidence_count", 0)),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
            verified=bool(data.get("verified", False)),
            verification_history=[
                VerificationRecord.from_dict(item)
                for item in data.get("verification_history", [])
            ],
            tags=[str(tag) for tag in data.get("tags", [])],
            related_projects=[str(p) for p in data.get("related_projects", [])],
            related_files=[str(f) for f in data.get("related_files", [])],
            related_tools=[str(t) for t in data.get("related_tools", [])],
            status=KnowledgeStatus(data.get("status", KnowledgeStatus.CANDIDATE.value)),
            fingerprint=str(data.get("fingerprint", "")),
            last_verified_at=(
                _parse_datetime(data["last_verified_at"])
                if data.get("last_verified_at")
                else None
            ),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class LearningResult:
    """Outcome of one learning extraction pass."""

    source: KnowledgeSource
    candidates_created: tuple[KnowledgeItem, ...]
    candidates_updated: tuple[KnowledgeItem, ...]
    patterns_detected: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "candidates_created": [item.to_dict() for item in self.candidates_created],
            "candidates_updated": [item.to_dict() for item in self.candidates_updated],
            "patterns_detected": self.patterns_detected,
            "message": self.message,
        }


@dataclass
class _CorrectionTracker:
    """Tracks repeated user corrections before promotion to knowledge."""

    fingerprint: str
    summary: str
    count: int
    last_seen: str
    user: str
    project_id: str
    related_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "summary": self.summary,
            "count": self.count,
            "last_seen": self.last_seen,
            "user": self.user,
            "project_id": self.project_id,
            "related_tools": list(self.related_tools),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _CorrectionTracker:
        return cls(
            fingerprint=str(data["fingerprint"]),
            summary=str(data.get("summary", "")),
            count=int(data.get("count", 0)),
            last_seen=str(data.get("last_seen", "")),
            user=str(data.get("user", "")),
            project_id=str(data.get("project_id", "")),
            related_tools=[str(t) for t in data.get("related_tools", [])],
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return _utc_now()
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return _utc_now()
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def default_schema() -> dict[str, Any]:
    """Return empty knowledge learning store."""
    return {
        "schema_version": SCHEMA_VERSION,
        "knowledge": [],
        "correction_trackers": [],
    }


def _normalize_text(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _fingerprint_seed(category: str, title: str, description: str) -> str:
    normalized = _normalize_text(f"{category}|{title}|{description}")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _confidence_from_evidence(evidence_count: int, *, verified: bool = False) -> float:
    if verified:
        return max(VERIFIED_CONFIDENCE_FLOOR, min(0.98, 0.75 + evidence_count * 0.03))
    base = 0.30
    bonus = min(0.55, evidence_count * 0.08)
    return round(min(0.90, base + bonus), 3)


class KnowledgeLearningEngine:
    """Extract, score, and lifecycle-manage reusable knowledge from experience."""

    def __init__(
        self,
        *,
        memory_service: MemoryService | None = None,
        learning_memory: LearningMemory | None = None,
        project_intelligence: ProjectIntelligence | None = None,
        code_intelligence: CodeIntelligence | None = None,
        mission_manager: MissionManager | None = None,
        developer_workflow: DeveloperWorkflow | None = None,
        reasoning_engine: ReasoningEngine | None = None,
        executive_function: ExecutiveFunction | None = None,
        context_manager: ContextManager | None = None,
        file_path: str | Path = DEFAULT_STORE_PATH,
    ) -> None:
        self._memory_service = memory_service
        self._learning_memory = learning_memory
        self._project_intelligence = project_intelligence
        self._code_intelligence = code_intelligence
        self._mission_manager = mission_manager
        self._developer_workflow = developer_workflow
        self._reasoning_engine = reasoning_engine
        self._executive_function = executive_function
        self._context_manager = context_manager
        self._file_path = Path(file_path)
        self._knowledge: dict[str, KnowledgeItem] = {}
        self._correction_trackers: dict[str, _CorrectionTracker] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public learning API
    # ------------------------------------------------------------------

    def learn_from_interaction(
        self,
        user_message: str,
        assistant_response: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
        tools_used: list[str] | None = None,
        outcome: str | None = None,
    ) -> LearningResult:
        """Extract lessons from a completed user interaction."""
        created: list[KnowledgeItem] = []
        updated: list[KnowledgeItem] = []
        patterns = 0

        if self._looks_like_correction(user_message):
            result = self.learn_from_feedback(
                user_message,
                context=assistant_response,
                user=user,
                project_id=project_id,
                related_tools=tools_used,
            )
            return result

        lesson_text = self._extract_lesson_from_interaction(
            user_message,
            assistant_response,
            outcome=outcome,
        )
        if lesson_text:
            item, was_created = self._upsert_knowledge(
                title=self._title_from_text(lesson_text, prefix="Interaction"),
                category=KnowledgeCategory.LESSON,
                description=lesson_text,
                source=KnowledgeSource.INTERACTION,
                user=user,
                project_id=project_id,
                related_tools=tools_used or [],
                tags=self._tags_from_text(user_message),
            )
            (created if was_created else updated).append(item)

        if outcome:
            category = (
                KnowledgeCategory.STRATEGY_SUCCESS
                if self._is_success_outcome(outcome)
                else KnowledgeCategory.STRATEGY_FAILURE
                if self._is_failure_outcome(outcome)
                else KnowledgeCategory.LESSON
            )
            item, was_created = self._upsert_knowledge(
                title=self._title_from_text(outcome, prefix="Outcome"),
                category=category,
                description=(
                    f"Interaction outcome: {outcome}. "
                    f"User: {user_message[:200]}"
                ),
                source=KnowledgeSource.INTERACTION,
                user=user,
                project_id=project_id,
                related_tools=tools_used or [],
            )
            (created if was_created else updated).append(item)

        return LearningResult(
            source=KnowledgeSource.INTERACTION,
            candidates_created=tuple(created),
            candidates_updated=tuple(updated),
            patterns_detected=patterns,
            message=f"Processed interaction — {len(created)} new, {len(updated)} updated.",
        )

    def learn_from_project(
        self,
        message: str = "",
        *,
        user: str | None = None,
        project_id: str | None = None,
    ) -> LearningResult:
        """Extract architectural and workflow knowledge from project context."""
        created: list[KnowledgeItem] = []
        updated: list[KnowledgeItem] = []

        if self._project_intelligence is None:
            return LearningResult(
                source=KnowledgeSource.PROJECT,
                candidates_created=(),
                candidates_updated=(),
                patterns_detected=0,
                message="Project Intelligence unavailable.",
            )

        summary = self._project_intelligence.analyze_project(
            user=user,
            project_id=project_id,
        )
        if summary and summary.summary:
            item, was_created = self._upsert_knowledge(
                title="Project architecture insight",
                category=KnowledgeCategory.CONVENTION,
                description=summary.summary[:800],
                source=KnowledgeSource.PROJECT,
                user=user,
                project_id=project_id or self._resolve_project_id(),
                tags=["architecture", "project"],
                metadata={"module_count": len(summary.modules)},
            )
            (created if was_created else updated).append(item)

        if message:
            location = self._project_intelligence.find_feature(message)
            if location and location.confidence > 0:
                primary = (
                    location.primary_files[0]
                    if location.primary_files
                    else location.owner_module
                )
                desc = (
                    f"Feature '{location.feature}' maps to {location.owner_module} "
                    f"({location.confidence:.0%} confidence)."
                )
                item, was_created = self._upsert_knowledge(
                    title=f"Feature location: {location.feature}",
                    category=KnowledgeCategory.WORKFLOW,
                    description=desc,
                    source=KnowledgeSource.PROJECT,
                    user=user,
                    project_id=project_id or self._resolve_project_id(),
                    related_files=[primary] if primary else [],
                    tags=["feature", "navigation"],
                )
                (created if was_created else updated).append(item)

        return LearningResult(
            source=KnowledgeSource.PROJECT,
            candidates_created=tuple(created),
            candidates_updated=tuple(updated),
            patterns_detected=0,
            message=f"Project learning — {len(created)} new, {len(updated)} updated.",
        )

    def learn_from_execution(
        self,
        *,
        mission_id: str | None = None,
        tool_name: str = "",
        success: bool = True,
        summary_message: str = "",
        user: str | None = None,
        project_id: str | None = None,
    ) -> LearningResult:
        """Learn from a completed tool or mission execution."""
        created: list[KnowledgeItem] = []
        updated: list[KnowledgeItem] = []

        category = (
            KnowledgeCategory.STRATEGY_SUCCESS
            if success
            else KnowledgeCategory.STRATEGY_FAILURE
        )
        title_prefix = "Successful" if success else "Failed"
        tool_label = tool_name or "execution"
        description = summary_message or (
            f"{'Successful' if success else 'Failed'} {tool_label} execution."
        )

        related_tools = [tool_name] if tool_name else []
        item, was_created = self._upsert_knowledge(
            title=f"{title_prefix} strategy: {tool_label}",
            category=category,
            description=description[:600],
            source=KnowledgeSource.EXECUTION,
            user=user,
            project_id=project_id or self._resolve_project_id(),
            related_tools=related_tools,
            tags=["execution", "tool" if tool_name else "mission"],
            metadata={"mission_id": mission_id or "", "success": success},
        )
        (created if was_created else updated).append(item)

        if self._learning_memory is not None and tool_name:
            from memory.learning_memory import LearningOutcome

            outcome = (
                LearningOutcome.SUCCESS if success else LearningOutcome.FAILURE
            )
            self._learning_memory.record_outcome(
                domain="tool_execution",
                approach=tool_name,
                outcome=outcome,
                context=summary_message,
                user=user or "",
                project_id=project_id or "",
            )

        if self._mission_manager is not None and mission_id:
            mission = self._mission_manager.runtime.get_mission(mission_id)
            if mission and not success:
                item2, was_created2 = self._upsert_knowledge(
                    title=f"Mission blocker: {mission.title}",
                    category=KnowledgeCategory.STRATEGY_FAILURE,
                    description=(
                        f"Mission '{mission.title}' encountered execution failure: "
                        f"{summary_message or 'unknown error'}"
                    ),
                    source=KnowledgeSource.EXECUTION,
                    user=user,
                    project_id=project_id or mission.project_id,
                    related_tools=related_tools,
                    tags=["mission", "blocked"],
                    metadata={"mission_id": mission_id},
                )
                (created if was_created2 else updated).append(item2)

        return LearningResult(
            source=KnowledgeSource.EXECUTION,
            candidates_created=tuple(created),
            candidates_updated=tuple(updated),
            patterns_detected=0,
            message=f"Execution learning — {len(created)} new, {len(updated)} updated.",
        )

    def learn_from_code_change(
        self,
        *,
        files_changed: list[str],
        change_summary: str = "",
        patch_approved: bool = False,
        user: str | None = None,
        project_id: str | None = None,
    ) -> LearningResult:
        """Learn conventions and patterns from code changes."""
        created: list[KnowledgeItem] = []
        updated: list[KnowledgeItem] = []

        if not files_changed and not change_summary:
            return LearningResult(
                source=KnowledgeSource.CODE_CHANGE,
                candidates_created=(),
                candidates_updated=(),
                patterns_detected=0,
                message="No code change signals provided.",
            )

        description = change_summary or (
            f"Code change across {len(files_changed)} file(s): "
            f"{', '.join(files_changed[:5])}"
        )
        category = (
            KnowledgeCategory.CONVENTION
            if patch_approved
            else KnowledgeCategory.PATTERN
        )
        item, was_created = self._upsert_knowledge(
            title=self._title_from_text(description, prefix="Code change"),
            category=category,
            description=description[:600],
            source=KnowledgeSource.CODE_CHANGE,
            user=user,
            project_id=project_id or self._resolve_project_id(),
            related_files=files_changed[:20],
            tags=["code", "patch" if patch_approved else "draft"],
            metadata={"approved": patch_approved},
        )
        (created if was_created else updated).append(item)

        if self._code_intelligence is not None and files_changed:
            for file_path in files_changed[:3]:
                try:
                    module = self._code_intelligence.summarize_module(file_path)
                except Exception:
                    logger.debug("Module summary unavailable for %s", file_path)
                    continue
                if module and module.purpose:
                    mod_item, mod_created = self._upsert_knowledge(
                        title=f"Module pattern: {module.name}",
                        category=KnowledgeCategory.PATTERN,
                        description=module.purpose[:500],
                        source=KnowledgeSource.CODE_CHANGE,
                        user=user,
                        project_id=project_id or self._resolve_project_id(),
                        related_files=[file_path],
                        tags=["module", "structure"],
                    )
                    (created if mod_created else updated).append(mod_item)

        return LearningResult(
            source=KnowledgeSource.CODE_CHANGE,
            candidates_created=tuple(created),
            candidates_updated=tuple(updated),
            patterns_detected=len(files_changed),
            message=f"Code change learning — {len(created)} new, {len(updated)} updated.",
        )

    def learn_from_feedback(
        self,
        feedback: str,
        *,
        context: str = "",
        user: str | None = None,
        project_id: str | None = None,
        related_tools: list[str] | None = None,
    ) -> LearningResult:
        """Detect user corrections and recurring preference signals."""
        created: list[KnowledgeItem] = []
        updated: list[KnowledgeItem] = []
        patterns = 0

        summary = self._normalize_correction(feedback)
        if not summary:
            return LearningResult(
                source=KnowledgeSource.FEEDBACK,
                candidates_created=(),
                candidates_updated=(),
                patterns_detected=0,
                message="No correction signal detected in feedback.",
            )

        fingerprint = _fingerprint_seed("correction", summary, user or "")
        tracker = self._correction_trackers.get(fingerprint)
        now_iso = _utc_now_iso()
        if tracker is None:
            tracker = _CorrectionTracker(
                fingerprint=fingerprint,
                summary=summary,
                count=1,
                last_seen=now_iso,
                user=user or "",
                project_id=project_id or "",
                related_tools=list(related_tools or []),
            )
            self._correction_trackers[fingerprint] = tracker
        else:
            tracker.count += 1
            tracker.last_seen = now_iso
            if related_tools:
                tracker.related_tools = sorted(
                    set(tracker.related_tools) | set(related_tools)
                )

        category = KnowledgeCategory.CORRECTION
        if tracker.count >= CORRECTION_REPEAT_THRESHOLD:
            category = KnowledgeCategory.PATTERN
            patterns = 1

        description = summary
        if context:
            description = f"{summary}\n\nContext: {context[:400]}"

        item, was_created = self._upsert_knowledge(
            title=self._title_from_text(summary, prefix="User correction"),
            category=category,
            description=description[:600],
            source=KnowledgeSource.FEEDBACK,
            user=user,
            project_id=project_id or self._resolve_project_id(),
            related_tools=related_tools or [],
            tags=["feedback", "correction"],
            metadata={"correction_count": tracker.count},
            fingerprint_override=fingerprint,
        )
        (created if was_created else updated).append(item)
        self._save()

        return LearningResult(
            source=KnowledgeSource.FEEDBACK,
            candidates_created=tuple(created),
            candidates_updated=tuple(updated),
            patterns_detected=patterns,
            message=(
                f"Feedback processed — correction count {tracker.count}, "
                f"{len(created)} new, {len(updated)} updated."
            ),
        )

    def learn_from_workflow(
        self,
        plan: DeveloperWorkflowPlan,
        *,
        user: str | None = None,
        project_id: str | None = None,
    ) -> LearningResult:
        """Discover reusable workflows from a developer workflow plan."""
        created: list[KnowledgeItem] = []
        updated: list[KnowledgeItem] = []

        steps = plan.next_steps
        if not steps:
            return LearningResult(
                source=KnowledgeSource.WORKFLOW,
                candidates_created=(),
                candidates_updated=(),
                patterns_detected=0,
                message="No workflow steps to learn from.",
            )

        workflow_desc = "\n".join(f"- {step}" for step in steps[:8])
        related_files = list(plan.relevant_files[:15])
        related_tools = list(plan.recommended_tools[:10])

        item, was_created = self._upsert_knowledge(
            title=self._title_from_text(plan.goal, prefix="Workflow"),
            category=KnowledgeCategory.WORKFLOW,
            description=workflow_desc[:800],
            source=KnowledgeSource.WORKFLOW,
            user=user,
            project_id=project_id or self._resolve_project_id(),
            related_files=related_files,
            related_tools=related_tools,
            tags=["workflow", str(plan.intent.value) if hasattr(plan, "intent") else "dev"],
            metadata={"intent": getattr(plan.intent, "value", "")},
        )
        (created if was_created else updated).append(item)

        return LearningResult(
            source=KnowledgeSource.WORKFLOW,
            candidates_created=tuple(created),
            candidates_updated=tuple(updated),
            patterns_detected=1,
            message=f"Workflow learning — {len(created)} new, {len(updated)} updated.",
        )

    def learn_from_reasoning(
        self,
        reasoning_result: ReasoningResult,
        *,
        user: str | None = None,
        project_id: str | None = None,
    ) -> LearningResult:
        """Extract strategy knowledge from a ReasoningResult."""
        created: list[KnowledgeItem] = []
        updated: list[KnowledgeItem] = []

        if reasoning_result.recommendation:
            rec = reasoning_result.recommendation
            rationale = (
                rec.supporting_arguments[0]
                if rec.supporting_arguments
                else ""
            )
            item, was_created = self._upsert_knowledge(
                title=self._title_from_text(rec.strategy, prefix="Strategy"),
                category=KnowledgeCategory.STRATEGY_SUCCESS,
                description=(
                    f"{rec.strategy}\n\nRationale: {rationale[:400]}"
                ),
                source=KnowledgeSource.REASONING,
                user=user,
                project_id=project_id or self._resolve_project_id(),
                tags=["reasoning", "strategy"],
                metadata={"confidence": rec.confidence},
            )
            (created if was_created else updated).append(item)

        for risk in reasoning_result.risks[:3]:
            item, was_created = self._upsert_knowledge(
                title=self._title_from_text(risk.summary, prefix="Risk"),
                category=KnowledgeCategory.LESSON,
                description=f"{risk.summary} (severity: {risk.severity})",
                source=KnowledgeSource.REASONING,
                user=user,
                project_id=project_id or self._resolve_project_id(),
                tags=["risk", "reasoning"],
            )
            (created if was_created else updated).append(item)

        return LearningResult(
            source=KnowledgeSource.REASONING,
            candidates_created=tuple(created),
            candidates_updated=tuple(updated),
            patterns_detected=0,
            message=f"Reasoning learning — {len(created)} new, {len(updated)} updated.",
        )

    def generate_candidate_knowledge(
        self,
        *,
        title: str,
        description: str,
        category: KnowledgeCategory = KnowledgeCategory.LESSON,
        source: KnowledgeSource = KnowledgeSource.MANUAL,
        user: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        related_files: list[str] | None = None,
        related_tools: list[str] | None = None,
    ) -> KnowledgeItem:
        """Create a manual knowledge candidate."""
        item, _ = self._upsert_knowledge(
            title=title,
            category=category,
            description=description,
            source=source,
            user=user,
            project_id=project_id,
            tags=tags or [],
            related_files=related_files or [],
            related_tools=related_tools or [],
            force_new=True,
        )
        return item

    def approve_candidate(
        self,
        knowledge_id: str,
        *,
        actor: str = "user",
        note: str = "",
    ) -> KnowledgeItem | None:
        """Promote a candidate to verified knowledge."""
        item = self._knowledge.get(knowledge_id)
        if item is None or item.status == KnowledgeStatus.REJECTED:
            return None

        now = _utc_now()
        record = VerificationRecord(
            action="approved",
            actor=actor,
            note=note or "Promoted to verified knowledge.",
            timestamp=now,
        )
        item.status = KnowledgeStatus.VERIFIED
        item.verified = True
        item.last_verified_at = now
        item.updated_at = now
        item.verification_history.append(record)
        item.confidence = _confidence_from_evidence(item.evidence_count, verified=True)
        self._save()
        return item

    def reject_candidate(
        self,
        knowledge_id: str,
        *,
        actor: str = "user",
        note: str = "",
    ) -> KnowledgeItem | None:
        """Reject a knowledge candidate."""
        item = self._knowledge.get(knowledge_id)
        if item is None:
            return None

        now = _utc_now()
        record = VerificationRecord(
            action="rejected",
            actor=actor,
            note=note or "Rejected by user.",
            timestamp=now,
        )
        item.status = KnowledgeStatus.REJECTED
        item.verified = False
        item.updated_at = now
        item.confidence = 0.0
        item.verification_history.append(record)
        self._save()
        return item

    def list_candidates(
        self,
        *,
        category: KnowledgeCategory | None = None,
        min_confidence: float = MIN_CANDIDATE_CONFIDENCE,
    ) -> tuple[KnowledgeItem, ...]:
        """Return knowledge items awaiting verification."""
        items = [
            item
            for item in self._knowledge.values()
            if item.status == KnowledgeStatus.CANDIDATE
            and item.confidence >= min_confidence
            and (category is None or item.category == category)
        ]
        items.sort(key=lambda i: (-i.confidence, -i.evidence_count, i.title))
        return tuple(items)

    def list_verified_knowledge(
        self,
        *,
        category: KnowledgeCategory | None = None,
    ) -> tuple[KnowledgeItem, ...]:
        """Return verified knowledge entries."""
        items = [
            item
            for item in self._knowledge.values()
            if item.status == KnowledgeStatus.VERIFIED
            and (category is None or item.category == category)
        ]
        items.sort(
            key=lambda i: (
                -(i.last_verified_at or i.updated_at).timestamp(),
                -i.confidence,
            )
        )
        return tuple(items)

    def search_knowledge(
        self,
        query: str,
        *,
        verified_only: bool = False,
        limit: int = 20,
    ) -> tuple[KnowledgeItem, ...]:
        """Search knowledge by title, description, and tags."""
        tokens = set(_normalize_text(query).split())
        if not tokens:
            return ()

        scored: list[tuple[float, KnowledgeItem]] = []
        for item in self._knowledge.values():
            if verified_only and item.status != KnowledgeStatus.VERIFIED:
                continue
            if item.status == KnowledgeStatus.REJECTED:
                continue

            haystack = _normalize_text(
                f"{item.title} {item.description} {' '.join(item.tags)}"
            )
            hay_tokens = set(haystack.split())
            overlap = len(tokens & hay_tokens)
            if overlap == 0 and query.lower() not in item.title.lower():
                continue
            score = overlap + item.confidence * 0.5
            scored.append((score, item))

        scored.sort(key=lambda pair: (-pair[0], -pair[1].confidence))
        return tuple(item for _, item in scored[:limit])

    def update_confidence(
        self,
        knowledge_id: str,
        *,
        delta: float = 0.0,
        absolute: float | None = None,
        evidence_increment: int = 0,
    ) -> KnowledgeItem | None:
        """Adjust confidence and evidence for a knowledge entry."""
        item = self._knowledge.get(knowledge_id)
        if item is None or item.status == KnowledgeStatus.REJECTED:
            return None

        if evidence_increment:
            item.evidence_count += evidence_increment

        if absolute is not None:
            item.confidence = max(0.0, min(1.0, absolute))
        else:
            item.confidence = max(0.0, min(1.0, item.confidence + delta))

        if item.status == KnowledgeStatus.VERIFIED:
            item.confidence = max(
                item.confidence,
                _confidence_from_evidence(item.evidence_count, verified=True),
            )
        elif item.evidence_count:
            item.confidence = max(
                item.confidence,
                _confidence_from_evidence(item.evidence_count),
            )

        item.updated_at = _utc_now()
        self._save()
        return item

    def merge_duplicate_knowledge(
        self,
        primary_id: str,
        duplicate_id: str,
    ) -> KnowledgeItem | None:
        """Merge duplicate knowledge into the primary entry."""
        primary = self._knowledge.get(primary_id)
        duplicate = self._knowledge.get(duplicate_id)
        if primary is None or duplicate is None or primary_id == duplicate_id:
            return None

        primary.evidence_count += duplicate.evidence_count
        primary.tags = sorted(set(primary.tags) | set(duplicate.tags))
        primary.related_projects = sorted(
            set(primary.related_projects) | set(duplicate.related_projects)
        )
        primary.related_files = sorted(
            set(primary.related_files) | set(duplicate.related_files)
        )
        primary.related_tools = sorted(
            set(primary.related_tools) | set(duplicate.related_tools)
        )
        if duplicate.description and duplicate.description not in primary.description:
            primary.description = (
                f"{primary.description}\n\nMerged: {duplicate.description}"
            )[:1200]

        primary.confidence = _confidence_from_evidence(
            primary.evidence_count,
            verified=primary.verified,
        )
        primary.updated_at = _utc_now()
        primary.verification_history.append(
            VerificationRecord(
                action="merged",
                actor="system",
                note=f"Merged duplicate {duplicate_id}",
                timestamp=_utc_now(),
            )
        )
        del self._knowledge[duplicate_id]
        self._save()
        return primary

    def get_knowledge(self, knowledge_id: str) -> KnowledgeItem | None:
        """Return one knowledge entry by id."""
        return self._knowledge.get(knowledge_id)

    def format_for_prompt(
        self,
        query: str = "",
        *,
        limit: int = 5,
    ) -> str:
        """Format verified knowledge for optional prompt injection."""
        items = (
            self.search_knowledge(query, verified_only=True, limit=limit)
            if query
            else self.list_verified_knowledge()[:limit]
        )
        if not items:
            return ""
        lines = ["Connaissances vérifiées (apprentissage) :"]
        for item in items:
            lines.append(
                f"  - [{item.category.value}] {item.title} "
                f"(confiance {item.confidence:.0%}, preuves {item.evidence_count})"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upsert_knowledge(
        self,
        *,
        title: str,
        category: KnowledgeCategory,
        description: str,
        source: KnowledgeSource,
        user: str | None = None,
        project_id: str | None = None,
        related_files: list[str] | None = None,
        related_tools: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        fingerprint_override: str | None = None,
        force_new: bool = False,
    ) -> tuple[KnowledgeItem, bool]:
        fingerprint = fingerprint_override or _fingerprint_seed(
            category.value, title, description
        )
        now = _utc_now()
        project = project_id or self._resolve_project_id()

        if not force_new:
            for existing in self._knowledge.values():
                if (
                    existing.fingerprint == fingerprint
                    and existing.status != KnowledgeStatus.REJECTED
                ):
                    existing.evidence_count += 1
                    existing.updated_at = now
                    if (
                        category == KnowledgeCategory.PATTERN
                        and existing.category == KnowledgeCategory.CORRECTION
                    ):
                        existing.category = KnowledgeCategory.PATTERN
                    existing.confidence = _confidence_from_evidence(
                        existing.evidence_count,
                        verified=existing.verified,
                    )
                    if project and project not in existing.related_projects:
                        existing.related_projects.append(project)
                    for path in related_files or []:
                        if path not in existing.related_files:
                            existing.related_files.append(path)
                    for tool in related_tools or []:
                        if tool not in existing.related_tools:
                            existing.related_tools.append(tool)
                    for tag in tags or []:
                        if tag not in existing.tags:
                            existing.tags.append(tag)
                    self._save()
                    return existing, False

        item = KnowledgeItem(
            id=str(uuid.uuid4()),
            title=title.strip()[:120],
            category=category,
            description=description.strip(),
            source=source,
            confidence=_confidence_from_evidence(1),
            evidence_count=1,
            created_at=now,
            updated_at=now,
            verified=False,
            tags=list(tags or []),
            related_projects=[project] if project else [],
            related_files=list(related_files or []),
            related_tools=list(related_tools or []),
            status=KnowledgeStatus.CANDIDATE,
            fingerprint=fingerprint,
            metadata=dict(metadata or {}),
        )
        if user:
            item.metadata["user"] = user
        self._knowledge[item.id] = item
        self._save()
        return item, True

    def _resolve_project_id(self) -> str:
        if self._context_manager is not None:
            return self._context_manager.active_project or ""
        return ""

    def _looks_like_correction(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in _CORRECTION_MARKERS)

    def _normalize_correction(self, text: str) -> str:
        if not self._looks_like_correction(text):
            return ""
        cleaned = re.sub(r"\s+", " ", text.strip())
        return cleaned[:300]

    def _is_success_outcome(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in _SUCCESS_MARKERS)

    def _is_failure_outcome(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in _FAILURE_MARKERS)

    def _extract_lesson_from_interaction(
        self,
        user_message: str,
        assistant_response: str,
        *,
        outcome: str | None,
    ) -> str:
        if outcome and (self._is_success_outcome(outcome) or self._is_failure_outcome(outcome)):
            return ""
        combined = f"{user_message} {assistant_response}".strip()
        if len(combined) < 40:
            return ""
        preference_markers = ("préfère", "prefere", "always", "toujours", "never", "jamais")
        if any(marker in combined.lower() for marker in preference_markers):
            return combined[:400]
        if "souviens" in combined.lower() or "remember" in combined.lower():
            return combined[:400]
        return ""

    def _title_from_text(self, text: str, *, prefix: str = "Knowledge") -> str:
        normalized = re.sub(r"\s+", " ", text.strip())
        if len(normalized) <= 80:
            return normalized or prefix
        return f"{prefix}: {normalized[:77]}..."

    def _tags_from_text(self, text: str) -> list[str]:
        tokens = _normalize_text(text).split()
        return [token for token in tokens[:6] if len(token) > 3]

    def _load(self) -> None:
        if not self._file_path.exists():
            self._knowledge = {}
            self._correction_trackers = {}
            return

        try:
            with self._file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Knowledge learning store corrupt: %s", exc)
            self._knowledge = {}
            self._correction_trackers = {}
            return

        if raw.get("schema_version") != SCHEMA_VERSION:
            raw["schema_version"] = SCHEMA_VERSION

        self._knowledge = {
            item["id"]: KnowledgeItem.from_dict(item)
            for item in raw.get("knowledge", [])
        }
        self._correction_trackers = {
            tracker["fingerprint"]: _CorrectionTracker.from_dict(tracker)
            for tracker in raw.get("correction_trackers", [])
        }

    def _save(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "knowledge": [item.to_dict() for item in self._knowledge.values()],
            "correction_trackers": [
                tracker.to_dict() for tracker in self._correction_trackers.values()
            ],
        }
        with self._file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=4, ensure_ascii=False)

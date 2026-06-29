# =====================================
# Titan Initiative Engine
# =====================================

"""Detects opportunities and risks for controlled proactivity (Phase 9 — P9-050)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from brain.autonomy_policy import AutonomyPolicy, ProactiveLevel
from memory.learning_memory import LearningMemory


class InitiativeKind(str, Enum):
    """Classification of initiative signals."""

    OPPORTUNITY = "opportunity"
    RISK = "risk"
    REMINDER = "reminder"
    LEARNING = "learning"


@dataclass(frozen=True)
class InitiativeSignal:
    """One proactive suggestion or risk alert."""

    kind: InitiativeKind
    message: str
    priority: int = 0
    source: str = "initiative_engine"


@dataclass
class InitiativeResult:
    """Aggregated initiative analysis for prompt injection."""

    signals: list[InitiativeSignal] = field(default_factory=list)
    suppressed: bool = False

    @property
    def has_signals(self) -> bool:
        return bool(self.signals) and not self.suppressed

    def format_for_prompt(self) -> str:
        """Format signals for INITIATIVE section."""
        if not self.has_signals:
            return ""
        lines = ["Signaux d'initiative (à mentionner seulement si pertinent) :"]
        for signal in self.signals:
            prefix = {
                InitiativeKind.OPPORTUNITY: "Opportunité",
                InitiativeKind.RISK: "Risque",
                InitiativeKind.REMINDER: "Rappel",
                InitiativeKind.LEARNING: "Apprentissage",
            }[signal.kind]
            lines.append(f"  - [{prefix}] {signal.message}")
        return "\n".join(lines)


_RISK_KEYWORDS: tuple[str, ...] = (
    "urgent",
    "deadline",
    "bloqué",
    "bloque",
    "risque",
    "échéance",
    "echeance",
    "critique",
)

_OPPORTUNITY_KEYWORDS: tuple[str, ...] = (
    "prochaine étape",
    "prochaine etape",
    "comment avancer",
    "checkpoint",
    "point de contrôle",
)


class InitiativeEngine:
    """Rule-based initiative detection with policy guardrails."""

    def __init__(
        self,
        policy: AutonomyPolicy | None = None,
        learning_memory: LearningMemory | None = None,
    ) -> None:
        self._policy = policy or AutonomyPolicy.from_settings()
        self._learning = learning_memory

    def analyze(
        self,
        user_message: str,
        *,
        mission: dict | None = None,
        state: dict | None = None,
        user: str = "Nolan",
        project_id: str = "",
    ) -> InitiativeResult:
        """Detect initiative signals; respect proactive policy."""
        if not self._policy.should_surface_initiative():
            return InitiativeResult(suppressed=True)

        mission = mission or {}
        state = state or {}
        message_lower = user_message.lower()
        signals: list[InitiativeSignal] = []

        signals.extend(self._detect_risks(message_lower, mission, state))
        signals.extend(self._detect_opportunities(message_lower, mission))
        signals.extend(self._detect_mission_stall(mission))
        if self._learning is not None and project_id:
            signals.extend(self._detect_learning_warnings(project_id, user))

        signals.sort(key=lambda signal: signal.priority, reverse=True)
        cap = self._policy.initiative_max_suggestions()
        return InitiativeResult(signals=signals[:cap])

    def _detect_risks(
        self,
        message_lower: str,
        mission: dict,
        state: dict,
    ) -> list[InitiativeSignal]:
        signals: list[InitiativeSignal] = []
        for keyword in _RISK_KEYWORDS:
            if keyword in message_lower:
                signals.append(
                    InitiativeSignal(
                        kind=InitiativeKind.RISK,
                        message=(
                            f"Signal d'urgence détecté (« {keyword} ») — "
                            "prioriser clarté et prochaine action concrète."
                        ),
                        priority=90,
                    ),
                )
                break

        if mission.get("active") and state.get("progress") == "blocked":
            signals.append(
                InitiativeSignal(
                    kind=InitiativeKind.RISK,
                    message="Mission active marquée bloquée — proposer déblocage.",
                    priority=80,
                ),
            )
        return signals

    def _detect_opportunities(
        self,
        message_lower: str,
        mission: dict,
    ) -> list[InitiativeSignal]:
        signals: list[InitiativeSignal] = []
        for keyword in _OPPORTUNITY_KEYWORDS:
            if keyword in message_lower:
                signals.append(
                    InitiativeSignal(
                        kind=InitiativeKind.OPPORTUNITY,
                        message=(
                            "L'utilisateur cherche à avancer — "
                            "proposer une prochaine étape actionnable."
                        ),
                        priority=70,
                    ),
                )
                break

        if mission.get("active") and not signals:
            step = mission.get("current_step", 0)
            steps = mission.get("steps", [])
            if steps and step < len(steps):
                current = steps[step] if isinstance(steps[step], str) else steps[step].get("title", "")
                if current:
                    signals.append(
                        InitiativeSignal(
                            kind=InitiativeKind.OPPORTUNITY,
                            message=f"Étape mission en cours : {current}",
                            priority=50,
                        ),
                    )
        return signals

    def _detect_mission_stall(self, mission: dict) -> list[InitiativeSignal]:
        if not mission.get("active"):
            return []
        if self._policy.proactive_level is ProactiveLevel.LOW:
            return []
        return [
            InitiativeSignal(
                kind=InitiativeKind.REMINDER,
                message="Mission active — vérifier si l'étape courante avance.",
                priority=40,
            ),
        ]

    def _detect_learning_warnings(
        self,
        project_id: str,
        user: str,
    ) -> list[InitiativeSignal]:
        if self._learning is None:
            return []
        lessons = self._learning.get_lessons(project_id, user=user, limit=2)
        warnings = [
            lesson for lesson in lessons if lesson.startswith("[échoué]")
        ]
        if not warnings:
            return []
        return [
            InitiativeSignal(
                kind=InitiativeKind.LEARNING,
                message=(
                    f"Approches précédentes échouées sur {project_id} — "
                    "éviter de répéter sans adaptation."
                ),
                priority=60,
            ),
        ]

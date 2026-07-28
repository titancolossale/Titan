# =====================================
# Titan Execution Safety
# =====================================

"""Centralized execution safety classification and confirmation policy (Phase 18.2).

Evaluates an ``ExecutionTask`` before any side effect. Reuses AutonomyPolicy,
``TITAN_TOOL_DEFAULT_EXECUTION_MODE``, and confirmation TTL settings — does not
replace ``ConfirmationGate`` / tool confirmation; it applies the same policy
surface to cognitive ExecutionEngine tasks.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from brain.autonomy_policy import AutonomousActionType, AutonomyPolicy
from config.settings import (
    TITAN_TOOL_CONFIRMATION_TTL_SECONDS,
    TITAN_TOOL_DEFAULT_EXECUTION_MODE,
)

logger = logging.getLogger(__name__)

# Keys never copied into logs, public workspace state, or impact summaries.
_SENSITIVE_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "credential",
        "authorization",
        "auth_header",
        "bearer",
    }
)

_DESTRUCTIVE_PATTERNS = re.compile(
    r"\b(delete|destroy|drop|purge|wipe|rm\b|remove|truncate|format)\b",
    re.IGNORECASE,
)
_WRITE_PATTERNS = re.compile(
    r"\b(write|create|update|patch|edit|modify|save|append|insert|upload|send|"
    r"execute|exec|run|install|deploy)\b",
    re.IGNORECASE,
)
_READ_PATTERNS = re.compile(
    r"\b(read|list|get|fetch|search|query|inspect|show|view|status|health|"
    r"lookup|find)\b",
    re.IGNORECASE,
)
_FORBIDDEN_PATTERNS = re.compile(
    r"\b(exfiltrat|credential.?dump|disable.?safety|bypass.?confirm|"
    r"force.?push\s+main|rm\s+-rf\s+/)\b",
    re.IGNORECASE,
)


class ExecutionRiskLevel(str, Enum):
    """Risk classification for one ExecutionTask."""

    SAFE_READ = "SAFE_READ"
    LOW_RISK_WRITE = "LOW_RISK_WRITE"
    HIGH_RISK_WRITE = "HIGH_RISK_WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    FORBIDDEN = "FORBIDDEN"


class SafetyDecision(str, Enum):
    """Outcome of safety evaluation — gate before any side effect."""

    APPROVED = "APPROVED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    BLOCKED = "BLOCKED"
    FORBIDDEN = "FORBIDDEN"


@dataclass(frozen=True)
class ExecutionSafetyResult:
    """Structured safety evaluation for one ExecutionTask (Phase 18.2)."""

    task_id: str
    risk_level: ExecutionRiskLevel
    decision: SafetyDecision
    reason: str
    requires_confirmation: bool
    confirmation_id: str | None
    reversible: bool
    expected_impact: str
    evaluated_at: datetime
    action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "risk_level": self.risk_level.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_id": self.confirmation_id,
            "reversible": self.reversible,
            "expected_impact": self.expected_impact,
            "evaluated_at": self.evaluated_at.isoformat(),
            "action": self.action,
        }

    def format_for_prompt(self) -> str:
        """Concise prompt block — never includes secrets or full payloads."""
        lines = [
            "Execution Safety",
            f"Risk Level: {self.risk_level.value}",
        ]
        if self.requires_confirmation or self.decision == SafetyDecision.CONFIRMATION_REQUIRED:
            lines.append("Confirmation Required: yes")
            if self.confirmation_id:
                lines.append(f"Confirmation Id: {self.confirmation_id}")
        elif self.decision == SafetyDecision.APPROVED:
            lines.append("Confirmation Required: no")
        if self.decision in (SafetyDecision.BLOCKED, SafetyDecision.FORBIDDEN):
            lines.append(f"Blocked Reason: {self.reason}")
        if self.risk_level == ExecutionRiskLevel.DESTRUCTIVE and self.expected_impact:
            lines.append(f"Expected Impact: {self.expected_impact}")
        return "\n".join(lines)


@dataclass
class PendingExecutionConfirmation:
    """Persisted confirmation hold for an ExecutionTask awaiting approval."""

    confirmation_id: str
    task_id: str
    action: str | None
    risk_level: ExecutionRiskLevel
    expected_impact: str
    created_at: float
    decision_id: str | None = None
    executed: bool = False
    rejected: bool = False
    # Sanitized public metadata only — never raw tool arguments.
    public_metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionSafetyEvaluator:
    """Classify risk and apply confirmation policy before execution."""

    def __init__(
        self,
        *,
        autonomy_policy: AutonomyPolicy | None = None,
        confirmation_ttl_seconds: float | None = None,
        default_execution_mode: str | None = None,
    ) -> None:
        self._policy = autonomy_policy or AutonomyPolicy.from_settings()
        self._ttl = (
            TITAN_TOOL_CONFIRMATION_TTL_SECONDS
            if confirmation_ttl_seconds is None
            else float(confirmation_ttl_seconds)
        )
        mode = (
            TITAN_TOOL_DEFAULT_EXECUTION_MODE
            if default_execution_mode is None
            else str(default_execution_mode)
        )
        self._default_execution_mode = mode.lower().strip()

    @property
    def confirmation_ttl_seconds(self) -> float:
        return self._ttl

    @property
    def autonomy_policy(self) -> AutonomyPolicy:
        return self._policy

    def evaluate(
        self,
        *,
        task_id: str,
        action: str | None,
        capability: Any | None = None,
        action_metadata: Mapping[str, Any] | None = None,
        decision: Any | None = None,
        execution_mode: str | None = None,
        now: datetime | None = None,
        issue_confirmation_id: bool = True,
    ) -> ExecutionSafetyResult:
        """Evaluate safety for a pending task. No side effects beyond classification."""
        stamp = now or datetime.now(timezone.utc)
        meta = dict(action_metadata or {})
        risk = self.classify_risk(
            action=action,
            capability=capability,
            action_metadata=meta,
            decision=decision,
        )
        mode = (execution_mode or self._default_execution_mode or "live").lower()
        reversible = self._is_reversible(risk, capability, meta)
        impact = self._expected_impact(action, risk, meta)

        if risk == ExecutionRiskLevel.FORBIDDEN:
            result = ExecutionSafetyResult(
                task_id=task_id,
                risk_level=risk,
                decision=SafetyDecision.FORBIDDEN,
                reason=str(meta.get("forbidden_reason") or "Action is forbidden by policy"),
                requires_confirmation=False,
                confirmation_id=None,
                reversible=False,
                expected_impact=impact,
                evaluated_at=stamp,
                action=action,
            )
            return result

        requires = self._requires_confirmation(risk, capability, meta, mode)
        if requires:
            confirmation_id = str(uuid.uuid4()) if issue_confirmation_id else None
            reason = self._confirmation_reason(risk)
            return ExecutionSafetyResult(
                task_id=task_id,
                risk_level=risk,
                decision=SafetyDecision.CONFIRMATION_REQUIRED,
                reason=reason,
                requires_confirmation=True,
                confirmation_id=confirmation_id,
                reversible=reversible,
                expected_impact=impact,
                evaluated_at=stamp,
                action=action,
            )

        return ExecutionSafetyResult(
            task_id=task_id,
            risk_level=risk,
            decision=SafetyDecision.APPROVED,
            reason="Approved — within autonomy policy",
            requires_confirmation=False,
            confirmation_id=None,
            reversible=reversible,
            expected_impact=impact,
            evaluated_at=stamp,
            action=action,
        )

    def classify_risk(
        self,
        *,
        action: str | None,
        capability: Any | None = None,
        action_metadata: Mapping[str, Any] | None = None,
        decision: Any | None = None,
    ) -> ExecutionRiskLevel:
        """Classify from tool capability / side-effect metadata; default safer."""
        meta = dict(action_metadata or {})
        explicit = meta.get("risk_level") or meta.get("execution_risk")
        if explicit is not None:
            parsed = self._parse_risk_level(explicit)
            if parsed is not None:
                return parsed

        if meta.get("forbidden") is True or meta.get("permission") == "blocked":
            return ExecutionRiskLevel.FORBIDDEN

        text = (action or "").strip()
        if text and _FORBIDDEN_PATTERNS.search(text):
            return ExecutionRiskLevel.FORBIDDEN
        if meta.get("destructive") is True:
            return ExecutionRiskLevel.DESTRUCTIVE

        from_cap = self._risk_from_capability(capability)
        if from_cap is not None:
            return from_cap

        traits = self._side_effect_traits(capability, meta)
        if "forbidden" in traits:
            return ExecutionRiskLevel.FORBIDDEN
        if "destructive" in traits or "delete" in traits:
            return ExecutionRiskLevel.DESTRUCTIVE
        if text and _DESTRUCTIVE_PATTERNS.search(text):
            return ExecutionRiskLevel.DESTRUCTIVE

        if "high_risk" in traits or meta.get("high_risk") is True:
            return ExecutionRiskLevel.HIGH_RISK_WRITE
        if "read_only" in traits and "read_write" not in traits:
            return ExecutionRiskLevel.SAFE_READ
        if "read_write" in traits or "write" in traits:
            # Prefer safer (higher caution) when write is known but severity unclear.
            if meta.get("low_risk") is True:
                return ExecutionRiskLevel.LOW_RISK_WRITE
            return ExecutionRiskLevel.HIGH_RISK_WRITE

        if text and _WRITE_PATTERNS.search(text):
            return ExecutionRiskLevel.LOW_RISK_WRITE
        if text and _READ_PATTERNS.search(text):
            return ExecutionRiskLevel.SAFE_READ

        # Decision risk_score is advisory only when no capability metadata exists.
        risk_score = getattr(decision, "risk_score", None) if decision is not None else None
        if isinstance(risk_score, (int, float)):
            if risk_score >= 0.85:
                return ExecutionRiskLevel.DESTRUCTIVE
            if risk_score >= 0.65:
                return ExecutionRiskLevel.HIGH_RISK_WRITE
            if risk_score >= 0.35:
                return ExecutionRiskLevel.LOW_RISK_WRITE

        # Cognitive next-action strings without tool side effects: safe register.
        if capability is None and not meta:
            return ExecutionRiskLevel.SAFE_READ

        # Insufficient metadata → safer (more cautious) than SAFE_READ.
        return ExecutionRiskLevel.LOW_RISK_WRITE

    def _requires_confirmation(
        self,
        risk: ExecutionRiskLevel,
        capability: Any | None,
        meta: Mapping[str, Any],
        execution_mode: str,
    ) -> bool:
        # Non-LIVE modes skip confirmation (same rule as ConfirmationGate).
        if execution_mode and execution_mode != "live":
            return False
        if meta.get("dry_run") is True:
            return False

        if risk == ExecutionRiskLevel.SAFE_READ:
            return False
        if risk in (
            ExecutionRiskLevel.HIGH_RISK_WRITE,
            ExecutionRiskLevel.DESTRUCTIVE,
        ):
            return True
        if risk == ExecutionRiskLevel.LOW_RISK_WRITE:
            action_type = self._resolve_action_type(capability, meta)
            if action_type is not None:
                return self._policy.requires_confirmation(action_type)
            # Default write confirmation setting when action type unknown.
            return bool(self._policy.require_confirmation_writes)
        return True

    def _resolve_action_type(
        self,
        capability: Any | None,
        meta: Mapping[str, Any],
    ) -> AutonomousActionType | None:
        raw = meta.get("action_type")
        if raw is None and capability is not None:
            raw = getattr(capability, "action_type", None)
        if raw is None:
            return None
        try:
            return AutonomousActionType(str(raw))
        except ValueError:
            return None

    def _risk_from_capability(self, capability: Any | None) -> ExecutionRiskLevel | None:
        if capability is None:
            return None
        if getattr(capability, "requires_confirmation", None) is True:
            # Explicit confirm flag without CRITICAL → at least high-risk write.
            risk_enum = getattr(capability, "risk_level", None)
            risk_value = getattr(risk_enum, "value", risk_enum)
            if str(risk_value).lower() in {"critical"}:
                return ExecutionRiskLevel.DESTRUCTIVE
            return ExecutionRiskLevel.HIGH_RISK_WRITE

        risk_enum = getattr(capability, "risk_level", None)
        if risk_enum is None:
            return None
        risk_value = str(getattr(risk_enum, "value", risk_enum)).lower()
        traits = set(self._capability_traits(capability))
        if risk_value == "critical":
            return ExecutionRiskLevel.DESTRUCTIVE
        if risk_value == "high":
            return ExecutionRiskLevel.HIGH_RISK_WRITE
        if risk_value == "medium":
            return ExecutionRiskLevel.LOW_RISK_WRITE
        if risk_value in {"safe", "low"}:
            if "read_write" in traits or "write" in traits:
                return ExecutionRiskLevel.LOW_RISK_WRITE
            return ExecutionRiskLevel.SAFE_READ
        return None

    def _side_effect_traits(
        self,
        capability: Any | None,
        meta: Mapping[str, Any],
    ) -> set[str]:
        traits: set[str] = set()
        raw_traits = meta.get("execution_traits") or meta.get("side_effects")
        if isinstance(raw_traits, (list, tuple, set, frozenset)):
            traits.update(str(t).lower() for t in raw_traits)
        elif isinstance(raw_traits, str):
            traits.add(raw_traits.lower())
        traits.update(self._capability_traits(capability))
        return traits

    @staticmethod
    def _capability_traits(capability: Any | None) -> set[str]:
        if capability is None:
            return set()
        traits: set[str] = set()
        tags = getattr(capability, "tags", None) or ()
        for tag in tags:
            traits.add(str(tag).lower())
        caps = getattr(capability, "capabilities", None) or ()
        for cap in caps:
            traits.add(str(cap).lower())
        name = str(getattr(capability, "name", "") or "").lower()
        for verb in ("write", "delete", "create", "edit", "patch", "execute", "run", "read"):
            if verb in name:
                traits.add(verb)
                if verb != "read":
                    traits.add("read_write")
                else:
                    traits.add("read_only")
        return traits

    @staticmethod
    def _parse_risk_level(value: Any) -> ExecutionRiskLevel | None:
        if isinstance(value, ExecutionRiskLevel):
            return value
        text = str(value or "").strip().upper()
        if not text:
            return None
        try:
            return ExecutionRiskLevel(text)
        except ValueError:
            aliases = {
                "SAFE": ExecutionRiskLevel.SAFE_READ,
                "READ": ExecutionRiskLevel.SAFE_READ,
                "LOW": ExecutionRiskLevel.LOW_RISK_WRITE,
                "MEDIUM": ExecutionRiskLevel.LOW_RISK_WRITE,
                "HIGH": ExecutionRiskLevel.HIGH_RISK_WRITE,
                "CRITICAL": ExecutionRiskLevel.DESTRUCTIVE,
            }
            return aliases.get(text)

    @staticmethod
    def _is_reversible(
        risk: ExecutionRiskLevel,
        capability: Any | None,
        meta: Mapping[str, Any],
    ) -> bool:
        if "reversible" in meta:
            return bool(meta["reversible"])
        if risk in (ExecutionRiskLevel.DESTRUCTIVE, ExecutionRiskLevel.FORBIDDEN):
            return False
        if capability is not None and getattr(capability, "idempotent", False):
            return True
        return risk == ExecutionRiskLevel.SAFE_READ

    @staticmethod
    def _expected_impact(
        action: str | None,
        risk: ExecutionRiskLevel,
        meta: Mapping[str, Any],
    ) -> str:
        explicit = meta.get("expected_impact")
        if isinstance(explicit, str) and explicit.strip():
            return redact_sensitive_text(explicit.strip())
        label = (action or "action").strip() or "action"
        label = redact_sensitive_text(label)
        if risk == ExecutionRiskLevel.SAFE_READ:
            return f"Read-only: inspect '{label}' without modifying external state"
        if risk == ExecutionRiskLevel.LOW_RISK_WRITE:
            return f"Low-risk write: may update state for '{label}'"
        if risk == ExecutionRiskLevel.HIGH_RISK_WRITE:
            return f"High-risk write: may modify external systems for '{label}'"
        if risk == ExecutionRiskLevel.DESTRUCTIVE:
            return f"Destructive: may permanently remove or overwrite data for '{label}'"
        return f"Forbidden: '{label}' will not run"

    @staticmethod
    def _confirmation_reason(risk: ExecutionRiskLevel) -> str:
        if risk == ExecutionRiskLevel.DESTRUCTIVE:
            return "Destructive action requires explicit confirmation"
        if risk == ExecutionRiskLevel.HIGH_RISK_WRITE:
            return "High-risk write requires explicit confirmation"
        if risk == ExecutionRiskLevel.LOW_RISK_WRITE:
            return "Write confirmation required by autonomy settings"
        return "Confirmation required"


def is_sensitive_key(key: str) -> bool:
    """True when a metadata key looks like a secret field."""
    normalized = str(key or "").strip().lower().replace("-", "_")
    if not normalized:
        return False
    if normalized in _SENSITIVE_KEY_FRAGMENTS:
        return True
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def sanitize_public_metadata(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy metadata for public state/logs — drop sensitive keys and nested secrets."""
    if not data:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if is_sensitive_key(str(key)):
            continue
        if isinstance(value, Mapping):
            nested = sanitize_public_metadata(value)
            if nested:
                cleaned[str(key)] = nested
            continue
        if isinstance(value, str) and _looks_like_secret_value(value):
            continue
        cleaned[str(key)] = value
    return cleaned


def redact_sensitive_text(text: str) -> str:
    """Best-effort redaction of key=value secret patterns in free text."""
    if not text:
        return text
    redacted = text
    for fragment in _SENSITIVE_KEY_FRAGMENTS:
        redacted = re.sub(
            rf"({fragment}\s*[=:]\s*)([^\s,;]+)",
            r"\1[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )
    return redacted


def _looks_like_secret_value(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) >= 32 and re.fullmatch(r"[A-Za-z0-9_\-./+=]+", stripped):
        return True
    return False

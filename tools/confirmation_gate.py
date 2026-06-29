# =====================================
# Titan Tool Confirmation Gate
# =====================================

"""User confirmation gating for risky tool invocations (Phase 10A — P10A-020)."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field

from brain.autonomy_policy import AutonomousActionType, AutonomyPolicy
from config.settings import TITAN_TOOL_CONFIRMATION_TTL_SECONDS
from tools.tool_capability import ToolCapability
from tools.tool_enums import ExecutionMode, RiskLevel
from tools.tool_run_models import ConfirmationRequest, ToolExecutionContext


@dataclass(frozen=True)
class ConfirmationResult:
    """Outcome of confirmation evaluation before execution."""

    satisfied: bool
    request: ConfirmationRequest | None = None
    reason: str = ""


@dataclass
class PendingConfirmation:
    """Resolved pending approval record for Brain re-invocation."""

    token: str
    tool_name: str
    params: dict
    params_digest: str
    session_id: str
    turn_id: str
    user: str


@dataclass
class _PendingConfirmation:
    """In-memory pending approval record."""

    token: str
    tool_name: str
    params: dict
    params_digest: str
    session_id: str
    turn_id: str
    user: str
    created_at: float


@dataclass
class ConfirmationGate:
    """Evaluate and validate user confirmation for capability-gated tools."""

    autonomy_policy: AutonomyPolicy | None = None
    token_ttl_seconds: float = TITAN_TOOL_CONFIRMATION_TTL_SECONDS
    _pending: dict[str, _PendingConfirmation] = field(default_factory=dict)

    def evaluate(
        self,
        tool_name: str,
        capability: ToolCapability,
        context: ToolExecutionContext,
        params: dict | None = None,
    ) -> ConfirmationResult:
        """Return whether confirmation is satisfied or issue a pending request."""
        params_dict = dict(params or {})
        if not self.requires_confirmation(capability, context):
            return ConfirmationResult(satisfied=True)

        digest = self.params_digest(params_dict)
        if context.confirmed:
            if self.validate_confirmation(context, tool_name, params_dict):
                return ConfirmationResult(satisfied=True)
            return ConfirmationResult(
                satisfied=False,
                reason="Token de confirmation invalide ou expiré.",
            )

        request = self.issue_request(tool_name, capability, context, params_dict, digest)
        return ConfirmationResult(
            satisfied=False,
            request=request,
            reason=request.description,
        )

    def requires_confirmation(
        self,
        capability: ToolCapability,
        context: ToolExecutionContext,
    ) -> bool:
        """Decide if explicit approval is required (capability-first, provider-agnostic)."""
        if context.dry_run:
            return False

        if context.execution_mode != ExecutionMode.LIVE:
            return False

        if capability.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return True

        if capability.requires_confirmation is True:
            return True

        if capability.requires_confirmation is False:
            return False

        policy = self.autonomy_policy or AutonomyPolicy.from_settings()
        action_type = self._resolve_action_type(capability)
        if action_type is None:
            return capability.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

        return policy.requires_confirmation(action_type)

    def issue_request(
        self,
        tool_name: str,
        capability: ToolCapability,
        context: ToolExecutionContext,
        params: dict,
        params_digest: str | None = None,
    ) -> ConfirmationRequest:
        """Create a confirmation token and pending record for re-invocation."""
        digest = params_digest or self.params_digest(params)
        token = str(uuid.uuid4())
        self._pending[token] = _PendingConfirmation(
            token=token,
            tool_name=tool_name,
            params=dict(params),
            params_digest=digest,
            session_id=context.session_id,
            turn_id=context.turn_id,
            user=context.user,
            created_at=time.monotonic(),
        )
        description = self._build_description(tool_name, capability, params)
        return ConfirmationRequest(
            token=token,
            tool_name=tool_name,
            description=description,
            params_digest=digest,
        )

    def validate_confirmation(
        self,
        context: ToolExecutionContext,
        tool_name: str,
        params: dict | None = None,
    ) -> bool:
        """Verify confirmed flag, token, params digest, and TTL."""
        if not context.confirmed or not context.confirmation_token:
            return False

        pending = self._pending.get(context.confirmation_token)
        if pending is None:
            return False

        if pending.tool_name != tool_name:
            return False

        if pending.session_id != context.session_id:
            return False

        if pending.user != context.user:
            return False

        digest = self.params_digest(dict(params or {}))
        if pending.params_digest != digest:
            return False

        age = time.monotonic() - pending.created_at
        if age > self.token_ttl_seconds:
            self._pending.pop(context.confirmation_token, None)
            return False

        self._pending.pop(context.confirmation_token, None)
        return True

    def lookup_pending(self, token: str) -> PendingConfirmation | None:
        """Return pending confirmation metadata without consuming the token."""
        pending = self._pending.get(token)
        if pending is None:
            return None

        age = time.monotonic() - pending.created_at
        if age > self.token_ttl_seconds:
            self._pending.pop(token, None)
            return None

        return PendingConfirmation(
            token=pending.token,
            tool_name=pending.tool_name,
            params=dict(pending.params),
            params_digest=pending.params_digest,
            session_id=pending.session_id,
            turn_id=pending.turn_id,
            user=pending.user,
        )

    def purge_expired(self) -> int:
        """Remove expired pending confirmations; return count removed."""
        now = time.monotonic()
        expired = [
            token
            for token, pending in self._pending.items()
            if now - pending.created_at > self.token_ttl_seconds
        ]
        for token in expired:
            del self._pending[token]
        return len(expired)

    @staticmethod
    def params_digest(params: dict) -> str:
        """Stable hash of invocation parameters for token binding."""
        payload = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _resolve_action_type(capability: ToolCapability) -> AutonomousActionType | None:
        if capability.action_type is None:
            return None
        try:
            return AutonomousActionType(capability.action_type)
        except ValueError:
            return None

    @staticmethod
    def _build_description(
        tool_name: str,
        capability: ToolCapability,
        params: dict,
    ) -> str:
        risk = capability.risk_level.value
        mode = capability.execution_mode.value
        param_summary = ", ".join(f"{key}={value!r}" for key, value in params.items())
        if param_summary:
            return (
                f"Confirmer l'exécution de {tool_name!r} "
                f"(risque {risk}, mode {mode}) avec {param_summary} ?"
            )
        return (
            f"Confirmer l'exécution de {tool_name!r} "
            f"(risque {risk}, mode {mode}) ?"
        )

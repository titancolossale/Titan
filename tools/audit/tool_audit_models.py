# =====================================
# Titan Tool Audit Models
# =====================================

"""Structured audit event types for tool executions (Phase 10A — P10A-022)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


AUDIT_SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compute_params_digest(params: dict[str, Any] | None) -> str:
    """Return a truncated SHA256 digest of params — never log raw secrets."""
    payload = json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ToolAuditEvent:
    """Append-only audit record for a tool lifecycle transition."""

    timestamp: str
    event_type: str
    run_id: str
    tool_name: str
    caller: str = ""
    user: str = ""
    session_id: str = ""
    turn_id: str = ""
    risk_level: str = ""
    success: bool | None = None
    duration_ms: float | None = None
    error_code: str = ""
    params_digest: str = ""
    execution_mode: str = ""
    health_state: str = ""
    provider_version: str = ""
    quota_remaining: int | None = None
    dependencies_checked: bool = False
    message: str = ""
    schema_version: int = AUDIT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONL persistence."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolAuditEvent:
        """Restore an audit event from persisted JSON."""
        return cls(
            timestamp=str(data.get("timestamp", "")),
            event_type=str(data.get("event_type", "")),
            run_id=str(data.get("run_id", "")),
            tool_name=str(data.get("tool_name", "")),
            caller=str(data.get("caller", "")),
            user=str(data.get("user", "")),
            session_id=str(data.get("session_id", "")),
            turn_id=str(data.get("turn_id", "")),
            risk_level=str(data.get("risk_level", "")),
            success=data.get("success"),
            duration_ms=data.get("duration_ms"),
            error_code=str(data.get("error_code", "")),
            params_digest=str(data.get("params_digest", "")),
            execution_mode=str(data.get("execution_mode", "")),
            health_state=str(data.get("health_state", "")),
            provider_version=str(data.get("provider_version", "")),
            quota_remaining=data.get("quota_remaining"),
            dependencies_checked=bool(data.get("dependencies_checked", False)),
            message=str(data.get("message", "")),
            schema_version=int(data.get("schema_version", AUDIT_SCHEMA_VERSION)),
        )

    @classmethod
    def build(
        cls,
        *,
        event_type: str,
        run_id: str,
        tool_name: str,
        caller: str = "",
        user: str = "",
        session_id: str = "",
        turn_id: str = "",
        risk_level: str = "",
        success: bool | None = None,
        duration_ms: float | None = None,
        error_code: str = "",
        params_digest: str = "",
        execution_mode: str = "",
        health_state: str = "",
        provider_version: str = "",
        quota_remaining: int | None = None,
        dependencies_checked: bool = False,
        message: str = "",
    ) -> ToolAuditEvent:
        """Factory with UTC timestamp."""
        return cls(
            timestamp=_utc_now_iso(),
            event_type=event_type,
            run_id=run_id,
            tool_name=tool_name,
            caller=caller,
            user=user,
            session_id=session_id,
            turn_id=turn_id,
            risk_level=risk_level,
            success=success,
            duration_ms=duration_ms,
            error_code=error_code,
            params_digest=params_digest,
            execution_mode=execution_mode,
            health_state=health_state,
            provider_version=provider_version,
            quota_remaining=quota_remaining,
            dependencies_checked=dependencies_checked,
            message=message,
        )

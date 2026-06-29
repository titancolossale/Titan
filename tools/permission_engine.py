# =====================================
# Titan Tool Permission Engine
# =====================================

"""Caller and execution-mode permission checks (Phase 10A — P10A-016)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.tool_capability import ToolCapability
from tools.tool_enums import ExecutionMode
from tools.tool_policy import ToolPolicy
from tools.tool_run_models import ToolExecutionContext


@dataclass(frozen=True)
class PermissionResult:
    """Outcome of a permission evaluation."""

    allowed: bool
    reason: str = ""


@dataclass
class PermissionEngine:
    """Evaluate whether a caller may invoke a tool in the requested mode."""

    policy: ToolPolicy

    def evaluate(
        self,
        tool_name: str,
        capability: ToolCapability,
        context: ToolExecutionContext,
    ) -> PermissionResult:
        """Check caller allowlist and execution mode compatibility."""
        if not self.policy.is_allowed(context.caller, tool_name):
            return PermissionResult(
                allowed=False,
                reason=self.policy.deny_message(context.caller, tool_name),
            )

        mode = context.execution_mode
        if mode not in capability.supported_execution_modes:
            supported = ", ".join(sorted(m.value for m in capability.supported_execution_modes))
            return PermissionResult(
                allowed=False,
                reason=(
                    f"Mode d'exécution {mode.value!r} non supporté pour {tool_name!r}. "
                    f"Modes autorisés : {supported}."
                ),
            )

        return PermissionResult(allowed=True)

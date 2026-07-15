# =====================================
# Titan Tool Policy
# =====================================

"""Agent-level tool allowlists (Phase 6 — P6-030)."""

from __future__ import annotations

# Brain orchestrator key — full access to registered tools.
BRAIN_CALLER = "brain"

# Per-agent allowlists; extend when new agents or tools land.
AGENT_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    BRAIN_CALLER: frozenset(
        {
            "time",
            "file_read",
            "file_write",
            "python_exec",
            "web_search",
            "calendar",
            "email",
            "trading",
            "github",
            "obsidian",
            "browser",
        }
    ),
    "coding": frozenset(
        {"time", "file_read", "file_write", "python_exec", "github", "obsidian", "browser"}
    ),
    "research": frozenset({"time", "web_search", "github", "obsidian", "browser", "email", "trading"}),
    "planning": frozenset({"time"}),
    "reasoning": frozenset({"time"}),
    "memory": frozenset({"time"}),
    "general": frozenset({"time", "file_read"}),
}


class ToolPolicy:
    """Enforce which callers may invoke which tools."""

    def __init__(self, allowlist: dict[str, frozenset[str]] | None = None) -> None:
        self._allowlist = dict(allowlist or AGENT_TOOL_ALLOWLIST)

    def is_allowed(self, caller: str, tool_name: str) -> bool:
        """Return True if *caller* may invoke *tool_name*."""
        allowed = self._allowlist.get(caller)
        if allowed is None:
            return False
        return tool_name in allowed

    def allowed_tools(self, caller: str) -> frozenset[str]:
        """Return the tool set permitted for *caller*."""
        return self._allowlist.get(caller, frozenset())

    def deny_message(self, caller: str, tool_name: str) -> str:
        """Human-readable denial reason for logs and ToolResult errors."""
        allowed = sorted(self.allowed_tools(caller))
        if not allowed:
            return f"L'appelant {caller!r} n'a accès à aucun outil."
        return (
            f"Politique outils : {caller!r} ne peut pas appeler {tool_name!r}. "
            f"Autorisés : {', '.join(allowed)}."
        )

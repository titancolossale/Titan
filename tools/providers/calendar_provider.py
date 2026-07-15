# =====================================
# Titan Calendar Provider (Stub)
# =====================================

"""Calendar provider stub until external integration (P10A-026)."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field

from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.providers.base_provider import BaseProvider
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_health_resolver import resolve_provider_health
from tools.tool_enums import ExecutionMode, ToolHealthState


@dataclass
class CalendarResponse:
    """Structured calendar action response."""

    action: str
    success: bool = False
    data: str = ""
    error: str = ""
    provider: str = "calendar"


_STUB_VERSION = ProviderVersionInfo(
    provider_id="calendar",
    version="0.1.0",
    min_runtime_version="0.10.0",
    api_version=None,
    compatible_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
)


class CalendarProvider(BaseProvider):
    """Contract for calendar backends."""

    @property
    def provider_id(self) -> str:
        return "calendar"

    def capabilities(self) -> frozenset[str]:
        return frozenset({"calendar"})

    def supported_actions(self) -> frozenset[str]:
        return frozenset({"list", "create", "update", "delete"})

    @abstractmethod
    def execute(self, action: str = "list", **params: object) -> CalendarResponse:
        """Run a calendar action and return structured results."""


class StubCalendarProvider(CalendarProvider):
    """Placeholder calendar provider — no external API."""

    def __init__(self, *, context: ProviderContext | None = None) -> None:
        self.context = context

    @property
    def version_info(self) -> ProviderVersionInfo:
        return _STUB_VERSION

    def health_check(self) -> ProviderHealth:
        default = ProviderHealth(
            state=ToolHealthState.DEGRADED,
            message="Calendrier stub — intégration externe non disponible.",
        )
        return resolve_provider_health(
            self.provider_id,
            context=self.context,
            default_health=default,
        )

    def execute(self, action: str = "list", **params: object) -> CalendarResponse:
        _ = params
        return CalendarResponse(
            action=action,
            success=False,
            error=f"calendar non disponible (stub). Action : {action!r}",
            provider=self.provider_id,
        )

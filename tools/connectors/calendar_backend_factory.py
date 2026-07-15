# =====================================
# Titan Calendar Backend Factory
# =====================================

"""Select calendar backend by configuration without leaking Google into callers."""

from __future__ import annotations

from config.settings import (
    TITAN_CALENDAR_PROVIDER,
    TITAN_GOOGLE_CALENDAR_ENABLED,
)
from tools.connectors.calendar_backend import InMemoryCalendarBackend
from tools.connectors.calendar_backend_protocol import CalendarBackend


def create_calendar_backend(
    *,
    provider: str | None = None,
    google_enabled: bool | None = None,
) -> CalendarBackend:
    """Return the configured calendar backend implementation."""
    resolved_provider = (provider or TITAN_CALENDAR_PROVIDER).strip().lower()
    use_google = (
        TITAN_GOOGLE_CALENDAR_ENABLED if google_enabled is None else google_enabled
    )

    if resolved_provider == "google":
        if not use_google:
            raise ValueError(
                "TITAN_CALENDAR_PROVIDER=google mais TITAN_GOOGLE_CALENDAR_ENABLED=false. "
                "Activez Google Calendar dans .env."
            )
        from tools.connectors.google_calendar_provider import GoogleCalendarProvider

        return GoogleCalendarProvider.from_config()

    if resolved_provider not in {"mock", "memory", "inmemory"}:
        raise ValueError(
            f"Provider calendrier inconnu : {resolved_provider!r}. "
            "Valeurs supportées : mock, google."
        )

    backend = InMemoryCalendarBackend()
    backend.provider_name = "mock"
    return backend


def backend_label(backend: CalendarBackend) -> str:
    """Return a short provider label for connector warnings and health checks."""
    return getattr(backend, "provider_name", "mock")

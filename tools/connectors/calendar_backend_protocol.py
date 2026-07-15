# =====================================
# Titan Calendar Backend Protocol
# =====================================

"""Provider-independent calendar backend contract (Phase 14.2)."""

from __future__ import annotations

from typing import Protocol

from tools.connectors.calendar_backend import StoredCalendar, StoredEvent


class CalendarBackend(Protocol):
    """Backend interface consumed by CalendarConnector — no Google imports here."""

    provider_name: str

    def list_calendars(self) -> list[StoredCalendar]: ...

    def list_events(
        self,
        *,
        calendar_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[StoredEvent]: ...

    def read_event(self, event_id: str) -> StoredEvent | None: ...

    def search_events(
        self,
        query: str,
        *,
        calendar_id: str | None = None,
    ) -> list[StoredEvent]: ...

    def create_event(
        self,
        *,
        calendar_id: str,
        title: str,
        description: str = "",
        start_time: str,
        end_time: str,
        attendees: list[str] | None = None,
        location: str = "",
    ) -> StoredEvent: ...

    def update_event(
        self,
        event_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        attendees: list[str] | None = None,
        location: str | None = None,
    ) -> StoredEvent: ...

    def delete_event(self, event_id: str) -> bool: ...

    def detect_conflicts(
        self,
        *,
        calendar_id: str | None,
        start_time: str,
        end_time: str,
        exclude_event_id: str | None = None,
    ) -> list[StoredEvent]: ...

    def find_free_time(
        self,
        *,
        calendar_id: str | None,
        start_time: str,
        end_time: str,
        duration_minutes: int,
    ) -> list[tuple[str, str]]: ...

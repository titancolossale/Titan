# =====================================
# Titan Calendar Backend
# =====================================

"""In-memory calendar backend for provider-independent Calendar connector (Phase 14.1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta


def _parse_dt(value: str) -> datetime:
    """Parse ISO-like datetime strings used by calendar backends."""
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"Horodatage invalide : {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _format_dt(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


@dataclass
class StoredCalendar:
    """Internal calendar record."""

    calendar_id: str
    name: str


@dataclass
class StoredEvent:
    """Internal event record."""

    calendar_id: str
    event_id: str
    title: str
    description: str = ""
    start_time: str = ""
    end_time: str = ""
    attendees: list[str] = field(default_factory=list)
    location: str = ""


class InMemoryCalendarBackend:
    """Mock calendar storage — no external provider integration (Phase 14.1)."""

    provider_name = "mock"

    def __init__(self) -> None:
        self._calendars: dict[str, StoredCalendar] = {}
        self._events: dict[str, StoredEvent] = {}
        self.seed_defaults()

    def seed_defaults(self) -> None:
        """Populate default calendars and sample events for development/tests."""
        self._calendars.clear()
        self._events.clear()
        self._calendars["primary"] = StoredCalendar("primary", "Calendrier principal")
        self._calendars["work"] = StoredCalendar("work", "Travail")
        self._add_event(
            calendar_id="primary",
            title="Stand-up équipe",
            description="Point quotidien",
            start_time="2026-07-04T09:00:00",
            end_time="2026-07-04T09:30:00",
            attendees=["nolan@example.com"],
            location="Visio",
        )
        self._add_event(
            calendar_id="work",
            title="Revue projet Titan",
            description="Phase 14 planning",
            start_time="2026-07-04T14:00:00",
            end_time="2026-07-04T15:00:00",
            attendees=["nolan@example.com", "ibrahim@example.com"],
            location="Bureau",
        )
        self._add_event(
            calendar_id="primary",
            title="Séance gym",
            description="Entraînement cardio",
            start_time="2026-07-05T07:00:00",
            end_time="2026-07-05T08:00:00",
            attendees=["nolan@example.com"],
            location="Gym",
        )

    def list_calendars(self) -> list[StoredCalendar]:
        return list(self._calendars.values())

    def list_events(
        self,
        *,
        calendar_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[StoredEvent]:
        events = [
            event
            for event in self._events.values()
            if calendar_id is None or event.calendar_id == calendar_id
        ]
        if start_time:
            start = _parse_dt(start_time)
            events = [
                event
                for event in events
                if _parse_dt(event.end_time) >= start
            ]
        if end_time:
            end = _parse_dt(end_time)
            events = [
                event
                for event in events
                if _parse_dt(event.start_time) <= end
            ]
        return sorted(events, key=lambda item: item.start_time)

    def read_event(self, event_id: str) -> StoredEvent | None:
        return self._events.get(event_id)

    def search_events(
        self,
        query: str,
        *,
        calendar_id: str | None = None,
    ) -> list[StoredEvent]:
        lowered = query.lower().strip()
        if not lowered:
            return []
        results: list[StoredEvent] = []
        for event in self.list_events(calendar_id=calendar_id):
            haystack = " ".join(
                [
                    event.title,
                    event.description,
                    event.location,
                    " ".join(event.attendees),
                ],
            ).lower()
            if lowered in haystack:
                results.append(event)
        return results

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
    ) -> StoredEvent:
        if calendar_id not in self._calendars:
            raise ValueError(f"Calendrier introuvable : {calendar_id!r}")
        if not title.strip():
            raise ValueError("Le titre de l'événement est requis.")
        start = _parse_dt(start_time)
        end = _parse_dt(end_time)
        if end <= start:
            raise ValueError("La fin doit être postérieure au début.")
        return self._add_event(
            calendar_id=calendar_id,
            title=title.strip(),
            description=description.strip(),
            start_time=_format_dt(start),
            end_time=_format_dt(end),
            attendees=attendees or [],
            location=location.strip(),
        )

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
    ) -> StoredEvent:
        event = self._events.get(event_id)
        if event is None:
            raise ValueError(f"Événement introuvable : {event_id!r}")
        if title is not None:
            event.title = title.strip()
        if description is not None:
            event.description = description.strip()
        if start_time is not None:
            event.start_time = _format_dt(_parse_dt(start_time))
        if end_time is not None:
            event.end_time = _format_dt(_parse_dt(end_time))
        if attendees is not None:
            event.attendees = list(attendees)
        if location is not None:
            event.location = location.strip()
        start = _parse_dt(event.start_time)
        end = _parse_dt(event.end_time)
        if end <= start:
            raise ValueError("La fin doit être postérieure au début.")
        return event

    def delete_event(self, event_id: str) -> bool:
        if event_id not in self._events:
            return False
        del self._events[event_id]
        return True

    def detect_conflicts(
        self,
        *,
        calendar_id: str | None,
        start_time: str,
        end_time: str,
        exclude_event_id: str | None = None,
    ) -> list[StoredEvent]:
        start = _parse_dt(start_time)
        end = _parse_dt(end_time)
        conflicts: list[StoredEvent] = []
        for event in self.list_events(calendar_id=calendar_id):
            if exclude_event_id and event.event_id == exclude_event_id:
                continue
            event_start = _parse_dt(event.start_time)
            event_end = _parse_dt(event.end_time)
            if event_start < end and start < event_end:
                conflicts.append(event)
        return conflicts

    def find_free_time(
        self,
        *,
        calendar_id: str | None,
        start_time: str,
        end_time: str,
        duration_minutes: int,
    ) -> list[tuple[str, str]]:
        if duration_minutes <= 0:
            raise ValueError("La durée doit être positive.")
        window_start = _parse_dt(start_time)
        window_end = _parse_dt(end_time)
        if window_end <= window_start:
            raise ValueError("La fenêtre de recherche est invalide.")
        duration = timedelta(minutes=duration_minutes)
        busy = self.list_events(
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
        )
        cursor = window_start
        free_slots: list[tuple[str, str]] = []
        for event in busy:
            event_start = _parse_dt(event.start_time)
            event_end = _parse_dt(event.end_time)
            if event_start > cursor:
                gap_end = min(event_start, window_end)
                self._append_free_slots(
                    free_slots,
                    cursor,
                    gap_end,
                    duration,
                )
            cursor = max(cursor, event_end)
        if cursor < window_end:
            self._append_free_slots(free_slots, cursor, window_end, duration)
        return free_slots

    def _add_event(
        self,
        *,
        calendar_id: str,
        title: str,
        description: str = "",
        start_time: str,
        end_time: str,
        attendees: list[str] | None = None,
        location: str = "",
    ) -> StoredEvent:
        event_id = str(uuid.uuid4())
        event = StoredEvent(
            calendar_id=calendar_id,
            event_id=event_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            attendees=list(attendees or []),
            location=location,
        )
        self._events[event_id] = event
        return event

    @staticmethod
    def _append_free_slots(
        slots: list[tuple[str, str]],
        start: datetime,
        end: datetime,
        duration: timedelta,
    ) -> None:
        cursor = start
        while cursor + duration <= end:
            slot_end = cursor + duration
            slots.append((_format_dt(cursor), _format_dt(slot_end)))
            cursor = slot_end

# =====================================
# Titan Google Calendar Provider
# =====================================

"""Google Calendar API backend for CalendarConnector (Phase 14.2).

CalendarConnector and upstream layers depend only on the backend interface —
no Google imports outside this module and google_oauth.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from tools.connectors.calendar_backend import (
    StoredCalendar,
    StoredEvent,
    _format_dt,
    _parse_dt,
)
from tools.connectors.google_oauth import GOOGLE_CALENDAR_SCOPES, load_credentials


class GoogleCalendarProvider:
    """Google Calendar backend implementing the CalendarConnector backend contract."""

    provider_name = "google"

    def __init__(self, service: Any) -> None:
        self._service = service

    @classmethod
    def from_credentials(cls, credentials: Any) -> GoogleCalendarProvider:
        """Build a provider from authorized Google credentials."""
        from googleapiclient.discovery import build

        service = build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
        return cls(service)

    @classmethod
    def from_config(cls) -> GoogleCalendarProvider:
        """Build a provider using configured token and client secret paths."""
        credentials = load_credentials(scopes=GOOGLE_CALENDAR_SCOPES)
        if credentials is None:
            raise ValueError(
                "Token Google Calendar absent ou expiré. "
                "Lancez : python main.py calendar-auth"
            )
        return cls.from_credentials(credentials)

    def list_calendars(self) -> list[StoredCalendar]:
        response = self._service.calendarList().list().execute()
        calendars: list[StoredCalendar] = []
        for item in response.get("items", []):
            calendars.append(
                StoredCalendar(
                    calendar_id=item.get("id", ""),
                    name=item.get("summary", item.get("id", "")),
                ),
            )
        return calendars

    def list_events(
        self,
        *,
        calendar_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[StoredEvent]:
        target_calendars = self._resolve_calendar_ids(calendar_id)
        events: list[StoredEvent] = []
        for cal_id in target_calendars:
            request_kwargs: dict[str, Any] = {
                "calendarId": cal_id,
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": 250,
            }
            if start_time:
                request_kwargs["timeMin"] = _to_rfc3339(start_time)
            if end_time:
                request_kwargs["timeMax"] = _to_rfc3339(end_time)
            page_token: str | None = None
            while True:
                if page_token:
                    request_kwargs["pageToken"] = page_token
                response = self._service.events().list(**request_kwargs).execute()
                for item in response.get("items", []):
                    events.append(_google_event_to_stored(item, cal_id))
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        return sorted(events, key=lambda item: item.start_time)

    def read_event(self, event_id: str) -> StoredEvent | None:
        from googleapiclient.errors import HttpError

        for calendar in self.list_calendars():
            try:
                item = (
                    self._service.events()
                    .get(calendarId=calendar.calendar_id, eventId=event_id)
                    .execute()
                )
            except HttpError as exc:
                if exc.resp.status == 404:
                    continue
                raise
            return _google_event_to_stored(item, calendar.calendar_id)
        return None

    def search_events(
        self,
        query: str,
        *,
        calendar_id: str | None = None,
    ) -> list[StoredEvent]:
        lowered = query.lower().strip()
        if not lowered:
            return []
        target_calendars = self._resolve_calendar_ids(calendar_id)
        events: list[StoredEvent] = []
        for cal_id in target_calendars:
            response = (
                self._service.events()
                .list(
                    calendarId=cal_id,
                    q=query,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=50,
                )
                .execute()
            )
            for item in response.get("items", []):
                events.append(_google_event_to_stored(item, cal_id))
        return events

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
        if not title.strip():
            raise ValueError("Le titre de l'événement est requis.")
        start = _parse_dt(start_time)
        end = _parse_dt(end_time)
        if end <= start:
            raise ValueError("La fin doit être postérieure au début.")
        resolved_calendar = calendar_id or "primary"
        body: dict[str, Any] = {
            "summary": title.strip(),
            "description": description.strip(),
            "location": location.strip(),
            "start": _to_google_datetime_field(start_time),
            "end": _to_google_datetime_field(end_time),
        }
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees if email.strip()]
        item = (
            self._service.events()
            .insert(calendarId=resolved_calendar, body=body)
            .execute()
        )
        return _google_event_to_stored(item, resolved_calendar)

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
        existing = self.read_event(event_id)
        if existing is None:
            raise ValueError(f"Événement introuvable : {event_id!r}")

        body: dict[str, Any] = {}
        if title is not None:
            body["summary"] = title.strip()
        if description is not None:
            body["description"] = description.strip()
        if location is not None:
            body["location"] = location.strip()
        if start_time is not None:
            body["start"] = _to_google_datetime_field(start_time)
        if end_time is not None:
            body["end"] = _to_google_datetime_field(end_time)
        if attendees is not None:
            body["attendees"] = [{"email": email} for email in attendees if email.strip()]

        item = (
            self._service.events()
            .patch(
                calendarId=existing.calendar_id,
                eventId=event_id,
                body=body,
            )
            .execute()
        )
        updated = _google_event_to_stored(item, existing.calendar_id)
        start = _parse_dt(updated.start_time)
        end = _parse_dt(updated.end_time)
        if end <= start:
            raise ValueError("La fin doit être postérieure au début.")
        return updated

    def delete_event(self, event_id: str) -> bool:
        existing = self.read_event(event_id)
        if existing is None:
            return False
        self._service.events().delete(
            calendarId=existing.calendar_id,
            eventId=event_id,
        ).execute()
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
        for event in self.list_events(
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
        ):
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
                _append_free_slots(free_slots, cursor, gap_end, duration)
            cursor = max(cursor, event_end)
        if cursor < window_end:
            _append_free_slots(free_slots, cursor, window_end, duration)
        return free_slots

    def _resolve_calendar_ids(self, calendar_id: str | None) -> list[str]:
        if calendar_id:
            return [calendar_id]
        return [item.calendar_id for item in self.list_calendars()] or ["primary"]


def _google_event_to_stored(item: dict[str, Any], calendar_id: str) -> StoredEvent:
    start = item.get("start", {})
    end = item.get("end", {})
    start_time = start.get("dateTime") or start.get("date", "")
    end_time = end.get("dateTime") or end.get("date", "")
    attendees = [
        attendee.get("email", "")
        for attendee in item.get("attendees", [])
        if attendee.get("email")
    ]
    return StoredEvent(
        calendar_id=calendar_id,
        event_id=item.get("id", ""),
        title=item.get("summary", ""),
        description=item.get("description", "") or "",
        start_time=_normalize_google_datetime(start_time),
        end_time=_normalize_google_datetime(end_time),
        attendees=attendees,
        location=item.get("location", "") or "",
    )


def _normalize_google_datetime(value: str) -> str:
    if not value:
        return ""
    if "T" not in value:
        return value
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return _format_dt(parsed)


def _to_rfc3339(value: str) -> str:
    cleaned = value.strip().replace("Z", "+00:00")
    parsed = _parse_dt(value)
    if "+" in cleaned[10:] or cleaned.endswith("Z"):
        return cleaned if cleaned.endswith("Z") else cleaned
    return parsed.isoformat() + "Z"


def _to_google_datetime_field(value: str) -> dict[str, str]:
    cleaned = value.strip()
    if "T" not in cleaned:
        return {"date": cleaned}
    if cleaned.endswith("Z") or "+" in cleaned[10:] or cleaned.count("-") > 2:
        return {"dateTime": cleaned.replace("Z", "+00:00")}
    return {"dateTime": cleaned, "timeZone": "UTC"}


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

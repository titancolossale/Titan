# =====================================
# Titan Calendar Models
# =====================================

"""Structured calendar results for the Calendar connector (Phase 14.1)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class CalendarEvent:
    """A single calendar event."""

    calendar_id: str
    event_id: str
    title: str
    description: str = ""
    start_time: str = ""
    end_time: str = ""
    attendees: tuple[str, ...] = ()
    location: str = ""
    status: str = "confirmed"


@dataclass(frozen=True)
class CalendarResult:
    """Structured outcome from a Calendar connector operation."""

    calendar_id: str = ""
    event_id: str = ""
    title: str = ""
    description: str = ""
    start_time: str = ""
    end_time: str = ""
    attendees: tuple[str, ...] = ()
    location: str = ""
    status: str = "ok"
    warnings: tuple[str, ...] = ()
    events: tuple[CalendarEvent, ...] = ()
    calendars: tuple[str, ...] = ()
    free_slots: tuple[tuple[str, str], ...] = ()
    conflicts: tuple[CalendarEvent, ...] = ()

    def to_json(self) -> str:
        """Serialize for ToolResult.data and logging."""
        payload = {
            "calendar_id": self.calendar_id,
            "event_id": self.event_id,
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "attendees": list(self.attendees),
            "location": self.location,
            "status": self.status,
            "warnings": list(self.warnings),
            "events": [asdict(event) for event in self.events],
            "calendars": list(self.calendars),
            "free_slots": [
                {"start_time": start, "end_time": end}
                for start, end in self.free_slots
            ],
            "conflicts": [asdict(event) for event in self.conflicts],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def format_summary(self) -> str:
        """Return a concise French summary for tool output."""
        lines = [f"Statut : {self.status}"]
        if self.calendar_id:
            lines.append(f"Calendrier : {self.calendar_id}")
        if self.event_id:
            lines.append(f"Événement : {self.event_id}")
        if self.title:
            lines.append(f"Titre : {self.title}")
        if self.start_time or self.end_time:
            lines.append(f"Période : {self.start_time} → {self.end_time}")
        if self.location:
            lines.append(f"Lieu : {self.location}")
        if self.attendees:
            lines.append(f"Participants : {', '.join(self.attendees)}")
        if self.calendars:
            lines.append(f"Calendriers ({len(self.calendars)}) : {', '.join(self.calendars)}")
        if self.events:
            lines.append(f"Événements trouvés : {len(self.events)}")
        if self.conflicts:
            lines.append(f"Conflits détectés : {len(self.conflicts)}")
        if self.free_slots:
            lines.append(f"Créneaux libres : {len(self.free_slots)}")
        if self.warnings:
            lines.append(f"Avertissements : {', '.join(self.warnings)}")
        if self.description:
            preview = self.description[:200].strip()
            if preview:
                lines.append("")
                lines.append(preview)
        return "\n".join(lines)


@dataclass
class CalendarSessionState:
    """In-memory connector session tracking for mock backend state."""

    started: bool = False
    default_calendar_id: str = "primary"
    warnings: list[str] = field(default_factory=list)

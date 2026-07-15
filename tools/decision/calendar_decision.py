# =====================================
# Titan Calendar Decision Layer
# =====================================

"""Decide when and how Titan uses the Calendar connector (Phase 14.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from tools.connectors.calendar_connector import CalendarConnector

_DATE_PATTERN = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?)\b",
)

_TIME_H_PATTERN = re.compile(
    r"(?:à|a)\s*(\d{1,2})h(?:\s*(\d{2}))?",
    re.IGNORECASE,
)

_RELATIVE_DAY_OFFSETS: dict[str, int] = {
    "demain": 1,
    "tomorrow": 1,
    "aujourd'hui": 0,
    "aujourdhui": 0,
    "today": 0,
}

_CALENDAR_SIGNALS = (
    "calendrier",
    "calendar",
    "agenda",
    "réunion",
    "reunion",
    "rendez-vous",
    "rendez vous",
    "meeting",
    "schedule",
    "planifier",
    "événement",
    "evenement",
    "événements",
    "evenements",
    "créneau",
    "creneau",
    "qu'est-ce que j'ai",
    "quest ce que j ai",
)

_LIST_CALENDARS_KEYWORDS = (
    "liste les calendriers",
    "list calendars",
    "mes calendriers",
    "my calendars",
)

_LIST_EVENTS_KEYWORDS = (
    "liste les événements",
    "liste les evenements",
    "list events",
    "mes événements",
    "mes evenements",
    "mon agenda",
    "my events",
    "qu'est-ce que j'ai",
    "quest ce que j ai",
)

_READ_EVENT_KEYWORDS = (
    "détails de l'événement",
    "details de l evenement",
    "read event",
    "lire l'événement",
    "lire l evenement",
)

_SEARCH_KEYWORDS = (
    "cherche",
    "chercher",
    "recherche",
    "search",
    "trouve",
    "find event",
)

_CREATE_KEYWORDS = (
    "ajoute",
    "ajouter",
    "crée",
    "creer",
    "create event",
    "planifie",
    "planifier",
    "nouvelle réunion",
    "nouvelle reunion",
    "new meeting",
    "schedule meeting",
)

_UPDATE_KEYWORDS = (
    "modifie",
    "modifier",
    "update event",
    "déplace",
    "deplace",
    "reschedule",
)

_DELETE_KEYWORDS = (
    "supprime",
    "supprimer",
    "delete event",
    "annule",
    "annuler",
    "cancel event",
)

_CONFLICT_KEYWORDS = (
    "conflit",
    "conflict",
    "chevauche",
    "overlap",
    "disponible à",
    "disponible a",
)

_FREE_TIME_KEYWORDS = (
    "créneau libre",
    "creneau libre",
    "free time",
    "find availability",
    "disponibilité",
    "disponibilite",
    "when am i free",
)


class CalendarDecision(str, Enum):
    """Outcome of the Calendar decision layer."""

    LIST_CALENDARS = "list_calendars"
    LIST_EVENTS = "list_events"
    READ_EVENT = "read_event"
    SEARCH_EVENTS = "search_events"
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    DETECT_CONFLICTS = "detect_conflicts"
    FIND_FREE_TIME = "find_free_time"
    DO_NOT_USE_CALENDAR = "do_not_use_calendar"


@dataclass(frozen=True)
class CalendarDecisionResult:
    """Structured Calendar routing decision."""

    decision: CalendarDecision
    reason: str
    calendar_id: str = "primary"
    event_id: str = ""
    query: str = ""
    start_time: str = ""
    end_time: str = ""
    title: str = ""
    tool_params: tuple[tuple[str, object], ...] = ()

    def tool_params_dict(self) -> dict[str, object]:
        """Return params suitable for ToolRequest."""
        return dict(self.tool_params)


class CalendarDecisionEngine:
    """Map natural language requests to Calendar connector actions."""

    def __init__(self, connector: CalendarConnector | None = None) -> None:
        self._connector = connector or CalendarConnector(enabled=True)

    def decide(self, message: str) -> CalendarDecisionResult:
        """Return the Calendar action Titan should take for *message*."""
        lowered = message.lower().strip()
        if not any(signal in lowered for signal in _CALENDAR_SIGNALS):
            return CalendarDecisionResult(
                decision=CalendarDecision.DO_NOT_USE_CALENDAR,
                reason="Aucune intention calendrier détectée.",
            )
        if not self._connector.is_configured:
            return CalendarDecisionResult(
                decision=CalendarDecision.DO_NOT_USE_CALENDAR,
                reason="Connecteur Calendar désactivé ou non configuré.",
            )

        start_time, end_time = self._extract_time_range(message)

        if any(kw in lowered for kw in _LIST_CALENDARS_KEYWORDS):
            return self._result(
                CalendarDecision.LIST_CALENDARS,
                "Liste des calendriers demandée.",
            )

        if any(kw in lowered for kw in _FREE_TIME_KEYWORDS):
            if not start_time or not end_time:
                return CalendarDecisionResult(
                    decision=CalendarDecision.DO_NOT_USE_CALENDAR,
                    reason="Recherche de créneaux libres — plage horaire manquante.",
                )
            return self._result(
                CalendarDecision.FIND_FREE_TIME,
                "Recherche de créneaux libres demandée.",
                start_time=start_time,
                end_time=end_time,
            )

        if any(kw in lowered for kw in _CONFLICT_KEYWORDS):
            if not start_time or not end_time:
                return CalendarDecisionResult(
                    decision=CalendarDecision.DO_NOT_USE_CALENDAR,
                    reason="Détection de conflits — plage horaire manquante.",
                )
            return self._result(
                CalendarDecision.DETECT_CONFLICTS,
                "Détection de conflits de planification demandée.",
                start_time=start_time,
                end_time=end_time,
            )

        if any(kw in lowered for kw in _DELETE_KEYWORDS):
            event_id = self._extract_event_id(message)
            params: list[tuple[str, object]] = [("action", "delete_event")]
            if event_id:
                params.append(("event_id", event_id))
            return CalendarDecisionResult(
                decision=CalendarDecision.DELETE_EVENT,
                reason="Suppression d'événement demandée.",
                event_id=event_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _UPDATE_KEYWORDS):
            event_id = self._extract_event_id(message)
            params = [("action", "update_event")]
            if event_id:
                params.append(("event_id", event_id))
            if start_time:
                params.append(("start_time", start_time))
            if end_time:
                params.append(("end_time", end_time))
            return CalendarDecisionResult(
                decision=CalendarDecision.UPDATE_EVENT,
                reason="Modification d'événement demandée.",
                event_id=event_id,
                start_time=start_time,
                end_time=end_time,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _CREATE_KEYWORDS):
            title = self._extract_title(message)
            if not title and "événement" in lowered:
                match = re.search(
                    r"événement\s+(?:de\s+)?(.+?)(?:\s+demain|\s+à\s+|\s+a\s+|$)",
                    message,
                    re.IGNORECASE,
                )
                if match:
                    title = match.group(1).strip().rstrip(".")
            params = [
                ("action", "create_event"),
                ("title", title or message.strip()[:120]),
            ]
            if start_time:
                params.append(("start_time", start_time))
            if end_time:
                params.append(("end_time", end_time))
            return CalendarDecisionResult(
                decision=CalendarDecision.CREATE_EVENT,
                reason="Création d'événement demandée.",
                title=title,
                start_time=start_time,
                end_time=end_time,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _READ_EVENT_KEYWORDS):
            event_id = self._extract_event_id(message)
            params = [("action", "read_event")]
            if event_id:
                params.append(("event_id", event_id))
            return CalendarDecisionResult(
                decision=CalendarDecision.READ_EVENT,
                reason="Lecture d'événement demandée.",
                event_id=event_id,
                tool_params=tuple(params),
            )

        if any(kw in lowered for kw in _SEARCH_KEYWORDS):
            query = self._extract_search_query(message)
            return self._result(
                CalendarDecision.SEARCH_EVENTS,
                "Recherche d'événements demandée.",
                query=query or message.strip(),
            )

        if any(kw in lowered for kw in _LIST_EVENTS_KEYWORDS):
            params_list: list[tuple[str, object]] = [("action", "list_events")]
            if start_time:
                params_list.append(("start_time", start_time))
            if end_time:
                params_list.append(("end_time", end_time))
            return CalendarDecisionResult(
                decision=CalendarDecision.LIST_EVENTS,
                reason="Liste des événements demandée.",
                start_time=start_time,
                end_time=end_time,
                tool_params=tuple(params_list),
            )

        return self._result(
            CalendarDecision.LIST_EVENTS,
            "Intention calendrier générale — liste des événements par défaut.",
            start_time=start_time,
            end_time=end_time,
        )

    def _result(
        self,
        decision: CalendarDecision,
        reason: str,
        *,
        query: str = "",
        start_time: str = "",
        end_time: str = "",
    ) -> CalendarDecisionResult:
        params: list[tuple[str, object]] = [("action", decision.value)]
        if query:
            params.append(("query", query))
        if start_time:
            params.append(("start_time", start_time))
        if end_time:
            params.append(("end_time", end_time))
        return CalendarDecisionResult(
            decision=decision,
            reason=reason,
            query=query,
            start_time=start_time,
            end_time=end_time,
            tool_params=tuple(params),
        )

    @staticmethod
    def _extract_time_range(message: str) -> tuple[str, str]:
        matches = _DATE_PATTERN.findall(message)
        if len(matches) >= 2:
            return matches[0], matches[1]
        if len(matches) == 1:
            start = matches[0]
            if "T" not in start and " " not in start:
                return f"{start}T09:00:00", f"{start}T17:00:00"
            return start, start

        relative = CalendarDecisionEngine._resolve_relative_day(message)
        if relative is not None:
            day_start, day_end = relative
            clock = CalendarDecisionEngine._extract_clock_time(message)
            if clock is not None:
                hour, minute = clock
                start_dt = day_start.replace(hour=hour, minute=minute, second=0)
                end_dt = start_dt + timedelta(hours=1)
                return (
                    start_dt.replace(microsecond=0).isoformat(),
                    end_dt.replace(microsecond=0).isoformat(),
                )
            return (
                day_start.replace(microsecond=0).isoformat(),
                day_end.replace(microsecond=0).isoformat(),
            )
        return "", ""

    @staticmethod
    def _resolve_relative_day(message: str) -> tuple[datetime, datetime] | None:
        """Map demain/aujourd'hui to a day window when no ISO date is present."""
        lowered = message.lower()
        for keyword, offset_days in _RELATIVE_DAY_OFFSETS.items():
            if keyword in lowered:
                base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                target = base + timedelta(days=offset_days)
                day_end = target.replace(hour=23, minute=59, second=59)
                if any(kw in lowered for kw in _FREE_TIME_KEYWORDS):
                    return (
                        target.replace(hour=9, minute=0, second=0),
                        target.replace(hour=17, minute=0, second=0),
                    )
                return target, day_end
        return None

    @staticmethod
    def _extract_clock_time(message: str) -> tuple[int, int] | None:
        """Parse French clock shorthand such as ``à 15h`` or ``à 15h30``."""
        match = _TIME_H_PATTERN.search(message)
        if match is None:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return hour, minute

    @staticmethod
    def _extract_event_id(message: str) -> str:
        match = re.search(r"\bevent[_-]?id[=:\s]+([a-zA-Z0-9-]+)", message, re.I)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_title(message: str) -> str:
        for marker in ("intitulé:", "intitule:", "titre:", "title:"):
            lowered = message.lower()
            if marker in lowered:
                idx = lowered.index(marker)
                return message[idx + len(marker) :].strip()
        return ""

    @staticmethod
    def _extract_search_query(message: str) -> str:
        lowered = message.lower()
        for marker in (
            "liés au ",
            "lies au ",
            "lié au ",
            "lie au ",
            "pour ",
            "about ",
            "containing ",
            "avec ",
        ):
            if marker in lowered:
                idx = lowered.index(marker)
                return message[idx + len(marker) :].strip().rstrip(".")
        return message.strip()

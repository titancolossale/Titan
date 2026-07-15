# =====================================
# Titan Calendar Connector
# =====================================

"""Calendar scheduling connector — provider-independent (Phase 14.1–14.2).

Google Calendar integration is injected via backend factory; this module never
imports Google APIs directly.
"""

from __future__ import annotations

from tools.connectors.base_connector import ConnectorResult
from tools.connectors.calendar_backend import InMemoryCalendarBackend, StoredEvent
from tools.connectors.calendar_backend_factory import backend_label, create_calendar_backend
from tools.connectors.calendar_backend_protocol import CalendarBackend
from tools.connectors.calendar_models import CalendarEvent, CalendarResult, CalendarSessionState
from tools.connectors.calendar_permissions import (
    CALENDAR_SUPPORTED_ACTIONS,
    CalendarPermissionLevel,
    evaluate_calendar_permission,
    is_confirmed,
    normalize_calendar_action,
)
from tools.connectors.calendar_validator import validate_calendar_config

_READ_ACTIONS = frozenset({
    "list_calendars",
    "list_events",
    "read_event",
    "search_events",
    "detect_conflicts",
    "find_free_time",
})

_WRITE_ACTIONS = frozenset({
    "create_event",
    "update_event",
    "delete_event",
})

_SUPPORTED_ACTIONS = _READ_ACTIONS | _WRITE_ACTIONS


class CalendarConnector:
    """Operate on calendars via a pluggable backend with permission gating."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 30.0,
        backend: CalendarBackend | InMemoryCalendarBackend | None = None,
        provider: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._provider = provider
        if backend is None:
            validation = validate_calendar_config(
                enabled=enabled,
                timeout_seconds=timeout_seconds,
                provider=provider,
            )
            if validation.ok and validation.provider == "google":
                backend = create_calendar_backend(provider="google")
            else:
                backend = InMemoryCalendarBackend()
        self._backend = backend
        self._backend_label = backend_label(backend)
        self._session = CalendarSessionState()

    @property
    def connector_id(self) -> str:
        return "calendar"

    @property
    def backend(self) -> CalendarBackend:
        return self._backend

    @property
    def is_configured(self) -> bool:
        if not self._enabled:
            return False
        effective_provider = (
            "mock" if self._backend_label == "mock" else (self._provider or None)
        )
        validation = validate_calendar_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=effective_provider,
        )
        return validation.ok

    @property
    def session(self) -> CalendarSessionState:
        return self._session

    def configuration_error(self) -> str:
        """Return a French error when the connector is not ready."""
        effective_provider = (
            "mock" if self._backend_label == "mock" else (self._provider or None)
        )
        result = validate_calendar_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=effective_provider,
        )
        return result.message

    def health_check(self) -> tuple[bool, str]:
        """Probe connector readiness without mutating external state."""
        validation = validate_calendar_config(
            enabled=self._enabled,
            timeout_seconds=self._timeout,
            provider=self._provider,
        )
        if not validation.ok:
            return False, validation.message
        self._session.started = True
        try:
            calendar_count = len(self._backend.list_calendars())
        except Exception as exc:
            return False, f"Échec de connexion au backend calendrier : {exc}"
        backend_name = "Google Calendar" if self._backend_label == "google" else "mock"
        return True, (
            f"{validation.message} Backend {backend_name} : "
            f"{calendar_count} calendrier(s) accessible(s)."
        )

    def supported_actions(self) -> frozenset[str]:
        return _SUPPORTED_ACTIONS

    def execute(self, action: str, params: dict) -> ConnectorResult:
        """Dispatch *action* to the connector implementation."""
        normalized = normalize_calendar_action(action)
        if normalized not in self.supported_actions():
            if normalized in CALENDAR_SUPPORTED_ACTIONS - _SUPPORTED_ACTIONS:
                return ConnectorResult(
                    success=False,
                    action=action,
                    error=f"Action bloquée ou non implémentée : {action!r}",
                )
            return ConnectorResult(
                success=False,
                action=action,
                error=f"Action non supportée : {action!r}",
            )
        if not self.is_configured:
            return ConnectorResult(
                success=False,
                action=action,
                error=self.configuration_error(),
            )
        permission = evaluate_calendar_permission(
            normalized,
            params,
            confirmed=is_confirmed(params),
        )
        if permission.level == CalendarPermissionLevel.BLOCKED:
            return ConnectorResult(
                success=False,
                action=normalized,
                error=permission.reason,
            )
        if (
            permission.level == CalendarPermissionLevel.CONFIRMATION_REQUIRED
            and normalized in _WRITE_ACTIONS
        ):
            return ConnectorResult(
                success=False,
                action=normalized,
                error=permission.reason,
            )
        self._session.started = True
        return self._execute_action(normalized, params)

    def _execute_action(self, action: str, params: dict) -> ConnectorResult:
        dispatch = {
            "list_calendars": self._list_calendars,
            "list_events": self._list_events,
            "read_event": self._read_event,
            "search_events": self._search_events,
            "create_event": self._create_event,
            "update_event": self._update_event,
            "delete_event": self._delete_event,
            "detect_conflicts": self._detect_conflicts,
            "find_free_time": self._find_free_time,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ConnectorResult(
                success=False,
                action=action,
                error=f"Action non implémentée : {action!r}",
            )
        try:
            return handler(params)
        except ValueError as exc:
            return ConnectorResult(success=False, action=action, error=str(exc))

    def _list_calendars(self, params: dict) -> ConnectorResult:
        calendars = self._backend.list_calendars()
        result = CalendarResult(
            status="ok",
            calendars=tuple(calendar.name for calendar in calendars),
            warnings=self._provider_warning(),
        )
        return self._success("list_calendars", result)

    def _list_events(self, params: dict) -> ConnectorResult:
        calendar_id = str(params.get("calendar_id", "")).strip() or None
        events = self._backend.list_events(
            calendar_id=calendar_id,
            start_time=str(params.get("start_time", "")).strip() or None,
            end_time=str(params.get("end_time", "")).strip() or None,
        )
        result = CalendarResult(
            calendar_id=calendar_id or "",
            status="ok",
            events=tuple(self._to_event_model(event) for event in events),
            warnings=self._provider_warning(),
        )
        return self._success("list_events", result)

    def _read_event(self, params: dict) -> ConnectorResult:
        event_id = str(params.get("event_id", "")).strip()
        if not event_id:
            return ConnectorResult(
                success=False,
                action="read_event",
                error="Paramètre event_id requis.",
            )
        event = self._backend.read_event(event_id)
        if event is None:
            return ConnectorResult(
                success=False,
                action="read_event",
                error=f"Événement introuvable : {event_id!r}",
            )
        model = self._to_event_model(event)
        result = CalendarResult(
            calendar_id=model.calendar_id,
            event_id=model.event_id,
            title=model.title,
            description=model.description,
            start_time=model.start_time,
            end_time=model.end_time,
            attendees=model.attendees,
            location=model.location,
            status="ok",
            warnings=self._provider_warning(),
        )
        return self._success("read_event", result, target_path=event_id)

    def _search_events(self, params: dict) -> ConnectorResult:
        query = str(params.get("query", params.get("q", ""))).strip()
        calendar_id = str(params.get("calendar_id", "")).strip() or None
        events = self._backend.search_events(query, calendar_id=calendar_id)
        result = CalendarResult(
            calendar_id=calendar_id or "",
            title=query,
            status="ok",
            events=tuple(self._to_event_model(event) for event in events),
            warnings=self._provider_warning(),
        )
        return self._success("search_events", result)

    def _create_event(self, params: dict) -> ConnectorResult:
        calendar_id = str(
            params.get("calendar_id", self._session.default_calendar_id),
        ).strip()
        title = str(params.get("title", "")).strip()
        if not title and params.get("query"):
            title = str(params.get("query", "")).strip()
        attendees_raw = params.get("attendees", [])
        attendees = (
            list(attendees_raw)
            if isinstance(attendees_raw, list)
            else [str(attendees_raw)]
            if attendees_raw
            else []
        )
        event = self._backend.create_event(
            calendar_id=calendar_id,
            title=title,
            description=str(params.get("description", "")).strip(),
            start_time=str(params.get("start_time", "")).strip(),
            end_time=str(params.get("end_time", "")).strip(),
            attendees=attendees,
            location=str(params.get("location", "")).strip(),
        )
        model = self._to_event_model(event)
        warnings = self._provider_warning()
        conflicts = self._backend.detect_conflicts(
            calendar_id=calendar_id,
            start_time=event.start_time,
            end_time=event.end_time,
            exclude_event_id=event.event_id,
        )
        conflict_warning: tuple[str, ...] = ()
        if conflicts:
            conflict_warning = (
                f"{len(conflicts)} conflit(s) détecté(s) avec d'autres événements.",
            )
        result = CalendarResult(
            calendar_id=model.calendar_id,
            event_id=model.event_id,
            title=model.title,
            description=model.description,
            start_time=model.start_time,
            end_time=model.end_time,
            attendees=model.attendees,
            location=model.location,
            status="created",
            warnings=warnings + conflict_warning,
            conflicts=tuple(self._to_event_model(item) for item in conflicts),
        )
        return self._success("create_event", result, target_path=event.event_id)

    def _update_event(self, params: dict) -> ConnectorResult:
        event_id = str(params.get("event_id", "")).strip()
        if not event_id:
            return ConnectorResult(
                success=False,
                action="update_event",
                error="Paramètre event_id requis.",
            )
        attendees_raw = params.get("attendees")
        attendees = None
        if isinstance(attendees_raw, list):
            attendees = list(attendees_raw)
        event = self._backend.update_event(
            event_id,
            title=str(params["title"]).strip() if "title" in params else None,
            description=(
                str(params["description"]).strip()
                if "description" in params
                else None
            ),
            start_time=(
                str(params["start_time"]).strip()
                if "start_time" in params
                else None
            ),
            end_time=(
                str(params["end_time"]).strip()
                if "end_time" in params
                else None
            ),
            attendees=attendees,
            location=(
                str(params["location"]).strip()
                if "location" in params
                else None
            ),
        )
        model = self._to_event_model(event)
        result = CalendarResult(
            calendar_id=model.calendar_id,
            event_id=model.event_id,
            title=model.title,
            description=model.description,
            start_time=model.start_time,
            end_time=model.end_time,
            attendees=model.attendees,
            location=model.location,
            status="updated",
            warnings=self._provider_warning(),
        )
        return self._success("update_event", result, target_path=event_id)

    def _delete_event(self, params: dict) -> ConnectorResult:
        event_id = str(params.get("event_id", "")).strip()
        if not event_id:
            return ConnectorResult(
                success=False,
                action="delete_event",
                error="Paramètre event_id requis.",
            )
        deleted = self._backend.delete_event(event_id)
        if not deleted:
            return ConnectorResult(
                success=False,
                action="delete_event",
                error=f"Événement introuvable : {event_id!r}",
            )
        result = CalendarResult(
            event_id=event_id,
            status="deleted",
            warnings=self._provider_warning(),
        )
        return self._success("delete_event", result, target_path=event_id)

    def _detect_conflicts(self, params: dict) -> ConnectorResult:
        start_time = str(params.get("start_time", "")).strip()
        end_time = str(params.get("end_time", "")).strip()
        if not start_time or not end_time:
            return ConnectorResult(
                success=False,
                action="detect_conflicts",
                error="Paramètres start_time et end_time requis.",
            )
        calendar_id = str(params.get("calendar_id", "")).strip() or None
        exclude_event_id = str(params.get("event_id", "")).strip() or None
        conflicts = self._backend.detect_conflicts(
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
            exclude_event_id=exclude_event_id,
        )
        result = CalendarResult(
            calendar_id=calendar_id or "",
            start_time=start_time,
            end_time=end_time,
            status="ok" if not conflicts else "conflict",
            conflicts=tuple(self._to_event_model(item) for item in conflicts),
            warnings=self._provider_warning(),
        )
        return self._success("detect_conflicts", result)

    def _find_free_time(self, params: dict) -> ConnectorResult:
        start_time = str(params.get("start_time", "")).strip()
        end_time = str(params.get("end_time", "")).strip()
        duration_raw = params.get("duration_minutes", 30)
        try:
            duration_minutes = int(duration_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("duration_minutes invalide.") from exc
        if not start_time or not end_time:
            return ConnectorResult(
                success=False,
                action="find_free_time",
                error="Paramètres start_time et end_time requis.",
            )
        calendar_id = str(params.get("calendar_id", "")).strip() or None
        slots = self._backend.find_free_time(
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
        )
        result = CalendarResult(
            calendar_id=calendar_id or "",
            start_time=start_time,
            end_time=end_time,
            status="ok",
            free_slots=tuple(slots),
            warnings=self._provider_warning(),
        )
        return self._success("find_free_time", result)

    def _provider_warning(self) -> tuple[str, ...]:
        if self._backend_label == "google":
            return ()
        return ("Backend mock — aucun provider externe connecté.",)

    @staticmethod
    def _to_event_model(event: StoredEvent) -> CalendarEvent:
        return CalendarEvent(
            calendar_id=event.calendar_id,
            event_id=event.event_id,
            title=event.title,
            description=event.description,
            start_time=event.start_time,
            end_time=event.end_time,
            attendees=tuple(event.attendees),
            location=event.location,
            status="confirmed",
        )

    @staticmethod
    def _success(
        action: str,
        result: CalendarResult,
        *,
        target_path: str = "",
    ) -> ConnectorResult:
        return ConnectorResult(
            success=True,
            action=action,
            data=result.to_json(),
            target_path=target_path,
        )

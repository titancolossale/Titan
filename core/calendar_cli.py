# =====================================
# Titan Calendar CLI
# =====================================

"""Manual Calendar health, OAuth, and smoke-test commands (Phase 14.2)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from config.settings import TITAN_CALENDAR_PROVIDER
from tools.connectors.calendar_connector import CalendarConnector
from tools.connectors.calendar_validator import validate_calendar_config
from tools.connectors.google_oauth import format_oauth_setup_guide, run_oauth_setup
from tools.permission_manager import PermissionLevel, PermissionManager

# Distinctive marker for production smoke-test events — never touch real events.
_SMOKE_TEST_EVENT_TITLE = "Titan Calendar Validation Test"
_SMOKE_TEST_START = "2099-06-15T14:00:00"
_SMOKE_TEST_END = "2099-06-15T15:00:00"
_SMOKE_TEST_UPDATED_TITLE = "Titan Calendar Validation Test (updated)"


def _print_step(label: str, success: bool, detail: str = "") -> None:
    status = "OK" if success else "ÉCHEC"
    line = f"  [{status}] {label}"
    if detail:
        line = f"{line} — {detail}"
    print(line)


def run_calendar_health() -> int:
    """Validate Calendar configuration and print a French health report."""
    validation = validate_calendar_config()
    print(validation.format_report())
    if not validation.ok:
        return 1

    connector = CalendarConnector()
    healthy, message = connector.health_check()
    print("")
    print(f"Health check : {'OK' if healthy else 'ÉCHEC'}")
    print(message)
    return 0 if healthy else 1


def run_calendar_auth() -> int:
    """Guide Nolan through local Google Calendar OAuth setup."""
    print(format_oauth_setup_guide())
    print("")
    success, message = run_oauth_setup()
    print(message)
    if not success:
        return 1

    validation = validate_calendar_config()
    print("")
    print(validation.format_report())
    return 0 if validation.ok else 1


def run_calendar_list() -> int:
    """List accessible calendars via the configured backend."""
    validation = validate_calendar_config()
    if not validation.ok:
        print(validation.format_report())
        return 1

    connector = CalendarConnector()
    outcome = connector.execute("list_calendars", {})
    if not outcome.success:
        print(f"Erreur : {outcome.error}")
        return 1

    payload = json.loads(outcome.data)
    calendars = payload.get("calendars", [])
    print("=== Calendriers accessibles ===")
    print(f"Provider : {TITAN_CALENDAR_PROVIDER}")
    print(f"Nombre : {len(calendars)}")
    print("")
    for index, name in enumerate(calendars, start=1):
        print(f"{index}. {name}")
    return 0


def run_calendar_smoke_test() -> int:
    """Run an end-to-end Calendar connector smoke test."""
    validation = validate_calendar_config()
    if not validation.ok:
        print(validation.format_report())
        return 1

    connector = CalendarConnector()
    print("=== Calendar — smoke test ===")
    print(f"Provider : {validation.provider}")
    print("")

    failures = 0
    list_result = connector.execute("list_calendars", {})
    detail = ""
    if list_result.success:
        payload = json.loads(list_result.data)
        detail = f"{len(payload.get('calendars', []))} calendrier(s)"
    _print_step("list_calendars", list_result.success, detail)
    failures += 0 if list_result.success else 1

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    list_events = connector.execute(
        "list_events",
        {
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        },
    )
    events_detail = ""
    if list_events.success:
        payload = json.loads(list_events.data)
        events_detail = f"{len(payload.get('events', []))} événement(s)"
    _print_step("list_events (7 jours)", list_events.success, events_detail)
    failures += 0 if list_events.success else 1

    search_result = connector.execute("search_events", {"query": "meeting"})
    _print_step("search_events", search_result.success)
    failures += 0 if search_result.success else 1

    conflict_result = connector.execute(
        "detect_conflicts",
        {
            "start_time": (start + timedelta(hours=10)).isoformat(),
            "end_time": (start + timedelta(hours=11)).isoformat(),
        },
    )
    _print_step("detect_conflicts", conflict_result.success)
    failures += 0 if conflict_result.success else 1

    free_result = connector.execute(
        "find_free_time",
        {
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "duration_minutes": 30,
        },
    )
    _print_step("find_free_time", free_result.success)
    failures += 0 if free_result.success else 1

    permission = PermissionManager().evaluate("calendar", "create_event")
    create_blocked = permission.level == PermissionLevel.CONFIRMATION_REQUIRED
    _print_step(
        "create_event (confirmation requise)",
        create_blocked,
        permission.reason,
    )
    failures += 0 if create_blocked else 1

    update_permission = PermissionManager().evaluate("calendar", "update_event")
    update_blocked = update_permission.level == PermissionLevel.CONFIRMATION_REQUIRED
    _print_step(
        "update_event (confirmation requise)",
        update_blocked,
        update_permission.reason,
    )
    failures += 0 if update_blocked else 1

    delete_permission = PermissionManager().evaluate("calendar", "delete_event")
    delete_blocked = delete_permission.level == PermissionLevel.CONFIRMATION_REQUIRED
    _print_step(
        "delete_event (confirmation requise)",
        delete_blocked,
        delete_permission.reason,
    )
    failures += 0 if delete_blocked else 1

    if validation.provider in {"mock", "google"}:
        failures += _run_smoke_test_crud_cycle(connector, validation.provider)

    print("")
    if failures == 0:
        print("Smoke test : SUCCÈS — Calendar est opérationnel.")
        return 0
    print(f"Smoke test : ÉCHEC — {failures} étape(s) en erreur.")
    return 1


def _run_smoke_test_crud_cycle(connector: CalendarConnector, provider: str) -> int:
    """Run create/read/update/search/delete on a temporary test event; return failure count."""
    failures = 0
    label_suffix = f" ({provider})"

    unconfirmed_create = connector.execute(
        "create_event",
        {
            "title": _SMOKE_TEST_EVENT_TITLE,
            "start_time": _SMOKE_TEST_START,
            "end_time": _SMOKE_TEST_END,
        },
    )
    blocked_without_confirm = not unconfirmed_create.success
    _print_step(
        f"create_event sans confirmation{label_suffix}",
        blocked_without_confirm,
        "bloqué comme attendu" if blocked_without_confirm else "devrait être bloqué",
    )
    failures += 0 if blocked_without_confirm else 1

    create_result = connector.execute(
        "create_event",
        {
            "title": _SMOKE_TEST_EVENT_TITLE,
            "start_time": _SMOKE_TEST_START,
            "end_time": _SMOKE_TEST_END,
            "description": "Événement temporaire — validation Phase 14.3",
            "confirmed": True,
        },
    )
    _print_step(f"create_event{label_suffix}", create_result.success)
    failures += 0 if create_result.success else 1
    if not create_result.success:
        return failures

    event_id = json.loads(create_result.data).get("event_id", "")
    if not event_id:
        _print_step(f"create_event event_id{label_suffix}", False, "event_id absent")
        return failures + 1

    read_result = connector.execute("read_event", {"event_id": event_id})
    read_detail = ""
    if read_result.success:
        payload = json.loads(read_result.data)
        read_detail = payload.get("title", "")
    _print_step(f"read_event{label_suffix}", read_result.success, read_detail)
    failures += 0 if read_result.success else 1

    unconfirmed_update = connector.execute(
        "update_event",
        {"event_id": event_id, "title": _SMOKE_TEST_UPDATED_TITLE},
    )
    update_blocked = not unconfirmed_update.success
    _print_step(
        f"update_event sans confirmation{label_suffix}",
        update_blocked,
        "bloqué comme attendu" if update_blocked else "devrait être bloqué",
    )
    failures += 0 if update_blocked else 1

    update_result = connector.execute(
        "update_event",
        {
            "event_id": event_id,
            "title": _SMOKE_TEST_UPDATED_TITLE,
            "confirmed": True,
        },
    )
    _print_step(f"update_event{label_suffix}", update_result.success)
    failures += 0 if update_result.success else 1

    search_result = connector.execute(
        "search_events",
        {"query": _SMOKE_TEST_EVENT_TITLE},
    )
    search_detail = ""
    if search_result.success:
        payload = json.loads(search_result.data)
        events = payload.get("events", [])
        search_detail = f"{len(events)} résultat(s)"
    _print_step(f"search_events (test event){label_suffix}", search_result.success, search_detail)
    failures += 0 if search_result.success else 1

    unconfirmed_delete = connector.execute("delete_event", {"event_id": event_id})
    delete_blocked = not unconfirmed_delete.success
    _print_step(
        f"delete_event sans confirmation{label_suffix}",
        delete_blocked,
        "bloqué comme attendu" if delete_blocked else "devrait être bloqué",
    )
    failures += 0 if delete_blocked else 1

    delete_result = connector.execute(
        "delete_event",
        {"event_id": event_id, "confirmed": True},
    )
    _print_step(f"delete_event (cleanup){label_suffix}", delete_result.success)
    failures += 0 if delete_result.success else 1

    verify_result = connector.execute("read_event", {"event_id": event_id})
    cleanup_ok = not verify_result.success
    _print_step(
        f"cleanup confirmé{label_suffix}",
        cleanup_ok,
        "événement supprimé" if cleanup_ok else "événement encore présent",
    )
    failures += 0 if cleanup_ok else 1

    return failures


def print_calendar_cli_help() -> None:
    """Print Calendar CLI subcommand help."""
    print(
        "Commandes Calendar :\n"
        "  python main.py calendar-health      — valider la configuration\n"
        "  python main.py calendar-auth        — authentification Google OAuth\n"
        "  python main.py calendar-list        — lister les calendriers accessibles\n"
        "  python main.py calendar-smoke-test  — test bout-en-bout (lecture + CRUD test)\n"
    )


def dispatch_calendar_command(command: str) -> int | None:
    """Run a Calendar CLI subcommand; return exit code or None if unknown."""
    normalized = command.strip().lower().replace("_", "-")
    if normalized == "calendar-health":
        return run_calendar_health()
    if normalized == "calendar-auth":
        return run_calendar_auth()
    if normalized == "calendar-list":
        return run_calendar_list()
    if normalized == "calendar-smoke-test":
        return run_calendar_smoke_test()
    if normalized in {"calendar-help", "calendar"}:
        print_calendar_cli_help()
        return 0
    return None

# =====================================
# Titan Email CLI
# =====================================

"""Manual Email health, OAuth, and smoke-test commands (Phase 15.2)."""

from __future__ import annotations

import json

from config.settings import TITAN_EMAIL_PROVIDER
from tools.connectors.email_connector import EmailConnector
from tools.connectors.email_validator import validate_email_config
from tools.connectors.gmail_oauth import format_gmail_oauth_setup_guide, run_gmail_oauth_setup
from tools.permission_manager import PermissionLevel, PermissionManager

_SMOKE_TEST_SUBJECT = "Titan Email Validation Test"
_SMOKE_TEST_BODY = "Brouillon temporaire — validation Phase 15.2 (ne pas envoyer)."


def _print_step(label: str, success: bool, detail: str = "") -> None:
    status = "OK" if success else "ÉCHEC"
    line = f"  [{status}] {label}"
    if detail:
        line = f"{line} — {detail}"
    print(line)


def run_email_health() -> int:
    """Validate Email configuration and print a French health report."""
    validation = validate_email_config()
    print(validation.format_report())
    if not validation.ok:
        return 1

    connector = EmailConnector()
    healthy, message = connector.health_check()
    print("")
    print(f"Health check : {'OK' if healthy else 'ÉCHEC'}")
    print(message)
    return 0 if healthy else 1


def run_email_auth() -> int:
    """Guide Nolan through local Gmail OAuth setup."""
    print(format_gmail_oauth_setup_guide())
    print("")
    success, message = run_gmail_oauth_setup()
    print(message)
    if not success:
        return 1

    validation = validate_email_config()
    print("")
    print(validation.format_report())
    return 0 if validation.ok else 1


def run_email_list() -> int:
    """List recent emails via the configured backend."""
    validation = validate_email_config()
    if not validation.ok:
        print(validation.format_report())
        return 1

    connector = EmailConnector()
    outcome = connector.execute("list_emails", {"limit": 10})
    if not outcome.success:
        print(f"Erreur : {outcome.error}")
        return 1

    payload = json.loads(outcome.data)
    emails = payload.get("emails", [])
    print("=== Emails récents ===")
    print(f"Provider : {TITAN_EMAIL_PROVIDER}")
    print(f"Nombre : {len(emails)}")
    print("")
    for index, email in enumerate(emails, start=1):
        unread = " [non lu]" if email.get("unread") else ""
        subject = email.get("subject", "(sans objet)")
        sender = email.get("sender", "")
        message_id = email.get("message_id", "")
        print(f"{index}. {subject}{unread}")
        print(f"   De : {sender}")
        print(f"   ID : {message_id}")
    return 0


def run_email_smoke_test() -> int:
    """Run an end-to-end Email connector smoke test."""
    validation = validate_email_config()
    if not validation.ok:
        print(validation.format_report())
        return 1

    connector = EmailConnector()
    print("=== Email — smoke test ===")
    print(f"Provider : {validation.provider}")
    print("")

    failures = 0

    list_result = connector.execute("list_emails", {"limit": 5})
    list_detail = ""
    if list_result.success:
        payload = json.loads(list_result.data)
        list_detail = f"{len(payload.get('emails', []))} email(s)"
    _print_step("list_emails", list_result.success, list_detail)
    failures += 0 if list_result.success else 1

    search_result = connector.execute("search_emails", {"query": "titan"})
    search_detail = ""
    if search_result.success:
        payload = json.loads(search_result.data)
        search_detail = f"{len(payload.get('emails', []))} résultat(s)"
    _print_step("search_emails", search_result.success, search_detail)
    failures += 0 if search_result.success else 1

    read_detail = ""
    read_success = True
    if list_result.success:
        emails = json.loads(list_result.data).get("emails", [])
        if emails:
            message_id = emails[0].get("message_id", "")
            read_result = connector.execute("read_email", {"message_id": message_id})
            read_success = read_result.success
            if read_success:
                payload = json.loads(read_result.data)
                read_detail = payload.get("subject", "")
        else:
            read_detail = "aucun email à lire"
    else:
        read_success = False
    _print_step("read_email", read_success, read_detail)
    failures += 0 if read_success else 1

    permission = PermissionManager().evaluate("email", "send_email", confirmed=False)
    send_blocked = permission.level == PermissionLevel.CONFIRMATION_REQUIRED
    _print_step(
        "send_email (confirmation requise)",
        send_blocked,
        permission.reason,
    )
    failures += 0 if send_blocked else 1

    compose_permission = PermissionManager().evaluate(
        "email",
        "compose_email",
        confirmed=False,
    )
    compose_blocked = compose_permission.level == PermissionLevel.CONFIRMATION_REQUIRED
    _print_step(
        "compose_email (confirmation requise)",
        compose_blocked,
        compose_permission.reason,
    )
    failures += 0 if compose_blocked else 1

    unconfirmed_compose = connector.execute(
        "compose_email",
        {
            "recipients": ["validation@example.com"],
            "subject": _SMOKE_TEST_SUBJECT,
            "body": _SMOKE_TEST_BODY,
        },
    )
    blocked_without_confirm = not unconfirmed_compose.success
    _print_step(
        "compose_email sans confirmation",
        blocked_without_confirm,
        "bloqué comme attendu" if blocked_without_confirm else "devrait être bloqué",
    )
    failures += 0 if blocked_without_confirm else 1

    if validation.provider == "mock":
        failures += _run_mock_smoke_test_crud(connector)
    elif validation.provider == "gmail":
        failures += _run_gmail_smoke_test_compose(connector)

    print("")
    if failures == 0:
        print("Smoke test : SUCCÈS — Email est opérationnel.")
        return 0
    print(f"Smoke test : ÉCHEC — {failures} étape(s) en erreur.")
    return 1


def _run_mock_smoke_test_crud(connector: EmailConnector) -> int:
    """Run compose/send/archive cycle on mock backend; return failure count."""
    failures = 0

    compose_result = connector.execute(
        "compose_email",
        {
            "recipients": ["validation@example.com"],
            "subject": _SMOKE_TEST_SUBJECT,
            "body": _SMOKE_TEST_BODY,
            "confirmed": True,
        },
    )
    _print_step("compose_email (mock)", compose_result.success)
    failures += 0 if compose_result.success else 1

    send_result = connector.execute(
        "send_email",
        {
            "recipients": ["validation@example.com"],
            "subject": _SMOKE_TEST_SUBJECT,
            "body": _SMOKE_TEST_BODY,
            "confirmed": True,
        },
    )
    send_expected_fail = not send_result.success
    _print_step(
        "send_email (mock — non disponible)",
        send_expected_fail,
        "bloqué comme attendu" if send_expected_fail else "devrait échouer sur mock",
    )
    failures += 0 if send_expected_fail else 1

    return failures


def _run_gmail_smoke_test_compose(connector: EmailConnector) -> int:
    """Create a Gmail draft with confirmation; return failure count."""
    failures = 0

    compose_result = connector.execute(
        "compose_email",
        {
            "recipients": ["validation@example.com"],
            "subject": _SMOKE_TEST_SUBJECT,
            "body": _SMOKE_TEST_BODY,
            "confirmed": True,
        },
    )
    draft_detail = ""
    if compose_result.success:
        payload = json.loads(compose_result.data)
        draft_detail = payload.get("draft_id", payload.get("message_id", ""))
    _print_step("compose_email (Gmail brouillon)", compose_result.success, draft_detail)
    failures += 0 if compose_result.success else 1

    unconfirmed_send = connector.execute(
        "send_email",
        {
            "recipients": ["validation@example.com"],
            "subject": _SMOKE_TEST_SUBJECT,
            "body": _SMOKE_TEST_BODY,
        },
    )
    send_blocked = not unconfirmed_send.success
    _print_step(
        "send_email sans confirmation (Gmail)",
        send_blocked,
        "bloqué comme attendu" if send_blocked else "devrait être bloqué",
    )
    failures += 0 if send_blocked else 1

    return failures


def print_email_cli_help() -> None:
    """Print Email CLI subcommand help."""
    print(
        "Commandes Email :\n"
        "  python main.py email-health      — valider la configuration\n"
        "  python main.py email-auth        — authentification Gmail OAuth\n"
        "  python main.py email-list        — lister les emails récents\n"
        "  python main.py email-smoke-test  — test bout-en-bout (lecture + permissions)\n"
    )


def dispatch_email_command(command: str) -> int | None:
    """Run an Email CLI subcommand; return exit code or None if unknown."""
    normalized = command.strip().lower().replace("_", "-")
    if normalized == "email-health":
        return run_email_health()
    if normalized == "email-auth":
        return run_email_auth()
    if normalized == "email-list":
        return run_email_list()
    if normalized == "email-smoke-test":
        return run_email_smoke_test()
    if normalized in {"email-help", "email"}:
        print_email_cli_help()
        return 0
    return None

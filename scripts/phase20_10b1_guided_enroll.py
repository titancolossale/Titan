# =====================================
# Titan Phase 20.10B-1 Guided Enrollment Entry Point
# =====================================

"""Guided production enrollment launcher (Phase 20.10B-1).

By default this does NOT record Nolan or Ibrahim. It:

  1. Runs production enrollment pre-flight
  2. Prints exact Web App enrollment steps
  3. Optionally starts a consented session shell for the NEXT phase

Live microphone capture for the first real enrollment uses the existing
Web App Voice panel (``web/v2/voice/enrollment-ui.js``) — no UI redesign.

Usage (from project root):

    # Safe default — preflight + instructions only
    python scripts/phase20_10b1_guided_enroll.py --user Nolan

    # Show Ibrahim instructions
    python scripts/phase20_10b1_guided_enroll.py --user Ibrahim

    # Explicit dry-run (same as default)
    python scripts/phase20_10b1_guided_enroll.py --user Nolan --dry-run

Recording real voice is intentionally gated and deferred to Phase 20.10B-2.
Pass ``--allow-record`` only when Nolan is ready to enroll for real
(requires interactive confirmation). Even then, capture happens in the Web App.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from context.session_manager import SessionManager  # noqa: E402
from voice.embedding_provider import reset_embedding_registry_for_tests  # noqa: E402
from voice.enrollment_preflight import run_enrollment_preflight  # noqa: E402
from voice.enrollment_scripts import get_enrollment_script  # noqa: E402


def _print_web_steps(user: str, *, locale: str) -> None:
    script = get_enrollment_script(locale)
    phrases = list(script.phrases) if script else []
    print()
    print("=" * 64)
    print(f"GUIDED ENROLLMENT — {user} (Web App)")
    print("=" * 64)
    print("This phase prepared the environment. Recording is the NEXT step.")
    print()
    print("Exact steps when you are ready to enroll for real:")
    print("  1. Confirm pre-flight passed (this script / preflight CLI).")
    print("  2. Start the Web App:  python main.py web-dev")
    print("  3. Open the Voice panel in the Titan web UI.")
    print(f"  4. Select identity: {user}  (never enroll the other user by mistake).")
    print("  5. Read the consent text and check the consent box explicitly.")
    print("  6. Click Continuer — consent is required before any sample.")
    print("  7. For each phrase shown, click Enregistrer, speak clearly, Stop.")
    print("  8. Rejected samples can be retried — do not force bad audio.")
    print("  9. When enough samples are accepted, click Terminer.")
    print(" 10. Run Vérifier with a fresh spoken sample.")
    print(" 11. On success, the encrypted voice profile activates for this user only.")
    print()
    print("Safety reminders:")
    print("  • Nolan and Ibrahim enrollments are fully separate.")
    print("  • Saying « je suis Nolan/Ibrahim » is CLAIMED, not VERIFIED.")
    print("  • Voice identity never authorizes destructive / financial actions alone.")
    print("  • Wake-word and always-listening stay OFF.")
    print("  • Raw audio is temporary; embeddings stay encrypted (AES-GCM).")
    print()
    if phrases:
        print(f"Sample phrases ({locale}) — for awareness only, do not record yet:")
        for idx, phrase in enumerate(phrases[:5], start=1):
            print(f"  {idx}. {phrase}")
        if len(phrases) > 5:
            print(f"  … +{len(phrases) - 5} more in the Web wizard")
    print("=" * 64)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 20.10B-1 guided enrollment entry (default: no recording)."
    )
    parser.add_argument(
        "--user",
        required=True,
        help="Enrollment target: Nolan or Ibrahim",
    )
    parser.add_argument(
        "--locale",
        default="fr-FR",
        help="Enrollment script locale (default fr-FR)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preflight + instructions only (default).",
    )
    parser.add_argument(
        "--allow-record",
        action="store_true",
        help=(
            "Acknowledge that real recording may begin in the Web App next. "
            "This CLI still does not capture microphone audio."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit preflight JSON instead of human instructions.",
    )
    parser.add_argument(
        "--skip-ecapa-load",
        action="store_true",
        help="Skip forcing ECAPA model load.",
    )
    args = parser.parse_args()

    user = SessionManager.normalize_user(args.user)
    if user is None:
        print(f"Unauthorized enrollment user: {args.user!r} (use Nolan or Ibrahim)")
        return 2

    reset_embedding_registry_for_tests()
    report = run_enrollment_preflight(force_ecapa_load=not args.skip_ecapa_load)

    if args.json:
        payload = {
            "user": user,
            "allow_record": bool(args.allow_record),
            "records_in_this_cli": False,
            "preflight": report,
            "next_method": "web_app_voice_panel",
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    print(f"Guided enrollment entry for {user}")
    print(f"preflight_overall={report.get('overall_status')} ready={report.get('ok')}")
    for item in report.get("check_list") or []:
        print(f"  [{item.get('status')}] {item.get('name')}: {item.get('message')}")

    if not report.get("ok"):
        print()
        print("Pre-flight FAILED — do not begin real enrollment yet.")
        print("Fix blocking checks, then re-run this script.")
        return 1

    _print_web_steps(user, locale=args.locale)

    if args.allow_record:
        print()
        print(
            "ALLOW_RECORD acknowledged: you may proceed to the Web App "
            "and record ONLY this user's samples when ready."
        )
        print("This CLI does not open the microphone.")
    else:
        print()
        print(
            "DRY-RUN: no microphone capture. When ready for real enrollment, "
            "re-run with --allow-record after reading the steps above, then use "
            "the Web App Voice panel."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

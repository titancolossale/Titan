# =====================================
# Titan Phase 20.10B-1 Enrollment Pre-flight CLI
# =====================================

"""Run production enrollment pre-flight WITHOUT recording anyone.

Usage (from project root):

    python scripts/phase20_10b1_enrollment_preflight.py
    python scripts/phase20_10b1_enrollment_preflight.py --json
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

# Settings import after dotenv so production activation flags apply.
from voice.embedding_provider import reset_embedding_registry_for_tests  # noqa: E402
from voice.enrollment_preflight import run_enrollment_preflight  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 20.10B-1 production enrollment pre-flight (no recording)."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report (never includes encryption keys or embeddings).",
    )
    parser.add_argument(
        "--skip-ecapa-load",
        action="store_true",
        help="Skip forcing ECAPA model load (faster; deps-only check).",
    )
    args = parser.parse_args()

    reset_embedding_registry_for_tests()
    report = run_enrollment_preflight(force_ecapa_load=not args.skip_ecapa_load)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Phase {report.get('phase')} pre-flight")
        print(f"overall={report.get('overall_status')} ready={report.get('ok')}")
        print(f"ready_for_real_enrollment={report.get('ready_for_real_enrollment')}")
        print(f"blocking={report.get('blocking_checks')}")
        print(f"warnings={report.get('warning_checks')}")
        for item in report.get("check_list") or []:
            print(
                f"  [{item.get('status')}] {item.get('name')}: {item.get('message')}"
            )
        method = report.get("enrollment_method") or {}
        print(f"enrollment_method={method.get('primary')}")
        print("records_biometric_samples=False")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

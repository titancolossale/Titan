# =====================================
# Migrate Web Conversations CLI
# =====================================

"""Apply durable conversation schema migrations (Phase 12.1).

Windows PowerShell:
  python scripts/migrate_web_conversations.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.web_conversations.db import (  # noqa: E402
    apply_migrations,
    backend_name,
    check_database_ready,
    get_engine,
    resolve_database_url,
)


def main() -> int:
    url = resolve_database_url()
    print(f"Backend: {backend_name(url)}")
    # Never print full credentials — show scheme/host only.
    safe = url.split("@")[-1] if "@" in url else url
    print(f"Target:  {safe}")
    engine = get_engine()
    applied = apply_migrations(engine)
    if applied:
        print(f"Applied: {', '.join(applied)}")
    else:
        print("Applied: (none — already up to date)")
    ok, message, details = check_database_ready(engine)
    print(f"Ready:   {ok} — {message}")
    print(f"Details: {details}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

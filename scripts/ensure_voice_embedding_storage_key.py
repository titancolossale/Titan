# =====================================
# Titan Voice Embedding Storage Key Bootstrap
# =====================================

"""Safely ensure TITAN_VOICE_EMBEDDING_STORAGE_KEY exists in local .env.

Never prints the key value. Never commits secrets. Idempotent.

Usage (from project root):

    python scripts/ensure_voice_embedding_storage_key.py
"""

from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
KEY_NAME = "TITAN_VOICE_EMBEDDING_STORAGE_KEY"
KEY_LINE_RE = re.compile(rf"^{re.escape(KEY_NAME)}\s*=", re.MULTILINE)


def _generate_key() -> str:
    # 32 bytes → 64 hex chars; AES key is derived via SHA-256(material|key_id).
    return secrets.token_hex(32)


def ensure_storage_key(*, env_path: Path = ENV_PATH) -> dict[str, object]:
    """Ensure a storage key line exists in ``.env``. Does not print the secret."""
    created = False
    updated = False
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8")
    else:
        text = ""
        created = True

    if KEY_LINE_RE.search(text):
        # Key already present — do not overwrite.
        # Detect empty assignment.
        empty = re.search(
            rf"^{re.escape(KEY_NAME)}\s*=\s*$",
            text,
            re.MULTILINE,
        )
        empty_quoted = re.search(
            rf'^{re.escape(KEY_NAME)}\s*=\s*["\']\s*["\']\s*$',
            text,
            re.MULTILINE,
        )
        if empty or empty_quoted:
            key = _generate_key()
            text = KEY_LINE_RE.sub(f"{KEY_NAME}={key}", text, count=1)
            env_path.write_text(text, encoding="utf-8")
            updated = True
            return {
                "ok": True,
                "action": "filled_empty",
                "path": str(env_path),
                "key_configured": True,
                "key_printed": False,
            }
        return {
            "ok": True,
            "action": "unchanged",
            "path": str(env_path),
            "key_configured": True,
            "key_printed": False,
        }

    key = _generate_key()
    block = (
        "\n# Phase 20.10B-1 — AES-GCM embedding storage (NEVER commit / NEVER share)\n"
        f"{KEY_NAME}={key}\n"
    )
    if text and not text.endswith("\n"):
        text += "\n"
    text += block
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(text, encoding="utf-8")
    return {
        "ok": True,
        "action": "created" if created else "appended",
        "path": str(env_path),
        "key_configured": True,
        "key_printed": False,
    }


def main() -> int:
    result = ensure_storage_key()
    # Never print the key — only status.
    print(
        f"ok={result['ok']} action={result['action']} "
        f"key_configured={result['key_configured']} key_printed=False"
    )
    print("Restart Titan processes to pick up .env changes.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

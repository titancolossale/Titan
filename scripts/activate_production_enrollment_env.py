# =====================================
# Titan Phase 20.10B-1 Production Env Activation
# =====================================

"""Activate production enrollment environment flags in local ``.env``.

Sets ECAPA provider, production biometric trust, AES-GCM encryption flags.
Ensures a storage key exists (never prints it). Does not record anyone.

Usage (from project root):

    python scripts/activate_production_enrollment_env.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENV_PATH = ROOT / ".env"

# Non-secret production activation pairs.
ACTIVATION_VARS: dict[str, str] = {
    "TITAN_VOICE_EMBEDDING_PROVIDER": "ecapa",
    "TITAN_VOICE_EMBEDDING_VERSION": "ecapa_v1",
    "TITAN_VOICE_BIOMETRIC_TRUST_MODE": "production",
    "TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST": "true",
    "TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY": "false",
    "TITAN_VOICE_EMBEDDING_ENCRYPTION": "true",
    "TITAN_VOICE_EMBEDDING_RETAIN_RAW_AUDIO": "false",
    "TITAN_VOICE_EMBEDDING_KEY_ID": "primary",
    "TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT": "true",
    "TITAN_VOICE_ALWAYS_LISTENING": "false",
    "TITAN_VOICE_WAKE_WORD_ENABLED": "false",
}


def _upsert_env_var(text: str, key: str, value: str) -> tuple[str, str]:
    """Return (new_text, action) where action is created|updated|unchanged."""
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    match = pattern.search(text)
    line = f"{key}={value}"
    if match:
        current = match.group(0)
        if current.strip() == line:
            return text, "unchanged"
        return pattern.sub(line, text, count=1), "updated"
    if text and not text.endswith("\n"):
        text += "\n"
    text += f"{line}\n"
    return text, "created"


def activate_production_enrollment_env(*, env_path: Path = ENV_PATH) -> dict[str, object]:
    """Write production enrollment activation flags + ensure encryption key."""
    import importlib.util

    key_mod_path = ROOT / "scripts" / "ensure_voice_embedding_storage_key.py"
    spec = importlib.util.spec_from_file_location(
        "ensure_voice_embedding_storage_key", key_mod_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load ensure_voice_embedding_storage_key module")
    key_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(key_mod)

    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    actions: dict[str, str] = {}

    header = (
        "\n# Phase 20.10B-1 — production enrollment activation "
        "(non-secret flags; key separate)\n"
    )
    if "Phase 20.10B-1 — production enrollment activation" not in text:
        if text and not text.endswith("\n"):
            text += "\n"
        text += header

    for key, value in ACTIVATION_VARS.items():
        text, action = _upsert_env_var(text, key, value)
        actions[key] = action

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(text, encoding="utf-8")

    key_result = key_mod.ensure_storage_key(env_path=env_path)
    return {
        "ok": True,
        "path": str(env_path),
        "actions": actions,
        "storage_key": {
            "action": key_result.get("action"),
            "key_configured": key_result.get("key_configured"),
            "key_printed": False,
        },
        "records_biometric_samples": False,
    }


def main() -> int:
    result = activate_production_enrollment_env()
    print(f"ok={result['ok']} path={result['path']}")
    for key, action in (result.get("actions") or {}).items():
        print(f"  {key}: {action}")
    key_info = result.get("storage_key") or {}
    print(
        f"  TITAN_VOICE_EMBEDDING_STORAGE_KEY: {key_info.get('action')} "
        f"configured={key_info.get('key_configured')} printed=False"
    )
    print("Restart Titan processes to pick up .env changes.")
    print("Next: python scripts/phase20_10b1_enrollment_preflight.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

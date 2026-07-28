# =====================================
# Phase 19.4 — Environment validation (no secrets printed)
# =====================================
"""Confirm provider/key/DB/auth/stream/health without exposing secrets."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


def _present(name: str) -> dict:
    value = os.getenv(name, "")
    return {
        "name": name,
        "set": bool(value.strip()),
        "length": len(value.strip()) if value else 0,
    }


def main() -> int:
    report: dict = {"ok": True, "checks": []}

    # --- API key present (never print value) ---
    key = os.getenv("OPENAI_API_KEY", "").strip()
    key_ok = bool(key) and key != "your_key_here" and len(key) > 20
    report["checks"].append(
        {
            "name": "openai_api_key_loaded",
            "ok": key_ok,
            "length": len(key) if key else 0,
        }
    )
    if not key_ok:
        report["ok"] = False

    model = os.getenv("TITAN_LLM_MODEL", "gpt-5.2").strip()
    report["checks"].append({"name": "configured_model", "ok": bool(model), "model": model})

    # --- Settings contract ---
    from config import settings

    stream_on = bool(getattr(settings, "TITAN_CONVERSATION_STREAM_ENABLED", False))
    auth_required = bool(getattr(settings, "TITAN_AUTH_REQUIRED", False))
    persist_on = bool(getattr(settings, "TITAN_CONVERSATION_PERSISTENCE_ENABLED", False))
    db_url = (getattr(settings, "TITAN_DATABASE_URL", "") or "").strip()
    public_base = (getattr(settings, "TITAN_PUBLIC_BASE_URL", "") or "").strip()
    app_env = getattr(settings, "TITAN_APP_ENV", "development")

    report["checks"].append(
        {
            "name": "streaming_enabled",
            "ok": stream_on,
            "value": stream_on,
        }
    )
    if not stream_on:
        report["ok"] = False

    report["checks"].append(
        {
            "name": "auth_required",
            "ok": True,  # informational for local; production must be true
            "value": auth_required,
            "app_env": app_env,
            "production_expectation": app_env == "production" and auth_required,
        }
    )

    report["checks"].append(
        {
            "name": "conversation_persistence_enabled",
            "ok": persist_on,
            "value": persist_on,
        }
    )

    # DB URL may contain password — never print it
    db_scheme = ""
    if db_url:
        db_scheme = db_url.split("://", 1)[0]
    report["checks"].append(
        {
            "name": "database_url",
            "ok": bool(db_url) if app_env == "production" else True,
            "set": bool(db_url),
            "scheme": db_scheme or "sqlite-fallback-expected-when-empty",
            "is_postgres": db_scheme.startswith("postgres"),
        }
    )

    report["checks"].append(
        {
            "name": "public_base_url",
            "ok": True,
            "set": bool(public_base),
            "value": public_base or None,
        }
    )

    report["checks"].extend(
        [
            _present("TITAN_AUTH_USERNAME"),
            {
                **_present("TITAN_AUTH_PASSWORD_HASH"),
                "name": "TITAN_AUTH_PASSWORD_HASH",
            },
        ]
    )

    # --- Provider reachability (models.list or lightweight probe) ---
    provider_ok = False
    provider_detail: dict = {}
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        # Prefer listing models filtered by configured model id
        models = client.models.list()
        ids = {m.id for m in models.data}
        model_exists = model in ids
        # Some model ids may not appear in list (e.g. dated aliases) — try a tiny responses call
        if not model_exists:
            try:
                client.with_options(timeout=30.0).responses.create(
                    model=model,
                    input="ping",
                    max_output_tokens=5,
                )
                model_exists = True
                provider_detail["probe"] = "responses.create_ok"
            except Exception as exc:  # noqa: BLE001 — report exact layer
                provider_detail["probe_error"] = type(exc).__name__
                provider_detail["probe_message"] = str(exc)[:200]
        else:
            provider_detail["probe"] = "models.list_contains_model"
        provider_ok = model_exists
        provider_detail["model"] = model
        provider_detail["models_listed"] = len(ids)
    except Exception as exc:  # noqa: BLE001
        provider_detail["error_type"] = type(exc).__name__
        provider_detail["error_message"] = str(exc)[:200]
        report["ok"] = False

    report["checks"].append(
        {
            "name": "provider_reachable_and_model_exists",
            "ok": provider_ok,
            **provider_detail,
        }
    )
    if not provider_ok:
        report["ok"] = False

    # --- Local Postgres readiness if URL present ---
    if db_url and db_scheme.startswith("postgres"):
        pg_ok = False
        pg_detail: dict = {}
        try:
            import psycopg

            with psycopg.connect(db_url, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            pg_ok = True
            pg_detail["select_1"] = True
        except Exception as exc:  # noqa: BLE001
            pg_detail["error_type"] = type(exc).__name__
            pg_detail["error_message"] = str(exc)[:200]
            if app_env == "production":
                report["ok"] = False
        report["checks"].append(
            {"name": "postgres_reachable", "ok": pg_ok, **pg_detail}
        )
    else:
        report["checks"].append(
            {
                "name": "postgres_reachable",
                "ok": None,
                "skipped": True,
                "reason": "no postgres URL in local env; Railway preferred for final validation",
            }
        )

    # --- Railway health/ready if public URL known ---
    targets = []
    if public_base:
        targets.append(public_base.rstrip("/"))
    # Documented production host from auth docs
    targets.append("https://titan-production-e377.up.railway.app")
    targets = list(dict.fromkeys(targets))

    import urllib.request

    for base in targets:
        for path in ("/health", "/ready"):
            url = f"{base}{path}"
            entry: dict = {"name": f"endpoint:{url}", "ok": False}
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    entry["status"] = resp.status
                    entry["ok"] = 200 <= resp.status < 300
                    try:
                        entry["body_keys"] = list(json.loads(body).keys())[:20]
                    except json.JSONDecodeError:
                        entry["body_preview"] = body[:120]
            except Exception as exc:  # noqa: BLE001
                entry["error_type"] = type(exc).__name__
                entry["error_message"] = str(exc)[:200]
            report["checks"].append(entry)

    out = ROOT / "data" / "phase19_4_env_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

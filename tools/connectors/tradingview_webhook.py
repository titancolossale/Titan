# =====================================
# Titan TradingView Webhook Handler
# =====================================

"""HTTP-agnostic webhook entry point for TradingView alerts (Phase 16.2)."""

from __future__ import annotations

import json
from typing import Any

from tools.connectors.tradingview_provider import TradingViewProvider


def handle_tradingview_webhook(
    body: str | bytes,
    *,
    headers: dict[str, str] | None = None,
    provider: TradingViewProvider | None = None,
    secret: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Process a TradingView webhook POST body.

    Returns ``(status_code, response_dict)`` for HTTP servers (FastAPI, Flask, etc.).
    Does not place orders — persists and returns the extracted signal only.
    """
    backend = provider or TradingViewProvider()
    try:
        signal = backend.receive_alert(body, headers=headers, secret=secret)
    except ValueError as exc:
        message = str(exc)
        status = 401 if "Secret" in message or "secret" in message else 400
        return status, {"ok": False, "error": message}

    return 200, {
        "ok": True,
        "alert_id": signal.alert_id,
        "signal": signal.to_dict(),
    }


def parse_webhook_body(body: str | bytes) -> str | dict[str, Any]:
    """Normalize webhook body to str or dict for provider consumption."""
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    text = str(body).strip()
    if not text:
        return ""
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return text
    return decoded if isinstance(decoded, dict) else text

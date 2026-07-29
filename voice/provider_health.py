# =====================================
# Titan Voice Provider Health Aggregator
# =====================================

"""Fleet-wide provider / transport / embedding health snapshot (Phase 20.8)."""

from __future__ import annotations

import logging
import time
from typing import Any

from voice.diagnostics import emit_voice_diagnostic
from voice.embedding_provider import get_embedding_provider
from voice.providers.realtime_registry import (
    RealtimeProviderRegistry,
    get_realtime_registry,
)
from voice.transport.browser_hub import BrowserVoiceHub, get_browser_voice_hub
from voice.transport.socket_backends import websocket_client_available

logger = logging.getLogger(__name__)


def collect_provider_health(
    *,
    realtime_registry: RealtimeProviderRegistry | None = None,
    browser_hub: BrowserVoiceHub | None = None,
    include_capabilities: bool = True,
) -> dict[str, Any]:
    """Aggregate provider health, connection state, embedding + transport info."""
    registry = realtime_registry or get_realtime_registry()
    hub = browser_hub or get_browser_voice_hub()
    started = time.perf_counter()

    stt_health: list[dict[str, Any]] = []
    for provider_id in registry.list_stt():
        entry: dict[str, Any] = {"provider_id": provider_id, "role": "stt"}
        try:
            provider = registry.create_stt(provider_id)
            entry["healthy"] = bool(provider.health_check())
            if include_capabilities:
                caps = provider.capabilities
                entry["capabilities"] = caps.to_dict() if hasattr(caps, "to_dict") else {}
        except Exception as exc:
            entry["healthy"] = False
            entry["error"] = type(exc).__name__
        stt_health.append(entry)

    tts_health: list[dict[str, Any]] = []
    for provider_id in registry.list_tts():
        entry = {"provider_id": provider_id, "role": "tts"}
        try:
            provider = registry.create_tts(provider_id)
            entry["healthy"] = bool(provider.health_check())
            if include_capabilities:
                caps = provider.capabilities
                entry["capabilities"] = caps.to_dict() if hasattr(caps, "to_dict") else {}
        except Exception as exc:
            entry["healthy"] = False
            entry["error"] = type(exc).__name__
        tts_health.append(entry)

    embedding = get_embedding_provider()
    from voice.embedding_provider import get_embedding_registry

    embedding_registry = get_embedding_registry()
    embedding_info = {
        "embedding_version": embedding.embedding_version,
        "dimension": embedding.dimension,
        "available": embedding.is_available,
        "language_independent": True,
        "upgrade_ready": True,
        "providers": embedding_registry.list_providers(),
    }

    browser = hub.diagnostics_snapshot()
    snapshot = {
        "ok": True,
        "generated_at": time.time(),
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "live_socket_backend_available": websocket_client_available(),
        "stt": stt_health,
        "tts": tts_health,
        "stt_fallback": registry.stt_fallback_chain(),
        "tts_fallback": registry.tts_fallback_chain(),
        "embedding": embedding_info,
        "browser_transport": browser,
        "connection_state": {
            "browser_connections": browser.get("connection_count", 0),
            "browser_sessions": browser.get("session_bindings", 0),
        },
    }
    emit_voice_diagnostic(
        "PROVIDER_HEALTH_SNAPSHOT",
        stt_count=len(stt_health),
        tts_count=len(tts_health),
        live_socket_backend_available=snapshot["live_socket_backend_available"],
        browser_connections=snapshot["connection_state"]["browser_connections"],
    )
    return snapshot

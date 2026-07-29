# =====================================
# Titan Streaming Provider Failover
# =====================================

"""Disconnect / timeout / retry / fallback / manual switch (Phase 20.6)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from voice.exceptions import VoiceProviderError
from voice.providers.realtime_registry import RealtimeProviderRegistry, get_realtime_registry
from voice.providers.realtime_stt import RealtimeSTTProvider
from voice.providers.realtime_tts import RealtimeTTSProvider
from voice.transport.manager import TransportManager
from voice.transport.reconnect import ReconnectPolicy

logger = logging.getLogger(__name__)

FailoverEmit = Callable[[str, dict[str, Any]], None]


@dataclass
class FailoverConfig:
    max_retries: int = 3
    retry_base_delay_seconds: float = 0.2
    provider_timeout_seconds: float = 30.0
    sleep: Callable[[float], None] = field(default=time.sleep)


class StreamingProviderFailover:
    """Owns active realtime STT/TTS with automatic and manual recovery."""

    def __init__(
        self,
        *,
        registry: RealtimeProviderRegistry | None = None,
        preferred_stt: str = "mock_realtime_stt",
        preferred_tts: str = "mock_realtime_tts",
        config: FailoverConfig | None = None,
        transport_manager: TransportManager | None = None,
        emit: FailoverEmit | None = None,
    ) -> None:
        self._registry = registry or get_realtime_registry()
        self._config = config or FailoverConfig()
        self._emit = emit
        self._transport_manager = transport_manager
        self._preferred_stt = preferred_stt
        self._preferred_tts = preferred_tts
        self._stt: RealtimeSTTProvider | None = None
        self._tts: RealtimeTTSProvider | None = None
        self._stt_fallbacks: list[str] = []
        self._tts_fallbacks: list[str] = []
        self._retry_counts: dict[str, int] = {"stt": 0, "tts": 0}
        self._last_error: str | None = None
        # Reuse one policy instance — avoids per-retry allocations (Phase 20.8).
        self._retry_policy = ReconnectPolicy(
            max_attempts=self._config.max_retries,
            base_delay_seconds=self._config.retry_base_delay_seconds,
        )

    @property
    def stt(self) -> RealtimeSTTProvider:
        if self._stt is None:
            self.activate()
        assert self._stt is not None
        return self._stt

    @property
    def tts(self) -> RealtimeTTSProvider:
        if self._tts is None:
            self.activate()
        assert self._tts is not None
        return self._tts

    def activate(self) -> None:
        self._stt, self._stt_fallbacks = self._registry.resolve_stt_with_fallback(
            self._preferred_stt
        )
        self._tts, self._tts_fallbacks = self._registry.resolve_tts_with_fallback(
            self._preferred_tts
        )
        self._fire(
            "PROVIDER_FAILOVER_ACTIVATED",
            {
                "stt": self._stt.provider_id,
                "tts": self._tts.provider_id,
                "stt_fallbacks": list(self._stt_fallbacks),
                "tts_fallbacks": list(self._tts_fallbacks),
            },
        )

    def on_provider_disconnect(self, *, side: str = "stt") -> bool:
        self._fire("PROVIDER_DISCONNECT", {"side": side})
        return self._retry_or_fallback(side=side, reason="disconnect")

    def on_network_loss(self) -> bool:
        self._fire("PROVIDER_NETWORK_LOSS", {})
        recovered = False
        if self._transport_manager is not None:
            recovered = self._transport_manager.recover(reason="network_loss")
        stt_ok = self._retry_or_fallback(side="stt", reason="network_loss")
        tts_ok = self._retry_or_fallback(side="tts", reason="network_loss")
        return recovered or stt_ok or tts_ok

    def on_provider_timeout(self, *, side: str = "stt") -> bool:
        self._fire("PROVIDER_TIMEOUT", {"side": side})
        return self._retry_or_fallback(side=side, reason="timeout")

    def switch_stt(self, provider_id: str) -> RealtimeSTTProvider:
        """Manual STT provider switching."""
        previous = self._stt.provider_id if self._stt else None
        if self._stt is not None:
            try:
                self._stt.close()
            except Exception:
                pass
        self._stt = self._registry.create_stt(provider_id)
        self._preferred_stt = provider_id
        self._fire(
            "PROVIDER_SWITCHED",
            {"side": "stt", "from": previous, "to": self._stt.provider_id},
        )
        return self._stt

    def switch_tts(self, provider_id: str) -> RealtimeTTSProvider:
        previous = self._tts.provider_id if self._tts else None
        if self._tts is not None:
            try:
                self._tts.close()
            except Exception:
                pass
        self._tts = self._registry.create_tts(provider_id)
        self._preferred_tts = provider_id
        self._fire(
            "PROVIDER_SWITCHED",
            {"side": "tts", "from": previous, "to": self._tts.provider_id},
        )
        return self._tts

    def run_with_stt_retry(self, operation: Callable[[RealtimeSTTProvider], Any]) -> Any:
        """Execute an STT operation with timeout + retry + fallback."""
        policy = self._retry_policy
        attempt = 0
        last_exc: Exception | None = None
        while policy.should_retry(attempt):
            try:
                started = time.perf_counter()
                result = operation(self.stt)
                elapsed = time.perf_counter() - started
                if elapsed > self._config.provider_timeout_seconds:
                    raise VoiceProviderError("STT provider timeout")
                self._retry_counts["stt"] = 0
                return result
            except Exception as exc:
                last_exc = exc
                self._last_error = type(exc).__name__
                attempt += 1
                self._fire(
                    "PROVIDER_RETRY",
                    {"side": "stt", "attempt": attempt, "error": self._last_error},
                )
                if not self._retry_or_fallback(side="stt", reason="operation_error"):
                    break
                self._config.sleep(policy.delay_for_attempt(attempt - 1))
        raise VoiceProviderError(f"STT failover exhausted: {last_exc}") from last_exc

    def run_with_tts_retry(self, operation: Callable[[RealtimeTTSProvider], Any]) -> Any:
        policy = self._retry_policy
        attempt = 0
        last_exc: Exception | None = None
        while policy.should_retry(attempt):
            try:
                started = time.perf_counter()
                result = operation(self.tts)
                elapsed = time.perf_counter() - started
                if elapsed > self._config.provider_timeout_seconds:
                    raise VoiceProviderError("TTS provider timeout")
                self._retry_counts["tts"] = 0
                return result
            except Exception as exc:
                last_exc = exc
                self._last_error = type(exc).__name__
                attempt += 1
                self._fire(
                    "PROVIDER_RETRY",
                    {"side": "tts", "attempt": attempt, "error": self._last_error},
                )
                if not self._retry_or_fallback(side="tts", reason="operation_error"):
                    break
                self._config.sleep(policy.delay_for_attempt(attempt - 1))
        raise VoiceProviderError(f"TTS failover exhausted: {last_exc}") from last_exc

    def diagnostics(self) -> dict[str, Any]:
        return {
            "stt_provider": self._stt.provider_id if self._stt else None,
            "tts_provider": self._tts.provider_id if self._tts else None,
            "stt_fallbacks": list(self._stt_fallbacks),
            "tts_fallbacks": list(self._tts_fallbacks),
            "retry_counts": dict(self._retry_counts),
            "last_error": self._last_error,
            "transport": (
                self._transport_manager.metrics()
                if self._transport_manager is not None
                else None
            ),
        }

    def close(self) -> None:
        for provider in (self._stt, self._tts):
            if provider is None:
                continue
            try:
                provider.close()
            except Exception:
                pass
        if self._transport_manager is not None:
            self._transport_manager.shutdown()

    def _retry_or_fallback(self, *, side: str, reason: str) -> bool:
        self._retry_counts[side] = self._retry_counts.get(side, 0) + 1
        if side == "stt":
            if self._retry_counts["stt"] <= self._config.max_retries and self._stt is not None:
                try:
                    # Soft reopen — start() is caller's responsibility after recover.
                    self._fire(
                        "PROVIDER_RETRY",
                        {
                            "side": "stt",
                            "reason": reason,
                            "attempt": self._retry_counts["stt"],
                            "provider_id": self._stt.provider_id,
                        },
                    )
                    return True
                except Exception:
                    pass
            if not self._stt_fallbacks:
                self._fire(
                    "PROVIDER_FALLBACK_EXHAUSTED",
                    {"side": "stt", "reason": reason},
                )
                return False
            next_id = self._stt_fallbacks.pop(0)
            try:
                self.switch_stt(next_id)
                self._fire(
                    "PROVIDER_FALLBACK",
                    {"side": "stt", "to": next_id, "reason": reason},
                )
                return True
            except Exception as exc:
                self._last_error = type(exc).__name__
                return False

        if self._retry_counts["tts"] <= self._config.max_retries and self._tts is not None:
            self._fire(
                "PROVIDER_RETRY",
                {
                    "side": "tts",
                    "reason": reason,
                    "attempt": self._retry_counts["tts"],
                    "provider_id": self._tts.provider_id,
                },
            )
            return True
        if not self._tts_fallbacks:
            self._fire(
                "PROVIDER_FALLBACK_EXHAUSTED",
                {"side": "tts", "reason": reason},
            )
            return False
        next_id = self._tts_fallbacks.pop(0)
        try:
            self.switch_tts(next_id)
            self._fire(
                "PROVIDER_FALLBACK",
                {"side": "tts", "to": next_id, "reason": reason},
            )
            return True
        except Exception as exc:
            self._last_error = type(exc).__name__
            return False

    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception:
            pass

# =====================================
# Titan Phase 20.6 — True Realtime Streaming Providers Tests
# =====================================

"""Transport, provider switching, reconnect, failover, latency, diagnostics."""

from __future__ import annotations

from typing import Any

import pytest

from voice.diagnostics import VOICE_DIAGNOSTIC_EVENTS, VOICE_STREAM_EVENTS
from voice.latency_tracker import LatencyTracker
from voice.providers.deepgram_streaming import DeepgramStreamingSTT
from voice.providers.elevenlabs_streaming import ElevenLabsStreamingTTS
from voice.providers.failover import FailoverConfig, StreamingProviderFailover
from voice.providers.openai_realtime import OpenAIRealtimeSession
from voice.providers.openai_whisper_streaming import OpenAIWhisperStreamingSTT
from voice.providers.realtime_registry import RealtimeProviderRegistry
from voice.providers.realtime_stt import MockRealtimeSTTProvider
from voice.providers.realtime_tts import (
    AudioBufferConfig,
    MockRealtimeTTSProvider,
    SmoothedAudioBuffer,
)
from voice.providers.registry_bootstrap import register_realtime_voice_providers
from voice.providers.streaming_models import HypothesisStability
from voice.speech_to_text import TranscriptionResult
from voice.stream_performance import StreamPerformanceController
from voice.streaming_stt import IncrementalSTTConfig, IncrementalSTTEngine, TranscriptStage
from voice.streaming_tts import StreamingTTSEngine
from voice.transport import (
    HttpFallbackTransport,
    InMemoryTransport,
    ReconnectPolicy,
    ServerSentEventsTransport,
    TransportKind,
    TransportManager,
    TransportManagerConfig,
    WebSocketTransport,
    compute_backoff_seconds,
)
from voice.transport.base import TransportConfig, TransportState
from voice.tts_strategy import TTSStrategy, TTSStrategyConfig, TTSStrategyMode


def test_backoff_and_reconnect_policy() -> None:
    delay = compute_backoff_seconds(0, base_delay_seconds=0.25, jitter_ratio=0.0)
    assert delay == 0.25
    policy = ReconnectPolicy(max_attempts=3, base_delay_seconds=0.1, jitter_ratio=0.0)
    assert policy.should_retry(0)
    assert policy.should_retry(2)
    assert not policy.should_retry(3)
    assert policy.delay_for_attempt(1) == pytest.approx(0.2)


def test_inmemory_transport_send_receive_heartbeat_shutdown() -> None:
    events: list[str] = []
    transport = InMemoryTransport(
        TransportConfig(heartbeat_timeout_seconds=60.0),
        emit=lambda e, _d: events.append(e.value if hasattr(e, "value") else str(e)),
    )
    transport.connect()
    assert transport.is_connected
    seq = transport.send(b"hello", binary=True)
    assert seq == 0
    transport.peer_push({"ok": True} if False else '{"type":"pong"}')
    message = transport.receive(timeout=0.1)
    assert message is not None
    transport.heartbeat()
    assert transport.check_liveness()
    transport.disconnect(reason="test")
    assert transport.state == TransportState.CLOSED
    assert "TRANSPORT_CONNECTED" in events
    assert "TRANSPORT_CLOSED" in events


def test_websocket_sse_http_fallback_kinds() -> None:
    ws = WebSocketTransport(TransportConfig(url="ws://test"))
    ws.connect()
    assert ws.kind == TransportKind.WEBSOCKET
    ws.send(b"a", binary=True)
    ws.disconnect()

    sse = ServerSentEventsTransport(TransportConfig(url="https://test/events"))
    sse.connect()
    assert sse.kind == TransportKind.SSE
    sse.push_event("data: hello")
    msg = sse.receive(timeout=0.1)
    assert msg is not None
    assert "hello" in msg.as_text()
    sse.disconnect()

    http = HttpFallbackTransport(TransportConfig(url="https://test"))
    http.connect()
    assert http.kind == TransportKind.HTTP
    http.inject_response(b"chunk")
    got = http.receive(timeout=0.1)
    assert got is not None and got.as_bytes() == b"chunk"
    http.disconnect()


def test_transport_manager_reconnect_and_fallback() -> None:
    primary = InMemoryTransport(TransportConfig(max_reconnect_attempts=2), name="primary")
    fallback = HttpFallbackTransport(TransportConfig())
    sleeps: list[float] = []
    manager = TransportManager(
        primary,
        fallbacks=[fallback],
        config=TransportManagerConfig(auto_recover=True, sleep=lambda s: sleeps.append(s)),
        reconnect=ReconnectPolicy(max_attempts=2, base_delay_seconds=0.01, jitter_ratio=0.0),
    )
    manager.connect()
    assert manager.kind == TransportKind.MEMORY
    primary.mark_disconnected(reason="network")
    # Force recovery via failed primary reconnect then HTTP fallback.
    primary.disconnect(reason="force")
    # Make primary fail connect by closing permanently — use mark + recover.
    ok = manager.recover(reason="test")
    assert ok is True
    metrics = manager.metrics()
    assert metrics["recovery_attempts"] >= 1
    manager.switch_to(TransportKind.HTTP)
    assert manager.kind == TransportKind.HTTP
    manager.shutdown()
    assert manager.active.state == TransportState.CLOSED


def test_mock_realtime_stt_partial_stable_final_language_speaker() -> None:
    events: list[str] = []
    stt = MockRealtimeSTTProvider(
        final_text="bonjour titan agent",
        emit=lambda e, _d: events.append(e),
    )
    stt.set_speaker_id("nolan")
    stt.start(language="fr-FR")
    stt.send_audio(b"x" * 900)
    partial = stt.poll()
    assert partial is not None
    assert partial.stability == HypothesisStability.PARTIAL
    stt.send_audio(b"y" * 3000)
    stable = stt.poll()
    assert stable is not None
    assert stable.stability == HypothesisStability.STABLE
    stt.set_language("en-US")
    final = stt.finish()
    assert final is not None
    assert final.is_final
    assert final.speaker_id == "nolan"
    assert final.language == "en-US"
    assert "PROVIDER_STT_HYPOTHESIS" in events


def test_deepgram_streaming_hypothesis_injection() -> None:
    transport = InMemoryTransport(name="dg")
    stt = DeepgramStreamingSTT(transport=transport, api_key="")
    stt.start(language="fr-FR")
    stt.send_audio(b"pcm")
    stt.inject_deepgram_message(
        {
            "is_final": False,
            "start": 0.1,
            "duration": 0.5,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "bonjour",
                        "confidence": 0.6,
                        "words": [{"speaker": 0}],
                    }
                ]
            },
        }
    )
    hyp = stt.poll()
    assert hyp is not None
    assert hyp.text == "bonjour"
    assert hyp.stability == HypothesisStability.PARTIAL
    assert hyp.speaker_id == "0"
    stt.inject_deepgram_message(
        {
            "is_final": True,
            "channel": {"alternatives": [{"transcript": "bonjour titan", "confidence": 0.9}]},
        }
    )
    final = stt.finish()
    assert final is not None
    assert "titan" in final.text


def test_whisper_streaming_with_injected_transcribe() -> None:
    transport = InMemoryTransport(name="whisper")

    def _transcribe(audio: bytes, locale: str) -> TranscriptionResult:
        return TranscriptionResult(
            text="whisper final",
            duration_seconds=0.01,
            provider_id="openai_whisper_streaming",
            locale=locale,
            confidence=0.88,
        )

    stt = OpenAIWhisperStreamingSTT(
        transport=transport,
        transcribe_fn=_transcribe,
    )
    stt.start(language="fr-FR")
    stt.send_audio(b"a" * 2000)
    assert stt.poll() is not None  # partial
    stt.send_audio(b"b" * 7000)
    stable = stt.poll()
    assert stable is not None
    assert stable.stability == HypothesisStability.STABLE
    final = stt.finish()
    assert final is not None
    assert final.text == "whisper final"


def test_elevenlabs_streaming_chunks_and_cancel() -> None:
    transport = InMemoryTransport(name="eleven")
    tts = ElevenLabsStreamingTTS(
        transport=transport,
        api_key="",
        buffer_config=AudioBufferConfig(min_chunk_bytes=1),
    )
    tts.start(locale="fr-FR", voice="Rachel")
    tts.synthesize_incremental("Bonjour.")
    chunk = tts.poll_audio(force=True)
    assert chunk is not None
    assert chunk.audio_bytes
    tts.cancel()
    assert tts.cancel_token.cancelled


def test_openai_realtime_bidirectional_session() -> None:
    transport = InMemoryTransport(name="realtime")
    session = OpenAIRealtimeSession(transport=transport, api_key="")
    session.start(language="fr-FR")
    session.send_audio(b"pcm-audio")
    session.inject_provider_event(
        {"type": "transcript.partial", "text": "bon", "confidence": 0.4}
    )
    hyp = session.poll_hypothesis()
    assert hyp is not None and hyp.stability == HypothesisStability.PARTIAL
    session.synthesize_incremental("Réponse")
    audio = session.poll_audio()
    assert audio is not None
    final = session.finish_input()
    assert final is not None and final.is_final
    session.cancel()
    session.close()


def test_smoothed_audio_buffer_and_performance() -> None:
    buf = SmoothedAudioBuffer(AudioBufferConfig(min_chunk_bytes=10, max_pending_chunks=4))
    from voice.providers.streaming_models import AudioStreamChunk

    buf.push(AudioStreamChunk(audio_bytes=b"12345", sequence=0, provider_id="m"))
    assert buf.pop_ready() is None
    buf.push(AudioStreamChunk(audio_bytes=b"67890abcde", sequence=1, provider_id="m"))
    ready = buf.pop_ready()
    assert ready is not None
    assert len(ready.audio_bytes) >= 10

    perf = StreamPerformanceController()
    assert perf.ingest_mic_audio(b"x" * 100) is None
    block = perf.ingest_mic_audio(b"y" * 3200)
    assert block is not None
    assert perf.admit_tts_chunk(100)
    snap = perf.to_dict()
    assert snap["coalesce_count"] >= 1


def test_incremental_stt_engine_uses_realtime_provider() -> None:
    realtime = MockRealtimeSTTProvider(final_text="stable brain text")
    engine = IncrementalSTTEngine(
        locale="fr-FR",
        provider_id="mock",
        config=IncrementalSTTConfig(
            use_realtime_provider=True,
            coalesce_audio=False,
            partial_min_bytes=1,
            stable_min_bytes=1,
        ),
        realtime_provider=realtime,
    )
    engine.ingest_chunk(b"x" * 1000)
    engine.ingest_chunk(b"y" * 3000)
    assert engine.result.stage in {TranscriptStage.PARTIAL, TranscriptStage.STABLE}
    final = engine.finalize()
    assert final.stage == TranscriptStage.FINAL
    assert "brain" in final.brain_text or final.brain_text


def test_streaming_tts_engine_uses_realtime_provider() -> None:
    strategy = TTSStrategy(
        config=TTSStrategyConfig(mode=TTSStrategyMode.SENTENCE_BUFFERED),
        provider_id="mock",
    )
    realtime = MockRealtimeTTSProvider(chunk_size=32)
    engine = StreamingTTSEngine(
        strategy,
        realtime_provider=realtime,
        prefer_realtime=True,
    )
    result = engine.synthesize_from_deltas(
        ["Bonjour Titan."],
        full_text="Bonjour Titan.",
        locale="fr-FR",
    )
    assert result.chunks
    assert result.first_audio_ms >= 0.0


def test_provider_switching_and_fallback() -> None:
    registry = RealtimeProviderRegistry()

    class AltSTT(MockRealtimeSTTProvider):
        @property
        def provider_id(self) -> str:
            return "alt_stt"

    registry.register_stt("mock_realtime_stt", MockRealtimeSTTProvider)
    registry.register_stt("alt_stt", AltSTT)
    registry.set_stt_fallback_chain(["alt_stt", "mock_realtime_stt"])
    registry.register_tts("mock_realtime_tts", MockRealtimeTTSProvider)
    registry.set_tts_fallback_chain(["mock_realtime_tts"])

    events: list[str] = []
    failover = StreamingProviderFailover(
        registry=registry,
        preferred_stt="mock_realtime_stt",
        preferred_tts="mock_realtime_tts",
        config=FailoverConfig(max_retries=5, sleep=lambda _s: None),
        emit=lambda e, _d: events.append(e),
    )
    failover.activate()
    assert failover.stt.provider_id == "mock_realtime_stt"
    switched = failover.switch_stt("alt_stt")
    assert switched.provider_id == "alt_stt"
    assert "PROVIDER_SWITCHED" in events
    assert failover.on_provider_disconnect(side="stt")
    assert failover.on_network_loss()
    assert failover.on_provider_timeout(side="tts")
    diag = failover.diagnostics()
    assert diag["stt_provider"]
    failover.close()


def test_registry_bootstrap_lists_streaming_providers() -> None:
    registry = RealtimeProviderRegistry()
    register_realtime_voice_providers(realtime_registry=registry)
    stt_ids = registry.list_stt()
    tts_ids = registry.list_tts()
    assert "mock_realtime_stt" in stt_ids
    assert "openai_whisper_streaming" in stt_ids
    assert "deepgram_streaming" in stt_ids
    assert "elevenlabs_streaming" in tts_ids
    caps = registry.capabilities_snapshot()
    assert caps["stt"] and caps["tts"]


def test_stream_interruption_cancels_realtime_tts() -> None:
    strategy = TTSStrategy(provider_id="mock")
    realtime = MockRealtimeTTSProvider()
    engine = StreamingTTSEngine(
        strategy, realtime_provider=realtime, prefer_realtime=True
    )
    engine.cancel()
    assert engine.cancel_token.cancelled
    assert realtime.cancel_token.cancelled


def test_latency_tracker_phase20_6_marks() -> None:
    tracker = LatencyTracker()
    tracker.mark_mic_latency(12.5)
    tracker.mark_first_audio()
    tracker.mark_first_transcript()
    tracker.mark_provider_latency(40.0)
    tracker.mark_first_brain_token(8.0)
    tracker.mark_first_tts_audio(15.0)
    tracker.mark_stage_durations(stt_ms=20.0, brain_ms=30.0, tts_ms=25.0)
    tracker.mark_response_complete()
    data = tracker.to_dict()
    assert data["mic_latency_ms"] == 12.5
    assert data["provider_latency_ms"] == 40.0
    assert data["conversation_turnaround_ms"] > 0
    assert data["stt_ms"] == 20.0


def test_diagnostics_include_provider_events() -> None:
    assert "PROVIDER_STT_HYPOTHESIS" in VOICE_DIAGNOSTIC_EVENTS
    assert "PROVIDER_TTS_CHUNK" in VOICE_DIAGNOSTIC_EVENTS
    assert "PROVIDER_FALLBACK" in VOICE_DIAGNOSTIC_EVENTS
    assert "PROVIDER_TRANSPORT_RECOVERED" in VOICE_STREAM_EVENTS
    assert "PROVIDER_SWITCHED" in VOICE_STREAM_EVENTS


def test_provider_failover_run_with_retry() -> None:
    registry = RealtimeProviderRegistry()
    calls = {"n": 0}

    class Flaky(MockRealtimeSTTProvider):
        @property
        def provider_id(self) -> str:
            return "flaky_stt"

        def health_check(self) -> bool:
            return True

    registry.register_stt("flaky_stt", Flaky)
    registry.register_stt("mock_realtime_stt", MockRealtimeSTTProvider)
    registry.set_stt_fallback_chain(["mock_realtime_stt"])
    failover = StreamingProviderFailover(
        registry=registry,
        preferred_stt="flaky_stt",
        preferred_tts="mock_realtime_tts",
        config=FailoverConfig(max_retries=2, sleep=lambda _s: None),
    )
    failover.activate()

    def op(provider: Any) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return provider.provider_id

    result = failover.run_with_stt_retry(op)
    assert result
    assert calls["n"] >= 2

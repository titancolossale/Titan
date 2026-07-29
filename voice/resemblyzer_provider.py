# =====================================
# Titan Resemblyzer Embedding Backend
# =====================================

"""Resemblyzer-compatible speaker embedding fallback (Phase 20.12).

Activated when the ``resemblyzer`` package is installed. Lazy model load;
missing dependency → unavailable without affecting ``/health`` / ``/ready``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Iterable

from voice.audio_prep import decode_pcm16_mono
from voice.ecapa_provider import ProviderInitStatus, normalize_embedding
from voice.embedding_capabilities import (
    EmbeddingBackendFamily,
    EmbeddingCapabilities,
    EmbeddingTrustLevel,
)
from voice.embedding_provider import (
    RESEMBLYZER_VERSION,
    LocalEmbeddingProvider,
)
from voice.exceptions import VoiceConfigurationError

logger = logging.getLogger(__name__)

RESEMBLYZER_MODEL_VERSION = "resemblyzer_ge2e_v1"
RESEMBLYZER_DIM = 256
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_INIT_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_VOICE_RESEMBLYZER_INIT_TIMEOUT", "60")
)


def probe_resemblyzer_dependencies() -> dict[str, Any]:
    """Detect Resemblyzer availability without loading the encoder."""
    ok = False
    error: str | None = None
    try:
        import resemblyzer  # noqa: F401

        ok = True
    except Exception as exc:  # pragma: no cover — env dependent
        error = type(exc).__name__
    return {
        "resemblyzer": ok,
        "available": ok,
        "error": error,
        "model_version": RESEMBLYZER_MODEL_VERSION,
    }


class ResemblyzerEmbeddingProvider(LocalEmbeddingProvider):
    """Resemblyzer VoiceEncoder backend (production-trusted when available)."""

    def __init__(
        self,
        *,
        init_timeout_seconds: float = DEFAULT_INIT_TIMEOUT_SECONDS,
        inference_fn: Callable[[bytes], list[float]] | None = None,
        force_available: bool | None = None,
    ) -> None:
        self._init_timeout = max(1.0, float(init_timeout_seconds))
        self._inference_fn = inference_fn
        self._encoder: Any | None = None
        self._lock = threading.RLock()
        self._init_status = ProviderInitStatus.NOT_LOADED
        self._init_error: str | None = None
        self._init_ms: float | None = None
        self._deps = probe_resemblyzer_dependencies()
        if force_available is not None:
            self._deps_available = bool(force_available)
        elif inference_fn is not None:
            self._deps_available = True
        else:
            self._deps_available = bool(self._deps.get("available"))
        if not self._deps_available and inference_fn is None:
            self._init_status = ProviderInitStatus.UNAVAILABLE

    @property
    def embedding_version(self) -> str:
        return RESEMBLYZER_VERSION

    @property
    def dimension(self) -> int:
        return RESEMBLYZER_DIM

    @property
    def provider_id(self) -> str:
        return "resemblyzer"

    @property
    def model_version(self) -> str:
        return RESEMBLYZER_MODEL_VERSION

    @property
    def init_status(self) -> ProviderInitStatus:
        return self._init_status

    @property
    def is_available(self) -> bool:
        return self._deps_available

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        trust = (
            EmbeddingTrustLevel.PRODUCTION
            if self._deps_available
            else EmbeddingTrustLevel.UNAVAILABLE
        )
        return EmbeddingCapabilities(
            provider_id=self.provider_id,
            embedding_version=self.embedding_version,
            dimension=self.dimension,
            backend_family=EmbeddingBackendFamily.RESEMBLYZER,
            trust_level=trust,
            available=self._deps_available,
            requires_external_dependency=True,
            requires_network=False,
            notes=(
                "Resemblyzer GE2E VoiceEncoder fallback.",
                f"init_status={self._init_status.value}",
            ),
        )

    def ensure_loaded(self) -> None:
        if self._inference_fn is not None:
            self._init_status = ProviderInitStatus.READY
            return
        if not self._deps_available:
            self._init_status = ProviderInitStatus.UNAVAILABLE
            raise VoiceConfigurationError(
                "Resemblyzer dependency unavailable.",
                code="resemblyzer_deps_unavailable",
            )
        with self._lock:
            if self._init_status == ProviderInitStatus.READY and self._encoder is not None:
                return
            if self._init_status == ProviderInitStatus.FAILED:
                raise VoiceConfigurationError(
                    f"Resemblyzer initialization previously failed: {self._init_error}",
                    code="resemblyzer_init_failed",
                )
            self._init_status = ProviderInitStatus.LOADING
            started = time.perf_counter()
            try:
                from resemblyzer import VoiceEncoder  # type: ignore

                self._encoder = VoiceEncoder()
                elapsed = (time.perf_counter() - started) * 1000.0
                if elapsed > self._init_timeout * 1000.0:
                    self._init_status = ProviderInitStatus.FAILED
                    self._init_error = "init_timeout"
                    self._encoder = None
                    raise VoiceConfigurationError(
                        "Resemblyzer initialization exceeded timeout.",
                        code="resemblyzer_init_timeout",
                    )
                self._init_ms = round(elapsed, 2)
                self._init_status = ProviderInitStatus.READY
                logger.info("RESEMBLYZER_MODEL_READY init_ms=%.2f", self._init_ms)
            except VoiceConfigurationError:
                raise
            except Exception as exc:
                self._init_status = ProviderInitStatus.FAILED
                self._init_error = type(exc).__name__
                self._encoder = None
                logger.warning(
                    "RESEMBLYZER_MODEL_INIT_FAILED error=%s", type(exc).__name__
                )
                raise VoiceConfigurationError(
                    f"Resemblyzer initialization failed: {type(exc).__name__}",
                    code="resemblyzer_init_failed",
                ) from exc

    def extract(self, audio_bytes: bytes) -> list[float]:
        if not audio_bytes:
            return [0.0] * self.dimension
        if self._inference_fn is not None:
            self.ensure_loaded()
            return normalize_embedding(self._inference_fn(audio_bytes))
        self.ensure_loaded()
        assert self._encoder is not None
        samples, _rate = decode_pcm16_mono(
            audio_bytes,
            source_rate=DEFAULT_SAMPLE_RATE,
            target_rate=DEFAULT_SAMPLE_RATE,
        )
        if not samples:
            return [0.0] * self.dimension
        try:
            import numpy as np

            wav = np.asarray(samples, dtype=np.float32)
            emb = self._encoder.embed_utterance(wav)
            flat = [float(v) for v in emb.tolist()]
            if len(flat) < self.dimension:
                flat = flat + [0.0] * (self.dimension - len(flat))
            elif len(flat) > self.dimension:
                flat = flat[: self.dimension]
            return normalize_embedding(flat)
        except VoiceConfigurationError:
            raise
        except Exception as exc:
            raise VoiceConfigurationError(
                f"Resemblyzer inference failed: {type(exc).__name__}",
                code="resemblyzer_inference_failed",
            ) from exc

    def health_dict(self) -> dict[str, object]:
        base = super().health_dict()
        base.update(
            {
                "model_version": self.model_version,
                "init_status": self._init_status.value,
                "init_error": self._init_error,
                "init_ms": self._init_ms,
                "dependencies": {"resemblyzer": self._deps.get("resemblyzer")},
                "lazy_load": True,
                "deterministic_inference": True,
                "normalized_embeddings": True,
            }
        )
        return base

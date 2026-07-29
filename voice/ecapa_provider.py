# =====================================
# Titan ECAPA-TDNN Embedding Backend
# =====================================

"""Production-capable local ECAPA-TDNN speaker embedding provider (Phase 20.12).

Uses SpeechBrain ``spkrec-ecapa-voxceleb`` when ``torch`` + ``speechbrain`` are
installed. Model loading is lazy and bounded; missing dependencies never crash
process startup or ``/health`` / ``/ready``.

Inference is deterministic (eval mode + ``inference_mode``) and L2-normalized.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

from voice.audio_prep import decode_pcm16_mono
from voice.embedding_capabilities import (
    EmbeddingBackendFamily,
    EmbeddingCapabilities,
    EmbeddingTrustLevel,
)
from voice.embedding_provider import ECAPA_VERSION, LocalEmbeddingProvider
from voice.exceptions import VoiceConfigurationError

logger = logging.getLogger(__name__)

ECAPA_MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
ECAPA_MODEL_VERSION = "ecapa_tdnn_voxceleb_v1"
ECAPA_DIM = 192
DEFAULT_SAMPLE_RATE = 16000

# Bound first-load wait so callers can fail gracefully (seconds).
DEFAULT_INIT_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_VOICE_ECAPA_INIT_TIMEOUT", "120")
)


class ProviderInitStatus(str, Enum):
    """Lazy model initialization lifecycle."""

    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


def probe_ecapa_dependencies() -> dict[str, Any]:
    """Detect optional ECAPA runtime deps without loading the model."""
    torch_ok = False
    torchaudio_ok = False
    speechbrain_ok = False
    torch_error: str | None = None
    torchaudio_error: str | None = None
    speechbrain_error: str | None = None
    try:
        import torch  # noqa: F401

        torch_ok = True
    except Exception as exc:  # pragma: no cover — env dependent
        torch_error = type(exc).__name__
    try:
        import torchaudio  # noqa: F401

        torchaudio_ok = True
    except Exception as exc:  # pragma: no cover — env dependent
        torchaudio_error = type(exc).__name__
    try:
        import speechbrain  # noqa: F401

        speechbrain_ok = True
    except Exception as exc:  # pragma: no cover — env dependent
        speechbrain_error = type(exc).__name__
    return {
        "torch": torch_ok,
        "torchaudio": torchaudio_ok,
        "speechbrain": speechbrain_ok,
        # SpeechBrain ECAPA needs torch + speechbrain; torchaudio is strongly
        # recommended and reported separately for production diagnostics.
        "available": torch_ok and speechbrain_ok,
        "torch_error": torch_error,
        "torchaudio_error": torchaudio_error,
        "speechbrain_error": speechbrain_error,
        "model_source": ECAPA_MODEL_SOURCE,
        "model_version": ECAPA_MODEL_VERSION,
    }


def normalize_embedding(values: Iterable[float]) -> list[float]:
    """L2-normalize an embedding vector."""
    vec = [float(v) for v in values]
    if not vec:
        return []
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class EcapaEmbeddingProvider(LocalEmbeddingProvider):
    """Real ECAPA-TDNN speaker embedding backend (lazy, CPU-compatible)."""

    def __init__(
        self,
        *,
        model_source: str = ECAPA_MODEL_SOURCE,
        savedir: str | Path | None = None,
        device: str | None = None,
        init_timeout_seconds: float = DEFAULT_INIT_TIMEOUT_SECONDS,
        inference_fn: Callable[[bytes], list[float]] | None = None,
        force_available: bool | None = None,
    ) -> None:
        self._model_source = model_source
        self._savedir = Path(
            savedir
            or os.getenv(
                "TITAN_VOICE_ECAPA_MODEL_DIR",
                "data/voice_models/ecapa",
            )
        )
        self._device = (device or os.getenv("TITAN_VOICE_ECAPA_DEVICE", "cpu")).strip()
        self._init_timeout = max(1.0, float(init_timeout_seconds))
        self._inference_fn = inference_fn
        self._classifier: Any | None = None
        self._lock = threading.RLock()
        self._init_status = ProviderInitStatus.NOT_LOADED
        self._init_error: str | None = None
        self._init_ms: float | None = None
        self._deps = probe_ecapa_dependencies()
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
        return ECAPA_VERSION

    @property
    def dimension(self) -> int:
        return ECAPA_DIM

    @property
    def provider_id(self) -> str:
        return "ecapa"

    @property
    def model_version(self) -> str:
        return ECAPA_MODEL_VERSION

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
            backend_family=EmbeddingBackendFamily.ECAPA_TDNN,
            trust_level=trust,
            available=self._deps_available,
            requires_external_dependency=True,
            requires_network=False,
            notes=(
                f"ECAPA-TDNN ({ECAPA_MODEL_SOURCE}).",
                f"init_status={self._init_status.value}",
                "Lazy CPU inference; missing deps → unavailable (not /ready failure).",
            ),
        )

    def ensure_loaded(self) -> None:
        """Load the model once (bounded). Safe to call concurrently."""
        if self._inference_fn is not None:
            self._init_status = ProviderInitStatus.READY
            return
        if not self._deps_available:
            self._init_status = ProviderInitStatus.UNAVAILABLE
            raise VoiceConfigurationError(
                "ECAPA-TDNN dependencies unavailable (torch/speechbrain).",
                code="ecapa_deps_unavailable",
            )
        with self._lock:
            if self._init_status == ProviderInitStatus.READY and self._classifier is not None:
                return
            if self._init_status == ProviderInitStatus.FAILED:
                raise VoiceConfigurationError(
                    f"ECAPA-TDNN initialization previously failed: {self._init_error}",
                    code="ecapa_init_failed",
                )
            self._init_status = ProviderInitStatus.LOADING
            started = time.perf_counter()
            try:
                self._classifier = self._load_classifier()
                elapsed = (time.perf_counter() - started) * 1000.0
                if elapsed > self._init_timeout * 1000.0:
                    self._init_status = ProviderInitStatus.FAILED
                    self._init_error = "init_timeout"
                    self._classifier = None
                    raise VoiceConfigurationError(
                        "ECAPA-TDNN initialization exceeded timeout.",
                        code="ecapa_init_timeout",
                    )
                self._init_ms = round(elapsed, 2)
                self._init_status = ProviderInitStatus.READY
                logger.info(
                    "ECAPA_MODEL_READY source=%s device=%s init_ms=%.2f",
                    self._model_source,
                    self._device,
                    self._init_ms,
                )
            except VoiceConfigurationError:
                raise
            except Exception as exc:
                self._init_status = ProviderInitStatus.FAILED
                self._init_error = type(exc).__name__
                self._classifier = None
                logger.warning("ECAPA_MODEL_INIT_FAILED error=%s", type(exc).__name__)
                raise VoiceConfigurationError(
                    f"ECAPA-TDNN initialization failed: {type(exc).__name__}",
                    code="ecapa_init_failed",
                ) from exc

    def _resolve_local_strategy(self) -> Any:
        """Pick SpeechBrain fetch strategy that works without Windows symlink rights."""
        from speechbrain.utils.fetching import LocalStrategy  # type: ignore

        raw = os.getenv("TITAN_VOICE_ECAPA_LOCAL_STRATEGY", "").strip().lower()
        if raw in {"copy", "copy_skip_cache", "symlink", "no_link"}:
            return LocalStrategy[raw.upper()]
        # Default SYMLINK fails on many Windows hosts (WinError 1314) without
        # Developer Mode / admin. COPY uses the HF cache and materializes files.
        if os.name == "nt":
            return LocalStrategy.COPY
        return LocalStrategy.SYMLINK

    def _load_classifier(self) -> Any:
        # Import lazily so Titan starts without optional biometric deps.
        from speechbrain.inference.speaker import EncoderClassifier  # type: ignore

        self._savedir.mkdir(parents=True, exist_ok=True)
        return EncoderClassifier.from_hparams(
            source=self._model_source,
            savedir=str(self._savedir),
            run_opts={"device": self._device},
            local_strategy=self._resolve_local_strategy(),
        )

    def extract(self, audio_bytes: bytes) -> list[float]:
        if not audio_bytes:
            return [0.0] * self.dimension
        if self._inference_fn is not None:
            self.ensure_loaded()
            return normalize_embedding(self._inference_fn(audio_bytes))
        self.ensure_loaded()
        assert self._classifier is not None
        samples, rate = decode_pcm16_mono(
            audio_bytes, source_rate=DEFAULT_SAMPLE_RATE, target_rate=DEFAULT_SAMPLE_RATE
        )
        if not samples:
            return [0.0] * self.dimension
        try:
            import torch

            waveform = torch.tensor(samples, dtype=torch.float32).unsqueeze(0)
            with torch.inference_mode():
                self._classifier.eval()
                embedding = self._classifier.encode_batch(waveform)
                flat = embedding.squeeze().detach().cpu().tolist()
            if isinstance(flat, float):
                flat = [flat]
            if len(flat) != self.dimension:
                # Pad / truncate defensively — never leak raw tensor logs.
                if len(flat) < self.dimension:
                    flat = list(flat) + [0.0] * (self.dimension - len(flat))
                else:
                    flat = list(flat)[: self.dimension]
            return normalize_embedding(flat)
        except VoiceConfigurationError:
            raise
        except Exception as exc:
            raise VoiceConfigurationError(
                f"ECAPA-TDNN inference failed: {type(exc).__name__}",
                code="ecapa_inference_failed",
            ) from exc

    def health_dict(self) -> dict[str, object]:
        base = super().health_dict()
        base.update(
            {
                "model_source": self._model_source,
                "model_version": self.model_version,
                "init_status": self._init_status.value,
                "init_error": self._init_error,
                "init_ms": self._init_ms,
                "device": self._device,
                "dependencies": {
                    "torch": self._deps.get("torch"),
                    "speechbrain": self._deps.get("speechbrain"),
                },
                "lazy_load": True,
                "deterministic_inference": True,
                "normalized_embeddings": True,
                "local_strategy": os.getenv(
                    "TITAN_VOICE_ECAPA_LOCAL_STRATEGY",
                    "copy" if os.name == "nt" else "symlink",
                ),
            }
        )
        return base

# =====================================
# Titan Voice Embedding Provider
# =====================================

"""Pluggable voice embedding interface (Phase 20.8–20.12).

Default remains histogram_v1 as a **development/test fallback only**.
Histogram embeddings must never silently become the trusted production
identity mechanism — see ``EmbeddingTrustLevel`` and migration helpers.

Production-oriented backends (Phase 20.12):
  • ECAPA-TDNN (SpeechBrain) — real local biometric when deps installed
  • Resemblyzer — real local biometric fallback when deps installed
  • External OpenAI-compatible (stub)
  • Local deterministic (available for production-path drills/tests)

Do NOT silently fall back to histogram identity in production trust mode.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from abc import ABC, abstractmethod
from typing import Any, Iterable, Protocol

from voice.embedding_capabilities import (
    HISTOGRAM_CAPABILITIES,
    LOCAL_DETERMINISTIC_CAPABILITIES,
    OPENAI_COMPAT_CAPABILITIES,
    EmbeddingCapabilities,
    EmbeddingTrustLevel,
)
from voice.enrollment_models import EMBEDDING_VERSION
from voice.exceptions import VoiceConfigurationError

logger = logging.getLogger(__name__)

FEATURE_DIM = 32

# Future / production embedding version ids.
ECAPA_VERSION = "ecapa_v1"
RESEMBLYZER_VERSION = "resemblyzer_v1"
OPENAI_COMPAT_VERSION = "openai_compat_v1"
LOCAL_DETERMINISTIC_VERSION = "local_det_v1"

# Versions that are never production-trusted without explicit re-enrollment.
DEV_FALLBACK_VERSIONS: frozenset[str] = frozenset({"histogram_v1", EMBEDDING_VERSION})


class VoiceEmbeddingProvider(Protocol):
    """Minimal contract for speaker embedding extractors."""

    @property
    def embedding_version(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    @property
    def is_available(self) -> bool: ...

    def extract(self, audio_bytes: bytes) -> list[float]: ...

    def quality_score(self, embedding: Iterable[float]) -> float: ...


class BaseEmbeddingProvider(ABC):
    """Shared helpers for embedding providers."""

    @property
    @abstractmethod
    def embedding_version(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @property
    def is_available(self) -> bool:
        return True

    @property
    def provider_id(self) -> str:
        return self.embedding_version

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        """Capability / trust declaration — subclasses override."""
        return EmbeddingCapabilities(
            provider_id=self.provider_id,
            embedding_version=self.embedding_version,
            dimension=self.dimension,
            backend_family=HISTOGRAM_CAPABILITIES.backend_family,
            trust_level=(
                EmbeddingTrustLevel.PRODUCTION
                if self.is_available
                else EmbeddingTrustLevel.UNAVAILABLE
            ),
            available=self.is_available,
        )

    @property
    def is_production_trusted(self) -> bool:
        return self.capabilities.is_production_trusted

    @property
    def is_dev_fallback(self) -> bool:
        return self.capabilities.is_dev_fallback

    @abstractmethod
    def extract(self, audio_bytes: bytes) -> list[float]: ...

    def quality_score(self, embedding: Iterable[float]) -> float:
        """Heuristic embedding quality in [0, 1] — higher is more informative."""
        values = [float(v) for v in embedding]
        if not values:
            return 0.0
        energy = math.sqrt(sum(v * v for v in values))
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        spread = math.sqrt(variance)
        score = min(1.0, (energy * 0.55) + (spread * 2.5))
        return max(0.0, round(score, 4))

    def compatible_with(self, other_version: str) -> bool:
        return self.embedding_version == (other_version or "").strip()

    def similarity(self, a: list[float], b: list[float]) -> float:
        """Provider-appropriate similarity (default: cosine / L2-normalized dot)."""
        return cosine_similarity(a, b)

    def health_dict(self) -> dict[str, object]:
        caps = self.capabilities
        return {
            "provider_id": self.provider_id,
            "embedding_version": self.embedding_version,
            "dimension": self.dimension,
            "available": self.is_available,
            "language_independent": caps.language_independent,
            "trust_level": caps.trust_level.value,
            "is_production_trusted": caps.is_production_trusted,
            "is_dev_fallback": caps.is_dev_fallback,
            "backend_family": caps.backend_family.value,
            "capabilities": caps.to_dict(),
        }


class HistogramEmbeddingProvider(BaseEmbeddingProvider):
    """Language-independent acoustic histogram+energy embedding (histogram_v1).

    **Development / test fallback only.** Must never silently become the
    trusted production speaker identity mechanism.
    """

    @property
    def embedding_version(self) -> str:
        return EMBEDDING_VERSION

    @property
    def dimension(self) -> int:
        return FEATURE_DIM

    @property
    def provider_id(self) -> str:
        return "histogram"

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        return HISTOGRAM_CAPABILITIES

    def extract(self, audio_bytes: bytes) -> list[float]:
        if not audio_bytes:
            return [0.0] * FEATURE_DIM

        data = audio_bytes
        if len(data) > 44 and data[:4] == b"RIFF":
            data = data[44:]
        if not data:
            data = audio_bytes

        features: list[float] = [0.0] * FEATURE_DIM
        hist_bins = FEATURE_DIM // 2
        for value in data:
            features[min(hist_bins - 1, value * hist_bins // 256)] += 1.0
        hist_total = float(len(data)) or 1.0
        for i in range(hist_bins):
            features[i] /= hist_total

        chunk = max(1, len(data) // hist_bins)
        for index in range(hist_bins):
            start = index * chunk
            end = start + chunk if index < hist_bins - 1 else len(data)
            block = data[start:end] or b"\x00"
            mean = sum(block) / len(block)
            energy = sum((b - mean) ** 2 for b in block) / len(block)
            transitions = sum(
                1
                for i in range(1, len(block))
                if (block[i] > 127) != (block[i - 1] > 127)
            )
            transition_rate = transitions / max(1, len(block) - 1)
            features[hist_bins + index] = math.sqrt(energy) / 128.0 + transition_rate

        norm = math.sqrt(sum(v * v for v in features)) or 1.0
        return [v / norm for v in features]


class LocalEmbeddingProvider(BaseEmbeddingProvider, ABC):
    """Base class for local (on-device) embedding backends."""

    @property
    def is_local(self) -> bool:
        return True


class DeterministicLocalEmbeddingProvider(LocalEmbeddingProvider):
    """Deterministic local embedding for production-path tests / migration drills.

    Produces stable 64-D L2-normalized vectors from audio content hashes.
    Marked production-trusted for plumbing tests only — not a biometric model.
    """

    @property
    def embedding_version(self) -> str:
        return LOCAL_DETERMINISTIC_VERSION

    @property
    def dimension(self) -> int:
        return LOCAL_DETERMINISTIC_CAPABILITIES.dimension

    @property
    def provider_id(self) -> str:
        return "local_deterministic"

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        return LOCAL_DETERMINISTIC_CAPABILITIES

    def extract(self, audio_bytes: bytes) -> list[float]:
        dim = self.dimension
        if not audio_bytes:
            return [0.0] * dim
        data = audio_bytes
        if len(data) > 44 and data[:4] == b"RIFF":
            data = data[44:]
        if not data:
            data = audio_bytes
        digest = hashlib.sha256(data).digest()
        # Expand hash material into a fixed-dimension float vector.
        features: list[float] = []
        seed = digest
        while len(features) < dim:
            seed = hashlib.sha256(seed).digest()
            for byte in seed:
                if len(features) >= dim:
                    break
                features.append((byte / 127.5) - 1.0)
        # Mix in coarse energy so similar-length speech is not purely random.
        energy = sum(data) / (len(data) * 255.0) if data else 0.0
        features[0] = (features[0] + energy) / 2.0
        norm = math.sqrt(sum(v * v for v in features)) or 1.0
        return [v / norm for v in features]


class _FutureStubEmbeddingProvider(BaseEmbeddingProvider):
    """Unavailable stub — reserved for backends not yet wired."""

    def __init__(
        self,
        *,
        provider_id: str,
        embedding_version: str,
        dimension: int = 192,
        capabilities: EmbeddingCapabilities | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._version = embedding_version
        self._dimension = dimension
        self._capabilities = capabilities

    @property
    def embedding_version(self) -> str:
        return self._version

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def is_available(self) -> bool:
        return False

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        if self._capabilities is not None:
            return self._capabilities
        return EmbeddingCapabilities(
            provider_id=self._provider_id,
            embedding_version=self._version,
            dimension=self._dimension,
            backend_family=HISTOGRAM_CAPABILITIES.backend_family,
            trust_level=EmbeddingTrustLevel.UNAVAILABLE,
            available=False,
            requires_external_dependency=True,
        )

    def extract(self, audio_bytes: bytes) -> list[float]:
        raise VoiceConfigurationError(
            f"Embedding provider {self._provider_id!r} ({self._version}) "
            "is prepared but not enabled. Keep histogram_v1 for development "
            "or activate a production-trusted backend explicitly.",
            code="embedding_provider_unavailable",
        )


class OpenAICompatibleEmbeddingProvider(_FutureStubEmbeddingProvider):
    """External OpenAI-compatible voice embedding backend (not enabled)."""

    def __init__(self) -> None:
        super().__init__(
            provider_id="openai_compat",
            embedding_version=OPENAI_COMPAT_VERSION,
            dimension=1536,
            capabilities=OPENAI_COMPAT_CAPABILITIES,
        )


class EmbeddingProviderRegistry:
    """Provider-independent registry for speaker embedding backends."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseEmbeddingProvider] = {}
        self._active_id: str = "histogram"

    def register(self, provider: BaseEmbeddingProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str | None = None) -> BaseEmbeddingProvider:
        key = (provider_id or self._active_id).strip()
        provider = self._providers.get(key)
        if provider is None:
            raise VoiceConfigurationError(
                f"Unknown embedding provider {key!r}",
                code="embedding_provider_unknown",
            )
        return provider

    def set_active(self, provider_id: str) -> BaseEmbeddingProvider:
        provider = self.get(provider_id)
        if not provider.is_available:
            raise VoiceConfigurationError(
                f"Cannot activate unavailable embedding provider {provider_id!r}",
                code="embedding_provider_unavailable",
            )
        self._active_id = provider.provider_id
        return provider

    def detect_capabilities(
        self, provider_id: str | None = None
    ) -> EmbeddingCapabilities:
        return self.get(provider_id).capabilities

    def list_production_ready(self) -> list[dict[str, object]]:
        return [
            p.health_dict()
            for p in self._providers.values()
            if p.is_available and p.is_production_trusted
        ]

    @property
    def active(self) -> BaseEmbeddingProvider:
        return self.get(self._active_id)

    def list_providers(self) -> list[dict[str, object]]:
        return [p.health_dict() for p in self._providers.values()]


def build_default_embedding_registry() -> EmbeddingProviderRegistry:
    # Import real biometric backends lazily to keep optional deps out of
    # cold-start import path for modules that only need histogram helpers.
    from voice.ecapa_provider import EcapaEmbeddingProvider
    from voice.resemblyzer_provider import ResemblyzerEmbeddingProvider

    registry = EmbeddingProviderRegistry()
    registry.register(HistogramEmbeddingProvider())
    registry.register(DeterministicLocalEmbeddingProvider())
    registry.register(EcapaEmbeddingProvider())
    registry.register(ResemblyzerEmbeddingProvider())
    registry.register(OpenAICompatibleEmbeddingProvider())
    return registry


# Public re-exports for isinstance / tests (resolved after base classes exist).
def __getattr__(name: str) -> Any:  # pragma: no cover — import seam
    if name == "EcapaEmbeddingProvider":
        from voice.ecapa_provider import EcapaEmbeddingProvider as _cls

        return _cls
    if name == "ResemblyzerEmbeddingProvider":
        from voice.resemblyzer_provider import ResemblyzerEmbeddingProvider as _cls

        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _select_preferred_provider(
    registry: EmbeddingProviderRegistry,
) -> None:
    """Activate preferred provider without silent histogram production trust."""
    from voice.biometric_trust import (
        BiometricTrustMode,
        resolve_biometric_trust_mode,
    )

    preferred = os.getenv("TITAN_VOICE_EMBEDDING_PROVIDER", "histogram").strip()
    trust_mode = resolve_biometric_trust_mode()
    try:
        if preferred and preferred != "histogram":
            candidate = registry.get(preferred)
            if candidate.is_available:
                registry.set_active(preferred)
                if (
                    preferred not in {"histogram", "local_deterministic"}
                    and not candidate.is_production_trusted
                    and not candidate.is_dev_fallback
                ):
                    logger.warning(
                        "Embedding provider %s activated but not "
                        "production-trusted (trust=%s)",
                        preferred,
                        candidate.capabilities.trust_level.value,
                    )
            elif trust_mode == BiometricTrustMode.PRODUCTION:
                # Never silently fall back to histogram in production mode.
                logger.warning(
                    "Preferred embedding provider %s unavailable; "
                    "refusing silent histogram fallback in production trust mode",
                    preferred,
                )
            else:
                logger.info(
                    "Preferred embedding provider %s unavailable; "
                    "keeping development histogram fallback",
                    preferred,
                )
        elif trust_mode == BiometricTrustMode.PRODUCTION and preferred == "histogram":
            # Prefer a real biometric backend when production mode + histogram default.
            for candidate_id in ("ecapa", "resemblyzer", "local_deterministic"):
                try:
                    candidate = registry.get(candidate_id)
                except VoiceConfigurationError:
                    continue
                if candidate.is_available and candidate.is_production_trusted:
                    registry.set_active(candidate_id)
                    logger.info(
                        "Production trust mode: auto-selected embedding provider %s",
                        candidate_id,
                    )
                    break
            else:
                logger.warning(
                    "Production trust mode active but no production-trusted "
                    "embedding provider available — verification will refuse "
                    "trusted identity until a real backend is installed"
                )
    except VoiceConfigurationError:
        pass


_REGISTRY: EmbeddingProviderRegistry | None = None
_DEFAULT_PROVIDER: BaseEmbeddingProvider | None = None


def get_embedding_registry() -> EmbeddingProviderRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_default_embedding_registry()
        _select_preferred_provider(_REGISTRY)
    return _REGISTRY


def get_embedding_provider() -> BaseEmbeddingProvider:
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is not None:
        return _DEFAULT_PROVIDER
    return get_embedding_registry().active


def set_embedding_provider(provider: BaseEmbeddingProvider | None) -> None:
    """Test seam — inject a custom provider or reset to registry default."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider


def reset_embedding_registry_for_tests() -> None:
    global _REGISTRY, _DEFAULT_PROVIDER
    _REGISTRY = None
    _DEFAULT_PROVIDER = None


def embeddings_compatible(version_a: str, version_b: str) -> bool:
    """Refuse cross-version compares that would silently corrupt confidence."""
    a = (version_a or "").strip()
    b = (version_b or "").strip()
    if not a or not b:
        return False
    return a == b


def is_dev_fallback_version(version: str) -> bool:
    """True when the embedding version is development/test-only."""
    return (version or "").strip() in DEV_FALLBACK_VERSIONS


def is_production_trusted_version(version: str) -> bool:
    """True when the version belongs to a production-trusted available provider."""
    version = (version or "").strip()
    if not version or is_dev_fallback_version(version):
        return False
    try:
        registry = get_embedding_registry()
        for provider in registry._providers.values():  # noqa: SLF001
            if (
                provider.embedding_version == version
                and provider.is_production_trusted
            ):
                return True
    except Exception:  # pragma: no cover — defensive
        return False
    return False


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def mean_embedding(embeddings: list[list[float]]) -> list[float]:
    if not embeddings:
        return []
    dim = len(embeddings[0])
    acc = [0.0] * dim
    count = 0
    for row in embeddings:
        if len(row) != dim:
            continue
        for i, v in enumerate(row):
            acc[i] += float(v)
        count += 1
    if count == 0:
        return []
    return [v / count for v in acc]


def aggregate_embeddings(
    embeddings: list[list[float]],
    *,
    method: str = "max_centroid",
) -> list[float]:
    """Aggregate multiple enrollment embeddings into one comparison vector.

    Methods:
      • ``mean`` — arithmetic mean
      • ``max_centroid`` — mean (default; used with max-vs-samples at verify time)
    """
    if method in {"mean", "max_centroid", "centroid"}:
        return mean_embedding(embeddings)
    raise VoiceConfigurationError(
        f"Unknown embedding aggregation method {method!r}",
        code="embedding_aggregation_unknown",
    )


def extract_embeddings_batch(audio_samples: list[bytes]) -> list[list[float]]:
    """Optimized multi-sample extract — single provider lookup."""
    provider = get_embedding_provider()
    return [provider.extract(audio) for audio in audio_samples]

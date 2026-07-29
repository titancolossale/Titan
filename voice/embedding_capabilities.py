# =====================================
# Titan Voice Embedding Capabilities
# =====================================

"""Provider capability detection for production speaker embeddings (Phase 20.11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EmbeddingTrustLevel(str, Enum):
    """How much Titan may trust embeddings from a provider for identity."""

    # Dev/test only — must never silently become production identity.
    DEVELOPMENT_FALLBACK = "development_fallback"
    # Wired production backend (ECAPA / Resemblyzer / external / local).
    PRODUCTION = "production"
    # Registered but not enabled / dependency missing.
    UNAVAILABLE = "unavailable"


class EmbeddingBackendFamily(str, Enum):
    """Logical backend families Titan supports."""

    HISTOGRAM = "histogram"
    ECAPA_TDNN = "ecapa_tdnn"
    RESEMBLYZER = "resemblyzer"
    OPENAI_COMPAT = "openai_compat"
    LOCAL = "local"
    EXTERNAL = "external"


@dataclass(frozen=True)
class EmbeddingCapabilities:
    """Declared capabilities for one embedding provider."""

    provider_id: str
    embedding_version: str
    dimension: int
    backend_family: EmbeddingBackendFamily
    trust_level: EmbeddingTrustLevel
    available: bool
    supports_cosine_similarity: bool = True
    supports_batch_extract: bool = True
    language_independent: bool = True
    requires_external_dependency: bool = False
    requires_network: bool = False
    stores_raw_audio: bool = False
    encryption_compatible: bool = True
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_production_trusted(self) -> bool:
        return (
            self.available
            and self.trust_level == EmbeddingTrustLevel.PRODUCTION
        )

    @property
    def is_dev_fallback(self) -> bool:
        return self.trust_level == EmbeddingTrustLevel.DEVELOPMENT_FALLBACK

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "embedding_version": self.embedding_version,
            "dimension": self.dimension,
            "backend_family": self.backend_family.value,
            "trust_level": self.trust_level.value,
            "available": self.available,
            "is_production_trusted": self.is_production_trusted,
            "is_dev_fallback": self.is_dev_fallback,
            "supports_cosine_similarity": self.supports_cosine_similarity,
            "supports_batch_extract": self.supports_batch_extract,
            "language_independent": self.language_independent,
            "requires_external_dependency": self.requires_external_dependency,
            "requires_network": self.requires_network,
            "stores_raw_audio": self.stores_raw_audio,
            "encryption_compatible": self.encryption_compatible,
            "notes": list(self.notes),
        }


# Histogram must never be treated as a production biometric identity backend.
HISTOGRAM_CAPABILITIES = EmbeddingCapabilities(
    provider_id="histogram",
    embedding_version="histogram_v1",
    dimension=32,
    backend_family=EmbeddingBackendFamily.HISTOGRAM,
    trust_level=EmbeddingTrustLevel.DEVELOPMENT_FALLBACK,
    available=True,
    requires_external_dependency=False,
    requires_network=False,
    notes=(
        "Development/test fallback only.",
        "Never silently trusted as production speaker identity.",
    ),
)

ECAPA_CAPABILITIES = EmbeddingCapabilities(
    provider_id="ecapa",
    embedding_version="ecapa_v1",
    dimension=192,
    backend_family=EmbeddingBackendFamily.ECAPA_TDNN,
    trust_level=EmbeddingTrustLevel.UNAVAILABLE,
    available=False,
    requires_external_dependency=True,
    requires_network=False,
    notes=("ECAPA-TDNN compatible — not enabled until dependency wired.",),
)

RESEMBLYZER_CAPABILITIES = EmbeddingCapabilities(
    provider_id="resemblyzer",
    embedding_version="resemblyzer_v1",
    dimension=256,
    backend_family=EmbeddingBackendFamily.RESEMBLYZER,
    trust_level=EmbeddingTrustLevel.UNAVAILABLE,
    available=False,
    requires_external_dependency=True,
    requires_network=False,
    notes=("Resemblyzer compatible — not enabled until dependency wired.",),
)

OPENAI_COMPAT_CAPABILITIES = EmbeddingCapabilities(
    provider_id="openai_compat",
    embedding_version="openai_compat_v1",
    dimension=1536,
    backend_family=EmbeddingBackendFamily.OPENAI_COMPAT,
    trust_level=EmbeddingTrustLevel.UNAVAILABLE,
    available=False,
    requires_external_dependency=True,
    requires_network=True,
    notes=("External OpenAI-compatible embedding API — not enabled.",),
)

LOCAL_DETERMINISTIC_CAPABILITIES = EmbeddingCapabilities(
    provider_id="local_deterministic",
    embedding_version="local_det_v1",
    dimension=64,
    backend_family=EmbeddingBackendFamily.LOCAL,
    trust_level=EmbeddingTrustLevel.PRODUCTION,
    available=True,
    requires_external_dependency=False,
    requires_network=False,
    notes=(
        "Deterministic local embedding for production-path tests and migration drills.",
        "Not a biometric model — used to exercise production trust plumbing.",
    ),
)

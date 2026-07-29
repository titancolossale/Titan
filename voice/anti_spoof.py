# =====================================
# Titan Voice Anti-Spoofing / Liveness
# =====================================

"""Extensible liveness / anti-spoofing layer (Phase 20.11 preparation).

Supports future detection of:
  • replayed recordings
  • synthesized speech
  • cloned voices
  • suspiciously identical samples

Does NOT claim perfect anti-spoofing. Verification must not be weakened when
anti-spoofing is unavailable — results are advisory overlays.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class LivenessAvailability(str, Enum):
    """Whether a liveness / anti-spoof check can run."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STUB = "stub"


class SpoofSignalKind(str, Enum):
    REPLAY = "replayed_recording"
    SYNTHESIZED = "synthesized_speech"
    CLONED = "cloned_voice"
    IDENTICAL_SAMPLES = "identical_samples"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SpoofSignal:
    """One advisory anti-spoof observation (never definitive alone)."""

    kind: SpoofSignalKind
    score: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "score": round(self.score, 4),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class LivenessResult:
    """Advisory liveness / anti-spoof outcome.

    When ``availability`` is not AVAILABLE, callers must leave verification
    thresholds unchanged — do not weaken or auto-pass identity checks.
    """

    availability: LivenessAvailability
    passed: bool | None
    confidence: float
    signals: tuple[SpoofSignal, ...] = ()
    reason: str = "not_evaluated"
    weakens_verification: bool = False  # always False by policy

    def to_dict(self) -> dict[str, Any]:
        return {
            "availability": self.availability.value,
            "passed": self.passed,
            "confidence": round(self.confidence, 4),
            "signals": [s.to_dict() for s in self.signals],
            "reason": self.reason,
            "weakens_verification": self.weakens_verification,
            "claims_perfect_anti_spoofing": False,
        }


class AntiSpoofProvider(ABC):
    """Pluggable anti-spoof / liveness backend."""

    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def availability(self) -> LivenessAvailability: ...

    @abstractmethod
    def evaluate(
        self,
        *,
        audio_bytes: bytes | None = None,
        embeddings: list[list[float]] | None = None,
        fingerprints: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LivenessResult: ...

    def health_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "availability": self.availability.value,
            "claims_perfect_anti_spoofing": False,
            "weakens_verification_when_unavailable": False,
        }


class NullAntiSpoofProvider(AntiSpoofProvider):
    """Default: anti-spoofing unavailable — verification unchanged."""

    @property
    def provider_id(self) -> str:
        return "null"

    @property
    def availability(self) -> LivenessAvailability:
        return LivenessAvailability.UNAVAILABLE

    def evaluate(
        self,
        *,
        audio_bytes: bytes | None = None,
        embeddings: list[list[float]] | None = None,
        fingerprints: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LivenessResult:
        return LivenessResult(
            availability=LivenessAvailability.UNAVAILABLE,
            passed=None,
            confidence=0.0,
            reason="anti_spoof_unavailable",
            weakens_verification=False,
        )


class HeuristicAntiSpoofProvider(AntiSpoofProvider):
    """Lightweight stub heuristics — advisory only, not production PAS.

    Detects suspiciously identical sample fingerprints and near-zero embedding
    variance. Does not claim replay / deepfake detection.
    """

    @property
    def provider_id(self) -> str:
        return "heuristic_stub"

    @property
    def availability(self) -> LivenessAvailability:
        return LivenessAvailability.STUB

    def evaluate(
        self,
        *,
        audio_bytes: bytes | None = None,
        embeddings: list[list[float]] | None = None,
        fingerprints: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LivenessResult:
        signals: list[SpoofSignal] = []
        fps = [str(f) for f in (fingerprints or []) if f]
        if fps and len(fps) != len(set(fps)):
            signals.append(
                SpoofSignal(
                    kind=SpoofSignalKind.IDENTICAL_SAMPLES,
                    score=1.0,
                    detail="duplicate_fingerprints_in_batch",
                )
            )

        if embeddings and len(embeddings) >= 2:
            # Near-identical consecutive embeddings → possible clone/replay reuse.
            from voice.embedding_provider import cosine_similarity

            for i in range(1, len(embeddings)):
                a, b = embeddings[i - 1], embeddings[i]
                if a and b and len(a) == len(b):
                    sim = cosine_similarity(list(a), list(b))
                    if sim >= 0.999:
                        signals.append(
                            SpoofSignal(
                                kind=SpoofSignalKind.IDENTICAL_SAMPLES,
                                score=sim,
                                detail=f"near_identical_embeddings_{i - 1}_{i}",
                            )
                        )

        # Explicit future hooks — currently informational only.
        meta = metadata or {}
        if meta.get("suspect_replay"):
            signals.append(
                SpoofSignal(
                    kind=SpoofSignalKind.REPLAY,
                    score=float(meta.get("replay_score", 0.5)),
                    detail="metadata_suspect_replay",
                )
            )
        if meta.get("suspect_synthesized"):
            signals.append(
                SpoofSignal(
                    kind=SpoofSignalKind.SYNTHESIZED,
                    score=float(meta.get("synth_score", 0.5)),
                    detail="metadata_suspect_synthesized",
                )
            )
        if meta.get("suspect_cloned"):
            signals.append(
                SpoofSignal(
                    kind=SpoofSignalKind.CLONED,
                    score=float(meta.get("clone_score", 0.5)),
                    detail="metadata_suspect_cloned",
                )
            )

        if signals:
            max_score = max(s.score for s in signals)
            return LivenessResult(
                availability=LivenessAvailability.STUB,
                passed=False,
                confidence=max_score,
                signals=tuple(signals),
                reason="heuristic_spoof_signals",
                weakens_verification=False,
            )

        return LivenessResult(
            availability=LivenessAvailability.STUB,
            passed=True,
            confidence=0.0,
            reason="no_heuristic_spoof_signals",
            weakens_verification=False,
        )


@dataclass
class AntiSpoofRegistry:
    """Registry of anti-spoof providers (extensible)."""

    _providers: dict[str, AntiSpoofProvider] = field(default_factory=dict)
    _active_id: str = "null"

    def register(self, provider: AntiSpoofProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str | None = None) -> AntiSpoofProvider:
        key = (provider_id or self._active_id).strip()
        provider = self._providers.get(key)
        if provider is None:
            return NullAntiSpoofProvider()
        return provider

    def set_active(self, provider_id: str) -> AntiSpoofProvider:
        provider = self.get(provider_id)
        self._active_id = provider.provider_id
        return provider

    @property
    def active(self) -> AntiSpoofProvider:
        return self.get(self._active_id)

    def list_providers(self) -> list[dict[str, Any]]:
        return [p.health_dict() for p in self._providers.values()]


_REGISTRY: AntiSpoofRegistry | None = None


def build_default_anti_spoof_registry() -> AntiSpoofRegistry:
    registry = AntiSpoofRegistry()
    registry.register(NullAntiSpoofProvider())
    registry.register(HeuristicAntiSpoofProvider())
    # Default: null — unavailable does not weaken verification.
    registry.set_active("null")
    return registry


def get_anti_spoof_registry() -> AntiSpoofRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_default_anti_spoof_registry()
        import os

        preferred = os.getenv("TITAN_VOICE_ANTI_SPOOF_PROVIDER", "null").strip()
        if preferred:
            try:
                _REGISTRY.set_active(preferred)
            except Exception:
                pass
    return _REGISTRY


def get_anti_spoof_provider() -> AntiSpoofProvider:
    return get_anti_spoof_registry().active


def reset_anti_spoof_registry_for_tests() -> None:
    global _REGISTRY
    _REGISTRY = None


def evaluate_liveness(
    *,
    audio_bytes: bytes | None = None,
    embeddings: list[list[float]] | None = None,
    fingerprints: Iterable[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> LivenessResult:
    """Run active anti-spoof provider; never weakens verification when unavailable."""
    result = get_anti_spoof_provider().evaluate(
        audio_bytes=audio_bytes,
        embeddings=embeddings,
        fingerprints=fingerprints,
        metadata=metadata,
    )
    # Hard policy: unavailable / stub must never weaken verification thresholds.
    if result.weakens_verification:
        return LivenessResult(
            availability=result.availability,
            passed=result.passed,
            confidence=result.confidence,
            signals=result.signals,
            reason=result.reason,
            weakens_verification=False,
        )
    return result

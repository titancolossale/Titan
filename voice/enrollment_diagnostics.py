# =====================================
# Titan Enrollment / Voice Diagnostics Aggregator
# =====================================

"""Enrollment + live-provider diagnostic snapshot (Phase 20.9 + 20.10A).

Tracks provider status, embedding quality, speaker/verification confidence,
session history, workflow states, failures, latency, and provider health —
never embeddings or raw audio.
"""

from __future__ import annotations

import time
from typing import Any

from voice.diagnostics import emit_voice_diagnostic
from voice.embedding_provider import get_embedding_provider, get_embedding_registry
from voice.enrollment_models import EnrollmentStatus
from voice.enrollment_workflow import (
    IN_FLIGHT_PRODUCTION_STATES,
    ProductionEnrollmentState,
)
from voice.provider_health import collect_provider_health
from voice.speaker_profile_store import SpeakerProfileStore


def collect_enrollment_diagnostics(
    *,
    store: SpeakerProfileStore | None = None,
    user_id: str | None = None,
    include_provider_health: bool = True,
) -> dict[str, Any]:
    """Aggregate enrollment readiness + provider diagnostics (safe metadata)."""
    started = time.perf_counter()
    profile_store = store or SpeakerProfileStore()
    profile_store.load()

    sessions = (
        profile_store.list_sessions_for_user(user_id)
        if user_id
        else list(getattr(profile_store, "_sessions", {}).values())
        if getattr(profile_store, "_sessions", None) is not None
        else []
    )
    # Ensure sessions loaded even when user_id is None.
    if not user_id:
        profile_store.load()
        sessions = list(profile_store._sessions.values())  # noqa: SLF001 — diagnostics only

    session_history: list[dict[str, Any]] = []
    verification_confidences: list[float] = []
    aggregate_qualities: list[float] = []
    latencies: list[float] = []
    failure_reasons: dict[str, int] = {}
    workflow_counts: dict[str, int] = {}
    quality_metric_samples = 0
    for session in sessions:
        public = session.to_public_dict()
        session_history.append(
            {
                "session_id": public["session_id"],
                "user_id": public["user_id"],
                "status": public["status"],
                "workflow_state": public.get("workflow_state"),
                "attempt_number": public.get("attempt_number"),
                "consent_given": public.get("consent_given"),
                "samples_collected": public.get("samples_collected"),
                "aggregate_quality_score": public.get("aggregate_quality_score"),
                "verification_status": public.get("verification_status"),
                "last_verification_confidence": public.get(
                    "last_verification_confidence"
                ),
                "processing_latency_ms": public.get("processing_latency_ms"),
                "session_label": public.get("session_label"),
                "failure_reason": public.get("failure_reason"),
                "updated_at": public.get("updated_at"),
            }
        )
        wf = str(public.get("workflow_state") or "unknown")
        workflow_counts[wf] = workflow_counts.get(wf, 0) + 1
        if session.failure_reason:
            key = str(session.failure_reason)
            failure_reasons[key] = failure_reasons.get(key, 0) + 1
        if session.aggregate_quality_score:
            aggregate_qualities.append(float(session.aggregate_quality_score))
        if session.processing_latency_ms:
            latencies.append(float(session.processing_latency_ms))
        if session.last_verification_confidence is not None:
            verification_confidences.append(float(session.last_verification_confidence))
        if session.last_quality_metrics:
            quality_metric_samples += 1

    profiles = profile_store.list_safe_profiles(user_id=user_id)
    speaker_confidences = [
        float(p.get("confidence") or 0.0) for p in profiles if p.get("active")
    ]
    for profile in profiles:
        if profile.get("confidence"):
            verification_confidences.append(float(profile["confidence"]))

    embedding = get_embedding_provider()
    registry = get_embedding_registry()
    embedding_block = {
        **embedding.health_dict(),
        "providers": registry.list_providers(),
        "upgrade_ready": True,
        # Histogram is available but never production-trusted.
        "active_production": embedding.is_production_trusted,
        "is_dev_fallback": embedding.is_dev_fallback,
        "production_ready_providers": registry.list_production_ready(),
    }

    from voice.anti_spoof import get_anti_spoof_provider
    from voice.embedding_migration import EmbeddingMigrationService
    from voice.identity_security import IdentitySecurityBoundary

    liveness = get_anti_spoof_provider().health_dict()
    migration = EmbeddingMigrationService(profile_store).public_status()
    identity_security = IdentitySecurityBoundary().assert_not_authorization()

    status_counts: dict[str, int] = {}
    for item in session_history:
        key = str(item.get("status") or "unknown")
        status_counts[key] = status_counts.get(key, 0) + 1

    audit = profile_store.list_audit_history(user_id=user_id, limit=50)

    in_flight = False
    for s in sessions:
        try:
            wf_state = ProductionEnrollmentState(s.workflow_state)
            if wf_state in IN_FLIGHT_PRODUCTION_STATES:
                in_flight = True
                break
        except ValueError:
            if s.status in {
                EnrollmentStatus.AWAITING_CONSENT,
                EnrollmentStatus.COLLECTING,
                EnrollmentStatus.VALIDATING,
                EnrollmentStatus.BUILDING_PROFILE,
                EnrollmentStatus.VERIFYING,
            }:
                in_flight = True
                break

    snapshot: dict[str, Any] = {
        "ok": True,
        "generated_at": time.time(),
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "provider_status": {
            "embedding": embedding_block,
        },
        "embedding_quality": {
            "session_aggregate_avg": (
                round(sum(aggregate_qualities) / len(aggregate_qualities), 4)
                if aggregate_qualities
                else None
            ),
            "samples_scored": len(aggregate_qualities),
            "production_metric_samples": quality_metric_samples,
        },
        "speaker_confidence": {
            "active_avg": (
                round(sum(speaker_confidences) / len(speaker_confidences), 4)
                if speaker_confidences
                else None
            ),
            "active_count": len(speaker_confidences),
        },
        "verification_confidence": {
            "avg": (
                round(
                    sum(verification_confidences) / len(verification_confidences), 4
                )
                if verification_confidences
                else None
            ),
            "count": len(verification_confidences),
        },
        "workflow": {
            "state_counts": workflow_counts,
            "failure_reasons": failure_reasons,
            "in_flight": in_flight,
        },
        "session_history": session_history[:50],
        "session_status_counts": status_counts,
        "audit_history": audit,
        "latency": {
            "enrollment_processing_avg_ms": (
                round(sum(latencies) / len(latencies), 2) if latencies else None
            ),
            "samples": len(latencies),
        },
        "profiles": profiles,
        "in_flight": in_flight,
        "liveness": liveness,
        "migration_status": migration,
        "identity_security": identity_security,
        "storage": profile_store.storage_health(),
    }

    if include_provider_health:
        health = collect_provider_health(include_capabilities=False)
        snapshot["provider_health"] = {
            "ok": health.get("ok"),
            "stt_count": len(health.get("stt") or []),
            "tts_count": len(health.get("tts") or []),
            "live_socket_backend_available": health.get(
                "live_socket_backend_available"
            ),
            "connection_state": health.get("connection_state"),
            "stt_fallback": health.get("stt_fallback"),
            "tts_fallback": health.get("tts_fallback"),
        }
        snapshot["provider_status"]["stt"] = health.get("stt")
        snapshot["provider_status"]["tts"] = health.get("tts")

    emit_voice_diagnostic(
        "ENROLLMENT_DIAGNOSTICS_SNAPSHOT",
        session_count=len(session_history),
        active_profiles=len(speaker_confidences),
        embedding_version=embedding.embedding_version,
        in_flight=snapshot["in_flight"],
        workflow_states=len(workflow_counts),
    )
    return snapshot

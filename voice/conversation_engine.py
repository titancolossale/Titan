# =====================================
# Titan Real-Time Conversation Engine
# =====================================

"""Continuous multi-turn voice conversation continuity (Phase 20.5).

Wraps live-session turn plumbing with:
- conversation / idle timeouts (checked on access — no polling loops)
- browser refresh / network reconnect recovery
- memory + speaker continuity without reloading Brain
- structured stream diagnostics
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from voice.cancellation import TurnCancellation
from voice.diagnostics import emit_voice_diagnostic
from voice.exceptions import VoiceSessionError
from voice.latency_tracker import ConversationLatencyMetrics, LatencyTracker

logger = logging.getLogger(__name__)

StreamEmit = Callable[[str, dict[str, Any]], None]


@dataclass
class ConversationContext:
    """In-memory continuity across turns — never reloads Brain."""

    conversation_id: str
    authenticated_user: str
    speaker_identity: str | None = None
    active_mission_id: str | None = None
    active_goal: str | None = None
    workspace_hint: str | None = None
    temporary_context: dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    last_transcript: str | None = None
    last_assistant_text: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "authenticated_user": self.authenticated_user,
            "speaker_identity": self.speaker_identity,
            "active_mission_id": self.active_mission_id,
            "active_goal": self.active_goal,
            "workspace_hint": self.workspace_hint,
            "turn_count": self.turn_count,
            "has_temporary_context": bool(self.temporary_context),
        }


@dataclass
class RecoveryRecord:
    """Durable-enough recovery token for browser refresh / reconnect."""

    recovery_token: str
    session_id: str
    conversation_id: str
    authenticated_user: str
    capture_mode: str
    speaker_identity: str | None
    created_at: float
    expires_at: float

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "recovery_token": self.recovery_token,
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "authenticated_user": self.authenticated_user,
            "capture_mode": self.capture_mode,
            "speaker_identity": self.speaker_identity,
            "expires_in_seconds": max(0.0, round(self.expires_at - time.monotonic(), 2)),
        }


@dataclass
class ConversationEngineConfig:
    idle_timeout_seconds: float = 90.0
    conversation_timeout_seconds: float = 1800.0
    recovery_ttl_seconds: float = 600.0


class RealtimeConversationEngine:
    """Owns continuous-conversation state across live session turns."""

    def __init__(
        self,
        *,
        config: ConversationEngineConfig | None = None,
        emit: StreamEmit | None = None,
    ) -> None:
        self._config = config or ConversationEngineConfig()
        self._emit = emit
        self._lock = threading.RLock()
        self._contexts: dict[str, ConversationContext] = {}
        self._session_activity: dict[str, float] = {}
        self._session_started: dict[str, float] = {}
        self._idle_sessions: set[str] = set()
        self._recoveries: dict[str, RecoveryRecord] = {}
        self._session_to_recovery: dict[str, str] = {}
        self._cancellations: dict[str, TurnCancellation] = {}
        self._latencies: dict[str, LatencyTracker] = {}
        self._event_buffers: dict[str, list[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Session binding
    # ------------------------------------------------------------------

    def bind_session(
        self,
        session_id: str,
        *,
        authenticated_user: str,
        conversation_id: str,
        capture_mode: str = "push_to_talk",
        speaker_identity: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            ctx = ConversationContext(
                conversation_id=conversation_id,
                authenticated_user=authenticated_user,
                speaker_identity=speaker_identity,
            )
            self._contexts[session_id] = ctx
            self._session_activity[session_id] = now
            self._session_started[session_id] = now
            self._cancellations[session_id] = TurnCancellation()
            self._latencies[session_id] = LatencyTracker()
            self._event_buffers[session_id] = []
            recovery = self._issue_recovery_locked(
                session_id=session_id,
                conversation_id=conversation_id,
                authenticated_user=authenticated_user,
                capture_mode=capture_mode,
                speaker_identity=speaker_identity,
            )
            return {
                "conversation": ctx.to_safe_dict(),
                "recovery": recovery.to_safe_dict(),
            }

    def touch(self, session_id: str) -> None:
        with self._lock:
            if session_id not in self._contexts:
                return
            was_idle = session_id in self._idle_sessions
            self._session_activity[session_id] = time.monotonic()
            ctx = self._contexts[session_id]
            ctx.touch()
            if was_idle:
                self._idle_sessions.discard(session_id)
                tracker = self._latencies.get(session_id)
                idle_ms = tracker.exit_idle() if tracker else 0.0
                self._fire(
                    session_id,
                    "VOICE_CONVERSATION_RESUMED",
                    {"idle_delay_ms": round(idle_ms, 2)},
                )
                emit_voice_diagnostic(
                    "VOICE_CONVERSATION_RESUMED",
                    session_id=session_id,
                    idle_delay_ms=round(idle_ms, 2),
                )

    def mark_idle(self, session_id: str) -> None:
        with self._lock:
            if session_id not in self._contexts:
                return
            if session_id in self._idle_sessions:
                return
            self._idle_sessions.add(session_id)
            tracker = self._latencies.get(session_id)
            if tracker:
                tracker.enter_idle()
            self._fire(session_id, "VOICE_CONVERSATION_IDLE", {})
            emit_voice_diagnostic("VOICE_CONVERSATION_IDLE", session_id=session_id)

    def note_turn(
        self,
        session_id: str,
        *,
        transcript: str | None,
        assistant_text: str | None,
        speaker_identity: str | None = None,
        temporary_context: dict[str, Any] | None = None,
    ) -> ConversationContext | None:
        with self._lock:
            ctx = self._contexts.get(session_id)
            if ctx is None:
                return None
            ctx.turn_count += 1
            ctx.last_transcript = transcript
            ctx.last_assistant_text = assistant_text
            if speaker_identity:
                ctx.speaker_identity = speaker_identity
            if temporary_context:
                ctx.temporary_context.update(temporary_context)
            ctx.touch()
            self._session_activity[session_id] = time.monotonic()
            # Refresh recovery with latest speaker.
            token = self._session_to_recovery.get(session_id)
            if token and token in self._recoveries:
                rec = self._recoveries[token]
                rec.speaker_identity = ctx.speaker_identity
            return ctx

    def sync_mission_goal(
        self,
        session_id: str,
        *,
        mission_id: str | None = None,
        goal: str | None = None,
        workspace_hint: str | None = None,
    ) -> None:
        with self._lock:
            ctx = self._contexts.get(session_id)
            if ctx is None:
                return
            if mission_id is not None:
                ctx.active_mission_id = mission_id
            if goal is not None:
                ctx.active_goal = goal
            if workspace_hint is not None:
                ctx.workspace_hint = workspace_hint
            ctx.touch()

    def get_context(self, session_id: str) -> ConversationContext | None:
        with self._lock:
            return self._contexts.get(session_id)

    def get_latency(self, session_id: str) -> LatencyTracker | None:
        with self._lock:
            return self._latencies.get(session_id)

    def get_cancellation(self, session_id: str) -> TurnCancellation | None:
        with self._lock:
            return self._cancellations.get(session_id)

    def reset_turn_cancellation(self, session_id: str) -> TurnCancellation:
        with self._lock:
            token = TurnCancellation()
            self._cancellations[session_id] = token
            return token

    def cancel_turn(self, session_id: str) -> None:
        with self._lock:
            token = self._cancellations.get(session_id)
            if token is not None:
                token.cancel_all()

    # ------------------------------------------------------------------
    # Timeouts (event-driven checks — no background polling)
    # ------------------------------------------------------------------

    def check_timeouts(self, session_id: str) -> str | None:
        """Return ``idle`` / ``conversation`` / None. Caller closes if needed."""
        with self._lock:
            started = self._session_started.get(session_id)
            activity = self._session_activity.get(session_id)
            if started is None or activity is None:
                return None
            now = time.monotonic()
            if now - started >= self._config.conversation_timeout_seconds:
                return "conversation"
            if now - activity >= self._config.idle_timeout_seconds:
                return "idle"
            return None

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    def recover(
        self,
        *,
        recovery_token: str | None = None,
        conversation_id: str | None = None,
        authenticated_user: str,
    ) -> dict[str, Any]:
        """Resolve a prior session for browser refresh / reconnect."""
        with self._lock:
            self._purge_expired_recoveries_locked()
            record: RecoveryRecord | None = None
            if recovery_token:
                record = self._recoveries.get(recovery_token)
            elif conversation_id:
                for rec in self._recoveries.values():
                    if (
                        rec.conversation_id == conversation_id
                        and rec.authenticated_user == authenticated_user
                    ):
                        record = rec
                        break
            if record is None or record.expires_at < time.monotonic():
                raise VoiceSessionError("No recoverable voice session")
            if record.authenticated_user != authenticated_user:
                raise VoiceSessionError("Recovery token user mismatch")
            emit_voice_diagnostic(
                "VOICE_SESSION_RECOVERED",
                session_id=record.session_id,
                conversation_id=record.conversation_id,
            )
            self._fire(
                record.session_id,
                "VOICE_SESSION_RECOVERED",
                {
                    "session_id": record.session_id,
                    "conversation_id": record.conversation_id,
                },
            )
            ctx = self._contexts.get(record.session_id)
            return {
                "recovered": True,
                "recovery": record.to_safe_dict(),
                "conversation": ctx.to_safe_dict() if ctx else None,
                "session_still_active": record.session_id in self._contexts,
            }

    def close_session(self, session_id: str, *, reason: str = "closed") -> None:
        with self._lock:
            self._fire(
                session_id,
                "VOICE_SESSION_CLOSED",
                {"reason": reason},
            )
            emit_voice_diagnostic(
                "VOICE_SESSION_CLOSED",
                session_id=session_id,
                reason=reason,
            )
            self._contexts.pop(session_id, None)
            self._session_activity.pop(session_id, None)
            self._session_started.pop(session_id, None)
            self._idle_sessions.discard(session_id)
            self._cancellations.pop(session_id, None)
            self._latencies.pop(session_id, None)
            self._event_buffers.pop(session_id, None)
            token = self._session_to_recovery.pop(session_id, None)
            # Keep recovery token briefly for refresh; only drop on hard cancel.
            if reason in {"cancel", "timeout", "conversation_timeout"} and token:
                self._recoveries.pop(token, None)

    def drain_events(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            events = self._event_buffers.get(session_id, [])
            self._event_buffers[session_id] = []
            return events

    def push_event(self, session_id: str, event: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._fire(session_id, event, payload)

    def latency_snapshot(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            tracker = self._latencies.get(session_id)
            return tracker.to_dict() if tracker else ConversationLatencyMetrics().to_dict()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _issue_recovery_locked(
        self,
        *,
        session_id: str,
        conversation_id: str,
        authenticated_user: str,
        capture_mode: str,
        speaker_identity: str | None,
    ) -> RecoveryRecord:
        # Replace prior recovery for this session.
        old = self._session_to_recovery.pop(session_id, None)
        if old:
            self._recoveries.pop(old, None)
        token = uuid4().hex
        now = time.monotonic()
        record = RecoveryRecord(
            recovery_token=token,
            session_id=session_id,
            conversation_id=conversation_id,
            authenticated_user=authenticated_user,
            capture_mode=capture_mode,
            speaker_identity=speaker_identity,
            created_at=now,
            expires_at=now + self._config.recovery_ttl_seconds,
        )
        self._recoveries[token] = record
        self._session_to_recovery[session_id] = token
        return record

    def _purge_expired_recoveries_locked(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._recoveries.items() if v.expires_at < now]
        for key in expired:
            rec = self._recoveries.pop(key, None)
            if rec and self._session_to_recovery.get(rec.session_id) == key:
                self._session_to_recovery.pop(rec.session_id, None)

    def _fire(self, session_id: str, event: str, payload: dict[str, Any]) -> None:
        entry = {"event": event, "session_id": session_id, **payload, "ts": time.time()}
        buf = self._event_buffers.setdefault(session_id, [])
        buf.append(entry)
        # Cap buffer to avoid unbounded growth.
        if len(buf) > 200:
            del buf[:-100]
        if self._emit is not None:
            try:
                self._emit(event, {"session_id": session_id, **payload})
            except Exception as exc:
                logger.debug("Conversation engine emit failed: %s", exc)

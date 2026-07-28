# =====================================
# Titan Brain Lock (Phase 19.6)
# =====================================

"""Process-global Brain lock with ownership tokens, heartbeats, and stale reclaim.

Serialization is preserved: at most one healthy owner runs Brain at a time.
Stale ownership (abandoned SSE / hung cleanup) can be reclaimed safely so the
service never stays permanently ``brain_busy``.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

_LOCK_WAIT_SLICE_SECONDS = 0.05


class BrainLockState(str, Enum):
    IDLE = "IDLE"
    WAITING = "WAITING"
    ACQUIRED = "ACQUIRED"
    RUNNING = "RUNNING"
    STREAMING = "STREAMING"
    RELEASING = "RELEASING"
    RELEASED = "RELEASED"
    STALE = "STALE"
    RECLAIMED = "RECLAIMED"


@dataclass
class BrainLockOwnership:
    """Mutable ownership snapshot protected by ``_state_lock``."""

    owner_request_id: str | None = None
    generation: int = 0
    acquired_at: float | None = None
    last_heartbeat_at: float | None = None
    owner_thread_id: int | None = None
    owner_thread_ref: threading.Thread | None = None
    owner_state: str = BrainLockState.IDLE.value
    release_reason: str | None = None
    stale_reclaim_count: int = 0
    waiter_count: int = 0
    last_error_code: str | None = None


@dataclass
class BrainLockConfig:
    wait_timeout_seconds: float = 5.0
    stale_seconds: float = 45.0
    heartbeat_seconds: float = 2.0
    reclaim_enabled: bool = True


def _safe_float(raw: Any, default: float, *, minimum: float = 0.05) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value != value or value <= 0:  # NaN / non-positive
        return default
    return max(minimum, value)


def _safe_bool(raw: Any, default: bool = True) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def load_brain_lock_config(
    *,
    wait_timeout: Any = None,
    stale_seconds: Any = None,
    heartbeat_seconds: Any = None,
    reclaim_enabled: Any = None,
) -> BrainLockConfig:
    """Load config with safe production defaults and invalid-value fallback."""
    wait = _safe_float(wait_timeout, 5.0, minimum=0.05)
    stale = _safe_float(stale_seconds, 45.0, minimum=0.1)
    heartbeat = _safe_float(heartbeat_seconds, 2.0, minimum=0.05)
    reclaim = _safe_bool(reclaim_enabled, True)

    # Stale threshold must exceed normal lock wait timeout.
    if stale <= wait:
        stale = max(wait * 3.0, wait + 10.0, 45.0)
    # Heartbeat interval must be much smaller than stale threshold.
    if heartbeat >= stale / 3.0:
        heartbeat = max(0.05, min(2.0, stale / 10.0))

    return BrainLockConfig(
        wait_timeout_seconds=wait,
        stale_seconds=stale,
        heartbeat_seconds=heartbeat,
        reclaim_enabled=reclaim,
    )


def _short_request_id(request_id: str | None) -> str | None:
    if not request_id:
        return None
    cleaned = request_id.strip()
    if len(cleaned) <= 12:
        return cleaned
    return f"{cleaned[:8]}…{cleaned[-4:]}"


class BrainLockManager:
    """Serialize Brain turns with heartbeat-aware stale reclaim."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], BrainLockConfig] | None = None,
        active_request_checker: Callable[[str], dict[str, Any] | None] | None = None,
        log_fn: Callable[..., None] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._ownership = BrainLockOwnership()
        self._generation_seq = 0
        self._invalidated_generations: set[int] = set()
        self._last_heartbeat_log_at = 0.0
        self._config_loader = config_loader or (lambda: load_brain_lock_config())
        self._active_request_checker = active_request_checker
        self._log = log_fn or (lambda event, **fields: None)
        # Test hooks (deterministic reclaim / hang simulation).
        self._test_force_stale: bool = False
        self._test_block_release: threading.Event | None = None

    @property
    def raw_lock(self) -> threading.Lock:
        return self._lock

    def config(self) -> BrainLockConfig:
        return self._config_loader()

    def owner_snapshot(self) -> str | None:
        with self._state_lock:
            return self._ownership.owner_request_id

    def generation_snapshot(self) -> int:
        with self._state_lock:
            return self._ownership.generation

    def is_generation_valid(self, generation: int | None) -> bool:
        if generation is None or generation <= 0:
            return False
        with self._state_lock:
            return generation not in self._invalidated_generations

    def diagnostics(self) -> dict[str, Any]:
        """Safe operational fields only — no secrets or message bodies."""
        cfg = self.config()
        now = time.monotonic()
        with self._state_lock:
            own = self._ownership
            owner = own.owner_request_id
            acquired = own.acquired_at
            heartbeat = own.last_heartbeat_at
            state = own.owner_state
            generation = own.generation
            waiters = own.waiter_count
            reclaim_count = own.stale_reclaim_count
            release_reason = own.release_reason
            last_error = own.last_error_code
            held = self._lock.locked()
        lock_age_ms = (
            int((now - acquired) * 1000) if acquired is not None else None
        )
        heartbeat_age_ms = (
            int((now - heartbeat) * 1000) if heartbeat is not None else None
        )
        return {
            "lock_state": state if owner or held else BrainLockState.IDLE.value,
            "owner_request_id": _short_request_id(owner),
            "owner_present": owner is not None,
            "lock_held": held,
            "lock_age_ms": lock_age_ms,
            "heartbeat_age_ms": heartbeat_age_ms,
            "generation": generation,
            "waiters": waiters,
            "stale_reclaim_count": reclaim_count,
            "last_release_reason": release_reason,
            "last_error_code": last_error,
            "stale_seconds": cfg.stale_seconds,
            "wait_timeout_seconds": cfg.wait_timeout_seconds,
            "heartbeat_seconds": cfg.heartbeat_seconds,
            "reclaim_enabled": cfg.reclaim_enabled,
        }

    def _emit(self, event: str, **fields: Any) -> None:
        safe = dict(fields)
        if "owner" in safe and isinstance(safe["owner"], str):
            safe["owner"] = _short_request_id(safe["owner"])
        if "stale_owner" in safe and isinstance(safe["stale_owner"], str):
            safe["stale_owner"] = _short_request_id(safe["stale_owner"])
        self._log(event, **safe)

    def _owner_terminal_or_absent(self, owner_request_id: str) -> tuple[bool, str]:
        """Return (is_abandonable, reason) for stale-condition third clause."""
        checker = self._active_request_checker
        if checker is None:
            return True, "no_active_registry"
        info = checker(owner_request_id)
        if info is None:
            return True, "owner_not_registered"
        if info.get("cancelled"):
            return True, "owner_cancelled"
        if info.get("expired"):
            return True, "owner_deadline_expired"
        if info.get("terminal"):
            return True, "owner_terminal"
        return False, "owner_active"

    def _thread_dead(self, thread_ref: threading.Thread | None) -> bool:
        if thread_ref is None:
            return False
        try:
            return not thread_ref.is_alive()
        except Exception:
            return False

    def evaluate_stale(
        self,
        *,
        now: float | None = None,
        cfg: BrainLockConfig | None = None,
    ) -> dict[str, Any]:
        """Inspect whether current ownership is safely reclaimable."""
        cfg = cfg or self.config()
        now = time.monotonic() if now is None else now
        with self._state_lock:
            own = self._ownership
            owner = own.owner_request_id
            acquired = own.acquired_at
            heartbeat = own.last_heartbeat_at
            generation = own.generation
            thread_ref = own.owner_thread_ref
            state = own.owner_state
            if owner is None or acquired is None:
                return {
                    "stale": False,
                    "reason": "no_owner",
                    "owner": None,
                    "generation": generation,
                }
            lock_age = now - acquired
            hb_at = heartbeat if heartbeat is not None else acquired
            heartbeat_age = now - hb_at
            snapshot = {
                "owner": owner,
                "generation": generation,
                "lock_age": lock_age,
                "heartbeat_age": heartbeat_age,
                "state": state,
            }

        if self._test_force_stale:
            abandonable, abandon_reason = True, "test_force_stale"
        else:
            if lock_age < cfg.stale_seconds:
                return {
                    "stale": False,
                    "reason": "lock_age_ok",
                    **snapshot,
                    "abandon_reason": None,
                }
            if heartbeat_age < cfg.stale_seconds:
                return {
                    "stale": False,
                    "reason": "heartbeat_fresh",
                    **snapshot,
                    "abandon_reason": None,
                }
            abandonable, abandon_reason = self._owner_terminal_or_absent(owner)
            if not abandonable and self._thread_dead(thread_ref):
                abandonable, abandon_reason = True, "owner_thread_dead"
            if not abandonable:
                return {
                    "stale": False,
                    "reason": "owner_still_active",
                    **snapshot,
                    "abandon_reason": abandon_reason,
                }

        return {
            "stale": True,
            "reason": "stale_conditions_met",
            **snapshot,
            "abandon_reason": abandon_reason,
            "lock_age_ms": int(lock_age * 1000),
            "heartbeat_age_ms": int(heartbeat_age * 1000),
        }

    def try_reclaim_stale(self, *, waiter_request_id: str) -> bool:
        """Atomically reclaim a stale lock. Returns True when lock was freed."""
        cfg = self.config()
        if not cfg.reclaim_enabled and not self._test_force_stale:
            self._emit(
                "CHAT_BRAIN_LOCK_RECLAIM_REJECTED",
                request_id=waiter_request_id,
                result="reclaim_disabled",
                stage="lock",
            )
            return False

        # Serialize inspect+reclaim under state mutex; only one waiter wins.
        with self._state_lock:
            self._emit(
                "CHAT_BRAIN_LOCK_RECLAIM_ATTEMPT",
                request_id=waiter_request_id,
                owner=self._ownership.owner_request_id,
                generation=self._ownership.generation,
                stage="lock",
            )
            verdict = self._evaluate_stale_unlocked(cfg=cfg)
            if not verdict.get("stale"):
                self._emit(
                    "CHAT_BRAIN_LOCK_RECLAIM_REJECTED",
                    request_id=waiter_request_id,
                    owner=verdict.get("owner"),
                    generation=verdict.get("generation"),
                    result=verdict.get("reason"),
                    stage="lock",
                )
                return False

            stale_owner = self._ownership.owner_request_id
            stale_gen = self._ownership.generation
            held_ms = verdict.get("lock_age_ms")
            self._invalidated_generations.add(stale_gen)
            # Cap invalidated set to avoid unbounded growth in long-lived workers.
            if len(self._invalidated_generations) > 4096:
                oldest = sorted(self._invalidated_generations)[:2048]
                self._invalidated_generations.difference_update(oldest)

            self._ownership.owner_state = BrainLockState.STALE.value
            self._emit(
                "CHAT_BRAIN_LOCK_STALE_DETECTED",
                request_id=waiter_request_id,
                stale_owner=stale_owner,
                generation=stale_gen,
                held_ms=held_ms,
                heartbeat_age_ms=verdict.get("heartbeat_age_ms"),
                abandon_reason=verdict.get("abandon_reason"),
                stage="lock",
            )

            self._ownership.owner_request_id = None
            self._ownership.acquired_at = None
            self._ownership.last_heartbeat_at = None
            self._ownership.owner_thread_id = None
            self._ownership.owner_thread_ref = None
            self._ownership.owner_state = BrainLockState.RECLAIMED.value
            self._ownership.release_reason = "stale_reclaim"
            self._ownership.stale_reclaim_count += 1
            reclaim_count = self._ownership.stale_reclaim_count

        try:
            self._lock.release()
        except RuntimeError:
            logger.exception(
                "CHAT_BRAIN_LOCK_RECLAIMED request_id=%s result=release_error "
                "stale_owner=%s",
                waiter_request_id,
                stale_owner,
            )
            self._emit(
                "CHAT_BRAIN_LOCK_RECLAIM_REJECTED",
                request_id=waiter_request_id,
                stale_owner=stale_owner,
                generation=stale_gen,
                result="release_error",
                stage="lock",
            )
            return False

        self._emit(
            "CHAT_BRAIN_LOCK_RECLAIMED",
            request_id=waiter_request_id,
            stale_owner=stale_owner,
            generation=stale_gen,
            result="reclaimed",
            held_ms=held_ms,
            stale_reclaim_count=reclaim_count,
            stage="lock",
        )
        logger.warning(
            "CHAT_BRAIN_LOCK_RECLAIMED request_id=%s stale_owner=%s "
            "generation=%s held_ms=%s",
            waiter_request_id,
            stale_owner,
            stale_gen,
            held_ms,
        )
        return True

    def _evaluate_stale_unlocked(self, *, cfg: BrainLockConfig) -> dict[str, Any]:
        """Stale evaluation assuming ``_state_lock`` is held for ownership fields.

        Active-request checker is invoked without re-entering ``_state_lock``.
        """
        own = self._ownership
        owner = own.owner_request_id
        acquired = own.acquired_at
        heartbeat = own.last_heartbeat_at
        generation = own.generation
        thread_ref = own.owner_thread_ref
        state = own.owner_state
        if owner is None or acquired is None:
            return {
                "stale": False,
                "reason": "no_owner",
                "owner": None,
                "generation": generation,
            }

        now = time.monotonic()
        lock_age = now - acquired
        hb_at = heartbeat if heartbeat is not None else acquired
        heartbeat_age = now - hb_at
        snapshot = {
            "owner": owner,
            "generation": generation,
            "lock_age": lock_age,
            "heartbeat_age": heartbeat_age,
            "state": state,
            "lock_age_ms": int(lock_age * 1000),
            "heartbeat_age_ms": int(heartbeat_age * 1000),
        }

        if self._test_force_stale:
            return {
                "stale": True,
                "reason": "stale_conditions_met",
                **snapshot,
                "abandon_reason": "test_force_stale",
            }

        if lock_age < cfg.stale_seconds:
            return {"stale": False, "reason": "lock_age_ok", **snapshot}
        if heartbeat_age < cfg.stale_seconds:
            return {"stale": False, "reason": "heartbeat_fresh", **snapshot}

        # Release state lock briefly for checker to avoid nested lock hazards.
        # Caller holds _state_lock — checker must not call back into manager
        # methods that take _state_lock. Checker only reads deadlines.
        abandonable, abandon_reason = self._owner_terminal_or_absent(owner)
        if not abandonable and self._thread_dead(thread_ref):
            abandonable, abandon_reason = True, "owner_thread_dead"
        if not abandonable:
            return {
                "stale": False,
                "reason": "owner_still_active",
                **snapshot,
                "abandon_reason": abandon_reason,
            }
        return {
            "stale": True,
            "reason": "stale_conditions_met",
            **snapshot,
            "abandon_reason": abandon_reason,
        }

    def acquire(
        self,
        request_id: str,
        *,
        timeout_seconds: float | None = None,
        deadline_check: Callable[[], None] | None = None,
        remaining_budget_ms: Callable[[], int | None] | None = None,
    ) -> int | None:
        """Acquire lock; return ownership generation or None on bounded timeout."""
        cfg = self.config()
        budget = (
            cfg.wait_timeout_seconds
            if timeout_seconds is None
            else max(0.05, float(timeout_seconds))
        )
        wait_started = time.monotonic()
        with self._state_lock:
            self._ownership.waiter_count += 1
            owner_before = self._ownership.owner_request_id
            generation_before = self._ownership.generation
        self._emit(
            "CHAT_BRAIN_LOCK_WAIT",
            request_id=request_id,
            wait_ms=0,
            owner=owner_before,
            generation=generation_before,
            result="waiting",
            remaining_budget_ms=(
                remaining_budget_ms() if remaining_budget_ms else None
            ),
            stage="lock_wait",
        )
        self._emit(
            "CHAT_BRAIN_LOCK_SNAPSHOT",
            request_id=request_id,
            **{
                k: v
                for k, v in self.diagnostics().items()
                if k
                in {
                    "lock_state",
                    "owner_request_id",
                    "lock_age_ms",
                    "heartbeat_age_ms",
                    "generation",
                    "waiters",
                    "stale_reclaim_count",
                }
            },
            stage="lock_wait",
        )

        try:
            while True:
                if deadline_check is not None:
                    deadline_check()
                waited = time.monotonic() - wait_started
                remaining_lock = budget - waited
                if remaining_lock <= 0:
                    if self.try_reclaim_stale(waiter_request_id=request_id):
                        wait_started = time.monotonic()
                        continue
                    # Another waiter may have just reclaimed — try once without wait.
                    if self._lock.acquire(timeout=0):
                        waited_ms = int((time.monotonic() - wait_started) * 1000)
                        now = time.monotonic()
                        thread = threading.current_thread()
                        with self._state_lock:
                            self._generation_seq += 1
                            generation = self._generation_seq
                            self._ownership.owner_request_id = request_id
                            self._ownership.generation = generation
                            self._ownership.acquired_at = now
                            self._ownership.last_heartbeat_at = now
                            self._ownership.owner_thread_id = threading.get_ident()
                            self._ownership.owner_thread_ref = thread
                            self._ownership.owner_state = BrainLockState.ACQUIRED.value
                            self._ownership.release_reason = None
                            self._ownership.last_error_code = None
                        self._emit(
                            "CHAT_BRAIN_LOCK_ACQUIRED",
                            request_id=request_id,
                            wait_ms=waited_ms,
                            owner=request_id,
                            generation=generation,
                            result="acquired_after_reclaim_race",
                            remaining_budget_ms=(
                                remaining_budget_ms() if remaining_budget_ms else None
                            ),
                            stage="lock",
                        )
                        return generation
                    with self._state_lock:
                        owner_now = self._ownership.owner_request_id
                        self._ownership.last_error_code = "brain_busy"
                    self._emit(
                        "CHAT_BRAIN_LOCK_TIMEOUT",
                        request_id=request_id,
                        wait_ms=int(waited * 1000),
                        owner=owner_now,
                        result="timeout",
                        remaining_budget_ms=(
                            remaining_budget_ms() if remaining_budget_ms else None
                        ),
                        stage="lock_wait",
                    )
                    return None

                rem_budget = 30.0
                if remaining_budget_ms is not None:
                    ms = remaining_budget_ms()
                    if ms is not None:
                        rem_budget = max(0.01, ms / 1000.0)
                slice_timeout = min(
                    _LOCK_WAIT_SLICE_SECONDS,
                    remaining_lock,
                    rem_budget,
                )
                if self._lock.acquire(timeout=slice_timeout):
                    waited_ms = int((time.monotonic() - wait_started) * 1000)
                    now = time.monotonic()
                    thread = threading.current_thread()
                    with self._state_lock:
                        self._generation_seq += 1
                        generation = self._generation_seq
                        self._ownership.owner_request_id = request_id
                        self._ownership.generation = generation
                        self._ownership.acquired_at = now
                        self._ownership.last_heartbeat_at = now
                        self._ownership.owner_thread_id = threading.get_ident()
                        self._ownership.owner_thread_ref = thread
                        self._ownership.owner_state = BrainLockState.ACQUIRED.value
                        self._ownership.release_reason = None
                        self._ownership.last_error_code = None
                    self._emit(
                        "CHAT_BRAIN_LOCK_ACQUIRED",
                        request_id=request_id,
                        wait_ms=waited_ms,
                        owner=request_id,
                        generation=generation,
                        result="acquired",
                        remaining_budget_ms=(
                            remaining_budget_ms() if remaining_budget_ms else None
                        ),
                        stage="lock",
                    )
                    return generation
        finally:
            with self._state_lock:
                self._ownership.waiter_count = max(0, self._ownership.waiter_count - 1)

    def heartbeat(
        self,
        request_id: str,
        generation: int,
        *,
        state: str | None = None,
        force_log: bool = False,
    ) -> bool:
        """Update ownership heartbeat if ``generation`` still owns the lock."""
        cfg = self.config()
        now = time.monotonic()
        with self._state_lock:
            own = self._ownership
            if (
                own.owner_request_id != request_id
                or own.generation != generation
                or generation in self._invalidated_generations
            ):
                return False
            own.last_heartbeat_at = now
            if state:
                own.owner_state = state
            should_log = force_log or (
                now - self._last_heartbeat_log_at >= cfg.heartbeat_seconds
            )
            if should_log:
                self._last_heartbeat_log_at = now
                log_fields = {
                    "request_id": request_id,
                    "generation": generation,
                    "owner_state": own.owner_state,
                    "lock_age_ms": (
                        int((now - own.acquired_at) * 1000)
                        if own.acquired_at is not None
                        else None
                    ),
                    "stage": "heartbeat",
                }
            else:
                log_fields = None
        if log_fields is not None:
            self._emit("CHAT_BRAIN_LOCK_HEARTBEAT", **log_fields)
        return True

    def set_state(self, request_id: str, generation: int, state: str) -> bool:
        return self.heartbeat(request_id, generation, state=state, force_log=False)

    def release(
        self,
        request_id: str,
        generation: int | None,
        *,
        reason: str = "released",
    ) -> bool:
        """Release only when ownership token still matches."""
        if generation is not None and not self.is_generation_valid(generation):
            self._emit(
                "CHAT_BRAIN_STALE_OWNER_RESUMED",
                request_id=request_id,
                generation=generation,
                result="stale_generation",
                stage="lock",
            )
            self._emit(
                "CHAT_BRAIN_LOCK_RELEASE_SKIPPED_OWNER_MISMATCH",
                request_id=request_id,
                generation=generation,
                result="stale_generation",
                stage="lock",
            )
            self._emit(
                "CHAT_BRAIN_STALE_OWNER_IGNORED",
                request_id=request_id,
                generation=generation,
                result="release_skipped",
                stage="lock",
            )
            return False

        if self._test_block_release is not None:
            self._test_block_release.wait(timeout=30.0)

        with self._state_lock:
            own = self._ownership
            owner = own.owner_request_id
            current_gen = own.generation
            acquired_at = own.acquired_at
            if owner != request_id or (
                generation is not None and current_gen != generation
            ):
                self._emit(
                    "CHAT_BRAIN_LOCK_RELEASE_SKIPPED_OWNER_MISMATCH",
                    request_id=request_id,
                    owner=owner,
                    generation=generation,
                    current_generation=current_gen,
                    result="skipped_not_owner",
                    stage="lock",
                )
                return False
            if generation in self._invalidated_generations:
                self._emit(
                    "CHAT_BRAIN_LOCK_RELEASE_SKIPPED_OWNER_MISMATCH",
                    request_id=request_id,
                    generation=generation,
                    result="invalidated",
                    stage="lock",
                )
                return False

            own.owner_state = BrainLockState.RELEASING.value
            held_ms = (
                int((time.monotonic() - acquired_at) * 1000)
                if acquired_at is not None
                else None
            )
            own.owner_request_id = None
            own.acquired_at = None
            own.last_heartbeat_at = None
            own.owner_thread_id = None
            own.owner_thread_ref = None
            own.owner_state = BrainLockState.RELEASED.value
            own.release_reason = reason
            # Keep generation number for diagnostics; next acquire bumps it.

        try:
            self._lock.release()
        except RuntimeError:
            logger.exception(
                "CHAT_BRAIN_LOCK_RELEASED request_id=%s result=release_error",
                request_id,
            )
            self._emit(
                "CHAT_BRAIN_LOCK_RELEASED",
                request_id=request_id,
                owner=request_id,
                generation=generation,
                result="release_error",
                held_ms=held_ms,
                stage="lock",
            )
            return False

        self._emit(
            "CHAT_BRAIN_LOCK_RELEASED",
            request_id=request_id,
            owner=request_id,
            generation=generation,
            result=reason,
            held_ms=held_ms,
            stage="lock",
        )
        return True

    def reset_for_tests(self) -> None:
        """Drop ownership metadata and ensure the lock is free."""
        with self._state_lock:
            owned = self._ownership.owner_request_id is not None
            self._ownership = BrainLockOwnership()
            self._invalidated_generations.clear()
            self._test_force_stale = False
            self._test_block_release = None
            self._last_heartbeat_log_at = 0.0
        if owned:
            try:
                self._lock.release()
            except RuntimeError:
                pass
        if self._lock.acquire(timeout=0.01):
            self._lock.release()

# =====================================
# Titan Streaming Brain Adapter
# =====================================

"""Incremental Brain reasoning for live voice turns (Phase 20.5).

Emits response deltas / sentence completions while preserving a single
Brain.process_request() call — no duplicated assistant response or reasoning.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from voice.cancellation import CancelToken

if TYPE_CHECKING:
    from brain.brain import Brain

logger = logging.getLogger(__name__)

StreamEmit = Callable[[str, dict[str, Any]], None]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class StreamingBrainResult:
    """Outcome of one streaming Brain turn."""

    final_text: str = ""
    deltas: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)
    first_token_ms: float = 0.0
    completed_ms: float = 0.0
    cancelled: bool = False
    duplicate_prevented: bool = False

    def to_safe_dict(self) -> dict[str, Any]:
        preview = self.final_text
        if len(preview) > 120:
            preview = preview[:120] + "…"
        return {
            "chars": len(self.final_text),
            "delta_count": len(self.deltas),
            "sentence_count": len(self.sentences),
            "first_token_ms": round(self.first_token_ms, 2),
            "completed_ms": round(self.completed_ms, 2),
            "cancelled": self.cancelled,
            "duplicate_prevented": self.duplicate_prevented,
            "preview": preview or None,
        }


class StreamingBrainAdapter:
    """Runs Brain.process_request once with a delta stream + cancel token."""

    def __init__(
        self,
        brain: Brain,
        *,
        emit: StreamEmit | None = None,
        cancel_token: CancelToken | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._brain = brain
        self._emit = emit
        self._cancel = cancel_token or CancelToken(name="brain")
        self._timeout = float(timeout_seconds)
        self._lock = threading.Lock()
        self._completed_keys: set[str] = set()

    @property
    def cancel_token(self) -> CancelToken:
        return self._cancel

    def reset_cancel(self) -> None:
        self._cancel.reset()

    def run(
        self,
        request: str,
        *,
        turn_key: str | None = None,
    ) -> StreamingBrainResult:
        """Execute Brain once. Duplicate turn_key returns empty (no re-run)."""
        result = StreamingBrainResult()
        key = turn_key or request[:96]
        with self._lock:
            if key in self._completed_keys:
                result.duplicate_prevented = True
                return result
            # Reserve key early so parallel double-submit cannot re-enter.
            self._completed_keys.add(key)

        if self._cancel.cancelled:
            result.cancelled = True
            return result

        self._fire("BRAIN_STREAM_STARTED", {"chars": len(request)})
        started = time.perf_counter()
        first_token_at: list[float] = []
        sentence_buf = ""
        adapter = self

        class _Stream:
            def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
                del event_type, data

            def emit_text_delta(self, text: str) -> None:
                if not text or adapter._cancel.cancelled:
                    return
                if not first_token_at:
                    first_token_at.append(time.perf_counter())
                    result.first_token_ms = (first_token_at[0] - started) * 1000.0
                result.deltas.append(text)
                nonlocal sentence_buf
                sentence_buf += text
                adapter._fire(
                    "BRAIN_STREAM_DELTA",
                    {"chars": len(text), "total_chars": sum(len(d) for d in result.deltas)},
                )
                # Emit sentence completions when punctuation lands.
                while True:
                    match = _SENTENCE_SPLIT_RE.search(sentence_buf)
                    if not match:
                        break
                    sentence = sentence_buf[: match.start()].strip()
                    sentence_buf = sentence_buf[match.end() :]
                    if sentence:
                        result.sentences.append(sentence)
                        adapter._fire(
                            "BRAIN_STREAM_SENTENCE",
                            {"chars": len(sentence), "index": len(result.sentences) - 1},
                        )

            def emit_response_started(self) -> None:
                return None

            def start_thinking(self, **kwargs: Any) -> None:
                del kwargs

            def finish_thinking(self) -> None:
                return None

        try:
            brain_result = self._call_with_timeout(
                lambda: self._brain.process_request(request, stream=_Stream()),
            )
            if self._cancel.cancelled:
                result.cancelled = True
                result.final_text = "".join(result.deltas).strip()
                result.completed_ms = (time.perf_counter() - started) * 1000.0
                self._fire("BRAIN_STREAM_COMPLETED", {"cancelled": True, **result.to_safe_dict()})
                return result

            response_text = (getattr(brain_result, "final_response", None) or "").strip()
            if not result.deltas and response_text:
                # Providers that skip streaming still yield one synthetic delta.
                _Stream().emit_text_delta(response_text)
            result.final_text = response_text or "".join(result.deltas).strip()
            if sentence_buf.strip():
                result.sentences.append(sentence_buf.strip())
            if not first_token_at and result.final_text:
                result.first_token_ms = (time.perf_counter() - started) * 1000.0
            result.completed_ms = (time.perf_counter() - started) * 1000.0
            self._fire("BRAIN_STREAM_COMPLETED", result.to_safe_dict())
            return result
        except Exception:
            # Allow retry on hard failure by releasing the reservation.
            with self._lock:
                self._completed_keys.discard(key)
            raise

    def _call_with_timeout(self, fn: Callable[[], Any]) -> Any:
        box: dict[str, Any] = {}
        error: list[BaseException] = []

        def _target() -> None:
            try:
                box["value"] = fn()
            except BaseException as exc:  # noqa: BLE001 — re-raised below
                error.append(exc)

        thread = threading.Thread(target=_target, name="voice-brain-stream", daemon=True)
        thread.start()
        thread.join(timeout=self._timeout)
        if thread.is_alive():
            self._cancel.cancel()
            from voice.exceptions import VoiceProviderError

            raise VoiceProviderError("Brain stream timed out")
        if error:
            raise error[0]
        return box.get("value")

    def _fire(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is None:
            return
        try:
            self._emit(event, payload)
        except Exception as exc:
            logger.debug("Streaming Brain emit failed: %s", exc)

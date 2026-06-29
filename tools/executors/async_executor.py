# =====================================
# Titan Async Executor
# =====================================

"""Thread-pool async execution foundation for tool runs (Phase 10A — P10A-026)."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from config.settings import TITAN_TOOL_ASYNC_POOL_SIZE, TITAN_TOOL_MAX_CONCURRENT_RUNS
from tools.cancellation_registry import CancellationRegistry
from tools.executors.sync_executor import SyncExecutor
from tools.tool_result import ToolResult


@dataclass
class AsyncExecutor:
    """Submit sync tool work to a thread pool for async/background delivery."""

    sync_executor: SyncExecutor
    cancellation_registry: CancellationRegistry
    max_workers: int = TITAN_TOOL_ASYNC_POOL_SIZE
    max_concurrent_runs: int = TITAN_TOOL_MAX_CONCURRENT_RUNS
    _pool: ThreadPoolExecutor | None = field(default=None, init=False, repr=False)
    _futures: dict[str, Future[ToolResult]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        if self._pool is None:
            workers = max(1, min(self.max_workers, self.max_concurrent_runs))
            self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="titan-tool")

    @property
    def active_count(self) -> int:
        """Return number of tracked in-flight futures."""
        with self._lock:
            return sum(1 for future in self._futures.values() if not future.done())

    def submit(
        self,
        run_id: str,
        tool_name: str,
        params: dict,
        *,
        timeout_seconds: float | None = None,
        on_complete: Callable[[str, ToolResult], None] | None = None,
    ) -> Future[ToolResult]:
        """Queue tool execution on the thread pool."""
        self.cancellation_registry.register(run_id)

        def _worker() -> ToolResult:
            if self.cancellation_registry.is_cancelled(run_id):
                reason = self.cancellation_registry.reason(run_id) or "Annulé"
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=reason,
                    source="async_executor",
                    run_id=run_id,
                    metadata={"cancelled": True},
                )
            result = self.sync_executor.execute(
                tool_name,
                params,
                timeout_seconds=timeout_seconds,
            )
            result.run_id = run_id
            if self.cancellation_registry.is_cancelled(run_id):
                reason = self.cancellation_registry.reason(run_id) or "Annulé"
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=reason,
                    source="async_executor",
                    run_id=run_id,
                    metadata={"cancelled": True},
                )
            return result

        assert self._pool is not None
        future = self._pool.submit(_worker)

        def _done_callback(done: Future[ToolResult]) -> None:
            if on_complete is None:
                return
            try:
                on_complete(run_id, done.result())
            except Exception:
                pass

        future.add_done_callback(_done_callback)

        with self._lock:
            self._futures[run_id] = future
        return future

    def get_future(self, run_id: str) -> Future[ToolResult] | None:
        """Return the future for a submitted run."""
        with self._lock:
            return self._futures.get(run_id)

    def poll(self, run_id: str, *, timeout: float | None = None) -> ToolResult | None:
        """Block until the run completes or timeout expires."""
        future = self.get_future(run_id)
        if future is None:
            return None
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            return None

    def shutdown(self, *, wait: bool = False) -> None:
        """Shut down the thread pool."""
        if self._pool is not None:
            self._pool.shutdown(wait=wait, cancel_futures=not wait)

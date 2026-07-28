# =====================================
# Phase 19.4 — Re-run failed heavy scenarios
# =====================================
"""Re-run scenarios 12 (25-turn) and 14 (concurrency) after soak fixes."""

from __future__ import annotations

import json
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import after path setup — reuses isolation from live soak module.
from scripts.phase19_4_live_soak import (  # noqa: E402
    SOAK_DIR,
    _build_brain,
    _ms,
    _pct,
)


def main() -> int:
    brain = _build_brain()
    from core.mission_models import MissionPriority

    brain.mission_manager.create_mission(
        "Phase19.4 Soak Mission",
        "Safe conversation-only soak validation",
        ["Validate greeting", "Validate continuity", "Validate recovery"],
        priority=MissionPriority.NORMAL,
    )

    latencies: list[float] = []

    def _turn(message: str) -> dict:
        rid = f"soak-{uuid.uuid4().hex[:12]}"
        llm = brain.llm
        setattr(llm, "_active_request_id", rid)
        t0 = time.perf_counter()
        result = brain.process_request(message)
        total_ms = _ms(t0)
        latencies.append(total_ms)
        text = (result.final_response or "") if result else ""
        setattr(llm, "_active_request_id", None)
        return {
            "request_id": rid,
            "total_ms": total_ms,
            "response_chars": len(text),
            "response_preview": text[:180],
            "error_code": getattr(llm, "last_error_code", None),
        }

    report: dict = {
        "phase": "19.4-rerun",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": [],
    }

    # --- 12 long conversation ---
    print("=== 12_long_conversation_25 ===", flush=True)
    responses: list[str] = []
    conv_lat: list[float] = []
    t0 = time.perf_counter()
    for i in range(25):
        msg = (
            f"Conversation soak tour {i+1}/25. "
            f"Réponds en une phrase courte confirmant le numéro {i+1} "
            f"et que l'on parle toujours de la validation Phase 19.4."
        )
        out = _turn(msg)
        conv_lat.append(out["total_ms"])
        responses.append(out.get("response_preview") or "")
        print(f"  turn {i+1}/25 {out['total_ms']}ms chars={out['response_chars']}", flush=True)
    dup_pairs = sum(1 for a, b in zip(responses, responses[1:]) if a and a == b)
    active = brain.mission_manager.get_active_mission()
    mission_label = None
    if active is not None:
        mission_label = getattr(active, "title", None) or getattr(active, "name", None)
    s12 = {
        "name": "12_long_conversation_25",
        "ok": len(responses) == 25 and all(responses) and dup_pairs == 0 and active is not None,
        "turns": 25,
        "duplicate_consecutive": dup_pairs,
        "avg_ms": round(statistics.mean(conv_lat), 2),
        "p95_ms": _pct(conv_lat, 95),
        "mission_still_active": mission_label,
        "wall_ms": _ms(t0),
    }
    report["scenarios"].append(s12)
    print(("PASS" if s12["ok"] else "FAIL"), "12", s12, flush=True)

    # --- 14 concurrent ---
    print("=== 14_concurrent ===", flush=True)
    from api.chat_service import (
        _acquire_brain_lock,
        _release_brain_lock,
        reset_brain_lock_for_tests,
    )
    from brain.request_deadline import RequestDeadline

    reset_brain_lock_for_tests()
    results: list[dict] = []

    def worker(n: int) -> dict:
        rid = f"soak-conc-{n}-{uuid.uuid4().hex[:8]}"
        deadline = RequestDeadline.start(total_seconds=30, request_id=rid)
        started = time.perf_counter()
        # Holder keeps the lock longer than waiter lock budgets → bounded busy.
        if n == 0:
            generation = _acquire_brain_lock(rid, deadline, timeout_seconds=5.0)
            if generation is None:
                return {"n": n, "acquired": False, "ms": _ms(started), "busy": True}
            try:
                time.sleep(2.0)
                return {"n": n, "acquired": True, "ms": _ms(started), "busy": False}
            finally:
                _release_brain_lock(rid, generation)
        generation = _acquire_brain_lock(rid, deadline, timeout_seconds=0.4)
        if generation is None:
            return {"n": n, "acquired": False, "ms": _ms(started), "busy": True}
        try:
            time.sleep(0.05)
            return {"n": n, "acquired": True, "ms": _ms(started), "busy": False}
        finally:
            _release_brain_lock(rid, generation)

    t0 = time.perf_counter()
    # Start holder first so waiters contend.
    holder_fut = None
    with ThreadPoolExecutor(max_workers=3) as pool:
        holder_fut = pool.submit(worker, 0)
        time.sleep(0.15)
        futs = [pool.submit(worker, i) for i in (1, 2)]
        results.append(holder_fut.result())
        for f in as_completed(futs):
            results.append(f.result())
    acquired_count = sum(1 for r in results if r.get("acquired"))
    busy_count = sum(1 for r in results if r.get("busy"))
    # Serialized Brain: at least one waiter must see bounded busy/timeout.
    lock_ok = acquired_count >= 1 and busy_count >= 1 and len(results) == 3
    reset_brain_lock_for_tests()

    out_a: dict = {}
    out_b: dict = {}

    def ra() -> None:
        nonlocal out_a
        out_a = _turn("Concurrent A: dis A")

    def rb() -> None:
        nonlocal out_b
        time.sleep(0.05)
        out_b = _turn("Concurrent B: dis B")

    t1 = threading.Thread(target=ra)
    t2 = threading.Thread(target=rb)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    both_ok = out_a.get("response_chars", 0) > 0 and out_b.get("response_chars", 0) > 0
    s14 = {
        "name": "14_concurrent",
        "ok": lock_ok and both_ok,
        "lock_results": results,
        "acquired_count": acquired_count,
        "busy_count": busy_count,
        "turn_a_chars": out_a.get("response_chars"),
        "turn_b_chars": out_b.get("response_chars"),
        "wall_ms": _ms(t0),
    }
    report["scenarios"].append(s14)
    print(("PASS" if s14["ok"] else "FAIL"), "14", s14, flush=True)

    report["ok"] = all(s["ok"] for s in report["scenarios"])
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    out = SOAK_DIR / "phase19_4_rerun_12_14.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out} ok={report['ok']}", flush=True)

    # Merge into main report if present
    main_report_path = SOAK_DIR / "phase19_4_report.json"
    if main_report_path.exists():
        main = json.loads(main_report_path.read_text(encoding="utf-8"))
        by_name = {s["name"]: s for s in main.get("scenarios", [])}
        for s in report["scenarios"]:
            by_name[s["name"]] = s
        main["scenarios"] = list(by_name.values())
        main["failures"] = [s for s in main["scenarios"] if not s.get("ok")]
        main["ok"] = len(main["failures"]) == 0
        main["rerun_12_14"] = report
        main_report_path.write_text(json.dumps(main, indent=2, default=str), encoding="utf-8")
        print(f"Merged into main report ok={main['ok']}", flush=True)

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

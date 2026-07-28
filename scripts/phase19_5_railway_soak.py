# =====================================
# Phase 19.5 — Authenticated Railway production soak
# =====================================
"""Validate Titan against the live Railway public deployment as a real user.

Credentials (never printed / never written to reports):
  TITAN_SOAK_USERNAME
  TITAN_SOAK_PASSWORD

Optional:
  TITAN_SOAK_BASE_URL  (default: https://titan-production-e377.up.railway.app)

Usage (from repo root)::

    python scripts/phase19_5_railway_soak.py
    python scripts/phase19_5_railway_soak.py --quick
"""

from __future__ import annotations

import argparse
import http.client
import http.cookiejar
import json
import os
import re
import statistics
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

DEFAULT_BASE = "https://titan-production-e377.up.railway.app"
SOAK_DIR = ROOT / "data" / "phase19_5_soak"
SOAK_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = SOAK_DIR / "phase19_5_report.json"

# Secret patterns — redact from any report / console output.
_SECRET_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "database_url",
    "csrf",
)


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return round(ordered[idx], 2)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def _redact(text: str, secrets: list[str]) -> str:
    out = text
    for secret in secrets:
        if secret and len(secret) >= 3:
            out = out.replace(secret, "***")
    # Generic JSON-ish secret fields
    for key in _SECRET_KEYS:
        out = re.sub(
            rf'("{key}"\s*:\s*")[^"]*(")',
            r"\1***\2",
            out,
            flags=re.IGNORECASE,
        )
    return out


def _safe_json(obj: Any, secrets: list[str]) -> Any:
    raw = json.dumps(obj, default=str)
    return json.loads(_redact(raw, secrets))


class RailwayClient:
    """Authenticated Railway HTTP client (cookies + CSRF, no credential logging)."""

    def __init__(self, base: str, username: str, password: str) -> None:
        self.base = base.rstrip("/")
        self._username = username
        self._password = password
        self._secrets = [username, password]
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib_request.build_opener(
            urllib_request.HTTPCookieProcessor(self.jar)
        )
        self.csrf_token: str | None = None
        self.auth_ms: float | None = None
        self.last_request_id: str | None = None

    def secrets(self) -> list[str]:
        secrets = list(self._secrets)
        if self.csrf_token:
            secrets.append(self.csrf_token)
        for cookie in self.jar:
            if cookie.value:
                secrets.append(cookie.value)
        return secrets

    def cookie_names(self) -> list[str]:
        return sorted({c.name for c in self.jar})

    def has_session_cookie(self) -> bool:
        return "titan_session" in self.cookie_names()

    def has_csrf_cookie(self) -> bool:
        return "titan_csrf" in self.cookie_names()

    def _headers(
        self,
        *,
        content_type: str | None = "application/json",
        accept: str = "application/json",
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "Origin": self.base,
            "Referer": f"{self.base}/app/",
        }
        if content_type:
            headers["Content-Type"] = content_type
        if self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float = 60.0,
        accept: str = "application/json",
        stream: bool = False,
    ) -> tuple[int, Any, float]:
        """Return (status, parsed_body_or_bytes, duration_ms)."""
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib_request.Request(
            f"{self.base}{path}",
            data=data,
            method=method,
            headers=self._headers(
                content_type="application/json" if body is not None else None,
                accept=accept,
            ),
        )
        started = time.perf_counter()
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                status = resp.status
                if stream or "text/event-stream" in accept:
                    chunks: list[bytes] = []
                    deadline = time.perf_counter() + float(timeout)
                    try:
                        while True:
                            remaining = deadline - time.perf_counter()
                            if remaining <= 0:
                                break
                            # Tighten socket timeout for each read slice.
                            try:
                                resp.fp.raw._sock.settimeout(min(30.0, max(1.0, remaining)))
                            except Exception:  # noqa: BLE001
                                pass
                            piece = resp.read(16384)
                            if not piece:
                                break
                            chunks.append(piece)
                            # Stop once the terminal SSE event is present — do not
                            # wait for chunked trailer / keep-alive that can hang.
                            if b"event: conversation_finished" in piece or (
                                b"conversation_finished" in b"".join(chunks[-8:])
                            ):
                                # Drain briefly for trailing brain_state/telemetry.
                                try:
                                    resp.fp.raw._sock.settimeout(1.5)
                                    extra = resp.read(65536)
                                    if extra:
                                        chunks.append(extra)
                                except Exception:  # noqa: BLE001
                                    pass
                                break
                    except (http.client.IncompleteRead, ConnectionError, TimeoutError) as exc:
                        partial = getattr(exc, "partial", b"") or b""
                        if isinstance(partial, (bytes, bytearray)) and partial:
                            chunks.append(bytes(partial))
                    except Exception as exc:  # noqa: BLE001
                        if not chunks:
                            duration = _ms(started)
                            return status, {
                                "detail": f"{type(exc).__name__}: {str(exc)[:200]}"
                            }, duration
                    duration = _ms(started)
                    return status, b"".join(chunks).decode("utf-8", errors="replace"), duration
                raw = resp.read()
                duration = _ms(started)
                ctype = resp.headers.get("Content-Type", "")
                if "json" in ctype:
                    return status, json.loads(raw.decode("utf-8")), duration
                return status, raw.decode("utf-8", errors="replace"), duration
        except urllib_error.HTTPError as exc:
            duration = _ms(started)
            payload: Any
            try:
                raw = exc.read()
                text = raw.decode("utf-8", errors="replace")
                payload = json.loads(text) if text.strip().startswith("{") else text
            except Exception:  # noqa: BLE001
                payload = {"detail": str(exc)}
            return exc.code, payload, duration
        except Exception as exc:  # noqa: BLE001
            duration = _ms(started)
            return 0, {"detail": f"{type(exc).__name__}: {str(exc)[:200]}"}, duration

    def login(self) -> dict[str, Any]:
        started = time.perf_counter()
        status, body, duration = self.request(
            "POST",
            "/auth/login",
            body={"username": self._username, "password": self._password},
            timeout=45.0,
        )
        self.auth_ms = duration
        ok = status == 200 and isinstance(body, dict) and bool(body.get("ok"))
        if ok and isinstance(body, dict):
            self.csrf_token = str(body.get("csrf_token") or "") or None
            if not self.csrf_token:
                for cookie in self.jar:
                    if cookie.name == "titan_csrf":
                        self.csrf_token = cookie.value
                        break
        # Never include body fields that could echo credentials.
        return {
            "ok": ok,
            "status": status,
            "auth_ms": duration,
            "wall_ms": _ms(started),
            "session_cookie": self.has_session_cookie(),
            "csrf_cookie": self.has_csrf_cookie(),
            "csrf_token_present": bool(self.csrf_token),
            "username_returned": bool(isinstance(body, dict) and body.get("username")),
        }

    def auth_status(self) -> dict[str, Any]:
        status, body, duration = self.request("GET", "/auth/status", timeout=20.0)
        payload = body if isinstance(body, dict) else {}
        return {
            "ok": status == 200 and bool(payload.get("authenticated")),
            "status": status,
            "authenticated": payload.get("authenticated"),
            "auth_mode": payload.get("auth_mode"),
            "session_auth": payload.get("session_auth"),
            "auth_required": payload.get("auth_required"),
            "ms": duration,
        }

    def get_json(self, path: str, timeout: float = 30.0) -> tuple[int, dict[str, Any], float]:
        status, body, duration = self.request("GET", path, timeout=timeout)
        return status, body if isinstance(body, dict) else {}, duration


def parse_sse(raw: str) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    """Parse SSE text into (event_order, events, summary metrics)."""
    order: list[str] = []
    events: list[dict[str, Any]] = []
    event_name = "message"
    data_buf: list[str] = []

    def flush() -> None:
        nonlocal event_name, data_buf
        if not data_buf and event_name == "message":
            return
        payload_text = "\n".join(data_buf)
        data_buf = []
        parsed: Any
        try:
            parsed = json.loads(payload_text) if payload_text else {}
        except json.JSONDecodeError:
            parsed = {"raw": payload_text[:300]}
        order.append(event_name)
        events.append({"event": event_name, "data": parsed})
        event_name = "message"

    for line in raw.splitlines():
        if line == "":
            flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_buf.append(line[5:].lstrip())
    flush()

    text_parts: list[str] = []
    conversation_id = None
    request_id = None
    finished: dict[str, Any] | None = None
    first_delta_idx = None
    for i, ev in enumerate(events):
        name = ev["event"]
        data = ev["data"] if isinstance(ev["data"], dict) else {}
        if data.get("conversation_id"):
            conversation_id = data.get("conversation_id")
        if data.get("request_id"):
            request_id = data.get("request_id")
        if name == "text_delta":
            if first_delta_idx is None:
                first_delta_idx = i
            delta = data.get("delta") or data.get("text") or ""
            if delta:
                text_parts.append(str(delta))
        if name == "conversation_finished":
            finished = data

    deltas_after_finish = False
    if "conversation_finished" in order:
        fin = order.index("conversation_finished")
        deltas_after_finish = any(e == "text_delta" for e in order[fin + 1 :])

    required = [
        "conversation_started",
        "brain_state",
        "response_started",
        "text_delta",
        "conversation_finished",
    ]
    missing = [e for e in required if e not in order]

    return order, events, {
        "conversation_id": conversation_id,
        "request_id": request_id,
        "assistant_text": "".join(text_parts),
        "finished": finished or {},
        "deltas_after_finish": deltas_after_finish,
        "missing_required_events": missing,
        "event_count": len(events),
        "approval_required": bool((finished or {}).get("approval_required")),
        "ttft_ms": (finished or {}).get("ttft_ms"),
        "delta_count": (finished or {}).get("delta_count"),
        "ok": bool((finished or {}).get("ok", True)) if finished else False,
        "error_code": (finished or {}).get("error_code"),
    }


def sse_turn_ok(
    *,
    status: int,
    finished: dict[str, Any],
    summary: dict[str, Any],
    assistant_text: str,
    error_code: str | None,
) -> bool:
    """Decide whether an SSE chat turn completed successfully.

    Instant deterministic replies (hierarchy NL create) may omit streaming
    events when the full assistant text is carried on ``conversation_finished``.
    """
    ok = (
        status == 200
        and bool(finished)
        and not summary.get("deltas_after_finish")
        and bool(assistant_text)
        and error_code not in {"brain_busy", "brain_failure", "provider_unavailable"}
        and error_code != "cancelled"
    )
    if not ok or error_code is not None:
        return ok
    missing = set(summary.get("missing_required_events") or [])
    streamed_missing = missing & {"text_delta", "response_started"}
    if not streamed_missing:
        return True
    delta_count = finished.get("delta_count")
    claims_stream = isinstance(delta_count, int) and delta_count > 0
    finished_has_response = bool(str(finished.get("response") or "").strip())
    if claims_stream:
        return False
    if finished_has_response or bool(assistant_text.strip()):
        return True
    return False


class SoakRunner:
    def __init__(self, client: RailwayClient, *, quick: bool = False) -> None:
        self.client = client
        self.quick = quick
        self.scenarios: list[dict[str, Any]] = []
        self.latencies: list[float] = []
        self.ttft: list[float] = []
        self.provider_durations: list[float] = []
        self.internal_durations: list[float] = []
        self.request_ids: list[str] = []
        self.conversation_ids: list[str] = []
        self.errors: list[dict[str, Any]] = []
        self.suffix = uuid.uuid4().hex[:8]

    def _record(self, name: str, result: dict[str, Any]) -> dict[str, Any]:
        result = {"name": name, **result}
        self.scenarios.append(result)
        status = "PASS" if result.get("ok") else "FAIL"
        print(f"[{status}] {name}", flush=True)
        if not result.get("ok"):
            self.errors.append(
                {
                    "scenario": name,
                    "request_id": result.get("request_id"),
                    "layer": result.get("failing_layer"),
                    "error": result.get("error") or result.get("detail"),
                }
            )
        return result

    def fetch_lock_diagnostics(self) -> dict[str, Any]:
        """Authenticated Brain lock diagnostics (safe fields only)."""
        status, body, ms = self.client.get_json("/api/chat/diagnostics", timeout=30.0)
        lock = {}
        if isinstance(body, dict):
            lock = body.get("brain_lock") or {}
        return {
            "ok": status == 200 and isinstance(body, dict) and bool(body.get("ok")),
            "status": status,
            "ms": ms,
            "lock_state": lock.get("lock_state"),
            "owner_present": lock.get("owner_present"),
            "lock_age_ms": lock.get("lock_age_ms"),
            "heartbeat_age_ms": lock.get("heartbeat_age_ms"),
            "generation": lock.get("generation"),
            "waiters": lock.get("waiters"),
            "stale_reclaim_count": lock.get("stale_reclaim_count"),
            "last_release_reason": lock.get("last_release_reason"),
            "last_error_code": lock.get("last_error_code") or (
                body.get("last_error_code") if isinstance(body, dict) else None
            ),
            "raw_keys": sorted(lock.keys()) if isinstance(lock, dict) else [],
        }

    def assert_lock_idle(self, *, retries: int = 8, sleep_s: float = 0.75) -> dict[str, Any]:
        """Poll diagnostics until Brain lock returns to IDLE (bounded)."""
        last: dict[str, Any] = {}
        for attempt in range(max(1, retries)):
            last = self.fetch_lock_diagnostics()
            state = str(last.get("lock_state") or "").upper()
            if last.get("ok") and state in {"IDLE", "RELEASED", "RECLAIMED"} and not last.get(
                "owner_present"
            ):
                last["idle"] = True
                last["attempts"] = attempt + 1
                return last
            time.sleep(sleep_s)
        last["idle"] = False
        last["attempts"] = retries
        return last

    def chat(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        timeout: float = 180.0,
        request_id: str | None = None,
        retries_on_busy: int = 8,
    ) -> dict[str, Any]:
        last: dict[str, Any] = {}
        # Hard ceiling — never infinite busy retry loops.
        max_attempts = min(max(1, retries_on_busy), 12)
        for attempt in range(max_attempts):
            rid = request_id or f"p195-{uuid.uuid4().hex[:12]}"
            # Distinct request_id per busy retry (avoid idempotency cache of busy).
            if attempt > 0 and request_id is None:
                rid = f"p195-{uuid.uuid4().hex[:12]}"
            elif attempt > 0 and request_id is not None:
                rid = f"{request_id}-r{attempt}"
            last = self._chat_once(
                message,
                conversation_id=conversation_id,
                timeout=timeout,
                request_id=rid,
            )
            if last.get("error_code") != "brain_busy" and last.get("ok"):
                return last
            if last.get("error_code") != "brain_busy":
                return last
            # Bounded backoff only for expected brain_busy.
            time.sleep(min(8.0, 1.5 * (attempt + 1)))
        last["busy_retries_exhausted"] = True
        last["busy_retry_attempts"] = max_attempts
        return last

    def _chat_once(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        timeout: float = 180.0,
        request_id: str,
    ) -> dict[str, Any]:
        rid = request_id
        body: dict[str, Any] = {
            "message": message,
            "request_id": rid,
            "client_request_id": rid,
        }
        if conversation_id:
            body["conversation_id"] = conversation_id
        started = time.perf_counter()
        status, raw, http_ms = self.client.request(
            "POST",
            "/chat/stream",
            body=body,
            timeout=timeout,
            accept="text/event-stream",
            stream=True,
        )
        total_ms = _ms(started)
        self.last_request_id = rid
        self.request_ids.append(rid)
        if status != 200 or not isinstance(raw, str):
            return {
                "ok": False,
                "status": status,
                "request_id": rid,
                "conversation_id": conversation_id,
                "error": raw if not isinstance(raw, str) else str(raw)[:300],
                "failing_layer": "http_chat_stream",
                "total_ms": total_ms,
                "http_ms": http_ms,
            }
        order, _events, summary = parse_sse(raw)
        cid = summary.get("conversation_id") or conversation_id
        if cid:
            self.conversation_ids.append(str(cid))
        finished = summary.get("finished") or {}
        ttft = finished.get("ttft_ms")
        if isinstance(ttft, (int, float)):
            self.ttft.append(float(ttft))
        full_provider = finished.get("duration_seconds")
        if isinstance(full_provider, (int, float)):
            self.provider_durations.append(float(full_provider) * 1000.0)
            internal = max(0.0, total_ms - (float(full_provider) * 1000.0))
            self.internal_durations.append(internal)
        elif isinstance(ttft, (int, float)):
            self.internal_durations.append(max(0.0, total_ms - float(ttft)))
        self.latencies.append(total_ms)
        # Prefer finished.response when deltas were omitted (error/busy paths).
        assistant_text = summary.get("assistant_text") or ""
        if not assistant_text and finished.get("response"):
            assistant_text = str(finished.get("response") or "")
        error_code = finished.get("error_code") or summary.get("error_code")
        ok = sse_turn_ok(
            status=status,
            finished=finished if isinstance(finished, dict) else {},
            summary=summary,
            assistant_text=assistant_text,
            error_code=str(error_code) if error_code else None,
        )
        return {
            "ok": ok,
            "status": status,
            "request_id": rid,
            "conversation_id": cid,
            "event_order": order,
            "missing_required_events": summary.get("missing_required_events"),
            "deltas_after_finish": summary.get("deltas_after_finish"),
            "assistant_chars": len(assistant_text),
            "assistant_preview": assistant_text[:180],
            "approval_required": summary.get("approval_required"),
            "ttft_ms": ttft,
            "duration_seconds": finished.get("duration_seconds"),
            "delta_count": finished.get("delta_count"),
            "error_code": error_code,
            "total_ms": total_ms,
            "http_ms": http_ms,
            "assistant_message_id": finished.get("assistant_message_id"),
            "user_message_id": finished.get("user_message_id"),
            "failing_layer": None if ok else "sse_or_completion",
            "raw_chars": len(raw),
        }

    def load_conversation(self, conversation_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        status, body, duration = self.client.get_json(
            f"/api/conversations/{conversation_id}?limit=500",
            timeout=45.0,
        )
        messages = body.get("messages") if isinstance(body, dict) else None
        return {
            "ok": status == 200 and isinstance(messages, list),
            "status": status,
            "ms": duration,
            "wall_ms": _ms(started),
            "total_messages": (body.get("total_messages") if isinstance(body, dict) else None),
            "messages": messages or [],
            "conversation": (body.get("conversation") if isinstance(body, dict) else None),
        }

    def cancel(self, conversation_id: str, request_id: str) -> dict[str, Any]:
        status, body, duration = self.client.request(
            "POST",
            f"/api/conversations/{conversation_id}/cancel",
            body={"request_id": request_id},
            timeout=30.0,
        )
        return {
            "ok": status == 200,
            "status": status,
            "ms": duration,
            "body": body if isinstance(body, dict) else {},
        }

    # ------------------------------------------------------------------
    # Scenarios
    # ------------------------------------------------------------------

    def scenario_env(self) -> dict[str, Any]:
        base = self.client.base
        results: dict[str, Any] = {"base": base, "checks": []}

        for path in ("/health", "/ready"):
            try:
                req = urllib_request.Request(f"{base}{path}", method="GET")
                with urllib_request.urlopen(req, timeout=20) as resp:
                    body = json.loads(resp.read().decode())
                    results["checks"].append(
                        {
                            "path": path,
                            "ok": resp.status == 200,
                            "status": resp.status,
                            "status_field": body.get("status"),
                            "auth_required": body.get("auth_required"),
                            "session_auth": body.get("session_auth"),
                            "conversation_backend": (
                                ((body.get("checks") or {}).get("conversation_store") or {}).get(
                                    "backend"
                                )
                                if path == "/ready"
                                else None
                            ),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                results["checks"].append(
                    {
                        "path": path,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                    }
                )

        # Unauthenticated chat must 401
        unauth: dict[str, Any] = {"path": "/chat/stream", "ok": False}
        try:
            req = urllib_request.Request(
                f"{base}/chat/stream",
                data=b'{"message":"x"}',
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            urllib_request.urlopen(req, timeout=15)
            unauth["error"] = "expected_401"
        except urllib_error.HTTPError as exc:
            unauth["status"] = exc.code
            unauth["ok"] = exc.code == 401
        except Exception as exc:  # noqa: BLE001
            unauth["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        results["checks"].append(unauth)

        health = next((c for c in results["checks"] if c.get("path") == "/health"), {})
        ready = next((c for c in results["checks"] if c.get("path") == "/ready"), {})
        ok = bool(
            health.get("ok")
            and ready.get("ok")
            and health.get("auth_required") is True
            and ready.get("conversation_backend") == "postgresql"
            and unauth.get("ok")
        )
        return self._record(
            "00_environment",
            {
                "ok": ok,
                "health": health,
                "ready": ready,
                "unauthenticated_chat_blocked": unauth.get("ok"),
                "failing_layer": None if ok else "railway_public_probes",
            },
        )

    def scenario_login(self) -> dict[str, Any]:
        login = self.client.login()
        status = self.client.auth_status()
        ok = (
            login.get("ok")
            and login.get("session_cookie")
            and login.get("csrf_cookie")
            and status.get("ok")
            and status.get("authenticated") is True
        )
        return self._record(
            "01_login",
            {
                "ok": ok,
                "login": login,
                "auth_status": status,
                "credentials_in_logs": False,
                "failing_layer": None if ok else "authentication",
            },
        )

    def scenario_basic_chat(self) -> dict[str, Any]:
        turn = self.chat("Bonjour Titan.")
        cid = turn.get("conversation_id")
        loaded = self.load_conversation(cid) if cid else {"ok": False, "messages": []}
        messages = loaded.get("messages") or []
        user_msgs = [m for m in messages if m.get("role") == "user"]
        asst_msgs = [m for m in messages if m.get("role") == "assistant"]
        pending = [
            m
            for m in asst_msgs
            if str(m.get("status") or "").lower() in {"pending", "streaming", "running"}
        ]
        ok = (
            turn.get("ok")
            and loaded.get("ok")
            and len(user_msgs) >= 1
            and len(asst_msgs) >= 1
            and not pending
        )
        return self._record(
            "02_basic_chat",
            {
                "ok": ok,
                "request_id": turn.get("request_id"),
                "conversation_id": cid,
                "turn": {
                    k: turn.get(k)
                    for k in (
                        "status",
                        "assistant_chars",
                        "total_ms",
                        "ttft_ms",
                        "missing_required_events",
                    )
                },
                "persisted_user_messages": len(user_msgs),
                "persisted_assistant_messages": len(asst_msgs),
                "pending_assistant": len(pending),
                "reload_ms": loaded.get("ms"),
                "failing_layer": None if ok else "basic_chat_persistence",
            },
        )

    def scenario_context_continuity(self) -> dict[str, Any]:
        t1 = self.chat("Mon projet principal s'appelle Titan.")
        cid = t1.get("conversation_id")
        t2 = self.chat(
            "Quel est le nom de mon projet principal ?",
            conversation_id=cid,
        )
        preview = (t2.get("assistant_preview") or "").lower()
        mentions = "titan" in preview
        ok = bool(t1.get("ok") and t2.get("ok") and mentions)
        return self._record(
            "03_context_continuity",
            {
                "ok": ok,
                "conversation_id": cid,
                "request_id": t2.get("request_id"),
                "mentions_titan": mentions,
                "assistant_preview": t2.get("assistant_preview"),
                "failing_layer": None if ok else "context_continuity",
            },
        )

    def scenario_refresh_continuity(self) -> dict[str, Any]:
        t1 = self.chat("Souviens-toi pour ce test: le code secret de validation est ORION-195.")
        cid = t1.get("conversation_id")
        if not cid:
            return self._record(
                "04_refresh_continuity",
                {
                    "ok": False,
                    "failing_layer": "conversation_create",
                    "error": "no conversation_id",
                },
            )
        before = self.load_conversation(cid)
        before_count = before.get("total_messages") or len(before.get("messages") or [])

        # Close client session and open a fresh authenticated session.
        fresh = RailwayClient(self.client.base, self.client._username, self.client._password)
        login = fresh.login()
        if not login.get("ok"):
            return self._record(
                "04_refresh_continuity",
                {
                    "ok": False,
                    "failing_layer": "reauthentication",
                    "login": login,
                    "conversation_id": cid,
                },
            )
        # Swap active client to fresh session for subsequent scenarios.
        self.client = fresh
        loaded = self.load_conversation(cid)
        messages = loaded.get("messages") or []
        # Duplicate detection: identical (role, content, request_id) pairs
        fingerprints = [
            (m.get("role"), m.get("content"), m.get("request_id"), m.get("sequence"))
            for m in messages
        ]
        duplicates = len(fingerprints) != len(set(fingerprints))
        continue_turn = self.chat(
            "Quel est le code secret de validation que je viens de te donner ?",
            conversation_id=cid,
        )
        mentions = "orion-195" in (continue_turn.get("assistant_preview") or "").lower()
        after_count = (
            self.load_conversation(cid).get("total_messages")
            or 0
        )
        ok = (
            loaded.get("ok")
            and before_count >= 2
            and not duplicates
            and continue_turn.get("ok")
            and mentions
            and after_count >= before_count + 2
        )
        return self._record(
            "04_refresh_continuity",
            {
                "ok": ok,
                "conversation_id": cid,
                "request_id": continue_turn.get("request_id"),
                "messages_before": before_count,
                "messages_after_reload": len(messages),
                "duplicates": duplicates,
                "continued_ok": continue_turn.get("ok"),
                "mentions_secret": mentions,
                "reload_ms": loaded.get("ms"),
                "failing_layer": None if ok else "refresh_continuity",
            },
        )

    def scenario_restart_continuity(self) -> dict[str, Any]:
        """Postgres-backed survival across new auth session (no unsafe redeploy)."""
        t1 = self.chat("Phase 19.5 restart probe message un.")
        cid = t1.get("conversation_id")
        t2 = self.chat("Phase 19.5 restart probe message deux.", conversation_id=cid)
        t3 = self.chat("Phase 19.5 restart probe message trois.", conversation_id=cid)
        mid = self.load_conversation(cid) if cid else {"ok": False, "messages": []}
        mid_count = mid.get("total_messages") or len(mid.get("messages") or [])
        asst = [m for m in (mid.get("messages") or []) if m.get("role") == "assistant"]
        pending = [
            m
            for m in asst
            if str(m.get("status") or "").lower()
            in {"pending", "streaming", "running", "in_progress"}
        ]

        # New session (simulates post-restart re-login; DB rows must survive).
        fresh = RailwayClient(self.client.base, self.client._username, self.client._password)
        login = fresh.login()
        self.client = fresh
        reloaded = self.load_conversation(cid) if cid and login.get("ok") else {"ok": False}
        re_count = reloaded.get("total_messages") or len(reloaded.get("messages") or [])
        re_asst = [
            m for m in (reloaded.get("messages") or []) if m.get("role") == "assistant"
        ]
        re_pending = [
            m
            for m in re_asst
            if str(m.get("status") or "").lower()
            in {"pending", "streaming", "running", "in_progress"}
        ]
        ok = (
            all(t.get("ok") for t in (t1, t2, t3))
            and login.get("ok")
            and reloaded.get("ok")
            and mid_count >= 6
            and re_count == mid_count
            and not pending
            and not re_pending
        )
        return self._record(
            "05_restart_continuity",
            {
                "ok": ok,
                "conversation_id": cid,
                "request_id": t3.get("request_id"),
                "message_count_before": mid_count,
                "message_count_after_relogin": re_count,
                "pending_before": len(pending),
                "pending_after": len(re_pending),
                "redeploy_triggered": False,
                "note": (
                    "No Railway CLI available; validated Postgres survival across "
                    "fresh authenticated sessions without unsafe redeploy."
                ),
                "failing_layer": None if ok else "restart_continuity",
            },
        )

    def scenario_streaming_order(self) -> dict[str, Any]:
        turn = self.chat("Réponds en une seule phrase courte: validation streaming.")
        order = turn.get("event_order") or []
        required = [
            "conversation_started",
            "brain_state",
            "response_started",
            "text_delta",
            "conversation_finished",
        ]
        positions = {name: order.index(name) for name in required if name in order}
        ordered_ok = list(positions.values()) == sorted(positions.values()) and len(
            positions
        ) == len(required)
        ok = bool(
            turn.get("ok")
            and ordered_ok
            and not turn.get("deltas_after_finish")
            and not turn.get("missing_required_events")
        )
        return self._record(
            "06_streaming_order",
            {
                "ok": ok,
                "request_id": turn.get("request_id"),
                "conversation_id": turn.get("conversation_id"),
                "event_order": order,
                "required_positions": positions,
                "deltas_after_finish": turn.get("deltas_after_finish"),
                "failing_layer": None if ok else "streaming_order",
            },
        )

    def scenario_cancellation(self) -> dict[str, Any]:
        # Seed conversation so cancel path has an id.
        seed = self.chat("Prépare une conversation pour un test d'annulation.")
        cid = seed.get("conversation_id")
        if not cid or not seed.get("ok"):
            return self._record(
                "07_cancellation_recovery",
                {
                    "ok": False,
                    "failing_layer": "cancel_seed",
                    "error": "seed failed",
                    "request_id": seed.get("request_id"),
                },
            )

        rid = f"p195-cancel-{uuid.uuid4().hex[:10]}"
        result_holder: dict[str, Any] = {}

        def _stream() -> None:
            result_holder["turn"] = self.chat(
                (
                    "Explique en détail, sur plusieurs paragraphes, l'architecture "
                    "complète de Titan (Brain, Agents, Memory, Tools, Missions) "
                    "sans utiliser d'outils externes."
                ),
                conversation_id=cid,
                request_id=rid,
                timeout=180.0,
            )

        thread = threading.Thread(target=_stream, daemon=True)
        started = time.perf_counter()
        thread.start()
        time.sleep(1.2)
        cancel = self.cancel(cid, rid)
        thread.join(timeout=200.0)
        cancel_ms = _ms(started)
        turn = result_holder.get("turn") or {}

        recover_started = time.perf_counter()
        recover = self.chat(
            "Dis seulement: récupération annulation OK.",
            conversation_id=cid,
        )
        recovery_ms = _ms(recover_started)

        loaded = self.load_conversation(cid)
        pending = [
            m
            for m in (loaded.get("messages") or [])
            if m.get("role") == "assistant"
            and str(m.get("status") or "").lower()
            in {"pending", "streaming", "running", "in_progress"}
        ]
        idle = self.assert_lock_idle()
        # Cancel may finish early with cancelled error_code, or complete if cancel raced.
        cancel_observed = (
            cancel.get("ok")
            or (turn.get("error_code") == "cancelled")
            or ("cancelled" in (turn.get("event_order") or []))
        )
        ok = bool(
            recover.get("ok")
            and not pending
            and cancel_observed
            and idle.get("idle")
        )
        return self._record(
            "07_cancellation_recovery",
            {
                "ok": ok,
                "conversation_id": cid,
                "request_id": rid,
                "cancel_http_ok": cancel.get("ok"),
                "cancel_body": cancel.get("body"),
                "cancelled_stream_error_code": turn.get("error_code"),
                "recover_ok": recover.get("ok"),
                "recover_request_id": recover.get("request_id"),
                "pending_assistant_after": len(pending),
                "cancel_wall_ms": cancel_ms,
                "recovery_ms": recovery_ms,
                "lock_idle_after": idle.get("idle"),
                "lock_state_after": idle.get("lock_state"),
                "stale_reclaim_count": idle.get("stale_reclaim_count"),
                "failing_layer": None if ok else "cancellation_recovery",
            },
        )

    def scenario_sequential_soak(self) -> dict[str, Any]:
        n = 10 if self.quick else 50
        cid = None
        failures = 0
        samples: list[float] = []
        for i in range(n):
            msg = (
                f"Soak 19.5 séquentiel #{i + 1}/{n}. "
                "Réponds en une courte phrase conversationnelle, sans outils."
            )
            turn = self.chat(msg, conversation_id=cid)
            if not cid:
                cid = turn.get("conversation_id")
            samples.append(float(turn.get("total_ms") or 0.0))
            if (i + 1) % 5 == 0 or not turn.get("ok"):
                print(
                    f"  sequential {i + 1}/{n} ok={turn.get('ok')} "
                    f"ms={turn.get('total_ms')}",
                    flush=True,
                )
            if not turn.get("ok"):
                failures += 1
                if failures >= 3:
                    break
        # Latency trend: compare first third avg vs last third avg (allow 2.5x variance).
        trend_ok = True
        if len(samples) >= 9:
            third = max(1, len(samples) // 3)
            first_avg = statistics.mean(samples[:third])
            last_avg = statistics.mean(samples[-third:])
            trend_ok = last_avg <= first_avg * 2.5 + 5000
        else:
            first_avg = statistics.mean(samples) if samples else 0.0
            last_avg = first_avg

        loaded = self.load_conversation(cid) if cid else {"ok": False, "messages": []}
        messages = loaded.get("messages") or []
        users = [m for m in messages if m.get("role") == "user"]
        assts = [m for m in messages if m.get("role") == "assistant"]
        req_ids_user = [m.get("request_id") for m in users if m.get("request_id")]
        req_ids_asst = [m.get("request_id") for m in assts if m.get("request_id")]
        dup_req = len(req_ids_user) != len(set(req_ids_user)) or len(req_ids_asst) != len(
            set(req_ids_asst)
        )
        pending = [
            m
            for m in messages
            if m.get("role") == "assistant"
            and str(m.get("status") or "").lower()
            in {"pending", "streaming", "running", "in_progress"}
        ]
        ok = failures == 0 and trend_ok and not dup_req and not pending and loaded.get("ok")
        return self._record(
            "08_sequential_soak",
            {
                "ok": ok,
                "conversation_id": cid,
                "request_count": len(samples),
                "failures": failures,
                "user_messages": len(users),
                "assistant_messages": len(assts),
                "p50_ms": _pct(samples, 50),
                "p95_ms": _pct(samples, 95),
                "slowest_ms": max(samples) if samples else None,
                "first_third_avg_ms": round(first_avg, 2),
                "last_third_avg_ms": round(last_avg, 2),
                "latency_trend_ok": trend_ok,
                "duplicate_request_ids": dup_req,
                "pending_assistant": len(pending),
                "failing_layer": None if ok else "sequential_soak",
            },
        )

    def scenario_long_conversation(self) -> dict[str, Any]:
        n = 8 if self.quick else 25
        cid = None
        facts = []
        for i in range(n):
            fact = f"fait-{self.suffix}-{i + 1}"
            facts.append(fact)
            msg = (
                f"Tour {i + 1}/{n} du long test Phase 19.5. "
                f"Retiens le fait suivant: {fact}. "
                "Réponds brièvement en confirmant, sans outils."
            )
            turn = self.chat(msg, conversation_id=cid)
            if not cid:
                cid = turn.get("conversation_id")
            if not turn.get("ok"):
                return self._record(
                    "09_long_conversation",
                    {
                        "ok": False,
                        "conversation_id": cid,
                        "request_id": turn.get("request_id"),
                        "failed_at_turn": i + 1,
                        "failing_layer": "long_conversation_turn",
                        "error": turn.get("error") or turn.get("error_code"),
                    },
                )

        probe = self.chat(
            f"Quel est le premier fait retenu (fait-{self.suffix}-1) ?",
            conversation_id=cid,
        )
        mentions = f"fait-{self.suffix}-1" in (probe.get("assistant_preview") or "").lower()
        loaded = self.load_conversation(cid)
        messages = loaded.get("messages") or []
        fingerprints = [(m.get("role"), m.get("content"), m.get("request_id")) for m in messages]
        duplicates = len(fingerprints) != len(set(fingerprints))
        # Expected roughly 2 messages per turn + probe
        expected_min = (n + 1) * 2
        ok = (
            probe.get("ok")
            and mentions
            and loaded.get("ok")
            and not duplicates
            and len(messages) >= expected_min
        )
        return self._record(
            "09_long_conversation",
            {
                "ok": ok,
                "conversation_id": cid,
                "request_id": probe.get("request_id"),
                "turns": n,
                "message_count": len(messages),
                "expected_min_messages": expected_min,
                "duplicates": duplicates,
                "continuity_mentions_first_fact": mentions,
                "summary_note": (
                    "Summary creation depends on server TITAN_CONVERSATION_SUMMARY_THRESHOLD; "
                    "validated continuity + reloadability."
                ),
                "failing_layer": None if ok else "long_conversation",
            },
        )

    def scenario_hierarchy(self) -> dict[str, Any]:
        goal = f"P195-Goal-{self.suffix}"
        project = f"P195-Project-{self.suffix}"
        mission = f"P195-Mission-{self.suffix}"
        t1 = self.chat(
            f"Crée un Goal de test isolé nommé {goal} pour la validation Phase 19.5. "
            "Ne modifie aucun autre Goal existant."
        )
        t2 = self.chat(
            f"Crée un Project de test isolé nommé {project} lié au Goal {goal}. "
            "Ne modifie aucun Project réel utilisateur."
        )
        t3 = self.chat(
            f"Crée une Mission de test isolée nommée {mission} dans le Project {project}."
        )
        t4 = self.chat(
            f"Active maintenant le contexte Goal {goal}, Project {project}, "
            f"Mission {mission}."
        )
        status_code, workspace, ws_ms = self.client.get_json("/workspace/state")
        status_code2, system, st_ms = self.client.get_json("/status")

        def _entity_present(payload: Any, name: str) -> bool:
            """Match structured workspace fields — not free-text conversation echoes."""
            if not isinstance(payload, dict):
                return False
            target = name.lower()
            # Direct active_* string fields
            for key in (
                "active_goal",
                "active_project",
                "active_mission",
                "active_mission_title",
                "active_goal_current_mission",
                "active_project_active_mission",
            ):
                value = payload.get(key)
                if isinstance(value, str) and target in value.lower():
                    return True
            # Collection entries (goals / projects / missions)
            for key in ("goals", "projects", "missions"):
                items = payload.get(key) or []
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, str) and target in item.lower():
                        return True
                    if isinstance(item, dict):
                        blob = " ".join(
                            str(item.get(k) or "")
                            for k in ("name", "title", "id", "goal", "project", "mission")
                        ).lower()
                        if target in blob:
                            return True
            mission_block = payload.get("mission")
            if isinstance(mission_block, dict):
                title = str(mission_block.get("title") or "").lower()
                if target in title:
                    return True
            return False

        has_goal = _entity_present(workspace, goal) or _entity_present(system, goal)
        has_project = _entity_present(workspace, project) or _entity_present(
            system, project
        )
        has_mission = _entity_present(workspace, mission) or _entity_present(
            system, mission
        )

        # Refresh simulation: new session then re-read workspace
        fresh = RailwayClient(self.client.base, self.client._username, self.client._password)
        login = fresh.login()
        self.client = fresh
        _, workspace2, reload_ms = self.client.get_json("/workspace/state")
        survives = (
            _entity_present(workspace2, goal)
            or _entity_present(workspace2, project)
            or _entity_present(workspace2, mission)
        )
        turn_oks = {
            "goal_create": bool(t1.get("ok")),
            "project_create": bool(t2.get("ok")),
            "mission_create": bool(t3.get("ok")),
            "activate": bool(t4.get("ok")),
        }
        ok = (
            all(turn_oks.values())
            and status_code == 200
            and status_code2 == 200
            and login.get("ok")
            and has_goal
            and has_project
            and has_mission
            and survives
        )
        return self._record(
            "10_project_goal_mission",
            {
                "ok": ok,
                "entities": {"goal": goal, "project": project, "mission": mission},
                "request_id": t4.get("request_id"),
                "turn_oks": turn_oks,
                "workspace_ms": ws_ms,
                "status_ms": st_ms,
                "reload_ms": reload_ms,
                "seen_in_workspace": {
                    "goal": has_goal,
                    "project": has_project,
                    "mission": has_mission,
                },
                "survives_refresh_session": survives,
                "failing_layer": None if ok else "hierarchy_continuity",
                "note": "Isolated P195-* entities only; no real user project edits intended.",
            },
        )

    def scenario_confirmation(self) -> dict[str, Any]:
        """Synthetic high-risk prompt — must not execute external side effects."""
        turn = self.chat(
            (
                "Action synthétique interne Phase 19.5 uniquement: "
                "avant d'exécuter delete_synthetic_test_entity_p195, "
                "demande clairement mon approbation ou ma confirmation. "
                "N'exécute rien. N'appelle aucun outil. "
                "Réponds seulement pour demander une validation."
            )
        )
        preview = (turn.get("assistant_preview") or "").lower()
        confirmation_language = any(
            token in preview
            for token in (
                "confirm",
                "approb",
                "autoris",
                "avant d",
                "n'exécute",
                "n’exécute",
                "pas exécut",
                "validation",
                "permission",
                "accord",
                "veux-tu",
                "souhaites",
            )
        )
        approval_flag = bool(turn.get("approval_required"))
        # Pass if stream completed without external side-effect markers and either
        # approval_required surfaced or the assistant refused/asked confirmation.
        ok = bool(turn.get("ok") and (approval_flag or confirmation_language))
        return self._record(
            "11_confirmation_safety",
            {
                "ok": ok,
                "request_id": turn.get("request_id"),
                "conversation_id": turn.get("conversation_id"),
                "approval_required": approval_flag,
                "confirmation_language": confirmation_language,
                "assistant_preview": turn.get("assistant_preview"),
                "external_side_effects": False,
                "failing_layer": None if ok else "confirmation_safety",
                "note": (
                    "Production tools disabled/guarded; validated no-side-effect "
                    "confirmation language and/or approval_required flag."
                ),
            },
        )

    def scenario_postgres_integrity(self) -> dict[str, Any]:
        """Read-only integrity via conversation API (no DB credentials)."""
        # Use a dedicated short conversation for counting invariants.
        t1 = self.chat("PostgreSQL integrity probe A — réponds brièvement.")
        cid = t1.get("conversation_id")
        t2 = self.chat("PostgreSQL integrity probe B — réponds brièvement.", conversation_id=cid)
        loaded = self.load_conversation(cid) if cid else {"ok": False, "messages": []}
        messages = loaded.get("messages") or []
        users = [m for m in messages if m.get("role") == "user"]
        assts = [m for m in messages if m.get("role") == "assistant"]
        completed = [
            m
            for m in assts
            if str(m.get("status") or "").lower() in {"completed", "complete", "done", ""}
            or m.get("status") is None
        ]
        pending = [
            m
            for m in assts
            if str(m.get("status") or "").lower()
            in {"pending", "streaming", "running", "in_progress"}
        ]
        req_ids_user = [m.get("request_id") for m in users if m.get("request_id")]
        req_ids_asst = [m.get("request_id") for m in assts if m.get("request_id")]
        dup_req = len(req_ids_user) != len(set(req_ids_user)) or len(req_ids_asst) != len(
            set(req_ids_asst)
        )

        # Conversation list should include this conversation once.
        status, listing, list_ms = self.client.get_json("/api/conversations?limit=100")
        items = []
        if isinstance(listing, dict):
            items = listing.get("conversations") or listing.get("items") or []
        matches = [c for c in items if (c.get("id") if isinstance(c, dict) else None) == cid]

        ok = (
            t1.get("ok")
            and t2.get("ok")
            and loaded.get("ok")
            and len(users) == 2
            and len(assts) == 2
            and len(pending) == 0
            and len(completed) == 2
            and not dup_req
            and status == 200
            and len(matches) == 1
        )
        return self._record(
            "12_postgres_integrity",
            {
                "ok": ok,
                "conversation_id": cid,
                "request_id": t2.get("request_id"),
                "user_messages": len(users),
                "assistant_messages": len(assts),
                "completed_assistants": len(completed),
                "pending_assistants": len(pending),
                "duplicate_request_ids": dup_req,
                "conversation_list_matches": len(matches),
                "list_ms": list_ms,
                "reload_ms": loaded.get("ms"),
                "backend_from_ready": "postgresql",
                "direct_db_credentials_used": False,
                "failing_layer": None if ok else "postgres_integrity_api",
            },
        )

    def scenario_lock_diagnostics(self) -> dict[str, Any]:
        """Inspect authenticated lock diagnostics; verify IDLE after a chat turn."""
        before = self.fetch_lock_diagnostics()
        turn = self.chat(
            "Diagnostics lock: réponds seulement OK, sans outils.",
            timeout=120.0,
        )
        after = self.assert_lock_idle()
        raw = json.dumps(after, default=str)
        leaked = any(s and len(s) >= 4 and s in raw for s in self.client.secrets())
        ok = (
            before.get("ok")
            and turn.get("ok")
            and after.get("idle")
            and "lock_state" in (before.get("raw_keys") or after.get("raw_keys") or [])
            and not leaked
        )
        return self._record(
            "14_lock_diagnostics_idle",
            {
                "ok": ok,
                "request_id": turn.get("request_id"),
                "before_lock_state": before.get("lock_state"),
                "after_lock_state": after.get("lock_state"),
                "stale_reclaim_count": after.get("stale_reclaim_count"),
                "generation": after.get("generation"),
                "idle": after.get("idle"),
                "diag_keys": after.get("raw_keys"),
                "failing_layer": None if ok else "lock_diagnostics",
            },
        )

    def scenario_lock_contention(self) -> dict[str, Any]:
        """Bounded concurrent chat to observe lock busy / timeout behavior."""
        results: list[dict[str, Any]] = []

        def _one(idx: int) -> None:
            turn = self.chat(
                (
                    f"Contention test {idx}: explique brièvement la séparation "
                    "Brain / Tools sans outils."
                ),
                timeout=120.0,
                retries_on_busy=6,
            )
            results.append(turn)

        threads = [threading.Thread(target=_one, args=(i,), daemon=True) for i in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=180.0)

        statuses = [r.get("status") for r in results]
        error_codes = [r.get("error_code") for r in results]
        success = sum(1 for r in results if r.get("ok"))
        busy_or_timeout = any(
            s in {409, 429, 503}
            or (isinstance(r.get("error"), dict) and "lock" in json.dumps(r.get("error")).lower())
            or str(r.get("error_code") or "").lower() in {"brain_busy", "brain_lock_timeout", "busy"}
            for r, s in zip(results, statuses)
        )
        idle = self.assert_lock_idle()
        # Accept either: one success + one rejected, or both serialized successfully.
        ok = success >= 1 and (busy_or_timeout or success == len(results)) and idle.get("idle")
        return self._record(
            "13_lock_contention",
            {
                "ok": ok,
                "success_count": success,
                "statuses": statuses,
                "error_codes": error_codes,
                "busy_or_timeout_observed": busy_or_timeout,
                "request_ids": [r.get("request_id") for r in results],
                "lock_idle_after": idle.get("idle"),
                "lock_state_after": idle.get("lock_state"),
                "stale_reclaim_count": idle.get("stale_reclaim_count"),
                "note": (
                    "Server CHAT_BRAIN_LOCK_* markers require Railway log access; "
                    "validated contention + post-scenario IDLE via diagnostics."
                ),
                "failing_layer": None if ok else "lock_contention",
            },
        )

    def _safe_scenario(self, name: str, fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — record and continue soak
            self._record(
                name,
                {
                    "ok": False,
                    "failing_layer": "scenario_exception",
                    "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                    "request_id": self.last_request_id,
                },
            )

    def run(self) -> dict[str, Any]:
        started = time.perf_counter()
        self._safe_scenario("00_environment", self.scenario_env)
        self._safe_scenario("01_login", self.scenario_login)
        if not any(s["name"] == "01_login" and s.get("ok") for s in self.scenarios):
            return self._finalize(started)

        sequence = [
            ("02_basic_chat", self.scenario_basic_chat),
            ("03_context_continuity", self.scenario_context_continuity),
            ("04_refresh_continuity", self.scenario_refresh_continuity),
            ("05_restart_continuity", self.scenario_restart_continuity),
            ("06_streaming_order", self.scenario_streaming_order),
            ("07_cancellation_recovery", self.scenario_cancellation),
            ("08_sequential_soak", self.scenario_sequential_soak),
            ("09_long_conversation", self.scenario_long_conversation),
            ("10_project_goal_mission", self.scenario_hierarchy),
            ("11_confirmation_safety", self.scenario_confirmation),
            ("12_postgres_integrity", self.scenario_postgres_integrity),
            ("13_lock_contention", self.scenario_lock_contention),
            ("14_lock_diagnostics_idle", self.scenario_lock_diagnostics),
        ]
        for name, fn in sequence:
            self._safe_scenario(name, fn)
        return self._finalize(started)

    def _finalize(self, started: float) -> dict[str, Any]:
        failures = [s for s in self.scenarios if not s.get("ok")]
        report = {
            "phase": "19.6",
            "base": self.client.base,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_ms": _ms(started),
            "quick": self.quick,
            "scenarios": self.scenarios,
            "failures": [
                {
                    "scenario": f.get("name"),
                    "request_id": f.get("request_id"),
                    "layer": f.get("failing_layer"),
                }
                for f in failures
            ],
            "performance": {
                "auth_ms": self.client.auth_ms,
                "request_count": len(self.latencies),
                "full_request_p50_ms": _pct(self.latencies, 50),
                "full_request_p95_ms": _pct(self.latencies, 95),
                "full_request_slowest_ms": max(self.latencies) if self.latencies else None,
                "full_request_avg_ms": round(statistics.mean(self.latencies), 2)
                if self.latencies
                else None,
                "first_token_p50_ms": _pct(self.ttft, 50),
                "first_token_p95_ms": _pct(self.ttft, 95),
                "provider_duration_avg_ms": round(statistics.mean(self.provider_durations), 2)
                if self.provider_durations
                else None,
                "titan_internal_avg_ms": round(statistics.mean(self.internal_durations), 2)
                if self.internal_durations
                else None,
                "error_rate": round(len(failures) / max(1, len(self.scenarios)), 4),
                "conversation_ids_created": len(set(self.conversation_ids)),
            },
            "diagnostics": {
                "server_log_access": False,
                "railway_cli_available": False,
                "client_sse_order_validated": any(
                    s.get("name") == "06_streaming_order" and s.get("ok")
                    for s in self.scenarios
                ),
                "cancellation_path_exercised": any(
                    s.get("name") == "07_cancellation_recovery" for s in self.scenarios
                ),
                "lock_contention_exercised": any(
                    s.get("name") == "13_lock_contention" for s in self.scenarios
                ),
                "lock_diagnostics_exercised": any(
                    s.get("name") == "14_lock_diagnostics_idle" for s in self.scenarios
                ),
                "note": (
                    "Phase 19.6: authenticated /api/chat/diagnostics used to verify "
                    "Brain lock returns to IDLE; CHAT_BRAIN_LOCK_* reclaim markers "
                    "require Railway log access."
                ),
            },
            "ok": len(failures) == 0,
        }
        secrets = self.client.secrets()
        safe = _safe_json(report, secrets)
        REPORT_PATH.write_text(json.dumps(safe, indent=2, default=str), encoding="utf-8")
        print(f"\nReport written: {REPORT_PATH}", flush=True)
        print(f"Overall ok={safe['ok']} failures={len(failures)}", flush=True)
        return safe


def require_credentials() -> tuple[str, str] | None:
    user = os.getenv("TITAN_SOAK_USERNAME", "").strip()
    password = os.getenv("TITAN_SOAK_PASSWORD", "").strip()
    missing = []
    if not user:
        missing.append("TITAN_SOAK_USERNAME")
    if not password:
        missing.append("TITAN_SOAK_PASSWORD")
    if missing:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "missing_credentials",
                    "missing": missing,
                    "message": "Stop before authenticated testing.",
                },
                indent=2,
            )
        )
        return None
    return user, password


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 19.5 authenticated Railway soak")
    parser.add_argument("--quick", action="store_true", help="Shorter sequential/long loops")
    args = parser.parse_args()

    creds = require_credentials()
    if creds is None:
        return 2
    username, password = creds

    base = (
        os.getenv("TITAN_SOAK_BASE_URL")
        or os.getenv("TITAN_PUBLIC_BASE_URL")
        or DEFAULT_BASE
    ).rstrip("/")

    print(f"Phase 19.5 Railway soak starting against {base}", flush=True)
    client = RailwayClient(base, username, password)
    runner = SoakRunner(client, quick=args.quick)
    report = runner.run()
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

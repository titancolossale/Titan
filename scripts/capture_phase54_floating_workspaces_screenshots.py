# =====================================
# Phase 5.4 — Floating Cognitive Workspaces screenshots
# =====================================
"""Capture floating workspace screenshots without starting the Titan API.

Serves ``web/v2`` statically and stubs ``/auth/status`` so the shell boots.
"""

from __future__ import annotations

import json
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "web" / "v2"
OUT = ROOT / "docs" / "design" / "screenshots"
PORT = 8781


class FrontendMockHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(V2), **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/auth/status":
            self._json({"auth_required": False, "dev_mode": True})
            return
        stub_exact = {
            "/events",
            "/status",
            "/chat",
            "/voice",
            "/auth/verify",
        }
        if path in stub_exact or path.startswith("/api/"):
            self._json({})
            return
        return super().do_GET()

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _pin_idle(page) -> None:
    page.evaluate(
        """() => {
          const app = window.__TITAN_V2__;
          const store = app?._store;
          const brain = app?.brain;
          // Stop reconnect storms from flipping cards after the pin.
          try { brain?._backendBridge?.disconnect?.(); } catch (_) {}
          if (brain?.setState) {
            brain.setState('idle', { force: true, source: 'screenshot' });
          }
          if (store?.setState) {
            store.setState({
              presence: 'idle',
              cognitiveState: 'idle',
              presenceLevel: 42,
              connectionState: 'connected',
              pipelineThinking: false,
              conversationActive: false,
              conversationPlanSteps: [],
              conversationThinkingLine: '',
              pipelineLabel: '',
              reasoningSummary: '',
              activeToolCount: 0,
              activeToolIds: [],
              recallActive: false,
              memoryStatusLine: 'Mémoire — en veille',
              lastError: null,
            });
          }
          const status = app?._regions?.status;
          const snap = brain?.getState?.() ?? { id: 'idle', label: 'Repos' };
          if (status?._updateMemoryUi) status._updateMemoryUi();
          if (status?._updateToolUi) status._updateToolUi();
          if (status?._updateCognitiveCard) {
            status._updateCognitiveCard('Idle', 'idle');
          }
          if (status?._updatePresenceCard) {
            status._updatePresenceCard({ ...snap, id: 'idle', label: 'Idle' });
          }
          if (status?._updateStrip) status._updateStrip();
        }"""
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    httpd = TCPServer(("127.0.0.1", PORT), FrontendMockHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1600, "height": 1000},
            device_scale_factor=1.25,
        )
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(
            f"http://127.0.0.1:{PORT}/?dev=1",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(3800)
        root_html = page.inner_html("#titan-v2-root")
        if "tdl-v2-workspace-grid" not in root_html:
            dump = "\n".join(errors[:40])
            raise RuntimeError(
                f"Shell did not mount. logs:\n{dump}\nroot_len={len(root_html)}"
            )
        if "card-recent-memory" not in root_html:
            raise RuntimeError("Recent Memory workspace missing")
        if "tdl-v2-card-presence" not in root_html:
            raise RuntimeError("Presence workspace missing")
        if "tdl-v2-workspace-dock" not in root_html:
            raise RuntimeError("Workspace dock marker missing")

        phase = page.locator("#titan-v2-root").get_attribute("data-phase")
        if phase != "5.4":
            raise RuntimeError(f"Expected root data-phase 5.4, got {phase!r}")

        _pin_idle(page)
        page.wait_for_timeout(800)
        _pin_idle(page)
        page.wait_for_timeout(500)

        page.screenshot(
            path=str(OUT / "phase-5.4-floating-workspaces-full.png"),
            full_page=False,
        )

        dock = page.locator(".tdl-v2-workspace-dock")
        dock.screenshot(path=str(OUT / "phase-5.4-workspace-dock.png"))

        memory = page.locator("#card-recent-memory")
        memory.screenshot(path=str(OUT / "phase-5.4-memory-idle.png"))

        browser.close()
    httpd.shutdown()
    print("Phase 5.4 screenshots written to", OUT)


if __name__ == "__main__":
    main()

# =====================================
# Phase 5 — Reference Layout Reconstruction screenshots
# =====================================
"""Capture full-shell composition screenshots without starting the Titan API.

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
PORT = 8777


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
          if (store?.setState) {
            store.setState({
              presence: 'idle',
              connectionState: 'connected',
              pipelineThinking: false,
              conversationActive: false,
              conversationPlanSteps: [],
              conversationThinkingLine: '',
              pipelineLabel: '',
              reasoningSummary: '',
              activeToolCount: 0,
              activeToolIds: [],
            });
          }
          const brain = app?.brain;
          if (brain?.setState) {
            brain.setState('idle', { force: true, source: 'screenshot' });
          }
          const orch = app?._regions?.orchestrator;
          if (orch?._updateObjectiveSection) orch._updateObjectiveSection('Idle', 'idle');
          if (orch?._updatePlanSection) orch._updatePlanSection();
          if (orch?._updateToolsSection) orch._updateToolsSection();
          if (orch?._syncPresenceDataset) orch._syncPresenceDataset();
          if (orch?._updateNeuralLabel) orch._updateNeuralLabel('Idle');
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
        page.wait_for_timeout(2800)
        root_html = page.inner_html("#titan-v2-root")
        if "tdl-v2-workspace-grid" not in root_html:
            dump = "\n".join(errors[:40])
            raise RuntimeError(f"Shell did not mount. logs:\n{dump}\nroot_len={len(root_html)}")
        if "tdl-v2-composition" not in root_html:
            raise RuntimeError("Phase 5 composition frame missing from shell")

        phase = page.locator("#titan-v2-root").get_attribute("data-phase")
        if phase != "5":
            raise RuntimeError(f"Expected root data-phase=5, got {phase!r}")

        _pin_idle(page)
        page.wait_for_timeout(600)

        page.screenshot(
            path=str(OUT / "phase-5-reference-layout-full.png"),
            full_page=False,
        )

        sidebar = page.locator("#tdl-v2-region-sidebar")
        sidebar.screenshot(path=str(OUT / "phase-5-sidebar.png"))

        orch = page.locator("#tdl-v2-region-orchestrator")
        orch.screenshot(path=str(OUT / "phase-5-orchestrator.png"))

        dock = page.locator("#tdl-v2-region-dock")
        dock.screenshot(path=str(OUT / "phase-5-floating-dock.png"))

        topbar = page.locator("#tdl-v2-region-topbar")
        topbar.screenshot(path=str(OUT / "phase-5-topbar.png"))

        browser.close()
    httpd.shutdown()
    print("Phase 5 screenshots written to", OUT)


if __name__ == "__main__":
    main()

# =====================================
# Phase 5.3 — Reference Scene Reconstruction screenshots
# =====================================
"""Capture reference scene screenshots without starting the Titan API.

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
PORT = 8780


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
        page.wait_for_timeout(3800)
        root_html = page.inner_html("#titan-v2-root")
        if "tdl-v2-workspace-grid" not in root_html:
            dump = "\n".join(errors[:40])
            raise RuntimeError(f"Shell did not mount. logs:\n{dump}\nroot_len={len(root_html)}")
        if "tdl-v2-satellite-core" not in root_html:
            raise RuntimeError("Titan Core label missing from shell")
        if "tdl-v2-satellite-core__gravity" not in root_html:
            raise RuntimeError("Core gravity well missing from shell")
        if "tdl-v2-satellite-link--secondary" not in root_html:
            raise RuntimeError("Secondary highway paths missing")

        phase = page.locator("#titan-v2-root").get_attribute("data-phase")
        if phase not in {"5.3", "5.4"}:
            raise RuntimeError(f"Expected root data-phase 5.3/5.4, got {phase!r}")

        layout = page.locator("#titan-v2-root").get_attribute("data-layout")
        if layout != "reference-scene":
            raise RuntimeError(f"Expected data-layout reference-scene, got {layout!r}")

        _pin_idle(page)
        page.wait_for_timeout(1200)

        page.screenshot(
            path=str(OUT / "phase-5.3-reference-scene-full.png"),
            full_page=False,
        )

        center = page.locator(".tdl-v2-center-stack")
        center.screenshot(path=str(OUT / "phase-5.3-titan-core.png"))

        field = page.locator(".tdl-v2-satellite-field")
        field.screenshot(path=str(OUT / "phase-5.3-satellite-orbits.png"))

        browser.close()
    httpd.shutdown()
    print("Phase 5.3 screenshots written to", OUT)


if __name__ == "__main__":
    main()

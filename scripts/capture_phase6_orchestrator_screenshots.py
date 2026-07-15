# =====================================
# Phase 6 — Living Cognitive Orchestrator screenshots
# =====================================
"""Capture right-orchestrator chrome screenshots without starting the Titan API.

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
              orchestrationDuration: null,
              systemsUsed: null,
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
          if (orch?._updateFooterStatus) orch._updateFooterStatus();
          if (orch?._syncPresenceDataset) orch._syncPresenceDataset();
          if (orch?._syncAliveDataset) orch._syncAliveDataset();
          if (orch?._updateNeuralLabel) orch._updateNeuralLabel('Idle');
        }"""
    )


def _pin_active(page) -> None:
    page.evaluate(
        """() => {
          const app = window.__TITAN_V2__;
          const store = app?._store;
          if (store?.setState) {
            store.setState({
              presence: 'thinking',
              connectionState: 'connected',
              pipelineThinking: true,
              conversationActive: true,
              pipelineLabel: 'Comparer notes Obsidian et sources web',
              conversationThinkingLine: 'Consultation Obsidian en cours',
              conversationPlanSteps: [
                'Understanding Request',
                'Memory Retrieval',
                'Obsidian Consultation',
              ],
              orchestrationDuration: 1.4,
              systemsUsed: { memory: true, obsidian: true, browser: false },
              activeToolCount: 1,
              activeToolIds: ['obsidian'],
            });
          }
          const brain = app?.brain;
          if (brain?.setState) {
            brain.setState('thinking', { force: true, source: 'screenshot' });
          }
          if (brain?.activateTool) {
            brain.activateTool('obsidian', { statusLine: 'Lecture vault — notes projet' });
          }
          const orch = app?._regions?.orchestrator;
          if (orch?._updatePlanSection) orch._updatePlanSection();
          if (orch?._updateToolsSection) orch._updateToolsSection();
          if (orch?._updateObjectiveSection) orch._updateObjectiveSection('Thinking', 'thinking');
          if (orch?._updateFooterStatus) orch._updateFooterStatus();
          if (orch?._updateNeuralLabel) orch._updateNeuralLabel('Thinking');
          if (orch?._syncAliveDataset) orch._syncAliveDataset();
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
        page.wait_for_timeout(2200)
        root_html = page.inner_html("#titan-v2-root")
        if "tdl-v2-workspace-grid" not in root_html:
            dump = "\n".join(errors[:40])
            raise RuntimeError(f"Shell did not mount. logs:\n{dump}\nroot_len={len(root_html)}")

        title = page.locator(".tdl-v2-orchestrator-header__title").inner_text()
        if "cognitive orchestrator" not in title.lower():
            raise RuntimeError(f"Unexpected orchestrator title: {title!r}")

        phase = page.locator(".tdl-v2-region--orchestrator").get_attribute("data-phase")
        if phase != "6":
            raise RuntimeError(f"Expected data-phase=6, got {phase!r}")

        footer = page.locator(".tdl-v2-orchestrator-footer").count()
        if footer < 1:
            raise RuntimeError("Runtime Status footer missing")

        _pin_idle(page)
        page.wait_for_timeout(2400)

        page.screenshot(path=str(OUT / "phase-6-orchestrator-full.png"), full_page=False)

        orch = page.locator(".tdl-v2-region--orchestrator")
        box = orch.bounding_box()
        if orch.count():
            orch.first.screenshot(path=str(OUT / "phase-6-orchestrator-panel.png"))

        if box:
            page.screenshot(
                path=str(OUT / "phase-6-orchestrator-crop.png"),
                clip={
                    "x": max(0, box["x"] - 8),
                    "y": 0,
                    "width": box["width"] + 16,
                    "height": 1000,
                },
            )

        _pin_active(page)
        page.wait_for_timeout(1800)
        if orch.count():
            orch.first.screenshot(path=str(OUT / "phase-6-orchestrator-active.png"))

        browser.close()

    httpd.shutdown()
    print(f"Wrote Phase 6 orchestrator screenshots to {OUT}")


if __name__ == "__main__":
    main()

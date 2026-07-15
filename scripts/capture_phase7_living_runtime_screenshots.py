# =====================================
# Phase 7 — Living Runtime Experience screenshots
# =====================================
"""Capture living runtime chrome screenshots without starting the Titan API.

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
PORT = 8778


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
              cognitiveState: 'idle',
              connectionState: 'connected',
              pipelineThinking: false,
              conversationActive: false,
              recallActive: false,
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
          const topbar = app?._regions?.topbar;
          if (topbar?._syncTelemetry) topbar._syncTelemetry();
          const status = app?._regions?.status;
          if (status?._updateMemoryUi) status._updateMemoryUi();
          if (status?._updateToolUi) status._updateToolUi();
          if (status?._updateCognitiveCard) status._updateCognitiveCard('Idle', 'idle');
          if (status?._updatePresenceCard) status._updatePresenceCard(brain?.getState?.() ?? { id: 'idle' });
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
              cognitiveState: 'thinking',
              connectionState: 'connected',
              pipelineThinking: true,
              conversationActive: true,
              recallActive: true,
              pipelineLabel: 'Comparer notes Obsidian et sources web',
              conversationThinkingLine: 'Réflexion et rappel mémoire',
              memoryStatusLine: 'Rappel — notes projet',
              orchestrationDuration: 1.4,
              systemsUsed: { memory: true, obsidian: true, browser: true },
              activeToolCount: 2,
              activeToolIds: ['obsidian', 'browser'],
              presenceLevel: 78,
            });
          }
          const brain = app?.brain;
          if (brain?.setState) {
            brain.setState('thinking', { force: true, source: 'screenshot' });
          }
          if (brain?.activateTool) {
            brain.activateTool('obsidian', { statusLine: 'Lecture vault — notes projet' });
            brain.activateTool('browser', { statusLine: 'Recherche — sources web' });
          }
          const topbar = app?._regions?.topbar;
          if (topbar?._syncTelemetry) topbar._syncTelemetry();
          const status = app?._regions?.status;
          if (status?._updateMemoryUi) status._updateMemoryUi();
          if (status?._updateToolUi) status._updateToolUi();
          if (status?._updateCognitiveCard) status._updateCognitiveCard('Thinking', 'thinking');
          if (status?._updatePresenceCard) {
            status._updatePresenceCard(brain?.getState?.() ?? { id: 'thinking' });
          }
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

        living = page.locator("#titan-v2-root").get_attribute("data-living")
        if living != "7":
            raise RuntimeError(f"Expected data-living=7, got {living!r}")

        topbar = page.locator(".tdl-v2-topbar--living")
        if topbar.count() < 1:
            raise RuntimeError("Living topbar missing")

        _pin_idle(page)
        page.wait_for_timeout(2400)

        page.screenshot(path=str(OUT / "phase-7-living-runtime-full.png"), full_page=False)

        bar = page.locator(".tdl-v2-topbar--telemetry").first
        box = bar.bounding_box()
        if box:
            page.screenshot(
                path=str(OUT / "phase-7-living-runtime-topbar.png"),
                clip={
                    "x": max(0, box["x"] - 4),
                    "y": max(0, box["y"] - 4),
                    "width": box["width"] + 8,
                    "height": box["height"] + 8,
                },
            )

        dock = page.locator(".tdl-v2-workspace-dock").first
        dock_box = dock.bounding_box() if dock.count() else None
        if dock_box:
            page.screenshot(
                path=str(OUT / "phase-7-living-runtime-workspaces.png"),
                clip={
                    "x": max(0, dock_box["x"] - 8),
                    "y": max(0, dock_box["y"] - 8),
                    "width": dock_box["width"] + 16,
                    "height": dock_box["height"] + 16,
                },
            )

        _pin_active(page)
        page.wait_for_timeout(1800)
        page.screenshot(path=str(OUT / "phase-7-living-runtime-active.png"), full_page=False)

        browser.close()

    httpd.shutdown()
    print(f"Wrote Phase 7 living runtime screenshots to {OUT}")


if __name__ == "__main__":
    main()

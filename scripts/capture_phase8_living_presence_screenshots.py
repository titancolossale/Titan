# =====================================
# Phase 8 — Living Presence screenshots
# =====================================
"""Capture living presence chrome screenshots without starting the Titan API.

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
PORT = 8779


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
        if living != "8":
            raise RuntimeError(f"Expected data-living=8, got {living!r}")

        if page.locator(".tdl-v2-living-presence").count() < 1:
            raise RuntimeError("Living presence atmosphere missing")
        if page.locator(".tdl-v2-satellite-core__heartbeat").count() < 1:
            raise RuntimeError("Core heartbeat marker missing")

        _pin_idle(page)
        page.wait_for_timeout(3200)

        page.screenshot(path=str(OUT / "phase-8-living-presence-full.png"), full_page=False)

        field = page.locator(".tdl-v2-satellite-field").first
        box = field.bounding_box() if field.count() else None
        if box:
            page.screenshot(
                path=str(OUT / "phase-8-living-presence-core.png"),
                clip={
                    "x": max(0, box["x"] - 8),
                    "y": max(0, box["y"] - 8),
                    "width": min(box["width"] + 16, 1600),
                    "height": min(box["height"] + 16, 1000),
                },
            )

        dock = page.locator(".tdl-v2-workspace-dock").first
        dock_box = dock.bounding_box() if dock.count() else None
        if dock_box:
            page.screenshot(
                path=str(OUT / "phase-8-living-presence-workspaces.png"),
                clip={
                    "x": max(0, dock_box["x"] - 8),
                    "y": max(0, dock_box["y"] - 8),
                    "width": dock_box["width"] + 16,
                    "height": dock_box["height"] + 16,
                },
            )

        orch = page.locator(".tdl-v2-orchestrator--presence, .tdl-v2-region--orchestrator").first
        orch_box = orch.bounding_box() if orch.count() else None
        if orch_box:
            page.screenshot(
                path=str(OUT / "phase-8-living-presence-orchestrator.png"),
                clip={
                    "x": max(0, orch_box["x"] - 4),
                    "y": max(0, orch_box["y"] - 4),
                    "width": orch_box["width"] + 8,
                    "height": orch_box["height"] + 8,
                },
            )

        browser.close()

    httpd.shutdown()
    print(f"Wrote Phase 8 living presence screenshots to {OUT}")


if __name__ == "__main__":
    main()

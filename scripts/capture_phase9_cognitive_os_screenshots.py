# =====================================
# Phase 9 — Cognitive Operating System screenshots
# =====================================
"""Capture cognitive OS chrome screenshots without starting the Titan API.

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
              cognitiveState: 'idle',
              connectionState: 'connected',
              pipelineThinking: false,
              conversationActive: false,
              recallActive: false,
              conversationPlanSteps: [],
              conversationThinkingLine: '',
              conversationStage: null,
              conversationEventType: null,
              memoryEventType: null,
              pipelineLabel: '',
              reasoningSummary: '',
              orchestrationDuration: null,
              orchestrationConfidence: null,
              systemsUsed: null,
              activeToolCount: 0,
              activeToolIds: [],
              contextPanelOpen: false,
              orchestratorDrawerOpen: false,
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
          const orch = app?._regions?.orchestrator;
          if (orch?._updateRuntimeMonitor) orch._updateRuntimeMonitor();
          if (orch?._updateObjectiveSection) orch._updateObjectiveSection('Idle', 'idle');
          if (orch?._updateFooterStatus) orch._updateFooterStatus();
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
        if living != "9":
            raise RuntimeError(f"Expected data-living=9, got {living!r}")

        cos = page.locator("#titan-v2-root").get_attribute("data-cognitive-os")
        if cos != "9":
            raise RuntimeError(f"Expected data-cognitive-os=9, got {cos!r}")

        if page.locator(".tdl-v2-topbar--cognitive-os").count() < 1:
            raise RuntimeError("Cognitive OS topbar missing")
        if page.locator("#tdl-v2-orchestrator-monitor").count() < 1:
            raise RuntimeError("Runtime monitor missing")
        if page.locator("#card-memory-confidence").count() < 1:
            raise RuntimeError("Memory confidence metric missing")

        _pin_idle(page)
        page.evaluate(
            """() => {
              const app = window.__TITAN_V2__;
              app?._store?.setState({
                contextPanelOpen: false,
                orchestratorDrawerOpen: false,
                connectionState: 'connected',
                presence: 'idle',
                cognitiveState: 'idle',
              });
              const panel = document.querySelector('.tdl-v2-context-panel');
              if (panel) {
                panel.dataset.open = 'false';
                panel.setAttribute('aria-hidden', 'true');
                panel.style.visibility = 'hidden';
                panel.style.pointerEvents = 'none';
              }
              app?._regions?.topbar?._syncTelemetry?.();
              app?._regions?.orchestrator?._updateRuntimeMonitor?.();
            }"""
        )
        page.wait_for_timeout(1600)
        page.evaluate(
            """() => {
              const app = window.__TITAN_V2__;
              app?._store?.setState({ connectionState: 'connected', presence: 'idle' });
              app?._regions?.topbar?._syncTelemetry?.();
            }"""
        )
        page.wait_for_timeout(900)

        page.screenshot(path=str(OUT / "phase-9-cognitive-os-full.png"), full_page=False)

        topbar = page.locator(".tdl-v2-topbar--cognitive-os, .tdl-v2-region--topbar").first
        box = topbar.bounding_box() if topbar.count() else None
        if box:
            page.screenshot(
                path=str(OUT / "phase-9-cognitive-os-topbar.png"),
                clip={
                    "x": max(0, box["x"] - 4),
                    "y": max(0, box["y"] - 4),
                    "width": min(box["width"] + 8, 1600),
                    "height": min(box["height"] + 8, 120),
                },
            )

        dock = page.locator(".tdl-v2-workspace-dock").first
        dock_box = dock.bounding_box() if dock.count() else None
        if dock_box:
            page.screenshot(
                path=str(OUT / "phase-9-cognitive-os-workspaces.png"),
                clip={
                    "x": max(0, dock_box["x"] - 8),
                    "y": max(0, dock_box["y"] - 8),
                    "width": dock_box["width"] + 16,
                    "height": dock_box["height"] + 16,
                },
            )

        orch = page.locator("#tdl-v2-region-orchestrator").first
        if orch.count() < 1:
            orch = page.locator(".tdl-v2-orchestrator--cognitive-os").first
        orch_box = orch.bounding_box() if orch.count() else None
        if orch_box and orch_box["width"] > 160:
            page.screenshot(
                path=str(OUT / "phase-9-cognitive-os-orchestrator.png"),
                clip={
                    "x": max(0, orch_box["x"] - 4),
                    "y": max(0, orch_box["y"] - 4),
                    "width": orch_box["width"] + 8,
                    "height": min(orch_box["height"] + 8, 900),
                },
            )
        else:
            page.screenshot(
                path=str(OUT / "phase-9-cognitive-os-orchestrator.png"),
                clip={"x": 1180, "y": 56, "width": 400, "height": 820},
            )

        browser.close()

    httpd.shutdown()
    print(f"Wrote Phase 9 cognitive OS screenshots to {OUT}")


if __name__ == "__main__":
    main()

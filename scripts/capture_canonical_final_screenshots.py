# =====================================
# Canonical Final Reference screenshots
# =====================================
"""Capture desktop screenshots of the reconstructed Titan Web App.

Serves ``web/v2`` statically and stubs auth/events so the shell boots.
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
PORT = 8791


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
              sidebarPinned: true,
              settingsOpen: false,
              presenceLevel: 42,
              lastError: null,
            });
          }
          const panel = document.querySelector('.tdl-v2-context-panel');
          if (panel) {
            panel.dataset.open = 'false';
            panel.setAttribute('aria-hidden', 'true');
            panel.style.visibility = 'hidden';
            panel.style.pointerEvents = 'none';
          }
          const overlay = document.getElementById('tdl-v2-overlay-layer');
          if (overlay) overlay.dataset.active = 'false';
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
          if (status?._updateStrip) status._updateStrip();
          const orch = app?._regions?.orchestrator;
          if (orch?._updateRuntimeMonitor) orch._updateRuntimeMonitor();
          if (orch?._updateObjectiveSection) orch._updateObjectiveSection('Idle', 'idle');
          if (orch?._updatePlanSection) orch._updatePlanSection();
          if (orch?._updateToolsSection) orch._updateToolsSection();
          if (orch?._updateFooterStatus) orch._updateFooterStatus();
          const sidebar = app?._regions?.sidebar;
          if (sidebar?._syncPresence) sidebar._syncPresence();
          // Re-assert presentation after any late SSE disconnect handlers.
          store.setState({
            connectionState: 'connected',
            cognitiveState: 'idle',
            presence: 'idle',
            presenceLevel: 42,
            lastError: null,
          });
          if (brain?.setState) {
            brain.setState('idle', { force: true, source: 'screenshot' });
          }
          if (status?._updateCognitiveCard) status._updateCognitiveCard('Idle', 'idle');
          if (status?._updatePresenceCard) status._updatePresenceCard({ id: 'idle' });
          if (status?._updateStrip) status._updateStrip();
          if (orch?._updateObjectiveSection) orch._updateObjectiveSection('Idle', 'idle');
          if (orch?._updateFooterStatus) orch._updateFooterStatus();
          if (sidebar?._syncPresence) sidebar._syncPresence();
        }"""
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    server = TCPServer(("127.0.0.1", PORT), FrontendMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{PORT}/index.html"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 950})
            page.goto(f"http://127.0.0.1:{PORT}/?dev=1", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2200)
            root_html = page.inner_html("#titan-v2-root")
            if "tdl-v2-workspace-grid" not in root_html:
                raise RuntimeError("Shell did not mount")
            canonical = page.locator("#titan-v2-root").get_attribute("data-canonical")
            if canonical != "final":
                raise RuntimeError(f"Expected data-canonical=final, got {canonical!r}")
            _pin_idle(page)
            page.wait_for_timeout(900)
            # SSE stubs may briefly mark error; re-pin honest idle presentation.
            _pin_idle(page)
            page.wait_for_timeout(700)

            shots = {
                "canonical-final-full.png": None,
                "canonical-final-sidebar.png": "#tdl-v2-region-sidebar",
                "canonical-final-topbar.png": "#tdl-v2-region-topbar",
                "canonical-final-orchestrator.png": "#tdl-v2-region-orchestrator",
                "canonical-final-workspaces.png": "#tdl-v2-dock-status-cards",
            }
            for name, selector in shots.items():
                path = OUT / name
                if selector:
                    loc = page.locator(selector)
                    loc.screenshot(path=str(path))
                else:
                    page.screenshot(path=str(path), full_page=False)
                print(f"wrote {path}")

            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()

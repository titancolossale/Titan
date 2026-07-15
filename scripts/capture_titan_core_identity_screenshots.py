# =====================================
# Titan Core Identity screenshots
# =====================================
"""Capture full desktop + Core close-up for Titan Core Identity validation."""

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
PORT = 8794


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
            });
          }
        }"""
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    server = TCPServer(("127.0.0.1", PORT), FrontendMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
            page.goto(f"http://127.0.0.1:{PORT}/?dev=1", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2200)
            root_html = page.inner_html("#titan-v2-root")
            if "tdl-v2-workspace-grid" not in root_html:
                raise RuntimeError("Shell did not mount")
            page.wait_for_selector(".tdl-v2-satellite-core__title", timeout=45000)
            page.wait_for_timeout(2800)
            _pin_idle(page)
            page.wait_for_timeout(900)

            full = OUT / "titan-core-identity-full.png"
            close = OUT / "titan-core-identity-closeup.png"
            page.screenshot(path=str(full), full_page=False)
            page.screenshot(
                path=str(close),
                clip={"x": 380, "y": 200, "width": 680, "height": 420},
            )
            print(f"wrote {full}")
            print(f"wrote {close}")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()

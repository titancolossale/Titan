# =====================================
# Neural Architecture Reconstruction screenshots
# =====================================
"""Capture neural world screenshots after Architecture Reconstruction.

Serves ``web/v2`` statically and stubs auth/events so the shell boots.
Locked chrome is visible for context; focus is the neural canvas.
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    server = TCPServer(("127.0.0.1", PORT), FrontendMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3200)

            page.screenshot(
                path=str(OUT / "neural-architecture-full.png"),
                full_page=False,
            )
            page.screenshot(
                path=str(OUT / "neural-architecture-field.png"),
                clip={"x": 280, "y": 90, "width": 880, "height": 560},
            )
            page.screenshot(
                path=str(OUT / "neural-architecture-core.png"),
                clip={"x": 480, "y": 220, "width": 480, "height": 360},
            )
            browser.close()
    finally:
        server.shutdown()

    for path in sorted(OUT.glob("neural-architecture-*.png")):
        print(f"{path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

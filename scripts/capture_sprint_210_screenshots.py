# =====================================
# Sprint 2.10 — Visual fidelity screenshots (frontend mock server)
# =====================================
"""Capture /app chrome screenshots without starting the Titan API.

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
PORT = 8771


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
        # Only stub API-shaped routes — never prefix-match real frontend modules
        # such as ``/status/status-region.js``.
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
        page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}"))

        page.goto(f"http://127.0.0.1:{PORT}/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        root_html = page.inner_html("#titan-v2-root")
        if "tdl-v2-workspace-grid" not in root_html:
            dump = "\n".join(errors[:40])
            raise RuntimeError(f"Shell did not mount. logs:\n{dump}\nroot_len={len(root_html)}")

        page.wait_for_timeout(3500)
        page.screenshot(path=str(OUT / "sprint-2.10-reference-fidelity.png"), full_page=False)

        orch = page.locator(".tdl-v2-region--orchestrator")
        if orch.count():
            orch.first.screenshot(path=str(OUT / "sprint-2.10-orchestrator.png"))

        page.screenshot(
            path=str(OUT / "sprint-2.10-sidebar-dock.png"),
            clip={"x": 0, "y": 0, "width": 520, "height": 1000},
        )
        browser.close()

    httpd.shutdown()
    print(f"Wrote screenshots to {OUT}")


if __name__ == "__main__":
    main()

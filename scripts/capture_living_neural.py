# =====================================
# Sprint 2.3 screenshot capture helper
# =====================================
"""Capture living neural intelligence screenshots via Playwright."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    thinking_js = """
    () => {
      const canvas = document.querySelector('.tdl-v2-neural-canvas');
      if (canvas) canvas.classList.add('tdl-v2-neural-canvas--thinking');
      const field = document.querySelector('.tdl-v2-satellite-field');
      if (!field) return;
      field.dataset.behavior = 'THINKING';
      const reasoning = field.querySelector('[data-satellite="reasoning"]');
      if (reasoning) reasoning.dataset.status = 'active';
      const memory = field.querySelector('[data-satellite="memory"]');
      if (memory) memory.dataset.status = 'waiting';
      const link = field.querySelector('.tdl-v2-satellite-link--reasoning');
      if (link) link.dataset.status = 'active';
    }
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        page.goto("http://127.0.0.1:8000/app/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2800)
        page.screenshot(path=str(OUT / "living-neural-idle.png"), full_page=False)

        page.evaluate(thinking_js)
        page.wait_for_timeout(1400)
        page.screenshot(path=str(OUT / "living-neural-thinking.png"), full_page=False)
        page.screenshot(
            path=str(OUT / "living-neural-core-closeup.png"),
            clip={"x": 420, "y": 180, "width": 600, "height": 420},
        )
        browser.close()

    for path in sorted(OUT.glob("living-neural-*.png")):
        print(f"{path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

# =====================================
# Titan Browser Production Validation (Phase 13.4)
# =====================================

"""Run real-world Browser Connector validation against live Playwright Chromium."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.browser_models import BrowserResult
from tools.connectors.browser_validator import validate_browser_config


def _first_paragraph(html: str, page_text: str) -> str:
    """Extract first <p> content, falling back to second text block."""
    from html import unescape

    match = re.search(r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
    if match:
        text = re.sub(r"<[^>]+>", "", match.group(1))
        cleaned = unescape(" ".join(text.split()))
        if cleaned:
            return cleaned
    blocks = [b.strip() for b in re.split(r"\n\s*\n", page_text.strip()) if b.strip()]
    if len(blocks) > 1:
        return " ".join(blocks[1].split())
    return page_text.strip()[:200]


def _parse_browser_result(data: str) -> BrowserResult:
    payload = json.loads(data)
    from tools.connectors.browser_models import DetectedButton, DetectedForm, DetectedLink

    return BrowserResult(
        url=payload["url"],
        page_title=payload["page_title"],
        page_text=payload["page_text"],
        detected_links=tuple(
            DetectedLink(href=l["href"], text=l["text"]) for l in payload.get("detected_links", [])
        ),
        detected_forms=tuple(
            DetectedForm(
                action=f["action"],
                method=f["method"],
                fields=tuple(f.get("fields", [])),
            )
            for f in payload.get("detected_forms", [])
        ),
        detected_buttons=tuple(
            DetectedButton(
                label=b["label"],
                button_type=b["button_type"],
                name=b.get("name", ""),
            )
            for b in payload.get("detected_buttons", [])
        ),
        status=payload.get("status", "ok"),
        warnings=tuple(payload.get("warnings", [])),
    )


def _chromium_version(connector: BrowserConnector) -> str:
    backend = connector._backend  # noqa: SLF001 — validation script only
    if hasattr(backend, "session") and backend.session.is_launched:
        browser = backend.session._browser  # noqa: SLF001
        if browser is not None:
            return browser.version
    return "unknown"


def run_validation() -> dict:
    """Execute both production validation scenarios and return structured results."""
    results: dict = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(),
        "playwright_version": importlib.metadata.version("playwright"),
        "browser_version": "unknown",
        "screenshot_path": "",
        "errors": [],
        "tests": [],
        "verdict": "FAIL",
    }

    config = validate_browser_config(enabled=True, require_playwright=True)
    if not config.ok:
        results["errors"].append(config.message)
        return results

    connector = BrowserConnector(enabled=True, timeout_seconds=60.0, headless=True)
    screenshot_dir = PROJECT_ROOT / "data" / "browser_screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    screenshot_path = screenshot_dir / f"validation_example_{stamp}.png"

    try:
        # --- Test 1: example.com ---
        test1: dict = {"name": "example.com", "steps": [], "passed": False}
        try:
            started, msg = connector.start()
            test1["steps"].append({"step": "launch_chromium", "ok": started, "detail": msg})
            if not started:
                raise RuntimeError(msg)

            results["browser_version"] = _chromium_version(connector)

            open_result = connector.execute("open_page", {"url": "https://example.com"})
            test1["steps"].append({
                "step": "open_page",
                "ok": open_result.success,
                "detail": open_result.error or "ok",
            })
            if not open_result.success:
                raise RuntimeError(open_result.error)

            page = _parse_browser_result(open_result.data)
            html = connector._backend._session.get_page_html()  # noqa: SLF001
            first_para = _first_paragraph(html, page.page_text)
            test1["page_title"] = page.page_title
            test1["current_url"] = page.url
            test1["first_paragraph"] = first_para
            test1["steps"].append({
                "step": "read_page_metadata",
                "ok": bool(page.page_title) and page.url.startswith("https://example.com"),
                "detail": f"title={page.page_title!r}, url={page.url}",
            })

            scroll_result = connector.execute("scroll_page", {"direction": "down", "pixels": 400})
            test1["steps"].append({
                "step": "scroll_down",
                "ok": scroll_result.success,
                "detail": scroll_result.error or "ok",
            })

            shot_result = connector.execute(
                "take_screenshot",
                {"path": str(screenshot_path)},
            )
            test1["steps"].append({
                "step": "take_screenshot",
                "ok": shot_result.success,
                "detail": str(screenshot_path) if shot_result.success else shot_result.error,
            })
            if shot_result.success:
                results["screenshot_path"] = str(screenshot_path)

            connector.stop()
            test1["steps"].append({
                "step": "close_browser",
                "ok": not connector.session.started,
                "detail": "session stopped",
            })

            test1["passed"] = all(s["ok"] for s in test1["steps"])
        except Exception as exc:
            test1["steps"].append({"step": "exception", "ok": False, "detail": str(exc)})
            results["errors"].append(f"Test 1: {exc}\n{traceback.format_exc()}")
            connector.stop()

        results["tests"].append(test1)

        # --- Test 2: wikipedia.org ---
        test2: dict = {"name": "wikipedia.org", "steps": [], "passed": False}
        connector2 = BrowserConnector(enabled=True, timeout_seconds=60.0, headless=True)
        try:
            started, msg = connector2.start()
            test2["steps"].append({"step": "launch_chromium", "ok": started, "detail": msg})
            if not started:
                raise RuntimeError(msg)

            open_result = connector2.execute("open_page", {"url": "https://www.wikipedia.org"})
            test2["steps"].append({
                "step": "open_page",
                "ok": open_result.success,
                "detail": open_result.error or "ok",
            })
            if not open_result.success:
                raise RuntimeError(open_result.error)

            read_result = connector2.execute("read_page", {})
            test2["steps"].append({
                "step": "read_page",
                "ok": read_result.success,
                "detail": read_result.error or "ok",
            })
            if not read_result.success:
                raise RuntimeError(read_result.error)

            page = _parse_browser_result(read_result.data)
            test2["page_title"] = page.page_title
            test2["link_count"] = len(page.detected_links)
            test2["button_count"] = len(page.detected_buttons)
            test2["text_length"] = len(page.page_text)
            test2["text_preview"] = page.page_text[:300]
            test2["sample_links"] = [
                {"href": l.href, "text": l.text} for l in page.detected_links[:5]
            ]
            test2["sample_buttons"] = [
                {"label": b.label, "type": b.button_type} for b in page.detected_buttons[:5]
            ]

            checks_ok = (
                bool(page.page_title)
                and len(page.detected_links) > 0
                and len(page.page_text) > 50
            )
            test2["steps"].append({
                "step": "verify_title_links_buttons_text",
                "ok": checks_ok,
                "detail": (
                    f"title={page.page_title!r}, links={len(page.detected_links)}, "
                    f"buttons={len(page.detected_buttons)}, text_len={len(page.page_text)}"
                ),
            })

            extract_result = connector2.execute("extract_text", {})
            test2["steps"].append({
                "step": "extract_text",
                "ok": extract_result.success,
                "detail": extract_result.error or "ok",
            })

            connector2.stop()
            test2["steps"].append({
                "step": "close_browser",
                "ok": not connector2.session.started,
                "detail": "session stopped",
            })

            test2["passed"] = all(s["ok"] for s in test2["steps"])
        except Exception as exc:
            test2["steps"].append({"step": "exception", "ok": False, "detail": str(exc)})
            results["errors"].append(f"Test 2: {exc}\n{traceback.format_exc()}")
            connector2.stop()

        results["tests"].append(test2)

    except Exception as exc:
        results["errors"].append(f"Fatal: {exc}\n{traceback.format_exc()}")

    all_passed = all(t.get("passed") for t in results["tests"]) and len(results["tests"]) == 2
    results["verdict"] = "PASS — Browser Connector V1 complete" if all_passed else "FAIL"
    return results


def main() -> int:
    results = run_validation()
    out_path = PROJECT_ROOT / "Browser-Validation.md"
    out_path.write_text(_format_report(results), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nReport written to: {out_path}")
    return 0 if results["verdict"].startswith("PASS") else 1


def _format_report(results: dict) -> str:
    lines = [
        "# Browser Production Validation Report (Phase 13.4)",
        "",
        f"**Generated:** {results['timestamp_utc']}",
        "",
        "## Environment",
        "",
        f"| Property | Value |",
        f"|----------|-------|",
        f"| OS | {results['os']} |",
        f"| Playwright version | {results['playwright_version']} |",
        f"| Chromium version | {results['browser_version']} |",
        f"| Screenshot path | {results['screenshot_path'] or '(none)'} |",
        "",
        "## Tests Performed",
        "",
    ]

    for test in results["tests"]:
        status = "PASS" if test.get("passed") else "FAIL"
        lines.append(f"### {test['name']} — {status}")
        lines.append("")
        for step in test.get("steps", []):
            mark = "✓" if step["ok"] else "✗"
            lines.append(f"- [{mark}] **{step['step']}**: {step['detail']}")
        lines.append("")

        if test["name"] == "example.com":
            if "page_title" in test:
                lines.append(f"- **Page title:** {test['page_title']}")
                lines.append(f"- **Current URL:** {test['current_url']}")
                lines.append(f"- **First paragraph:** {test.get('first_paragraph', '')}")
                lines.append("")
        elif test["name"] == "wikipedia.org":
            if "page_title" in test:
                lines.append(f"- **Page title:** {test['page_title']}")
                lines.append(f"- **Links detected:** {test.get('link_count', 0)}")
                lines.append(f"- **Buttons detected:** {test.get('button_count', 0)}")
                lines.append(f"- **Text length:** {test.get('text_length', 0)} chars")
                if test.get("sample_links"):
                    lines.append("- **Sample links:**")
                    for link in test["sample_links"]:
                        lines.append(f"  - `{link['href']}` — {link['text']}")
                if test.get("text_preview"):
                    lines.append("- **Text preview:**")
                    lines.append(f"  > {test['text_preview'][:200]}…")
                lines.append("")

    lines.extend([
        "## Errors",
        "",
    ])
    if results["errors"]:
        for err in results["errors"]:
            lines.append(f"```\n{err}\n```")
            lines.append("")
    else:
        lines.append("None.")
        lines.append("")

    lines.extend([
        "## Final Verdict",
        "",
        f"**{results['verdict']}**",
        "",
        "Constraints respected: no login, no form submission, no file download/upload, "
        "no external link clicks.",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

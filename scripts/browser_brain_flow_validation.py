# =====================================
# Titan Browser Brain Flow Validation (Phase 13.5)
# =====================================

"""Validate Browser Connector through the full Brain orchestration pipeline."""

from __future__ import annotations

import json
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from brain.decision_execution_bridge import availability_resolver_from_manager
from config.settings import PROJECT_ROOT as TITAN_ROOT
from core.execution_coordinator import ExecutionCoordinator
from tools.connectors.browser_validator import validate_browser_config
from tools.decision.models import ToolDecisionReport
from tools.permission_manager import PermissionLevel, resolve_tool_action

ROUTING_PATH = (
    "Brain (Reasoning) → NaturalLanguagePlanner → ReasoningLoop → "
    "ToolOrchestrator → PermissionManager → BrowserConnector → Playwright"
)

VALIDATION_COMMANDS: tuple[tuple[str, str], ...] = (
    ("open_page", "Titan, ouvre https://example.com"),
    ("read_page", "Titan, lis cette page"),
    ("scroll_page", "Titan, fais défiler la page"),
    ("take_screenshot", "Titan, prends une capture d'écran"),
    (
        "open_page_title",
        "Titan, ouvre https://www.wikipedia.org et donne-moi le titre de la page",
    ),
)


def _build_coordinator() -> ExecutionCoordinator:
    """Wire ExecutionCoordinator the same way Brain does (composition root)."""
    from agents.agent_manager import AgentManager
    from brain.executor import Executor
    from brain.decision_execution_bridge import decision_engine_from_manager
    from brain.reasoning import Reasoning
    from brain.tool_dispatcher import ToolDispatcher
    from core.task_manager import TaskManager
    from core.task_orchestrator import TaskOrchestrator
    from memory.memory_manager import MemoryManager
    from memory.memory_service import MemoryService
    from memory.long_term_memory import LongTermMemory
    from tools.tool_manager import ToolManager

    tool_manager = ToolManager()
    long_term = LongTermMemory()
    memory_service = MemoryService(short_term=MemoryManager(), long_term=long_term)
    agent_manager = AgentManager(memory_service=memory_service)
    task_orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    tool_dispatcher = ToolDispatcher(tool_manager)
    reasoning = Reasoning(
        decision_engine=decision_engine_from_manager(tool_manager),
        project_root=tool_manager.project_root,
    )
    return ExecutionCoordinator(
        task_orchestrator,
        tool_dispatcher,
        reasoning=reasoning,
        executor=Executor(),
    )


def _parse_browser_payload(data: str | None) -> dict[str, Any]:
    if not data:
        return {}
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {"raw": data[:500]}
    return payload if isinstance(payload, dict) else {"raw": data[:500]}


def _trace_routing(coordinator: ExecutionCoordinator, message: str) -> dict[str, Any]:
    """Capture routing metadata before execution (Brain pipeline stages)."""
    availability = availability_resolver_from_manager(
        coordinator.tool_dispatcher.tool_manager,
    )
    analysis = coordinator.reasoning.analyze(
        message,
        availability_resolver=availability,
    )
    report = analysis.get("decision_report")
    if not isinstance(report, ToolDecisionReport):
        report = None

    planner_result = coordinator.planner.plan(
        message,
        analysis,
        decision_report=report,
    )
    reviewed = coordinator.reasoning_loop.review(
        planner_result,
        message=message,
        decision_report=report,
        analysis=analysis,
    )
    tool_requests = coordinator.planner.to_tool_requests(reviewed.planner_result)
    if not tool_requests and analysis.get("tool_requests"):
        tool_requests = list(analysis.get("tool_requests") or [])

    permission_level = ""
    planned_action = ""
    if tool_requests:
        request = tool_requests[0]
        planned_action = str(request.params.get("action", resolve_tool_action(
            request.tool_name,
            request.params,
            report,
        )))
        permission = coordinator.tool_orchestrator.permission_manager.evaluate(
            request.tool_name,
            planned_action,
            request.params,
            decision_report=report,
        )
        permission_level = permission.level.value

    return {
        "brain_intent": getattr(report, "intent", None).value if report else "",
        "brain_selected_tool": getattr(report, "selected_tool", None) if report else None,
        "browser_action": getattr(report, "browser_action", None) if report else None,
        "planner_steps": reviewed.planner_result.total_steps,
        "reasoning_loop_confidence": reviewed.confidence_score,
        "clarification_required": reviewed.clarification_required,
        "planned_action": planned_action,
        "permission_level": permission_level,
        "tool_requests": [
            {"tool": r.tool_name, "params": dict(r.params)} for r in tool_requests
        ],
    }


def _run_command(
    coordinator: ExecutionCoordinator,
    *,
    check_id: str,
    message: str,
    screenshot_path: Path | None = None,
) -> dict[str, Any]:
    """Execute one NL command through ExecutionCoordinator and collect results."""
    entry: dict[str, Any] = {
        "check_id": check_id,
        "command": message,
        "routing_path": ROUTING_PATH,
        "passed": False,
        "errors": [],
    }
    try:
        routing = _trace_routing(coordinator, message)
        entry["routing"] = routing

        if routing.get("clarification_required"):
            entry["errors"].append("ReasoningLoop a demandé une clarification.")
            return entry

        if not routing.get("tool_requests"):
            entry["errors"].append("Aucune ToolRequest produite par Brain/Planner.")
            return entry

        exec_message = message
        if check_id == "take_screenshot" and screenshot_path is not None:
            exec_message = message
            coordinator.tool_dispatcher.tool_manager  # ensure wired

        result = coordinator.execute(exec_message)
        tool_results = result.tool_results or []
        if not tool_results:
            entry["errors"].append("ExecutionCoordinator n'a retourné aucun tool result.")
            return entry

        primary = tool_results[-1]
        entry["tool_success"] = primary.success
        entry["tool_error"] = primary.error or ""
        payload = _parse_browser_payload(primary.data)
        entry["result_summary"] = {
            "url": payload.get("url", ""),
            "page_title": payload.get("page_title", ""),
            "text_length": len(str(payload.get("page_text", ""))),
            "link_count": len(payload.get("detected_links", [])),
            "button_count": len(payload.get("detected_buttons", [])),
            "screenshot_path": payload.get("screenshot_path", ""),
            "action": payload.get("action", routing.get("planned_action", "")),
            "status": payload.get("status", ""),
        }

        if check_id == "take_screenshot" and screenshot_path is not None:
            shot_path = entry["result_summary"].get("screenshot_path") or str(screenshot_path)
            entry["screenshot_path"] = shot_path
            entry["passed"] = primary.success and Path(shot_path).exists()
        elif check_id == "open_page":
            entry["passed"] = (
                primary.success
                and bool(entry["result_summary"]["page_title"])
                and "example.com" in str(entry["result_summary"]["url"])
            )
        elif check_id == "read_page":
            entry["passed"] = (
                primary.success
                and entry["result_summary"]["text_length"] > 20
            )
        elif check_id == "scroll_page":
            entry["passed"] = primary.success and routing.get("planned_action") == "scroll_page"
        elif check_id == "open_page_title":
            entry["passed"] = (
                primary.success
                and bool(entry["result_summary"]["page_title"])
                and entry["result_summary"]["link_count"] > 0
            )
        else:
            entry["passed"] = primary.success

        if screenshot_path and entry["result_summary"].get("screenshot_path"):
            entry["screenshot_path"] = entry["result_summary"]["screenshot_path"]

    except Exception as exc:
        entry["errors"].append(f"{exc}\n{traceback.format_exc()}")

    return entry


def run_validation() -> dict[str, Any]:
    """Run the full Browser Brain flow validation suite."""
    results: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "13.5 — Browser Brain Flow Validation",
        "os": platform.platform(),
        "routing_path_confirmed": ROUTING_PATH,
        "screenshot_path": "",
        "errors": [],
        "commands": [],
        "checks": {
            "open_page": False,
            "read_title": False,
            "read_visible_text": False,
            "detect_links_buttons": False,
            "scroll_page": False,
            "take_screenshot": False,
            "close_browser": False,
        },
        "verdict": "FAIL",
    }

    config = validate_browser_config(enabled=True, require_playwright=True)
    if not config.ok:
        results["errors"].append(config.message)
        return results

    coordinator = _build_coordinator()
    screenshot_dir = TITAN_ROOT / "data" / "browser_screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    screenshot_path = screenshot_dir / f"brain_flow_{stamp}.png"

    for check_id, message in VALIDATION_COMMANDS:
        entry = _run_command(
            coordinator,
            check_id=check_id,
            message=message,
            screenshot_path=screenshot_path if check_id == "take_screenshot" else None,
        )
        results["commands"].append(entry)
        if entry.get("screenshot_path"):
            results["screenshot_path"] = entry["screenshot_path"]

        if check_id == "open_page" and entry.get("passed"):
            results["checks"]["open_page"] = True
            results["checks"]["read_title"] = bool(
                entry.get("result_summary", {}).get("page_title")
            )
            results["checks"]["read_visible_text"] = (
                entry.get("result_summary", {}).get("text_length", 0) > 20
            )
        elif check_id == "read_page" and entry.get("passed"):
            results["checks"]["read_visible_text"] = True
        elif check_id == "scroll_page" and entry.get("passed"):
            results["checks"]["scroll_page"] = True
        elif check_id == "take_screenshot" and entry.get("passed"):
            results["checks"]["take_screenshot"] = True
        elif check_id == "open_page_title" and entry.get("passed"):
            results["checks"]["read_title"] = True
            results["checks"]["detect_links_buttons"] = (
                entry.get("result_summary", {}).get("link_count", 0) > 0
            )

        if entry.get("errors"):
            results["errors"].extend(entry["errors"])

    # Clean browser shutdown via connector held by BrowserTool
    close_ok = False
    try:
        browser_tool = coordinator.tool_dispatcher.tool_manager.registry.get("browser")
        if browser_tool is not None:
            connector = browser_tool._connector  # noqa: SLF001 — validation cleanup
            connector.stop()
            close_ok = not connector.session.started
    except Exception as exc:
        results["errors"].append(f"close_browser: {exc}")

    results["checks"]["close_browser"] = close_ok
    all_checks = all(results["checks"].values())
    all_commands = all(cmd.get("passed") for cmd in results["commands"])
    if all_checks and all_commands and not results["errors"]:
        results["verdict"] = (
            "PASS — Browser Connector V1 validated through Titan Brain flow"
        )
    return results


def format_report(results: dict[str, Any]) -> str:
    """Render Browser-Brain-Flow-Validation.md content."""
    lines = [
        "# Browser Brain Flow Validation Report (Phase 13.5)",
        "",
        f"**Generated:** {results['timestamp_utc']}",
        "",
        "## Routing Path Confirmed",
        "",
        "```",
        results["routing_path_confirmed"],
        "```",
        "",
        "## Environment",
        "",
        "| Property | Value |",
        "|----------|-------|",
        f"| OS | {results['os']} |",
        f"| Screenshot path | {results.get('screenshot_path') or '(none)'} |",
        "",
        "## Commands Tested",
        "",
    ]

    for entry in results.get("commands", []):
        status = "PASS" if entry.get("passed") else "FAIL"
        lines.append(f"### `{entry.get('check_id')}` — {status}")
        lines.append("")
        lines.append(f"- **Command:** {entry.get('command')}")
        routing = entry.get("routing") or {}
        lines.append(f"- **Brain intent:** {routing.get('brain_intent', '')}")
        lines.append(f"- **Selected tool:** {routing.get('brain_selected_tool', '')}")
        lines.append(f"- **Browser action:** {routing.get('browser_action') or routing.get('planned_action', '')}")
        lines.append(f"- **Planner steps:** {routing.get('planner_steps', 0)}")
        lines.append(f"- **ReasoningLoop confidence:** {routing.get('reasoning_loop_confidence', '')}")
        lines.append(f"- **Permission level:** {routing.get('permission_level', '')}")
        lines.append(f"- **Tool success:** {entry.get('tool_success', False)}")
        summary = entry.get("result_summary") or {}
        if summary:
            lines.append(f"- **Page title:** {summary.get('page_title', '')}")
            lines.append(f"- **URL:** {summary.get('url', '')}")
            lines.append(f"- **Text length:** {summary.get('text_length', 0)} chars")
            lines.append(f"- **Links / buttons:** {summary.get('link_count', 0)} / {summary.get('button_count', 0)}")
        if entry.get("screenshot_path"):
            lines.append(f"- **Screenshot:** {entry['screenshot_path']}")
        if entry.get("tool_error"):
            lines.append(f"- **Error:** {entry['tool_error']}")
        if entry.get("errors"):
            for err in entry["errors"]:
                lines.append(f"- **Trace:** `{err[:200]}`")
        lines.append("")

    lines.extend([
        "## Validation Checks",
        "",
        "| Check | Result |",
        "|-------|--------|",
    ])
    for name, ok in results.get("checks", {}).items():
        mark = "✓" if ok else "✗"
        lines.append(f"| {name} | {mark} |")
    lines.append("")

    lines.extend(["## Errors", ""])
    if results.get("errors"):
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
    ])
    if results["verdict"].startswith("PASS"):
        lines.append(
            "Browser Connector V1 is fully complete and validated through Titan Brain flow."
        )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    results = run_validation()
    out_path = PROJECT_ROOT / "Browser-Brain-Flow-Validation.md"
    out_path.write_text(format_report(results), encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nReport written to: {out_path}")
    return 0 if results["verdict"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())

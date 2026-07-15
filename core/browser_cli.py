# =====================================
# Titan Browser CLI
# =====================================

"""Manual Browser health and Brain flow commands (Phase 13.2–13.5)."""

from __future__ import annotations

import json

from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.browser_validator import validate_browser_config
from tools.permission_manager import PermissionLevel, PermissionManager

_ROUTING_PATH = (
    "Brain → Planner → ReasoningLoop → ToolOrchestrator → "
    "PermissionManager → BrowserConnector → Playwright"
)


def _build_brain_coordinator():
    """Return an ExecutionCoordinator wired like Brain (Phase 13.5)."""
    from agents.agent_manager import AgentManager
    from brain.executor import Executor
    from brain.decision_execution_bridge import decision_engine_from_manager
    from brain.reasoning import Reasoning
    from brain.tool_dispatcher import ToolDispatcher
    from core.execution_coordinator import ExecutionCoordinator
    from core.task_manager import TaskManager
    from core.task_orchestrator import TaskOrchestrator
    from memory.memory_manager import MemoryManager
    from memory.memory_service import MemoryService
    from memory.long_term_memory import LongTermMemory
    from tools.tool_manager import ToolManager

    tool_manager = ToolManager()
    memory_service = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(),
    )
    agent_manager = AgentManager(memory_service=memory_service)
    task_orchestrator = TaskOrchestrator(
        TaskManager(agent_manager),
        agent_manager,
    )
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


def _print_tool_results(result) -> None:
    """Print tool execution output from an ExecutionResult."""
    if result.tool_results_text.strip():
        print(result.tool_results_text.strip())
        return
    for tool_result in result.tool_results or []:
        status = "OK" if tool_result.success else "ÉCHEC"
        print(f"[{status}] {tool_result.tool_name}")
        if tool_result.data:
            try:
                payload = json.loads(tool_result.data)
                preview = json.dumps(payload, ensure_ascii=False, indent=2)
                if len(preview) > 1200:
                    preview = preview[:1200] + "\n…"
                print(preview)
            except json.JSONDecodeError:
                print(tool_result.data[:800])
        if tool_result.error:
            print(f"Erreur : {tool_result.error}")


def run_browser_health() -> int:
    """Validate Browser configuration and print a French health report."""
    result = validate_browser_config()
    print(result.format_report())
    if not result.ok:
        return 1

    connector = BrowserConnector(
        enabled=True,
        timeout_seconds=result.timeout_seconds,
    )
    started, start_message = connector.start()
    print("")
    print(f"Session navigateur : {'OK' if started else 'ÉCHEC'}")
    print(start_message)

    backend_label = "Playwright"
    if started:
        print(f"Backend : {backend_label}")
        connector.stop()
        print("Navigateur fermé proprement.")

    permission = PermissionManager()
    open_perm = permission.evaluate("browser", "open_page", {"url": "https://example.com"})
    scroll_perm = permission.evaluate("browser", "scroll_page", {})
    click_perm = permission.evaluate("browser", "click_element", {})
    blocked_perm = permission.evaluate("browser", "execute_script", {})

    print("")
    print("Permissions :")
    print(f"  open_page -> {open_perm.level.value}")
    print(f"  scroll_page -> {scroll_perm.level.value}")
    print(f"  click_element -> {click_perm.level.value}")
    print(f"  execute_script -> {blocked_perm.level.value}")

    failures = 0
    if not started:
        failures += 1
    if open_perm.level != PermissionLevel.AUTO_ALLOWED:
        failures += 1
    if scroll_perm.level != PermissionLevel.AUTO_ALLOWED:
        failures += 1
    if click_perm.level != PermissionLevel.CONFIRMATION_REQUIRED:
        failures += 1
    if blocked_perm.level != PermissionLevel.BLOCKED:
        failures += 1

    print("")
    if failures == 0:
        print("Health test : SUCCÈS — Browser Playwright est prêt (foundation 13.2–13.3).")
        return 0
    print(f"Health test : ÉCHEC — {failures} vérification(s) en erreur.")
    return 1


def run_browser_brain_test() -> int:
    """Interactive Brain-flow browser test — type natural-language requests."""
    config = validate_browser_config(enabled=True, require_playwright=True)
    if not config.ok:
        print(config.format_report())
        return 1

    coordinator = _build_brain_coordinator()
    print("=== Browser Brain Flow — test manuel (Phase 13.5) ===")
    print(f"Chemin : {_ROUTING_PATH}")
    print("")
    print("Exemples :")
    print('  Titan, ouvre https://example.com')
    print('  Titan, lis cette page')
    print('  Titan, fais défiler la page')
    print('  Titan, prends une capture d\'écran')
    print("")
    print("Commandes : exit, quit, stop")
    print("")

    while True:
        try:
            message = input("Browser> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            break
        if not message:
            continue
        if message.lower() in {"exit", "quit", "stop", "bye"}:
            break

        try:
            result = coordinator.execute(message)
            _print_tool_results(result)
        except Exception as exc:
            print(f"Erreur interne : {exc}")
        print("")

    browser_tool = coordinator.tool_dispatcher.tool_manager.registry.get("browser")
    if browser_tool is not None:
        browser_tool._connector.stop()  # noqa: SLF001
        print("Navigateur fermé proprement.")
    return 0


def run_browser_brain_validate() -> int:
    """Run automated Brain-flow validation and write the Phase 13.5 report."""
    from scripts.browser_brain_flow_validation import main as validate_main

    return validate_main()


def print_browser_cli_help() -> None:
    """Print Browser CLI subcommand help."""
    print(
        "Commandes Browser :\n"
        "  python main.py browser-health          — valider Playwright, session et permissions\n"
        "  python main.py browser-brain-test      — test manuel via le flux Brain (REPL)\n"
        "  python main.py browser-brain-validate — validation automatisée Phase 13.5\n"
    )


def dispatch_browser_command(command: str) -> int | None:
    """Run a Browser CLI subcommand; return exit code or None if unknown."""
    normalized = command.strip().lower().replace("_", "-")
    if normalized == "browser-health":
        return run_browser_health()
    if normalized == "browser-brain-test":
        return run_browser_brain_test()
    if normalized == "browser-brain-validate":
        return run_browser_brain_validate()
    if normalized in {"browser-help", "browser"}:
        print_browser_cli_help()
        return 0
    return None

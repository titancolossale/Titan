# =====================================
# Titan Terminal Tool
# =====================================

"""Controlled local development terminal tool for Titan's core tool layer."""

from __future__ import annotations

import logging
import time

from core.actions.action import Action
from core.actions.action_registry import ActionRegistry
from core.actions.action_result import ActionResult
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.base_tool import BaseTool
from core.tools.terminal.exceptions import (
    TerminalConfigurationError,
    TerminalPermissionDeniedError,
    TerminalRuntimeError,
)
from core.tools.terminal.terminal_client import TerminalClient
from core.tools.terminal.terminal_config import TerminalConfig

logger = logging.getLogger(__name__)

PERMISSION_EXECUTE = "terminal.execute"
PERMISSION_GIT = "terminal.git"
PERMISSION_TESTING = "terminal.testing"

CAPABILITY_RUN_COMMAND = "run_command"
CAPABILITY_RUN_PYTHON = "run_python"
CAPABILITY_RUN_GIT = "run_git"
CAPABILITY_RUN_PYTEST = "run_pytest"
CAPABILITY_RUN_NPM = "run_npm"
CAPABILITY_RUN_UV = "run_uv"

_CAPABILITY_PERMISSIONS: dict[str, str] = {
    CAPABILITY_RUN_COMMAND: PERMISSION_EXECUTE,
    CAPABILITY_RUN_PYTHON: PERMISSION_EXECUTE,
    CAPABILITY_RUN_GIT: PERMISSION_GIT,
    CAPABILITY_RUN_PYTEST: PERMISSION_TESTING,
    CAPABILITY_RUN_NPM: PERMISSION_EXECUTE,
    CAPABILITY_RUN_UV: PERMISSION_EXECUTE,
}

_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "run_command": CAPABILITY_RUN_COMMAND,
    "run_python": CAPABILITY_RUN_PYTHON,
    "run_git": CAPABILITY_RUN_GIT,
    "run_pytest": CAPABILITY_RUN_PYTEST,
    "run_npm": CAPABILITY_RUN_NPM,
    "run_uv": CAPABILITY_RUN_UV,
}

_DEFAULT_PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        id=PERMISSION_EXECUTE,
        name="Execute Terminal",
        description="Run allowlisted shell commands in the project workspace.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
    Permission(
        id=PERMISSION_GIT,
        name="Terminal Git",
        description="Run git commands in the project workspace.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
    Permission(
        id=PERMISSION_TESTING,
        name="Terminal Testing",
        description="Run pytest and other test runners in the project workspace.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
)

_TIMEOUT_PARAMETER = {
    "timeout": {
        "type": "number",
        "required": False,
        "description": "Maximum execution time in seconds.",
    },
}

_CWD_PARAMETER = {
    "cwd": {
        "type": "string",
        "required": False,
        "description": "Working directory relative to the Terminal workspace.",
    },
}

_ARGS_PARAMETER = {
    "args": {
        "type": "string",
        "required": False,
        "description": "Arguments passed to the underlying command.",
    },
}


def _build_terminal_actions(tool_id: str) -> tuple[Action, ...]:
    """Return the canonical Terminal Tool actions."""
    return (
        Action(
            id="run_command",
            name="Run Command",
            description=(
                "Run an allowlisted shell command in the project workspace. "
                "Use for general terminal, shell, or cmd requests."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_EXECUTE,
            parameters={
                "command": {
                    "type": "string",
                    "required": True,
                    "description": "Shell command to execute (allowlisted binaries only).",
                },
                **_TIMEOUT_PARAMETER,
                **_CWD_PARAMETER,
            },
            metadata={"capability": CAPABILITY_RUN_COMMAND},
        ),
        Action(
            id="run_python",
            name="Run Python",
            description=(
                "Run the Python interpreter with arguments in the project workspace. "
                "Prefer this for python -m or interpreter flags; use Python Runtime "
                "for sandboxed snippets."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_EXECUTE,
            parameters={**_ARGS_PARAMETER, **_TIMEOUT_PARAMETER, **_CWD_PARAMETER},
            metadata={"capability": CAPABILITY_RUN_PYTHON},
        ),
        Action(
            id="run_git",
            name="Run Git",
            description=(
                "Run a git command in the project workspace. "
                "Use for git status, git diff, git log, and other local git operations."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_GIT,
            parameters={
                "args": {
                    "type": "string",
                    "required": False,
                    "description": "Git arguments (default: status).",
                },
                **_TIMEOUT_PARAMETER,
                **_CWD_PARAMETER,
            },
            metadata={"capability": CAPABILITY_RUN_GIT},
        ),
        Action(
            id="run_pytest",
            name="Run Pytest",
            description=(
                "Run pytest in the project workspace. "
                "Use for test, tests, pytest, and unit test requests."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_TESTING,
            parameters={
                "args": {
                    "type": "string",
                    "required": False,
                    "description": "Pytest arguments (default: tests/).",
                },
                **_TIMEOUT_PARAMETER,
                **_CWD_PARAMETER,
            },
            metadata={"capability": CAPABILITY_RUN_PYTEST},
        ),
        Action(
            id="run_npm",
            name="Run npm",
            description=(
                "Run npm in the project workspace. "
                "Use for npm install, npm test, npm run, and Node package scripts."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_EXECUTE,
            parameters={
                "args": {
                    "type": "string",
                    "required": True,
                    "description": "npm arguments (e.g. 'test', 'run build').",
                },
                **_TIMEOUT_PARAMETER,
                **_CWD_PARAMETER,
            },
            metadata={"capability": CAPABILITY_RUN_NPM},
        ),
        Action(
            id="run_uv",
            name="Run uv",
            description=(
                "Run uv in the project workspace. "
                "Use for uv sync, uv run, uv pip, and Python package management."
            ),
            tool_id=tool_id,
            permission_id=PERMISSION_EXECUTE,
            parameters={
                "args": {
                    "type": "string",
                    "required": True,
                    "description": "uv arguments (e.g. 'sync', 'run pytest').",
                },
                **_TIMEOUT_PARAMETER,
                **_CWD_PARAMETER,
            },
            metadata={"capability": CAPABILITY_RUN_UV},
        ),
    )


class TerminalTool(BaseTool):
    """Controlled Terminal tool backed by core permissions and actions.

    Executes allowlisted development commands inside the configured project
    workspace with timeout, output-size, and security gates. Dangerous commands
    are blocked. This tool is not part of the Brain.
    """

    def __init__(
        self,
        config: TerminalConfig | None = None,
        client: TerminalClient | None = None,
        permission_manager: PermissionManager | None = None,
        action_registry: ActionRegistry | None = None,
    ) -> None:
        super().__init__()
        self._permission_manager = permission_manager or PermissionManager()
        self._register_default_permissions()

        self._config = config or TerminalConfig.from_environment()
        self._client = client or TerminalClient(self._config)
        self._actions = _build_terminal_actions(self.id)

        if action_registry is not None:
            self._register_actions(action_registry)

    @property
    def id(self) -> str:
        return "terminal"

    @property
    def name(self) -> str:
        return "Terminal"

    @property
    def description(self) -> str:
        return (
            "Safely run allowlisted development terminal commands in the configured "
            "workspace: shell commands, git, pytest, python, npm, and uv. "
            "Captures stdout, stderr, exit code, and duration. No unrestricted shell."
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def category(self) -> str:
        return "shell"

    @property
    def requires_confirmation(self) -> bool:
        return True

    @property
    def capabilities(self) -> list[str]:
        return list(_CAPABILITY_PERMISSIONS.keys())

    @property
    def client(self) -> TerminalClient:
        """Return the underlying Terminal client."""
        return self._client

    @property
    def permission_manager(self) -> PermissionManager:
        """Return the permission manager used by this tool."""
        return self._permission_manager

    def list_actions(self) -> list[Action]:
        """Return the Terminal actions exposed by this tool."""
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        """Execute a registered Terminal action without performing permission checks.

        Permission verification is owned by ``ActionDispatcher``.
        """
        registered_ids = {action.id for action in self._actions}
        if action_id not in registered_ids:
            message = f"Unsupported Terminal action: {action_id}"
            logger.warning(message)
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                metadata={"action_id": action_id},
            )

        started = time.perf_counter()
        try:
            data = self._dispatch_action(action_id, **kwargs)
        except TerminalRuntimeError as exc:
            message = str(exc)
            logger.warning(
                "Terminal action failed: action=%s error=%s",
                action_id,
                message,
            )
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                execution_time=time.perf_counter() - started,
                metadata={"action_id": action_id},
            )
        except Exception as exc:
            message = str(exc)
            logger.exception(
                "Terminal action failed unexpectedly: action=%s error=%s",
                action_id,
                message,
            )
            return ActionResult(
                success=False,
                message=message,
                errors=[message],
                execution_time=time.perf_counter() - started,
                metadata={"action_id": action_id},
            )

        elapsed = time.perf_counter() - started
        success = bool(data.get("success", True))
        message = str(
            data.get(
                "message",
                f"Terminal action '{action_id}' completed successfully."
                if success
                else f"Terminal action '{action_id}' failed.",
            )
        )
        errors = list(data.get("errors", [])) if not success else []
        logger.info(
            "Terminal action completed: action=%s success=%s duration=%.3fs "
            "exit_code=%s command=%r",
            action_id,
            success,
            elapsed,
            data.get("exit_code"),
            data.get("command"),
        )
        return ActionResult(
            success=success,
            data=data,
            message=message,
            execution_time=elapsed,
            errors=errors,
            metadata={"action_id": action_id},
        )

    def execute(self, **kwargs: object) -> object:
        """Dispatch a Terminal action after permission checks.

        Legacy callers pass ``action`` in kwargs.
        """
        action = str(kwargs.get("action", "")).strip().lower()
        if not action:
            raise TerminalConfigurationError("Missing required parameter: action")

        capability = _ACTION_CAPABILITY_MAP.get(action)
        if capability is None:
            raise TerminalConfigurationError(f"Unsupported Terminal action: {action}")

        self._require_permission(capability)

        result = self.execute_action(action, **kwargs)
        if not result.success:
            self._raise_for_failed_action(action, result)

        return result.data

    def _dispatch_action(self, action_id: str, **kwargs: object) -> dict[str, object]:
        if action_id == "run_command":
            return self._run_command(**kwargs)
        if action_id == "run_python":
            return self._run_python(**kwargs)
        if action_id == "run_git":
            return self._run_git(**kwargs)
        if action_id == "run_pytest":
            return self._run_pytest(**kwargs)
        if action_id == "run_npm":
            return self._run_npm(**kwargs)
        if action_id == "run_uv":
            return self._run_uv(**kwargs)
        raise TerminalConfigurationError(f"Unsupported Terminal action: {action_id}")

    def _run_command(self, **kwargs: object) -> dict[str, object]:
        command = kwargs.get("command", "")
        if isinstance(command, (list, tuple)):
            command_value: str | list[str] = [str(item) for item in command]
        else:
            command_value = str(command)
        timeout = self._optional_timeout(kwargs.get("timeout"))
        cwd = self._optional_cwd(kwargs.get("cwd"))
        execution = self._client.run_command(command_value, timeout=timeout, cwd=cwd)
        return self._execution_payload("run_command", execution)

    def _run_python(self, **kwargs: object) -> dict[str, object]:
        args = self._optional_args(kwargs.get("args"), default="")
        timeout = self._optional_timeout(kwargs.get("timeout"))
        cwd = self._optional_cwd(kwargs.get("cwd"))
        execution = self._client.run_python(args, timeout=timeout, cwd=cwd)
        return self._execution_payload("run_python", execution)

    def _run_git(self, **kwargs: object) -> dict[str, object]:
        args = self._optional_args(kwargs.get("args"), default="status")
        timeout = self._optional_timeout(kwargs.get("timeout"))
        cwd = self._optional_cwd(kwargs.get("cwd"))
        execution = self._client.run_git(args, timeout=timeout, cwd=cwd)
        return self._execution_payload("run_git", execution)

    def _run_pytest(self, **kwargs: object) -> dict[str, object]:
        args = self._optional_args(kwargs.get("args"), default="tests/")
        timeout = self._optional_timeout(kwargs.get("timeout"))
        cwd = self._optional_cwd(kwargs.get("cwd"))
        execution = self._client.run_pytest(args, timeout=timeout, cwd=cwd)
        return self._execution_payload("run_pytest", execution)

    def _run_npm(self, **kwargs: object) -> dict[str, object]:
        args = self._optional_args(kwargs.get("args"), default="")
        if not str(args).strip() and not isinstance(args, (list, tuple)):
            raise TerminalConfigurationError("Missing required parameter: args")
        if isinstance(args, (list, tuple)) and not args:
            raise TerminalConfigurationError("Missing required parameter: args")
        timeout = self._optional_timeout(kwargs.get("timeout"))
        cwd = self._optional_cwd(kwargs.get("cwd"))
        execution = self._client.run_npm(args, timeout=timeout, cwd=cwd)
        return self._execution_payload("run_npm", execution)

    def _run_uv(self, **kwargs: object) -> dict[str, object]:
        args = self._optional_args(kwargs.get("args"), default="")
        if not str(args).strip() and not isinstance(args, (list, tuple)):
            raise TerminalConfigurationError("Missing required parameter: args")
        if isinstance(args, (list, tuple)) and not args:
            raise TerminalConfigurationError("Missing required parameter: args")
        timeout = self._optional_timeout(kwargs.get("timeout"))
        cwd = self._optional_cwd(kwargs.get("cwd"))
        execution = self._client.run_uv(args, timeout=timeout, cwd=cwd)
        return self._execution_payload("run_uv", execution)

    @staticmethod
    def _execution_payload(action_id: str, execution: object) -> dict[str, object]:
        data = execution.to_dict()  # type: ignore[attr-defined]
        success = bool(data.get("success"))
        errors: list[str] = []
        if data.get("timed_out"):
            errors.append(str(data.get("stderr") or "Execution timed out."))
        elif not success:
            detail = str(data.get("stderr") or data.get("stdout") or "non-zero exit")
            errors.append(detail)

        message = (
            f"Terminal action '{action_id}' completed successfully."
            if success
            else f"Terminal action '{action_id}' failed."
        )
        return {
            "action": action_id,
            "success": success,
            "stdout": data.get("stdout", ""),
            "stderr": data.get("stderr", ""),
            "exit_code": data.get("exit_code", 1),
            "duration": data.get("duration", 0.0),
            "command": data.get("command", ""),
            "cwd": data.get("cwd", ""),
            "timed_out": bool(data.get("timed_out", False)),
            "truncated": bool(data.get("truncated", False)),
            "message": message,
            "errors": errors,
        }

    @staticmethod
    def _optional_timeout(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise TerminalConfigurationError(
                f"Invalid timeout value: {value!r}"
            ) from exc

    @staticmethod
    def _optional_cwd(value: object) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    @staticmethod
    def _optional_args(value: object, *, default: str) -> str | list[str]:
        if value is None or value == "":
            return default
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        return str(value)

    def _register_actions(self, registry: ActionRegistry) -> None:
        for action in self._actions:
            if registry.action_exists(action.tool_id, action.id):
                continue
            registry.register_action(action)

    def _register_default_permissions(self) -> None:
        for permission in _DEFAULT_PERMISSIONS:
            if self._permission_manager.permission_exists(permission.id):
                continue
            self._permission_manager.register_permission(permission)
            logger.info("Registered Terminal permission: %s", permission.id)

    def _require_permission(self, capability: str) -> None:
        permission_id = _CAPABILITY_PERMISSIONS[capability]
        result = self._permission_manager.check_permission(permission_id)
        if not result.allowed:
            logger.warning(
                "Terminal permission denied: capability=%s permission=%s reason=%s",
                capability,
                permission_id,
                result.reason,
            )
            raise TerminalPermissionDeniedError(permission_id, result.reason)

    @staticmethod
    def _raise_for_failed_action(action: str, result: ActionResult) -> None:
        if "permission" in result.message.lower() or "confirmation" in result.message.lower():
            permission_id = str(result.metadata.get("permission_id", "unknown"))
            raise TerminalPermissionDeniedError(permission_id, result.message)
        raise TerminalConfigurationError(result.message or f"Terminal action failed: {action}")

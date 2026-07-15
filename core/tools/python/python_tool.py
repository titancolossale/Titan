# =====================================
# Titan Python Tool
# =====================================

"""Sandboxed Python execution tool for Titan's core tool layer."""

from __future__ import annotations

import logging
import time

from core.actions.action import Action
from core.actions.action_registry import ActionRegistry
from core.actions.action_result import ActionResult
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.base_tool import BaseTool
from core.tools.python.exceptions import (
    PythonConfigurationError,
    PythonPermissionDeniedError,
    PythonRuntimeError,
)
from core.tools.python.python_client import PythonRuntimeClient
from core.tools.python.python_config import PythonRuntimeConfig

logger = logging.getLogger(__name__)

PERMISSION_EXECUTE = "python.execute"
PERMISSION_FORMAT = "python.format"
PERMISSION_SYNTAX_CHECK = "python.syntax_check"

CAPABILITY_RUN_SCRIPT = "run_script"
CAPABILITY_RUN_SNIPPET = "run_snippet"
CAPABILITY_SYNTAX_CHECK = "syntax_check"
CAPABILITY_FORMAT_CODE = "format_code"

_CAPABILITY_PERMISSIONS: dict[str, str] = {
    CAPABILITY_RUN_SCRIPT: PERMISSION_EXECUTE,
    CAPABILITY_RUN_SNIPPET: PERMISSION_EXECUTE,
    CAPABILITY_SYNTAX_CHECK: PERMISSION_SYNTAX_CHECK,
    CAPABILITY_FORMAT_CODE: PERMISSION_FORMAT,
}

_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "run_script": CAPABILITY_RUN_SCRIPT,
    "run_snippet": CAPABILITY_RUN_SNIPPET,
    "syntax_check": CAPABILITY_SYNTAX_CHECK,
    "format_code": CAPABILITY_FORMAT_CODE,
}

_DEFAULT_PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        id=PERMISSION_EXECUTE,
        name="Execute Python",
        description="Run Python snippets or scripts in an isolated workspace.",
        level=PermissionLevel.CONFIRMATION_REQUIRED,
    ),
    Permission(
        id=PERMISSION_FORMAT,
        name="Format Python",
        description="Format Python source without executing it.",
        level=PermissionLevel.SAFE,
    ),
    Permission(
        id=PERMISSION_SYNTAX_CHECK,
        name="Syntax Check Python",
        description="Validate Python syntax without executing it.",
        level=PermissionLevel.SAFE,
    ),
)

_CODE_PARAMETER = {
    "code": {
        "type": "string",
        "required": True,
        "description": "Python source code.",
    },
}

_TIMEOUT_PARAMETER = {
    "timeout": {
        "type": "number",
        "required": False,
        "description": "Maximum execution time in seconds.",
    },
}


def _build_python_actions(tool_id: str) -> tuple[Action, ...]:
    """Return the canonical Python Runtime actions."""
    return (
        Action(
            id="run_snippet",
            name="Run Snippet",
            description="Execute a Python source snippet in an isolated workspace.",
            tool_id=tool_id,
            permission_id=PERMISSION_EXECUTE,
            parameters={**_CODE_PARAMETER, **_TIMEOUT_PARAMETER},
            metadata={"capability": CAPABILITY_RUN_SNIPPET},
        ),
        Action(
            id="run_script",
            name="Run Script",
            description="Execute a Python script file inside the isolated workspace.",
            tool_id=tool_id,
            permission_id=PERMISSION_EXECUTE,
            parameters={
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "Script path relative to the Python workspace.",
                },
                **_TIMEOUT_PARAMETER,
                "args": {
                    "type": "array",
                    "required": False,
                    "description": "Optional command-line arguments for the script.",
                },
            },
            metadata={"capability": CAPABILITY_RUN_SCRIPT},
        ),
        Action(
            id="syntax_check",
            name="Syntax Check",
            description="Validate Python syntax without executing the code.",
            tool_id=tool_id,
            permission_id=PERMISSION_SYNTAX_CHECK,
            parameters=dict(_CODE_PARAMETER),
            metadata={"capability": CAPABILITY_SYNTAX_CHECK},
        ),
        Action(
            id="format_code",
            name="Format Code",
            description="Format Python source without executing it.",
            tool_id=tool_id,
            permission_id=PERMISSION_FORMAT,
            parameters=dict(_CODE_PARAMETER),
            metadata={"capability": CAPABILITY_FORMAT_CODE},
        ),
    )


class PythonTool(BaseTool):
    """Sandboxed Python Runtime tool backed by core permissions and actions.

    Executes snippets and scripts inside an isolated working directory with
    timeout, output-size, and file-count limits. Network access and arbitrary
    shell execution are blocked. This tool is not part of the Brain.
    """

    def __init__(
        self,
        config: PythonRuntimeConfig | None = None,
        client: PythonRuntimeClient | None = None,
        permission_manager: PermissionManager | None = None,
        action_registry: ActionRegistry | None = None,
    ) -> None:
        super().__init__()
        self._permission_manager = permission_manager or PermissionManager()
        self._register_default_permissions()

        self._config = config or PythonRuntimeConfig.from_environment()
        self._client = client or PythonRuntimeClient(self._config)
        self._actions = _build_python_actions(self.id)

        if action_registry is not None:
            self._register_actions(action_registry)

    @property
    def id(self) -> str:
        return "python"

    @property
    def name(self) -> str:
        return "Python Runtime"

    @property
    def description(self) -> str:
        return (
            "Safely execute Python snippets and scripts in an isolated workspace. "
            "Supports syntax checking and formatting. No network or shell access."
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def category(self) -> str:
        return "runtime"

    @property
    def requires_confirmation(self) -> bool:
        return True

    @property
    def capabilities(self) -> list[str]:
        return list(_CAPABILITY_PERMISSIONS.keys())

    @property
    def client(self) -> PythonRuntimeClient:
        """Return the underlying runtime client."""
        return self._client

    @property
    def permission_manager(self) -> PermissionManager:
        """Return the permission manager used by this tool."""
        return self._permission_manager

    def list_actions(self) -> list[Action]:
        """Return the Python Runtime actions exposed by this tool."""
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        """Execute a registered Python action without performing permission checks.

        Permission verification is owned by ``ActionDispatcher``.
        """
        registered_ids = {action.id for action in self._actions}
        if action_id not in registered_ids:
            message = f"Unsupported Python action: {action_id}"
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
        except PythonRuntimeError as exc:
            message = str(exc)
            logger.warning(
                "Python action failed: action=%s error=%s",
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
                "Python action failed unexpectedly: action=%s error=%s",
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
                f"Python action '{action_id}' completed successfully."
                if success
                else f"Python action '{action_id}' failed.",
            )
        )
        errors = list(data.get("errors", [])) if not success else []
        logger.info(
            "Python action completed: action=%s success=%s duration=%.3fs "
            "files_created=%s",
            action_id,
            success,
            elapsed,
            data.get("files_created", []),
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
        """Dispatch a Python action after permission checks.

        Legacy callers pass ``action`` in kwargs.
        """
        action = str(kwargs.get("action", "")).strip().lower()
        if not action:
            raise PythonConfigurationError("Missing required parameter: action")

        capability = _ACTION_CAPABILITY_MAP.get(action)
        if capability is None:
            raise PythonConfigurationError(f"Unsupported Python action: {action}")

        self._require_permission(capability)

        result = self.execute_action(action, **kwargs)
        if not result.success:
            self._raise_for_failed_action(action, result)

        return result.data

    def _dispatch_action(self, action_id: str, **kwargs: object) -> dict[str, object]:
        if action_id == "run_snippet":
            return self._run_snippet(**kwargs)
        if action_id == "run_script":
            return self._run_script(**kwargs)
        if action_id == "syntax_check":
            return self._syntax_check(**kwargs)
        if action_id == "format_code":
            return self._format_code(**kwargs)
        raise PythonConfigurationError(f"Unsupported Python action: {action_id}")

    def _run_snippet(self, **kwargs: object) -> dict[str, object]:
        code = str(kwargs.get("code", ""))
        timeout = self._optional_timeout(kwargs.get("timeout"))
        execution = self._client.run_snippet(code, timeout=timeout)
        return self._execution_payload("run_snippet", execution)

    def _run_script(self, **kwargs: object) -> dict[str, object]:
        path = str(kwargs.get("path", "")).strip()
        if not path:
            raise PythonConfigurationError("Missing required parameter: path")
        timeout = self._optional_timeout(kwargs.get("timeout"))
        raw_args = kwargs.get("args")
        args: list[str] | None = None
        if isinstance(raw_args, (list, tuple)):
            args = [str(item) for item in raw_args]
        execution = self._client.run_script(path, timeout=timeout, args=args)
        payload = self._execution_payload("run_script", execution)
        payload["path"] = path
        return payload

    def _syntax_check(self, **kwargs: object) -> dict[str, object]:
        code = str(kwargs.get("code", ""))
        result = self._client.syntax_check(code)
        return {
            "action": "syntax_check",
            "success": result.valid,
            "valid": result.valid,
            "message": result.message,
            "line": result.line,
            "offset": result.offset,
            "stdout": "",
            "stderr": "" if result.valid else result.message,
            "exit_code": 0 if result.valid else 1,
            "duration": 0.0,
            "files_created": [],
            "errors": [] if result.valid else [result.message],
        }

    def _format_code(self, **kwargs: object) -> dict[str, object]:
        code = str(kwargs.get("code", ""))
        result = self._client.format_code(code)
        return {
            "action": "format_code",
            "success": True,
            "formatted_code": result.formatted_code,
            "changed": result.changed,
            "message": result.message,
            "stdout": result.formatted_code,
            "stderr": "",
            "exit_code": 0,
            "duration": 0.0,
            "files_created": [],
        }

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
            f"Python action '{action_id}' completed successfully."
            if success
            else f"Python action '{action_id}' failed."
        )
        return {
            "action": action_id,
            "success": success,
            "stdout": data.get("stdout", ""),
            "stderr": data.get("stderr", ""),
            "exit_code": data.get("exit_code", 1),
            "duration": data.get("duration", 0.0),
            "files_created": list(data.get("files_created", [])),
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
            raise PythonConfigurationError(
                f"Invalid timeout value: {value!r}"
            ) from exc

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
            logger.info("Registered Python permission: %s", permission.id)

    def _require_permission(self, capability: str) -> None:
        permission_id = _CAPABILITY_PERMISSIONS[capability]
        result = self._permission_manager.check_permission(permission_id)
        if not result.allowed:
            logger.warning(
                "Python permission denied: capability=%s permission=%s reason=%s",
                capability,
                permission_id,
                result.reason,
            )
            raise PythonPermissionDeniedError(permission_id, result.reason)

    @staticmethod
    def _raise_for_failed_action(action: str, result: ActionResult) -> None:
        if "permission" in result.message.lower() or "confirmation" in result.message.lower():
            permission_id = str(result.metadata.get("permission_id", "unknown"))
            raise PythonPermissionDeniedError(permission_id, result.message)
        raise PythonConfigurationError(result.message or f"Python action failed: {action}")

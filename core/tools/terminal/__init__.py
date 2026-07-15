# =====================================
# Titan Terminal Tool Package
# =====================================

"""Controlled local development terminal for Titan's core tool layer."""

from core.tools.terminal.exceptions import (
    TerminalConfigurationError,
    TerminalExecutionTimeoutError,
    TerminalOutputTooLargeError,
    TerminalPathError,
    TerminalPermissionDeniedError,
    TerminalRuntimeError,
    TerminalSecurityError,
)
from core.tools.terminal.models import CommandResult
from core.tools.terminal.terminal_client import TerminalClient
from core.tools.terminal.terminal_config import TerminalConfig
from core.tools.terminal.terminal_tool import (
    CAPABILITY_RUN_COMMAND,
    CAPABILITY_RUN_GIT,
    CAPABILITY_RUN_NPM,
    CAPABILITY_RUN_PYTEST,
    CAPABILITY_RUN_PYTHON,
    CAPABILITY_RUN_UV,
    PERMISSION_EXECUTE,
    PERMISSION_GIT,
    PERMISSION_TESTING,
    TerminalTool,
)

__all__ = [
    "CAPABILITY_RUN_COMMAND",
    "CAPABILITY_RUN_GIT",
    "CAPABILITY_RUN_NPM",
    "CAPABILITY_RUN_PYTEST",
    "CAPABILITY_RUN_PYTHON",
    "CAPABILITY_RUN_UV",
    "CommandResult",
    "PERMISSION_EXECUTE",
    "PERMISSION_GIT",
    "PERMISSION_TESTING",
    "TerminalClient",
    "TerminalConfig",
    "TerminalConfigurationError",
    "TerminalExecutionTimeoutError",
    "TerminalOutputTooLargeError",
    "TerminalPathError",
    "TerminalPermissionDeniedError",
    "TerminalRuntimeError",
    "TerminalSecurityError",
    "TerminalTool",
]

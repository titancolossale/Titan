# ==========================================
# Titan AI
# Main Entry Point
# ==========================================

import logging
import sys

from config.settings import LOG_DIR, LOG_LEVEL, TITAN_NAME, VERSION
from core.logging_config import setup_logging
from core.browser_cli import dispatch_browser_command
from core.broker_cli import dispatch_broker_command
from core.calendar_cli import dispatch_calendar_command
from core.email_cli import dispatch_email_command
from core.web_cli import dispatch_web_command
from core.obsidian_cli import dispatch_obsidian_command
from core.titan import Titan

setup_logging(LOG_LEVEL, LOG_DIR)

logger = logging.getLogger(__name__)


def main() -> None:
    """Start Titan REPL or run a CLI subcommand."""
    if len(sys.argv) > 1:
        exit_code = dispatch_obsidian_command(sys.argv[1])
        if exit_code is None:
            exit_code = dispatch_browser_command(sys.argv[1])
        if exit_code is None:
            exit_code = dispatch_calendar_command(sys.argv[1])
        if exit_code is None:
            exit_code = dispatch_email_command(sys.argv[1])
        if exit_code is None:
            exit_code = dispatch_broker_command(sys.argv[1])
        if exit_code is None:
            exit_code = dispatch_web_command(sys.argv[1])
        if exit_code is not None:
            raise SystemExit(exit_code)

    logger.info("%s v%s starting", TITAN_NAME, VERSION)
    titan = Titan()
    titan.start()


if __name__ == "__main__":
    main()

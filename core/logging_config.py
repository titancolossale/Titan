# =====================================
# Titan Logging Configuration
# =====================================

"""Central logging setup for Titan — rotating file and console handlers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILENAME = "titan.log"
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_level: str, log_dir: Path) -> None:
    """Configure the root logger with file rotation and console output.

    Args:
        log_level: Logging level name (e.g. ``INFO``, ``DEBUG``).
        log_dir: Directory where ``titan.log`` will be written.

    File handler uses RotatingFileHandler (5 MB × 3 backups).
    Console handler mirrors the same format for development.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILENAME

    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# =====================================
# Titan Logging Configuration Tests
# =====================================

"""Smoke tests for setup_logging."""

from __future__ import annotations

import logging
from pathlib import Path

from core.logging_config import LOG_FILENAME, setup_logging


def test_setup_logging_creates_log_file_after_info(tmp_path: Path) -> None:
    """setup_logging with a temp dir must create titan.log after logger.info."""
    log_dir = tmp_path / "logs"
    assert not log_dir.exists()

    setup_logging("INFO", log_dir)

    logger = logging.getLogger("test_logging_config")
    logger.info("logging smoke test")

    log_file = log_dir / LOG_FILENAME
    assert log_file.exists()

    content = log_file.read_text(encoding="utf-8")
    assert "logging smoke test" in content
    assert "INFO" in content

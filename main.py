# ==========================================
# Titan AI
# Main Entry Point
# ==========================================

import logging

from config.settings import LOG_DIR, LOG_LEVEL, TITAN_NAME, VERSION
from core.logging_config import setup_logging
from core.titan import Titan

setup_logging(LOG_LEVEL, LOG_DIR)

logger = logging.getLogger(__name__)
logger.info("%s v%s starting", TITAN_NAME, VERSION)

titan = Titan()
titan.start()
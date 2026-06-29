# ==========================================
# Titan Configuration
# ==========================================

import os
from pathlib import Path

TITAN_NAME = "Titan"
VERSION = "0.10.0"
CREATOR = "Nolan Hassing"

LOG_LEVEL = os.getenv("TITAN_LOG_LEVEL", "INFO")
LOG_DIR = Path(os.getenv("TITAN_LOG_DIR", "logs"))
DEBUG_BRAIN = os.getenv("TITAN_DEBUG_BRAIN", "false").lower() == "true"

# LLM configuration (Phase 2 — P2-002)
LLM_MODEL = os.getenv("TITAN_LLM_MODEL", "gpt-5.2")
MAX_PROMPT_TOKENS = int(os.getenv("TITAN_MAX_PROMPT_TOKENS", "12000"))
PROMPTS_DIR = Path(os.getenv("TITAN_PROMPTS_DIR", "prompts"))

# Tool framework (Phase 6 — P6-001)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL_PYTHON_EXEC_TIMEOUT = int(os.getenv("TITAN_TOOL_PYTHON_TIMEOUT", "5"))
TOOL_WRITE_DRY_RUN_DEFAULT = (
    os.getenv("TITAN_TOOL_WRITE_DRY_RUN", "true").lower() == "true"
)

# Conversation engine (Phase 7 — P7-001)
CONVERSATION_WINDOW_SIZE = int(os.getenv("TITAN_CONVERSATION_WINDOW", "10"))
CONVERSATION_MAX_STORED_TURNS = int(os.getenv("TITAN_CONVERSATION_MAX_TURNS", "50"))
CONVERSATION_SUMMARIZE_THRESHOLD = int(
    os.getenv("TITAN_CONVERSATION_SUMMARIZE_AT", "30")
)
CONVERSATION_PERSIST_SESSIONS = (
    os.getenv("TITAN_CONVERSATION_PERSIST", "false").lower() == "true"
)
SESSIONS_DIR = Path(os.getenv("TITAN_SESSIONS_DIR", "data/sessions"))

# Execution coordinator (Phase 8 — P8-001)
EXECUTION_MAX_AGENTS = int(os.getenv("TITAN_EXECUTION_MAX_AGENTS", "3"))
EXECUTION_MAX_TOOLS = int(os.getenv("TITAN_EXECUTION_MAX_TOOLS", "3"))

# Autonomy layer (Phase 9 — P9-001)
AUTONOMY_PROACTIVE_LEVEL = os.getenv("TITAN_AUTONOMY_PROACTIVE", "off")
AUTONOMY_AUTO_TOOL_USE = (
    os.getenv("TITAN_AUTONOMY_AUTO_TOOLS", "false").lower() == "true"
)
AUTONOMY_REQUIRE_CONFIRMATION_WRITES = (
    os.getenv("TITAN_AUTONOMY_CONFIRM_WRITES", "true").lower() == "true"
)
AUTONOMY_REQUIRE_CONFIRMATION_EXEC = (
    os.getenv("TITAN_AUTONOMY_CONFIRM_EXEC", "true").lower() == "true"
)
AUTONOMY_MAX_SCHEDULED_JOBS = int(os.getenv("TITAN_AUTONOMY_MAX_JOBS", "10"))

# LLM multi-model routing (Phase 9 — P9-070)
LLM_MODEL_CLASSIFICATION = os.getenv("TITAN_LLM_MODEL_CLASSIFICATION", LLM_MODEL)
LLM_MODEL_AGENT = os.getenv("TITAN_LLM_MODEL_AGENT", LLM_MODEL)
LLM_MODEL_EVALUATION = os.getenv("TITAN_LLM_MODEL_EVALUATION", LLM_MODEL)

# Scheduler persistence (Phase 9 — P9-040)
SCHEDULED_JOBS_PATH = Path(os.getenv("TITAN_SCHEDULED_JOBS_PATH", "data/scheduled_jobs.json"))
LEARNING_MEMORY_PATH = Path(os.getenv("TITAN_LEARNING_MEMORY_PATH", "data/learning_memory.json"))

# Tool runtime (Phase 10A — P10A-009)
TOOL_RUNTIME_VERSION = os.getenv("TITAN_TOOL_RUNTIME_VERSION", "0.10.0")
TITAN_TOOL_RUNTIME_V2 = (
    os.getenv("TITAN_TOOL_RUNTIME_V2", "true").lower() == "true"
)
TOOL_RUNS_PATH = Path(os.getenv("TITAN_TOOL_RUNS_PATH", "data/tool_runs.json"))
TOOL_METRICS_PATH = Path(os.getenv("TITAN_TOOL_METRICS_PATH", "data/tool_metrics.json"))
TOOL_AUDIT_PATH = Path(os.getenv("TITAN_TOOL_AUDIT_PATH", "logs/tools_audit.jsonl"))
TITAN_TOOL_DEFAULT_EXECUTION_MODE = os.getenv(
    "TITAN_TOOL_DEFAULT_EXECUTION_MODE", "live"
).lower()
TITAN_TOOL_MAX_CONCURRENT_RUNS = int(
    os.getenv("TITAN_TOOL_MAX_CONCURRENT_RUNS", "3")
)
TITAN_TOOL_ASYNC_POOL_SIZE = int(os.getenv("TITAN_TOOL_ASYNC_POOL_SIZE", "2"))
TITAN_TOOL_POLL_TIMEOUT_SECONDS = int(
    os.getenv("TITAN_TOOL_POLL_TIMEOUT_SECONDS", "120")
)
TITAN_TOOL_QUOTA_ENABLED = (
    os.getenv("TITAN_TOOL_QUOTA_ENABLED", "false").lower() == "true"
)
TITAN_TOOL_CONFIRMATION_TTL_SECONDS = float(
    os.getenv("TITAN_TOOL_CONFIRMATION_TTL", "300")
)
TITAN_TOOL_PERSIST_RUNS = (
    os.getenv("TITAN_TOOL_PERSIST_RUNS", "false").lower() == "true"
)
TITAN_TOOL_PERSIST_METRICS = (
    os.getenv("TITAN_TOOL_PERSIST_METRICS", "false").lower() == "true"
)
TITAN_TOOL_AUDIT_ENABLED = (
    os.getenv("TITAN_TOOL_AUDIT_ENABLED", "true").lower() == "true"
)

# Tool decision engine (Phase 10B — P10B-001)
TITAN_TOOL_DECISION_ENGINE = (
    os.getenv("TITAN_TOOL_DECISION_ENGINE", "true").lower() == "true"
)
# ==========================================
# Titan Configuration
# ==========================================

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


def _resolve_runtime_path(raw: str, default_relative: str) -> Path:
    """Resolve a runtime path relative to PROJECT_ROOT when not absolute."""
    value = (raw or default_relative).strip()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


DATA_DIR = _resolve_runtime_path(os.getenv("TITAN_DATA_DIR", "data"), "data")
MEMORY_DIR = _resolve_runtime_path(
    os.getenv("TITAN_MEMORY_DIR", str(DATA_DIR)),
    str(DATA_DIR),
)

# Load project-root .env before reading TITAN_* variables (CLI, Brain, web).
load_dotenv(ENV_FILE_PATH)

TITAN_NAME = "Titan"
VERSION = "0.44.0"
CREATOR = "Nolan Hassing"

LOG_LEVEL = os.getenv("TITAN_LOG_LEVEL", "INFO")
LOG_DIR = _resolve_runtime_path(os.getenv("TITAN_LOG_DIR", "logs"), "logs")
DEBUG_BRAIN = os.getenv("TITAN_DEBUG_BRAIN", "false").lower() == "true"

# LLM configuration (Phase 2 — P2-002)
LLM_MODEL = os.getenv("TITAN_LLM_MODEL", "gpt-5.2")
MAX_PROMPT_TOKENS = int(os.getenv("TITAN_MAX_PROMPT_TOKENS", "12000"))
PROMPTS_DIR = Path(os.getenv("TITAN_PROMPTS_DIR", "prompts"))

# Tool framework (Phase 6 — P6-001)
TOOL_PYTHON_EXEC_TIMEOUT = int(os.getenv("TITAN_TOOL_PYTHON_TIMEOUT", "5"))
TOOL_WRITE_DRY_RUN_DEFAULT = (
    os.getenv("TITAN_TOOL_WRITE_DRY_RUN", "true").lower() == "true"
)

# Python Runtime V1 (core/tools/python — Phase 2)
# Sandboxed snippet/script execution via Tool Execution Engine (not Brain).
TITAN_PYTHON_RUNTIME_TIMEOUT_SECONDS = float(
    os.getenv(
        "TITAN_PYTHON_RUNTIME_TIMEOUT_SECONDS",
        str(TOOL_PYTHON_EXEC_TIMEOUT),
    )
)
TITAN_PYTHON_RUNTIME_MAX_EXECUTION_SECONDS = float(
    os.getenv(
        "TITAN_PYTHON_RUNTIME_MAX_EXECUTION_SECONDS",
        str(TITAN_PYTHON_RUNTIME_TIMEOUT_SECONDS),
    )
)
TITAN_PYTHON_RUNTIME_MAX_OUTPUT_BYTES = int(
    os.getenv("TITAN_PYTHON_RUNTIME_MAX_OUTPUT_BYTES", str(64 * 1024))
)
TITAN_PYTHON_RUNTIME_MAX_FILE_COUNT = int(
    os.getenv("TITAN_PYTHON_RUNTIME_MAX_FILE_COUNT", "50")
)
_python_workspace_env = os.getenv("TITAN_PYTHON_RUNTIME_WORKSPACE", "").strip()
TITAN_PYTHON_RUNTIME_WORKSPACE = (
    Path(_python_workspace_env).expanduser() if _python_workspace_env else None
)

# Terminal Tool V1 (core/tools/terminal)
# Controlled workspace-bound shell access via Tool Execution Engine (not Brain).
TITAN_TERMINAL_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_TERMINAL_TIMEOUT_SECONDS", "30")
)
TITAN_TERMINAL_MAX_EXECUTION_SECONDS = float(
    os.getenv(
        "TITAN_TERMINAL_MAX_EXECUTION_SECONDS",
        str(max(TITAN_TERMINAL_TIMEOUT_SECONDS, 120.0)),
    )
)
TITAN_TERMINAL_MAX_OUTPUT_BYTES = int(
    os.getenv("TITAN_TERMINAL_MAX_OUTPUT_BYTES", str(64 * 1024))
)
_terminal_workspace_env = os.getenv("TITAN_TERMINAL_WORKSPACE", "").strip()
TITAN_TERMINAL_WORKSPACE = (
    Path(_terminal_workspace_env).expanduser()
    if _terminal_workspace_env
    else PROJECT_ROOT
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
SESSIONS_DIR = _resolve_runtime_path(
    os.getenv("TITAN_SESSIONS_DIR", str(DATA_DIR / "sessions")),
    str(DATA_DIR / "sessions"),
)

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
SCHEDULED_JOBS_PATH = _resolve_runtime_path(
    os.getenv("TITAN_SCHEDULED_JOBS_PATH", str(DATA_DIR / "scheduled_jobs.json")),
    str(DATA_DIR / "scheduled_jobs.json"),
)
LEARNING_MEMORY_PATH = _resolve_runtime_path(
    os.getenv("TITAN_LEARNING_MEMORY_PATH", str(DATA_DIR / "learning_memory.json")),
    str(DATA_DIR / "learning_memory.json"),
)
KNOWLEDGE_LEARNING_PATH = _resolve_runtime_path(
    os.getenv(
        "TITAN_KNOWLEDGE_LEARNING_PATH",
        str(DATA_DIR / "knowledge_learning.json"),
    ),
    str(DATA_DIR / "knowledge_learning.json"),
)

# Tool runtime (Phase 10A — P10A-009)
TOOL_RUNTIME_VERSION = os.getenv("TITAN_TOOL_RUNTIME_VERSION", "0.10.0")
TITAN_TOOL_RUNTIME_V2 = (
    os.getenv("TITAN_TOOL_RUNTIME_V2", "true").lower() == "true"
)
TOOL_RUNS_PATH = _resolve_runtime_path(
    os.getenv("TITAN_TOOL_RUNS_PATH", str(DATA_DIR / "tool_runs.json")),
    str(DATA_DIR / "tool_runs.json"),
)
TOOL_METRICS_PATH = _resolve_runtime_path(
    os.getenv("TITAN_TOOL_METRICS_PATH", str(DATA_DIR / "tool_metrics.json")),
    str(DATA_DIR / "tool_metrics.json"),
)
TOOL_TELEMETRY_PATH = _resolve_runtime_path(
    os.getenv("TITAN_TOOL_TELEMETRY_PATH", str(DATA_DIR / "provider_telemetry.json")),
    str(DATA_DIR / "provider_telemetry.json"),
)
TITAN_TELEMETRY_RETENTION = os.getenv("TITAN_TELEMETRY_RETENTION", "7d")
TITAN_TELEMETRY_MAX_RECORDS = int(os.getenv("TITAN_TELEMETRY_MAX_RECORDS", "10000"))
TOOL_AUDIT_PATH = Path(os.getenv("TITAN_TOOL_AUDIT_PATH", "logs/tools_audit.jsonl"))
ROLLBACK_HISTORY_PATH = _resolve_runtime_path(
    os.getenv("TITAN_ROLLBACK_HISTORY_PATH", str(DATA_DIR / "rollback_history.json")),
    str(DATA_DIR / "rollback_history.json"),
)
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
TITAN_TOOL_PERSIST_TELEMETRY = (
    os.getenv("TITAN_TOOL_PERSIST_TELEMETRY", "false").lower() == "true"
)
TITAN_TOOL_AUDIT_ENABLED = (
    os.getenv("TITAN_TOOL_AUDIT_ENABLED", "true").lower() == "true"
)

# Tool decision engine (Phase 10B — P10B-001)
TITAN_TOOL_DECISION_ENGINE = (
    os.getenv("TITAN_TOOL_DECISION_ENGINE", "true").lower() == "true"
)
TITAN_PROVIDER_FALLBACK_ENABLED = (
    os.getenv("TITAN_PROVIDER_FALLBACK_ENABLED", "false").lower() == "true"
)
# Provider fallback policy (Phase 10B — P10B-906)
TITAN_ALLOW_PROVIDER_FALLBACK = (
    os.getenv(
        "TITAN_ALLOW_PROVIDER_FALLBACK",
        os.getenv("TITAN_PROVIDER_FALLBACK_ENABLED", "false"),
    ).lower()
    == "true"
)
TITAN_ALLOW_CROSS_PROVIDER = (
    os.getenv("TITAN_ALLOW_CROSS_PROVIDER", "true").lower() == "true"
)
TITAN_ALLOW_RETRY = os.getenv("TITAN_ALLOW_RETRY", "true").lower() == "true"
TITAN_FALLBACK_TIMEOUT = float(os.getenv("TITAN_FALLBACK_TIMEOUT", "30"))

# Provider configuration (Phase 10B — P10B-302; non-secret only)
TITAN_WEB_SEARCH_ENABLED = (
    os.getenv("TITAN_WEB_SEARCH_ENABLED", "true").lower() == "true"
)
TITAN_WEB_SEARCH_PRIORITY = int(os.getenv("TITAN_WEB_SEARCH_PRIORITY", "100"))
TITAN_WEB_SEARCH_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_WEB_SEARCH_TIMEOUT_SECONDS", "30")
)
TITAN_WEB_SEARCH_RETRY_COUNT = int(os.getenv("TITAN_WEB_SEARCH_RETRY_COUNT", "2"))
TITAN_BRAVE_SEARCH_ENABLED = (
    os.getenv("TITAN_BRAVE_SEARCH_ENABLED", "true").lower() == "true"
)
TITAN_BRAVE_SEARCH_PRIORITY = int(os.getenv("TITAN_BRAVE_SEARCH_PRIORITY", "10"))
TITAN_BRAVE_SEARCH_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_BRAVE_SEARCH_TIMEOUT_SECONDS", "30")
)
TITAN_BRAVE_SEARCH_RETRY_COUNT = int(os.getenv("TITAN_BRAVE_SEARCH_RETRY_COUNT", "2"))
TITAN_CALENDAR_ENABLED = (
    os.getenv("TITAN_CALENDAR_ENABLED", "true").lower() == "true"
)
TITAN_CALENDAR_PRIORITY = int(os.getenv("TITAN_CALENDAR_PRIORITY", "100"))
TITAN_CALENDAR_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_CALENDAR_TIMEOUT_SECONDS", "30")
)
TITAN_CALENDAR_RETRY_COUNT = int(os.getenv("TITAN_CALENDAR_RETRY_COUNT", "2"))
TITAN_CALENDAR_PROVIDER = os.getenv("TITAN_CALENDAR_PROVIDER", "mock").strip().lower()
TITAN_GOOGLE_CALENDAR_ENABLED = (
    os.getenv("TITAN_GOOGLE_CALENDAR_ENABLED", "false").lower() == "true"
)
_google_client_secret_env = os.getenv(
    "TITAN_GOOGLE_CLIENT_SECRET_PATH",
    "data/google_client_secret.json",
).strip()
TITAN_GOOGLE_CLIENT_SECRET_PATH = Path(_google_client_secret_env).expanduser()
_google_token_env = os.getenv(
    "TITAN_GOOGLE_TOKEN_PATH",
    "data/google_calendar_token.json",
).strip()
TITAN_GOOGLE_TOKEN_PATH = Path(_google_token_env).expanduser()

# Email connector (Phase 15.1 — P151-001, Gmail backend Phase 15.2)
# Provider-independent foundation; Gmail OAuth via gmail_oauth.py.
TITAN_EMAIL_ENABLED = (
    os.getenv("TITAN_EMAIL_ENABLED", "true").lower() == "true"
)
TITAN_EMAIL_PRIORITY = int(os.getenv("TITAN_EMAIL_PRIORITY", "100"))
TITAN_EMAIL_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_EMAIL_TIMEOUT_SECONDS", "30")
)
TITAN_EMAIL_RETRY_COUNT = int(os.getenv("TITAN_EMAIL_RETRY_COUNT", "2"))
TITAN_EMAIL_PROVIDER = os.getenv("TITAN_EMAIL_PROVIDER", "mock").strip().lower()
TITAN_GMAIL_ENABLED = (
    os.getenv("TITAN_GMAIL_ENABLED", "false").lower() == "true"
)
_gmail_client_secret_env = os.getenv(
    "TITAN_GMAIL_CLIENT_SECRET_PATH",
    "data/google_gmail_client_secret.json",
).strip()
TITAN_GMAIL_CLIENT_SECRET_PATH = Path(_gmail_client_secret_env).expanduser()
_gmail_token_env = os.getenv(
    "TITAN_GMAIL_TOKEN_PATH",
    "data/google_gmail_token.json",
).strip()
TITAN_GMAIL_TOKEN_PATH = Path(_gmail_token_env).expanduser()

# Trading connector (Phase 16.1 — P161-001)
# Provider-independent foundation; mock/paper default. No live brokers connected.
TITAN_TRADING_ENABLED = (
    os.getenv("TITAN_TRADING_ENABLED", "true").lower() == "true"
)
TITAN_TRADING_PRIORITY = int(os.getenv("TITAN_TRADING_PRIORITY", "100"))
TITAN_TRADING_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_TRADING_TIMEOUT_SECONDS", "30")
)
TITAN_TRADING_RETRY_COUNT = int(os.getenv("TITAN_TRADING_RETRY_COUNT", "2"))
TITAN_TRADING_PROVIDER = os.getenv("TITAN_TRADING_PROVIDER", "mock").strip().lower()
TITAN_TRADING_MODE = os.getenv("TITAN_TRADING_MODE", "paper").strip().lower()
TITAN_TRADING_LIVE_ENABLED = (
    os.getenv("TITAN_TRADING_LIVE_ENABLED", "false").lower() == "true"
)
# Broker read-only foundation (Phase 16.4 — P164-001)
# Real broker providers (Apex, Rithmic, Tradovate, NinjaTrader) are read-only only.
# Paper broker ignores this flag and continues simulated execution in paper mode.
TITAN_BROKER_READ_ONLY = (
    os.getenv("TITAN_BROKER_READ_ONLY", "true").lower() == "true"
)
# Broker provider selection (Phase 16.5 — P165-001)
# When non-empty, overrides TITAN_TRADING_PROVIDER for the broker layer only.
TITAN_BROKER_PROVIDER = os.getenv("TITAN_BROKER_PROVIDER", "").strip().lower()
# Apex/Rithmic read-only adapter (Phase 16.5 — P165-001)
# Credential validation only — no live Rithmic SDK connection in this phase.
TITAN_RITHMIC_ENABLED = (
    os.getenv("TITAN_RITHMIC_ENABLED", "false").lower() == "true"
)
TITAN_RITHMIC_USERNAME = os.getenv("TITAN_RITHMIC_USERNAME", "").strip()
TITAN_RITHMIC_PASSWORD = os.getenv("TITAN_RITHMIC_PASSWORD", "").strip()
TITAN_RITHMIC_SYSTEM = os.getenv("TITAN_RITHMIC_SYSTEM", "").strip()
TITAN_RITHMIC_SERVER = os.getenv("TITAN_RITHMIC_SERVER", "").strip()
TITAN_RITHMIC_APP_NAME = os.getenv("TITAN_RITHMIC_APP_NAME", "Titan").strip()
TITAN_RITHMIC_APP_VERSION = os.getenv("TITAN_RITHMIC_APP_VERSION", "1.0").strip()

# TradingView webhook backend (Phase 16.2 — P162-001)
# Receive and understand alerts only — no order execution.
TITAN_TRADINGVIEW_ENABLED = (
    os.getenv("TITAN_TRADINGVIEW_ENABLED", "true").lower() == "true"
)
TITAN_TRADINGVIEW_WEBHOOK_SECRET = os.getenv(
    "TITAN_TRADINGVIEW_WEBHOOK_SECRET",
    "",
).strip()
_tradingview_store_env = os.getenv(
    "TITAN_TRADINGVIEW_ALERT_STORE_PATH",
    "data/tradingview_alerts.json",
).strip()
TITAN_TRADINGVIEW_ALERT_STORE_PATH = Path(_tradingview_store_env).expanduser()

TITAN_GITHUB_ENABLED = (
    os.getenv("TITAN_GITHUB_ENABLED", "true").lower() == "true"
)
TITAN_GITHUB_PRIORITY = int(os.getenv("TITAN_GITHUB_PRIORITY", "20"))
TITAN_GITHUB_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_GITHUB_TIMEOUT_SECONDS", "30")
)
TITAN_GITHUB_RETRY_COUNT = int(os.getenv("TITAN_GITHUB_RETRY_COUNT", "2"))

# Obsidian connector (Phase 12.5 — P125-001)
# Connects only to the user's EXISTING Obsidian vault (e.g. "Titan AI") via
# TITAN_OBSIDIAN_VAULT_PATH. Obsidian is external personal notes — not Titan memory.
# Titan must never create a new vault; prefer updating existing notes over create_note.
TITAN_OBSIDIAN_ENABLED = (
    os.getenv("TITAN_OBSIDIAN_ENABLED", "false").lower() == "true"
)
_obsidian_vault_env = os.getenv("TITAN_OBSIDIAN_VAULT_PATH", "").strip()
TITAN_OBSIDIAN_VAULT_PATH = (
    Path(_obsidian_vault_env).expanduser() if _obsidian_vault_env else None
)

# Browser connector (Phase 13.2 — Playwright backend)
# Read-only web page inspection; clicks, forms, and automation deferred to later phases.
TITAN_BROWSER_ENABLED = (
    os.getenv("TITAN_BROWSER_ENABLED", "false").lower() == "true"
)
TITAN_BROWSER_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_BROWSER_TIMEOUT_SECONDS", "30")
)
TITAN_BROWSER_HEADLESS = (
    os.getenv("TITAN_BROWSER_HEADLESS", "true").lower() == "true"
)

# Provider performance weighting (Phase 10B — P10B-1206)
TITAN_PROVIDER_PERF_LATENCY_WEIGHT = float(
    os.getenv("TITAN_PROVIDER_PERF_LATENCY_WEIGHT", "0.25")
)
TITAN_PROVIDER_PERF_FAILURE_WEIGHT = float(
    os.getenv("TITAN_PROVIDER_PERF_FAILURE_WEIGHT", "0.30")
)
TITAN_PROVIDER_PERF_RETRY_WEIGHT = float(
    os.getenv("TITAN_PROVIDER_PERF_RETRY_WEIGHT", "0.15")
)
TITAN_PROVIDER_PERF_HEALTH_WEIGHT = float(
    os.getenv("TITAN_PROVIDER_PERF_HEALTH_WEIGHT", "0.10")
)
TITAN_PROVIDER_PERF_SUCCESS_WEIGHT = float(
    os.getenv("TITAN_PROVIDER_PERF_SUCCESS_WEIGHT", "0.20")
)
TITAN_PROVIDER_PERF_MAX_LATENCY_MS = float(
    os.getenv("TITAN_PROVIDER_PERF_MAX_LATENCY_MS", "5000")
)
TITAN_PROVIDER_PERF_MIN_SAMPLES = int(
    os.getenv("TITAN_PROVIDER_PERF_MIN_SAMPLES", "5")
)
TITAN_PROVIDER_PERF_DEGRADED_THRESHOLD = float(
    os.getenv("TITAN_PROVIDER_PERF_DEGRADED_THRESHOLD", "45")
)

# Private web app foundation (Phase 17.1 — P171-001)
# Local-only by default; never bind publicly without explicit hardening.
TITAN_WEB_ENABLED = os.getenv("TITAN_WEB_ENABLED", "false").lower() == "true"
TITAN_WEB_HOST = os.getenv("TITAN_WEB_HOST", "127.0.0.1")
TITAN_WEB_PORT = int(os.getenv("TITAN_WEB_PORT", "8000"))
TITAN_WEB_SECRET_KEY = os.getenv("TITAN_WEB_SECRET_KEY", "").strip()
TITAN_WEB_REMOTE_PORT = int(os.getenv("TITAN_WEB_REMOTE_PORT", "8765"))
TITAN_WEB_DEV_MODE = os.getenv("TITAN_WEB_DEV_MODE", "false").lower() == "true"
# Ephemeral local-only secret used by `python main.py web-dev` when none is configured.
TITAN_WEB_DEV_SECRET = "titan-local-dev-only"
TITAN_WEB_MAX_MESSAGE_LENGTH = int(
    os.getenv("TITAN_WEB_MAX_MESSAGE_LENGTH", "16000"),
)
# Phase 11.1B / 11.4 — bounded chat/provider deadlines (seconds).
# Global wall-clock budget for one authenticated chat turn (preferred ≤30s).
TITAN_CHAT_DEADLINE_SECONDS = float(os.getenv("TITAN_CHAT_DEADLINE_SECONDS", "30"))
# Soft UI budget (legacy alias); must not exceed deadline + small client slack.
TITAN_CHAT_TIMEOUT_SECONDS = float(
    os.getenv("TITAN_CHAT_TIMEOUT_SECONDS", str(TITAN_CHAT_DEADLINE_SECONDS))
)
# Per-attempt provider HTTP timeout — capped further by remaining deadline.
TITAN_LLM_TIMEOUT_SECONDS = float(os.getenv("TITAN_LLM_TIMEOUT_SECONDS", "20"))
# Provider retries beyond the first attempt (total attempts = 1 + retries).
TITAN_LLM_MAX_RETRIES = int(os.getenv("TITAN_LLM_MAX_RETRIES", "1"))
# Complex-path orchestration caps (Phase 11.4).
TITAN_MAX_PLANNING_ITERATIONS = int(os.getenv("TITAN_MAX_PLANNING_ITERATIONS", "3"))
TITAN_MAX_REASONING_ITERATIONS = int(os.getenv("TITAN_MAX_REASONING_ITERATIONS", "3"))
TITAN_MAX_AGENT_HANDOFFS = int(os.getenv("TITAN_MAX_AGENT_HANDOFFS", "2"))
TITAN_MAX_TOOL_DECISION_SECONDS = float(
    os.getenv("TITAN_MAX_TOOL_DECISION_SECONDS", "5")
)
# Fast-path compact prompt / output caps.
TITAN_FAST_PATH_MAX_CONTEXT_CHARS = int(
    os.getenv("TITAN_FAST_PATH_MAX_CONTEXT_CHARS", "400")
)
TITAN_FAST_PATH_MAX_OUTPUT_TOKENS = int(
    os.getenv("TITAN_FAST_PATH_MAX_OUTPUT_TOKENS", "400")
)
TITAN_CHAT_DIAGNOSTICS = (
    os.getenv("TITAN_CHAT_DIAGNOSTICS", "true").lower() == "true"
)


def reload_env() -> Path:
    """Reload the project .env file and return its resolved path."""
    load_dotenv(ENV_FILE_PATH, override=True)
    return ENV_FILE_PATH


def env_bool(name: str, default: str = "false") -> bool:
    """Read a boolean environment variable after .env has been loaded."""
    return os.getenv(name, default).strip().lower() == "true"


def is_web_dev_mode() -> bool:
    """True when `python main.py web-dev` activated local development mode."""
    return env_bool("TITAN_WEB_DEV_MODE")


def get_web_secret_key() -> str:
    """Return the configured web API secret (reads os.environ at call time)."""
    return os.getenv("TITAN_WEB_SECRET_KEY", "").strip()

# Voice interface (Phase 17.8 web client + Voice Runtime V1 server-side)
TITAN_VOICE_ENABLED = os.getenv("TITAN_VOICE_ENABLED", "true").lower() == "true"
TITAN_VOICE_LOCALE = os.getenv("TITAN_VOICE_LOCALE", "fr-FR").strip()
TITAN_VOICE_CONTINUOUS = os.getenv("TITAN_VOICE_CONTINUOUS", "false").lower() == "true"
TITAN_VOICE_TTS_RATE = float(os.getenv("TITAN_VOICE_TTS_RATE", "0.95"))
TITAN_VOICE_TTS_PITCH = float(os.getenv("TITAN_VOICE_TTS_PITCH", "1.0"))
TITAN_VOICE_VOLUME = float(os.getenv("TITAN_VOICE_VOLUME", "1.0"))
TITAN_VOICE_VOICE = os.getenv("TITAN_VOICE_VOICE", "default").strip()
TITAN_VOICE_STT_PROVIDER = os.getenv("TITAN_VOICE_STT_PROVIDER", "mock").strip().lower()
TITAN_VOICE_TTS_PROVIDER = os.getenv("TITAN_VOICE_TTS_PROVIDER", "mock").strip().lower()
TITAN_VOICE_MICROPHONE = os.getenv("TITAN_VOICE_MICROPHONE", "default").strip()
TITAN_VOICE_SPEAKER = os.getenv("TITAN_VOICE_SPEAKER", "default").strip()
TITAN_VOICE_SILENCE_TIMEOUT = float(os.getenv("TITAN_VOICE_SILENCE_TIMEOUT", "2.0"))
TITAN_VOICE_CONVERSATION_MODE = os.getenv(
    "TITAN_VOICE_CONVERSATION_MODE", "single_shot"
).strip().lower()
TITAN_VOICE_SESSIONS_PATH = _resolve_runtime_path(
    os.getenv("TITAN_VOICE_SESSIONS_PATH", str(DATA_DIR / "voice_sessions.json")),
    str(DATA_DIR / "voice_sessions.json"),
)

# Phase 10 — Cloud deployment (TITAN_APP_ENV / PORT / PUBLIC_BASE_URL)
TITAN_APP_ENV = os.getenv("TITAN_APP_ENV", os.getenv("APP_ENV", "development")).strip().lower()
TITAN_PUBLIC_BASE_URL = os.getenv(
    "TITAN_PUBLIC_BASE_URL",
    os.getenv("PUBLIC_BASE_URL", ""),
).strip()
TITAN_ALLOWED_HOSTS = os.getenv(
    "TITAN_ALLOWED_HOSTS",
    os.getenv("ALLOWED_HOSTS", ""),
).strip()
TITAN_CORS_ALLOWED_ORIGINS = os.getenv(
    "TITAN_CORS_ALLOWED_ORIGINS",
    os.getenv("CORS_ALLOWED_ORIGINS", ""),
).strip()
TITAN_COOKIE_SECURE = (
    os.getenv("TITAN_COOKIE_SECURE", os.getenv("COOKIE_SECURE", "false")).lower() == "true"
)
TITAN_DATABASE_URL = os.getenv("TITAN_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()

# Phase 12.1 — Durable web conversation history (not long-term memory / not Obsidian)
TITAN_CONVERSATION_PERSISTENCE_ENABLED = (
    os.getenv("TITAN_CONVERSATION_PERSISTENCE_ENABLED", "true").lower() == "true"
)
# When true, /ready fails if the conversation DB cannot be reached or migrated.
TITAN_CONVERSATION_PERSISTENCE_REQUIRED = (
    os.getenv(
        "TITAN_CONVERSATION_PERSISTENCE_REQUIRED",
        "true" if TITAN_APP_ENV in {"production", "prod", "staging"} else "false",
    ).lower()
    == "true"
)
TITAN_CONVERSATION_CONTEXT_MAX_TOKENS = int(
    os.getenv("TITAN_CONVERSATION_CONTEXT_MAX_TOKENS", "3000")
)
TITAN_CONVERSATION_STREAM_ENABLED = (
    os.getenv("TITAN_CONVERSATION_STREAM_ENABLED", "true").lower() == "true"
)

# Phase 10.3 — Private production authentication (session cookies)
# Never put plaintext passwords here. Use TITAN_AUTH_PASSWORD_HASH only.
TITAN_AUTH_REQUIRED = os.getenv(
    "TITAN_AUTH_REQUIRED",
    os.getenv("AUTH_REQUIRED", ""),
).strip()
TITAN_AUTH_USERNAME = os.getenv("TITAN_AUTH_USERNAME", "").strip()
TITAN_AUTH_PASSWORD_HASH = os.getenv("TITAN_AUTH_PASSWORD_HASH", "").strip()
TITAN_AUTH_USERNAME_2 = os.getenv("TITAN_AUTH_USERNAME_2", "").strip()
TITAN_AUTH_PASSWORD_HASH_2 = os.getenv("TITAN_AUTH_PASSWORD_HASH_2", "").strip()
TITAN_SESSION_IDLE_MINUTES = int(os.getenv("TITAN_SESSION_IDLE_MINUTES", "60"))
TITAN_SESSION_MAX_HOURS = int(os.getenv("TITAN_SESSION_MAX_HOURS", "24"))

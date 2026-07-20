# =====================================
# Titan Web Conversation Database
# =====================================

"""SQLAlchemy engine + explicit migrations for durable conversations (Phase 12.1)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import Engine

from config.settings import DATA_DIR, PROJECT_ROOT, TITAN_DATABASE_URL

logger = logging.getLogger(__name__)

METADATA = MetaData()

conversations_table = Table(
    "web_conversations",
    METADATA,
    Column("id", String(64), primary_key=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("title", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("archived", Boolean, nullable=False, server_default=text("0")),
    Column("metadata_json", Text, nullable=False, server_default=text("'{}'")),
)

messages_table = Table(
    "web_messages",
    METADATA,
    Column("id", String(64), primary_key=True),
    Column("conversation_id", String(64), nullable=False, index=True),
    Column("role", String(32), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("request_id", String(128), nullable=True, index=True),
    Column("status", String(32), nullable=False),
    Column("error_code", String(64), nullable=True),
    Column("provider", String(64), nullable=True),
    Column("model", String(128), nullable=True),
    Column("metadata_json", Text, nullable=False, server_default=text("'{}'")),
    Column("sequence", Integer, nullable=False, server_default=text("0")),
)

schema_migrations_table = Table(
    "web_conversation_schema_migrations",
    METADATA,
    Column("version", String(64), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)

# Unique idempotency: one assistant row per (conversation_id, request_id, role=assistant)
# Enforced in application + partial unique index where supported.

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_engine_lock = threading.Lock()
_engine: Engine | None = None
_engine_url: str | None = None


class ConversationStoreUnavailable(RuntimeError):
    """Raised when durable conversation persistence is required but unavailable."""


def resolve_database_url(
    *,
    database_url: str | None = None,
    sqlite_path: Path | None = None,
    force_sqlite: bool = False,
) -> str:
    """Resolve SQLAlchemy URL: Postgres from DATABASE_URL, else local SQLite."""
    if force_sqlite:
        path = sqlite_path or (DATA_DIR / "conversations.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.resolve().as_posix()}"

    raw = (database_url if database_url is not None else TITAN_DATABASE_URL or "").strip()
    if raw:
        # Railway sometimes provides postgres:// — SQLAlchemy wants postgresql://
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://") :]
        return raw

    path = sqlite_path or (DATA_DIR / "conversations.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve().as_posix()}"


def backend_name(url: str) -> str:
    scheme = urlparse(url).scheme.lower()
    if scheme.startswith("sqlite"):
        return "sqlite"
    if scheme.startswith("postgres"):
        return "postgresql"
    return scheme or "unknown"


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def create_conversation_engine(
    *,
    database_url: str | None = None,
    sqlite_path: Path | None = None,
    force_sqlite: bool = False,
    echo: bool = False,
) -> Engine:
    """Create a SQLAlchemy engine for conversation persistence."""
    url = resolve_database_url(
        database_url=database_url,
        sqlite_path=sqlite_path,
        force_sqlite=force_sqlite,
    )
    connect_args: dict[str, Any] = {}
    if backend_name(url) == "sqlite":
        connect_args["check_same_thread"] = False
    engine = create_engine(url, future=True, echo=echo, connect_args=connect_args)
    if backend_name(url) == "sqlite":
        _configure_sqlite(engine)
    return engine


def get_engine(
    *,
    database_url: str | None = None,
    sqlite_path: Path | None = None,
    force_sqlite: bool = False,
    refresh: bool = False,
) -> Engine:
    """Process-wide conversation DB engine (lazy singleton)."""
    global _engine, _engine_url
    url = resolve_database_url(
        database_url=database_url,
        sqlite_path=sqlite_path,
        force_sqlite=force_sqlite,
    )
    with _engine_lock:
        if _engine is not None and not refresh and _engine_url == url:
            return _engine
        if _engine is not None:
            _engine.dispose()
        _engine = create_conversation_engine(
            database_url=database_url,
            sqlite_path=sqlite_path,
            force_sqlite=force_sqlite,
        )
        _engine_url = url
        return _engine


def reset_engine() -> None:
    """Test helper — dispose process engine."""
    global _engine, _engine_url
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _engine_url = None


def apply_migrations(engine: Engine | None = None) -> list[str]:
    """Apply explicit, idempotent schema migrations. Never drops production tables."""
    eng = engine or get_engine()
    applied: list[str] = []
    with eng.begin() as conn:
        METADATA.create_all(conn, tables=[schema_migrations_table])
        existing = {
            row[0]
            for row in conn.execute(
                text("SELECT version FROM web_conversation_schema_migrations")
            )
        }
        # Migration 001 — base tables (also via metadata for dialect portability)
        version = "001_web_conversations"
        if version not in existing:
            METADATA.create_all(
                conn,
                tables=[conversations_table, messages_table],
            )
            # Indexes for ownership + ordering
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_web_conversations_user_updated "
                    "ON web_conversations (user_id, updated_at)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_web_messages_conv_seq "
                    "ON web_messages (conversation_id, sequence, created_at)"
                )
            )
            # Idempotent assistant finalization key (SQLite/Postgres compatible unique)
            try:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "ux_web_messages_assistant_request "
                        "ON web_messages (conversation_id, request_id, role) "
                        "WHERE request_id IS NOT NULL AND role = 'assistant'"
                    )
                )
            except Exception:
                # Some SQLite builds reject partial indexes in older modes — app-level guard remains.
                logger.debug(
                    "Partial unique index unavailable; relying on app-level idempotency",
                    exc_info=True,
                )
            from core.web_conversations.models import utc_now

            conn.execute(
                text(
                    "INSERT INTO web_conversation_schema_migrations "
                    "(version, applied_at) VALUES (:v, :at)"
                ),
                {"v": version, "at": utc_now()},
            )
            applied.append(version)
            logger.info("CONVERSATION_MIGRATION_APPLIED version=%s", version)

        # Ensure base tables exist even if migration row was present but tables missing
        inspector = inspect(conn)
        names = set(inspector.get_table_names())
        if "web_conversations" not in names or "web_messages" not in names:
            METADATA.create_all(
                conn,
                tables=[conversations_table, messages_table],
            )

    return applied


def check_database_ready(engine: Engine | None = None) -> tuple[bool, str, dict[str, Any]]:
    """Return readiness for /ready — never logs secrets."""
    try:
        eng = engine or get_engine()
        url = str(eng.url)
        backend = backend_name(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
        has_tables = "web_conversations" in tables and "web_messages" in tables
        if not has_tables:
            return False, "Conversation tables missing — run migrations.", {
                "backend": backend,
                "tables_ok": False,
            }
        return True, f"Conversation store ready ({backend}).", {
            "backend": backend,
            "tables_ok": True,
        }
    except Exception as exc:
        return False, f"Conversation store unavailable: {type(exc).__name__}", {
            "backend": "unknown",
            "tables_ok": False,
            "error_type": type(exc).__name__,
        }


def migrations_dir() -> Path:
    return _MIGRATIONS_DIR


def default_sqlite_path() -> Path:
    return (DATA_DIR / "conversations.db").resolve()


def project_migrations_sql_path() -> Path:
    return PROJECT_ROOT / "migrations" / "001_web_conversations.sql"

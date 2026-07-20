-- Titan Phase 12.1 — Durable web conversations
-- Explicit, repeatable migration (SQLAlchemy apply_migrations is the runtime path).
-- Do NOT DROP tables. Safe to re-run with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS web_conversation_schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS web_conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    title VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS web_messages (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    request_id VARCHAR(128),
    status VARCHAR(32) NOT NULL,
    error_code VARCHAR(64),
    provider VARCHAR(64),
    model VARCHAR(128),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    sequence INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_web_conversations_user_id
    ON web_conversations (user_id);

CREATE INDEX IF NOT EXISTS ix_web_conversations_user_updated
    ON web_conversations (user_id, updated_at);

CREATE INDEX IF NOT EXISTS ix_web_messages_conversation_id
    ON web_messages (conversation_id);

CREATE INDEX IF NOT EXISTS ix_web_messages_request_id
    ON web_messages (request_id);

CREATE INDEX IF NOT EXISTS ix_web_messages_conv_seq
    ON web_messages (conversation_id, sequence, created_at);

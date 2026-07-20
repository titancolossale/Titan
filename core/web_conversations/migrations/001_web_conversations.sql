-- Mirror of migrations/001_web_conversations.sql for package-local discovery.
-- Runtime applies schema via core.web_conversations.db.apply_migrations().

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

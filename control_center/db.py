"""SQLite persistence layer.

SQLite (not an in-memory dict) so that state survives a process restart and
so that the atomic-claim pattern in executor.py (an UPDATE ... WHERE status=
'APPROVED', checking rowcount) is backed by a real single-writer lock instead
of an application-level mutex that a second process wouldn't see.
"""
from __future__ import annotations

import sqlite3

from . import settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    platform_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    target_id TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    reason TEXT,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    executed_at TEXT,
    external_id TEXT,
    failure_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_actions_account_hash ON actions(account_id, payload_hash);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL REFERENCES actions(id),
    decision TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    approved_hash TEXT NOT NULL,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_approvals_action ON approvals(action_id);

CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL REFERENCES actions(id),
    worker_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    result TEXT,
    external_id TEXT,
    error_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_executions_action ON executions(action_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    action_id TEXT,
    actor_role TEXT,
    actor_id TEXT,
    details_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id TEXT PRIMARY KEY,
    post_url TEXT NOT NULL UNIQUE,
    label TEXT,
    account_id TEXT NOT NULL,
    last_checked_at TEXT,
    last_comment_count INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    sources_accessed TEXT,
    result_count INTEGER NOT NULL DEFAULT 0,
    errors TEXT,
    status TEXT NOT NULL DEFAULT 'RUNNING'
);

-- Research findings are NOT actions. Nothing here is ever executable on
-- its own; the only way a row here leads to a real write is a human
-- explicitly converting it (research.convert_to_action), which creates
-- an ordinary PENDING row in `actions` through the normal request_action
-- path -- still requiring separate approval and execution.
CREATE TABLE IF NOT EXISTS research_items (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES research_runs(id),
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    external_id TEXT,
    author TEXT,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    content TEXT,
    content_hash TEXT,
    opportunity_type TEXT NOT NULL,
    topic_tags TEXT,
    relevance_score REAL,
    recency_score REAL,
    discussion_score REAL,
    novelty_score REAL,
    quality_signals TEXT,
    reason_surfaced TEXT,
    draft_content TEXT,
    suggested_action_type TEXT,
    suggested_target_id TEXT,
    suggested_payload TEXT,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SURFACED',
    converted_action_id TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    times_seen INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_items_dedup ON research_items(source_url, opportunity_type);
CREATE INDEX IF NOT EXISTS idx_research_items_status ON research_items(status);
CREATE INDEX IF NOT EXISTS idx_research_items_run ON research_items(run_id);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or settings.DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()

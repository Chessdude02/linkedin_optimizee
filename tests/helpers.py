"""Shared test fixtures. In-memory SQLite per test, so tests never touch a
file on disk and never interfere with each other."""
from __future__ import annotations

import sqlite3

from control_center import db


def fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    db.init_db(conn)
    return conn


def make_action(conn, actions_mod, **overrides):
    defaults = dict(
        caller_role="agent",
        agent_id="content-agent",
        account_id="acct-1",
        action_type="CREATE_POST",
        payload={"content": "hello world"},
        reason="test",
    )
    defaults.update(overrides)
    return actions_mod.request_action(conn, **defaults)

"""Append-only audit log.

Every state-changing event gets a row. Nothing here ever updates or deletes
an existing audit row (append-oriented, per the spec this project follows).
Secret-shaped values are scrubbed before they ever reach the log or the
details JSON blob, so a caller who accidentally passes a credential through
`details` does not leak it into a store meant to be safe to read broadly.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

_SECRET_KEY_MARKERS = ("key", "token", "secret", "password", "cookie", "authorization")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scrub(details: dict[str, Any]) -> dict[str, Any]:
    scrubbed: dict[str, Any] = {}
    for k, v in details.items():
        if any(marker in k.lower() for marker in _SECRET_KEY_MARKERS):
            scrubbed[k] = "***REDACTED***"
        else:
            scrubbed[k] = v
    return scrubbed


def log_event(
    conn: sqlite3.Connection,
    event_type: str,
    *,
    action_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    actor_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> str:
    row_id = str(uuid.uuid4())
    scrubbed = _scrub(details or {})
    conn.execute(
        "INSERT INTO audit_logs (id, event_type, action_id, actor_role, actor_id, "
        "details_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (row_id, event_type, action_id, actor_role, actor_id,
         json.dumps(scrubbed, default=str), _now_iso()),
    )
    conn.commit()
    return row_id


def list_events(
    conn: sqlite3.Connection,
    *,
    action_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if action_id is not None:
        clauses.append("action_id = ?")
        params.append(action_id)
    if event_type is not None:
        clauses.append("event_type = ?")
        params.append(event_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM audit_logs {where} ORDER BY created_at DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [dict(r) for r in rows]

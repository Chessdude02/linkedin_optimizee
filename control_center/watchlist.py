"""The Exploration Agent's watchlist: specific post URLs to keep tracking.

There is no LinkedIn search or feed API available anywhere in this
stack -- only per-post lookups (post body, comments, engagers) and a
user's own recent comments. So "explore LinkedIn" concretely means:
periodically re-check a list of specific posts you've told it to watch,
for new comments and engagement, and propose actions on what changed.

Managing this list is a deliberate operator step, same as
accounts.register_account -- not something request_action() or the
dashboard's approve/decline flow can do.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_target(
    conn: sqlite3.Connection, post_url: str, account_id: str, label: Optional[str] = None
) -> str:
    """Add a post URL to the watchlist. Idempotent: adding the same URL
    twice returns the existing entry's id rather than erroring."""
    existing = conn.execute(
        "SELECT id FROM watchlist WHERE post_url = ?", (post_url,)
    ).fetchone()
    if existing:
        return existing["id"]
    target_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO watchlist (id, post_url, label, account_id, last_checked_at, "
        "last_comment_count, added_at) VALUES (?, ?, ?, ?, NULL, 0, ?)",
        (target_id, post_url, label, account_id, _now_iso()),
    )
    conn.commit()
    return target_id


def remove_target(conn: sqlite3.Connection, target_id: str) -> None:
    conn.execute("DELETE FROM watchlist WHERE id = ?", (target_id,))
    conn.commit()


def list_targets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at").fetchall()
    return [dict(r) for r in rows]


def record_check(conn: sqlite3.Connection, target_id: str, comment_count: int) -> None:
    conn.execute(
        "UPDATE watchlist SET last_checked_at = ?, last_comment_count = ? WHERE id = ?",
        (_now_iso(), comment_count, target_id),
    )
    conn.commit()

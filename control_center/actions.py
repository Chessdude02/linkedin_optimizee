"""The Action Queue: the only interface agents get.

There is no publish_post(), delete_post(), approve_action(), or
execute_action() reachable from here. Agents call request_action() and
receive a PENDING action id — nothing they call has any side effect outside
this database.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from . import audit, settings
from .exceptions import DuplicateActionError, PermissionDeniedError
from .hashing import canonical_payload_hash
from .risk import risk_for
from .state_machine import PENDING

_ACTIVE_STATUSES = ("PENDING", "APPROVED", "EXECUTING", "EXECUTED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _find_active_duplicate(
    conn: sqlite3.Connection, account_id: str, payload_hash: str
) -> Optional[str]:
    placeholders = ",".join("?" for _ in _ACTIVE_STATUSES)
    row = conn.execute(
        f"SELECT id FROM actions WHERE account_id = ? AND payload_hash = ? "
        f"AND status IN ({placeholders}) LIMIT 1",
        (account_id, payload_hash, *_ACTIVE_STATUSES),
    ).fetchone()
    return row["id"] if row else None


def request_action(
    conn: sqlite3.Connection,
    *,
    caller_role: str,
    agent_id: str,
    account_id: str,
    action_type: str,
    payload: dict[str, Any],
    reason: str,
    target_id: Optional[str] = None,
    schedule: Optional[str] = None,
) -> dict[str, Any]:
    """Create a PENDING action request. Only callable as an agent.

    Returns {"action_id": ..., "status": "PENDING"}. Raises
    PermissionDeniedError, UnknownActionTypeError (via risk_for), or
    DuplicateActionError.
    """
    if caller_role != "agent":
        raise PermissionDeniedError(
            f"caller_role={caller_role!r} may not create action requests; only 'agent' may"
        )

    risk_level = risk_for(action_type)  # raises UnknownActionTypeError for anything unlisted

    payload_hash = canonical_payload_hash(action_type, account_id, target_id, payload, schedule)

    duplicate_id = _find_active_duplicate(conn, account_id, payload_hash)
    if duplicate_id is not None:
        raise DuplicateActionError(
            f"an active action with identical content already exists: {duplicate_id}"
        )

    action_id = str(uuid.uuid4())
    now = _now()
    expires_at = now + timedelta(minutes=settings.PENDING_TTL_MINUTES)

    conn.execute(
        "INSERT INTO actions (id, action_type, agent_id, account_id, target_id, "
        "payload_json, payload_hash, reason, risk_level, status, schema_version, "
        "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (
            action_id, action_type, agent_id, account_id, target_id,
            json.dumps(payload, default=str), payload_hash, reason, risk_level,
            PENDING, now.isoformat(), expires_at.isoformat(),
        ),
    )
    conn.commit()

    audit.log_event(
        conn, "ACTION_CREATED", action_id=action_id, actor_role="agent", actor_id=agent_id,
        details={"action_type": action_type, "risk_level": risk_level, "account_id": account_id},
    )

    return {"action_id": action_id, "status": PENDING}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json"))
    return d


def get_action(conn: sqlite3.Connection, action_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_actions(
    conn: sqlite3.Connection, *, status: Optional[str] = None, limit: int = 100
) -> list[dict[str, Any]]:
    if status is not None:
        rows = conn.execute(
            "SELECT * FROM actions WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM actions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def has_open_or_executed(
    conn: sqlite3.Connection, *, target_id: str, action_type: str
) -> bool:
    """True if an action of this type against this target is already
    pending review, approved, executing, or done. Used by agents that
    propose repeatedly over time (e.g. the Exploration Agent re-checking
    a watchlist) to avoid nagging with the same proposal every run.

    Deliberately does NOT count DECLINED/EXPIRED/FAILED as blocking --
    a human declining a reaction on a post doesn't forbid ever proposing
    a *comment* on it, and a failed attempt shouldn't permanently prevent
    retrying with fresh content.
    """
    row = conn.execute(
        "SELECT 1 FROM actions WHERE target_id = ? AND action_type = ? "
        "AND status IN ('PENDING', 'APPROVED', 'EXECUTING', 'EXECUTED') LIMIT 1",
        (target_id, action_type),
    ).fetchone()
    return row is not None


def count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) as n FROM actions GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


def expire_stale_pending(conn: sqlite3.Connection) -> int:
    """Lazily flip any PENDING action past its expires_at to EXPIRED.
    Called opportunistically by approvals.approve_action/decline_action
    and can also be run on a schedule. Returns the number expired."""
    now_iso = _now_iso()
    cur = conn.execute(
        "UPDATE actions SET status = 'EXPIRED' "
        "WHERE status = 'PENDING' AND expires_at IS NOT NULL AND expires_at < ?",
        (now_iso,),
    )
    conn.commit()
    if cur.rowcount:
        audit.log_event(conn, "ACTION_EXPIRED", details={"count": cur.rowcount, "reason": "pending_ttl"})
    return cur.rowcount

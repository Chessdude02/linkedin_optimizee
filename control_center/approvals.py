"""Human approval/decline interface.

Only callable with caller_role="human". An agent or the executor calling
these raises PermissionDeniedError — enforced here, not by convention.

Approval is tied to the exact payload hash at approval time. That hash is
frozen into the approvals row and never recomputed for that row; executor.py
recomputes the CURRENT hash from the action's stored fields and compares.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from . import audit, settings
from .actions import expire_stale_pending, get_action
from .exceptions import (
    ActionNotFoundError,
    ContentHashMismatchError,
    InvalidTransitionError,
    PermissionDeniedError,
)
from .state_machine import APPROVED, DECLINED, PENDING, validate_transition


def _now() -> datetime:
    return datetime.now(timezone.utc)


def approve_action(
    conn: sqlite3.Connection,
    *,
    caller_role: str,
    action_id: str,
    approved_by: str,
    expected_hash: str,
) -> dict[str, Any]:
    """Approve an action. `expected_hash` must equal the action's current
    payload_hash — this is the "the user must approve the exact action"
    requirement made concrete: approving the wrong/changed action raises
    ContentHashMismatchError instead of silently approving whatever is
    there now."""
    if caller_role != "human":
        raise PermissionDeniedError(
            f"caller_role={caller_role!r} may not approve actions; only 'human' may"
        )

    expire_stale_pending(conn)

    action = get_action(conn, action_id)
    if action is None:
        raise ActionNotFoundError(action_id)

    validate_transition(action["status"], APPROVED)

    if expected_hash != action["payload_hash"]:
        raise ContentHashMismatchError(
            "expected_hash does not match the action's current payload_hash; "
            "re-fetch the action and confirm you are approving its current content"
        )

    approval_id = str(uuid.uuid4())
    now = _now()
    approval_expires = now + timedelta(minutes=settings.APPROVAL_TTL_MINUTES)

    cur = conn.execute(
        "UPDATE actions SET status = ? WHERE id = ? AND status = ?",
        (APPROVED, action_id, PENDING),
    )
    if cur.rowcount != 1:
        # Someone else changed it between our read and our write.
        conn.rollback()
        raise InvalidTransitionError(
            f"action {action_id} was no longer PENDING when the approval was applied"
        )
    conn.execute(
        "INSERT INTO approvals (id, action_id, decision, approved_by, approved_at, "
        "approved_hash, expires_at) VALUES (?, ?, 'APPROVED', ?, ?, ?, ?)",
        (approval_id, action_id, approved_by, now.isoformat(), expected_hash,
         approval_expires.isoformat()),
    )
    conn.commit()

    audit.log_event(
        conn, "ACTION_APPROVED", action_id=action_id, actor_role="human", actor_id=approved_by,
        details={"approval_id": approval_id, "expires_at": approval_expires.isoformat()},
    )

    return {
        "action_id": action_id,
        "status": APPROVED,
        "approval_id": approval_id,
        "expires_at": approval_expires.isoformat(),
    }


def decline_action(
    conn: sqlite3.Connection,
    *,
    caller_role: str,
    action_id: str,
    declined_by: str,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    if caller_role != "human":
        raise PermissionDeniedError(
            f"caller_role={caller_role!r} may not decline actions; only 'human' may"
        )

    expire_stale_pending(conn)

    action = get_action(conn, action_id)
    if action is None:
        raise ActionNotFoundError(action_id)

    validate_transition(action["status"], DECLINED)

    now_iso = _now().isoformat()
    cur = conn.execute(
        "UPDATE actions SET status = ? WHERE id = ? AND status = ?",
        (DECLINED, action_id, PENDING),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise InvalidTransitionError(
            f"action {action_id} was no longer PENDING when the decline was applied"
        )
    conn.execute(
        "INSERT INTO approvals (id, action_id, decision, approved_by, approved_at, "
        "approved_hash, expires_at) VALUES (?, ?, 'DECLINED', ?, ?, ?, NULL)",
        (str(uuid.uuid4()), action_id, declined_by, now_iso, action["payload_hash"]),
    )
    conn.commit()

    audit.log_event(
        conn, "ACTION_DECLINED", action_id=action_id, actor_role="human", actor_id=declined_by,
        details={"reason": reason},
    )

    return {"action_id": action_id, "status": DECLINED}

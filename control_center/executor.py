"""The Execution Service. Only this module ever performs (or would perform)
a real write. Only callable with caller_role="executor" — an agent, a human,
or a dashboard process calling this raises PermissionDeniedError.

Phase 1+2 scope: the only backend implemented is the mock one
(settings.MOCK_EXECUTION=True, the default). If MOCK_EXECUTION is turned
off, execution is refused with NotImplementedError rather than silently
doing nothing or, worse, pretending to publish — the real Publora-backed
executor is Phase 4/5 work and does not exist yet.

Pre-execution checklist, in order, fail-closed at every step:
  1. caller_role must be "executor"
  2. global writes must be enabled (kill switch)
  3. action must exist
  4. action_type must be a known/supported type
  5. if already EXECUTED: return the prior result (exactly-once, no re-send)
  6. action status must be APPROVED
  7. an APPROVED approval record must exist for it
  8. that approval must not be expired
  9. the CURRENT payload hash must match the hash frozen at approval time
  10. the APPROVED -> EXECUTING transition must be won atomically (duplicate-
      worker protection)
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from . import audit, kill_switch, settings
from .actions import get_action
from .exceptions import ActionNotFoundError, PermissionDeniedError
from .hashing import canonical_payload_hash
from .risk import NOT_YET_IMPLEMENTED, VALID_ACTION_TYPES
from .state_machine import APPROVED, EXECUTED, EXECUTING, FAILED


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(expires_at_iso: Optional[str]) -> bool:
    if expires_at_iso is None:
        return False
    expires_at = datetime.fromisoformat(expires_at_iso)
    return datetime.now(timezone.utc) >= expires_at


def _latest_approval(conn: sqlite3.Connection, action_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM approvals WHERE action_id = ? AND decision = 'APPROVED' "
        "ORDER BY approved_at DESC LIMIT 1",
        (action_id,),
    ).fetchone()
    return dict(row) if row else None


def _blocked(conn: sqlite3.Connection, action_id: str, reason: str, worker_id: str) -> dict[str, Any]:
    conn.execute("UPDATE actions SET status = 'BLOCKED' WHERE id = ?", (action_id,))
    conn.commit()
    audit.log_event(
        conn, "ACTION_BLOCKED", action_id=action_id, actor_role="executor", actor_id=worker_id,
        details={"reason": reason},
    )
    return {"status": "BLOCKED", "reason": reason}


def _run_backend(action: dict[str, Any]) -> dict[str, Any]:
    """The only implemented backend: mock. Returns a SUCCESS result with a
    synthetic external_id and never contacts a real network."""
    if not settings.MOCK_EXECUTION:
        raise NotImplementedError(
            "Real (Publora-backed) execution is not implemented in this build. "
            "Refusing to execute for real rather than silently no-op'ing or "
            "faking success. Set MOCK_EXECUTION=true for development, or wait "
            "for the Phase 4/5 executor before enabling real writes."
        )
    return {"result": "SUCCESS", "external_id": f"mock-{uuid.uuid4()}"}


def execute_approved_action(
    conn: sqlite3.Connection,
    *,
    caller_role: str,
    action_id: str,
    worker_id: str,
) -> dict[str, Any]:
    if caller_role != "executor":
        raise PermissionDeniedError(
            f"caller_role={caller_role!r} may not execute actions; only 'executor' may"
        )

    # 1. Global kill switch, checked before anything else touches this action.
    if not kill_switch.get_write_enabled(conn):
        audit.log_event(
            conn, "ACTION_BLOCKED", action_id=action_id, actor_role="executor",
            actor_id=worker_id, details={"reason": "writes_disabled"},
        )
        return {"status": "BLOCKED", "reason": "writes_disabled"}

    action = get_action(conn, action_id)
    if action is None:
        raise ActionNotFoundError(action_id)

    if action["action_type"] not in VALID_ACTION_TYPES:
        return _blocked(conn, action_id, "unknown_action_type", worker_id)

    if action["action_type"] in NOT_YET_IMPLEMENTED:
        return _blocked(conn, action_id, f"action_type_not_implemented:{action['action_type']}", worker_id)

    # Exactly-once: an already-executed action returns its prior result and
    # never re-sends, whatever calls this again.
    if action["status"] == EXECUTED:
        return {"status": EXECUTED, "reason": "already_executed", "external_id": action["external_id"]}

    if action["status"] != APPROVED:
        return _blocked(conn, action_id, f"not_approved:status_is_{action['status']}", worker_id)

    approval = _latest_approval(conn, action_id)
    if approval is None:
        return _blocked(conn, action_id, "no_approval_record", worker_id)

    if _is_expired(approval["expires_at"]):
        conn.execute(
            "UPDATE actions SET status = 'EXPIRED' WHERE id = ? AND status = ?",
            (action_id, APPROVED),
        )
        conn.commit()
        audit.log_event(
            conn, "ACTION_EXPIRED", action_id=action_id, actor_role="executor", actor_id=worker_id,
            details={"reason": "approval_expired"},
        )
        return {"status": "EXPIRED", "reason": "approval_expired"}

    current_hash = canonical_payload_hash(
        action["action_type"], action["account_id"], action["target_id"], action["payload"],
    )
    if current_hash != approval["approved_hash"]:
        return _blocked(conn, action_id, "CONTENT_HASH_MISMATCH", worker_id)

    # Atomic claim: only one concurrent worker can win APPROVED -> EXECUTING.
    cur = conn.execute(
        "UPDATE actions SET status = ? WHERE id = ? AND status = ?",
        (EXECUTING, action_id, APPROVED),
    )
    conn.commit()
    if cur.rowcount != 1:
        return {"status": "REJECTED", "reason": "already_claimed_by_another_worker"}

    execution_id = str(uuid.uuid4())
    started_at = _now_iso()
    conn.execute(
        "INSERT INTO executions (id, action_id, worker_id, started_at) VALUES (?, ?, ?, ?)",
        (execution_id, action_id, worker_id, started_at),
    )
    conn.commit()
    audit.log_event(
        conn, "ACTION_EXECUTION_STARTED", action_id=action_id, actor_role="executor", actor_id=worker_id,
        details={"execution_id": execution_id},
    )

    try:
        result = _run_backend(action)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any failure here must FAIL, not raise past us
        error_code = str(exc)[:200]
        conn.execute(
            "UPDATE actions SET status = ?, failure_code = ? WHERE id = ?",
            (FAILED, error_code, action_id),
        )
        conn.execute(
            "UPDATE executions SET finished_at = ?, result = 'FAILED', error_code = ? WHERE id = ?",
            (_now_iso(), error_code, execution_id),
        )
        conn.commit()
        audit.log_event(
            conn, "ACTION_EXECUTION_FAILED", action_id=action_id, actor_role="executor", actor_id=worker_id,
            details={"error_code": error_code},
        )
        return {"status": FAILED, "error": error_code}

    if result.get("result") == "UNKNOWN":
        # Ambiguous outcome: do not guess, do not retry, require investigation.
        # Action is deliberately left in EXECUTING rather than guessed into
        # EXECUTED or FAILED.
        conn.execute(
            "UPDATE executions SET finished_at = ?, result = 'UNKNOWN' WHERE id = ?",
            (_now_iso(), execution_id),
        )
        conn.commit()
        audit.log_event(
            conn, "SECURITY_EVENT", action_id=action_id, actor_role="executor", actor_id=worker_id,
            details={"reason": "unknown_execution_result", "execution_id": execution_id},
        )
        return {
            "status": "UNKNOWN",
            "reason": "execution result could not be determined; human investigation required",
        }

    external_id = result["external_id"]
    conn.execute(
        "UPDATE actions SET status = ?, executed_at = ?, external_id = ? WHERE id = ? AND status = ?",
        (EXECUTED, _now_iso(), external_id, action_id, EXECUTING),
    )
    conn.execute(
        "UPDATE executions SET finished_at = ?, result = 'SUCCESS', external_id = ? WHERE id = ?",
        (_now_iso(), external_id, execution_id),
    )
    conn.commit()
    audit.log_event(
        conn, "ACTION_EXECUTION_SUCCEEDED", action_id=action_id, actor_role="executor", actor_id=worker_id,
        details={"external_id": external_id, "execution_id": execution_id},
    )
    return {"status": EXECUTED, "external_id": external_id}

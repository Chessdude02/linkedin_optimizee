"""Research findings: a separate, non-actionable layer in front of the
Action Queue.

RESEARCH ≠ AUTHORIZE ≠ EXECUTE. A research_item is not an action and has
no relationship to the action state machine (PENDING/APPROVED/EXECUTED)
until a human explicitly converts it via `convert_to_action()`, which is
the ONLY function in this module that ever calls
`control_center.actions.request_action()`. Discovering, analyzing, or
drafting content never creates a row in the `actions` table by itself.

Status values here (DISCOVERED/ANALYZED/SURFACED/DISMISSED/SAVED/DRAFTED/
CONVERTED_TO_ACTION) are deliberately a disjoint vocabulary from the
action state machine's (PENDING/APPROVED/EXECUTING/EXECUTED/...) so the
two are never confused for one another, in code or in the dashboard.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from . import actions as actions_mod
from .exceptions import AlreadyConvertedError, ResearchItemNotFoundError
from .hashing import canonical_payload_hash

DISCOVERED = "DISCOVERED"
ANALYZED = "ANALYZED"
SURFACED = "SURFACED"
DISMISSED = "DISMISSED"
SAVED = "SAVED"
DRAFTED = "DRAFTED"
CONVERTED_TO_ACTION = "CONVERTED_TO_ACTION"

# Statuses that mean "still an active, un-actioned finding" -- used to
# decide whether re-checking the same source+opportunity should surface
# it again or just bump its last_seen/times_seen quietly.
_ACTIVE_STATUSES = (DISCOVERED, ANALYZED, SURFACED, SAVED, DRAFTED)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Research runs ---------------------------------------------------


def start_run(conn: sqlite3.Connection, agent_id: str) -> str:
    run_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO research_runs (id, agent_id, started_at, result_count, "
        "errors, status) VALUES (?, ?, ?, 0, '[]', 'RUNNING')",
        (run_id, agent_id, _now_iso()),
    )
    conn.commit()
    return run_id


def finish_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    sources_accessed: list[str],
    result_count: int,
    errors: list[dict[str, str]],
) -> None:
    status = "COMPLETED" if not errors else "COMPLETED_WITH_ERRORS"
    conn.execute(
        "UPDATE research_runs SET finished_at = ?, sources_accessed = ?, "
        "result_count = ?, errors = ?, status = ? WHERE id = ?",
        (_now_iso(), json.dumps(sources_accessed), result_count, json.dumps(errors), status, run_id),
    )
    conn.commit()


def get_run(conn: sqlite3.Connection, run_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM research_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM research_runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ---- Research items ----------------------------------------------------


def find_existing(
    conn: sqlite3.Connection, *, source_url: str, opportunity_type: str
) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM research_items WHERE source_url = ? AND opportunity_type = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (source_url, opportunity_type),
    ).fetchone()
    return dict(row) if row else None


def create_or_touch_item(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    source: str,
    source_url: str,
    account_id: str,
    opportunity_type: str,
    external_id: Optional[str] = None,
    author: Optional[str] = None,
    published_at: Optional[str] = None,
    content: Optional[str] = None,
    topic_tags: Optional[list[str]] = None,
    reason_surfaced: str = "",
    draft_content: Optional[str] = None,
    suggested_action_type: Optional[str] = None,
    suggested_target_id: Optional[str] = None,
    suggested_payload: Optional[dict[str, Any]] = None,
    relevance_score: Optional[float] = None,
    recency_score: Optional[float] = None,
    discussion_score: Optional[float] = None,
    novelty_score: Optional[float] = None,
    quality_signals: Optional[dict[str, Any]] = None,
) -> tuple[str, bool]:
    """Create a research item, or -- if one with the same (source_url,
    opportunity_type) already exists -- just bump its last_seen/times_seen
    and return the existing id. This is the "don't repeatedly present the
    same content" rule: a dismissed item stays dismissed and isn't
    resurrected automatically, but the record is never deleted, and a
    genuinely new opportunity type on the same post still gets its own row.

    Returns (item_id, created) -- created=False means it already existed.
    """
    existing = find_existing(conn, source_url=source_url, opportunity_type=opportunity_type)
    now = _now_iso()
    if existing:
        conn.execute(
            "UPDATE research_items SET last_seen = ?, times_seen = times_seen + 1, "
            "updated_at = ? WHERE id = ?",
            (now, now, existing["id"]),
        )
        conn.commit()
        return existing["id"], False

    item_id = str(uuid.uuid4())
    content_hash = canonical_payload_hash(
        opportunity_type, account_id, source_url, {"content": content or ""}
    )
    conn.execute(
        """INSERT INTO research_items (
            id, run_id, source, source_url, external_id, author, published_at,
            retrieved_at, content, content_hash, opportunity_type, topic_tags,
            relevance_score, recency_score, discussion_score, novelty_score,
            quality_signals, reason_surfaced, draft_content, suggested_action_type,
            suggested_target_id, suggested_payload, account_id, status,
            converted_action_id, first_seen, last_seen, times_seen, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (
            item_id, run_id, source, source_url, external_id, author, published_at,
            now, content, content_hash, opportunity_type,
            json.dumps(topic_tags or []),
            relevance_score, recency_score, discussion_score, novelty_score,
            json.dumps(quality_signals or {}), reason_surfaced, draft_content,
            suggested_action_type, suggested_target_id,
            json.dumps(suggested_payload) if suggested_payload is not None else None,
            account_id, SURFACED, None, now, now, now, now,
        ),
    )
    conn.commit()
    return item_id, True


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for json_field in ("topic_tags", "quality_signals"):
        if d.get(json_field):
            d[json_field] = json.loads(d[json_field])
    if d.get("suggested_payload"):
        d["suggested_payload"] = json.loads(d["suggested_payload"])
    return d


def get_item(conn: sqlite3.Connection, item_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM research_items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_items(
    conn: sqlite3.Connection,
    *,
    status: Optional[str] = None,
    opportunity_type: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses, params = [], []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if opportunity_type is not None:
        clauses.append("opportunity_type = ?")
        params.append(opportunity_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM research_items {where} ORDER BY created_at DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def set_status(conn: sqlite3.Connection, item_id: str, status: str) -> None:
    item = get_item(conn, item_id)
    if item is None:
        raise ResearchItemNotFoundError(item_id)
    conn.execute(
        "UPDATE research_items SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now_iso(), item_id),
    )
    conn.commit()


def convert_to_action(
    conn: sqlite3.Connection, item_id: str, *, created_by: str
) -> dict[str, Any]:
    """The ONLY bridge from research to the Action Queue. A human clicking
    "Create Action Proposal" in the dashboard calls this. It creates an
    ordinary PENDING action via the normal request_action() path --
    NEVER pre-approved, never executed here. `created_by` is the human's
    identity, recorded in the agent_id for provenance (the same pattern
    scripts/request_action.py already uses for manual, human-initiated
    requests going through the agent-facing API).
    """
    item = get_item(conn, item_id)
    if item is None:
        raise ResearchItemNotFoundError(item_id)
    if item["status"] == CONVERTED_TO_ACTION:
        raise AlreadyConvertedError(
            f"research item {item_id} was already converted to action {item['converted_action_id']}"
        )
    if not item.get("suggested_action_type"):
        raise ValueError(f"research item {item_id} has no suggested_action_type to convert")

    result = actions_mod.request_action(
        conn,
        caller_role="agent",
        agent_id=f"research-conversion:{created_by}",
        account_id=item["account_id"],
        action_type=item["suggested_action_type"],
        target_id=item.get("suggested_target_id"),
        payload=item.get("suggested_payload") or {},
        reason=f"Converted from research finding: {item.get('reason_surfaced', '')}",
    )
    conn.execute(
        "UPDATE research_items SET status = ?, converted_action_id = ?, updated_at = ? WHERE id = ?",
        (CONVERTED_TO_ACTION, result["action_id"], _now_iso(), item_id),
    )
    conn.commit()
    return result

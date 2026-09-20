"""Global emergency write control.

This is a runtime-toggleable value stored in system_settings, layered on top
of the WRITE_ENABLED environment default from settings.py. It overrides
everything: pending approvals, previous approvals, agent requests, and
scheduled operations all still funnel through executor.py, which checks
this before anything else.

Fail-closed: if the stored value is missing, corrupt, or unparseable, this
returns False (writes disabled). It never fails open.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import audit, settings

_KEY = "write_enabled"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_write_enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT value FROM system_settings WHERE key = ?", (_KEY,)
    ).fetchone()
    if row is None:
        # Never toggled at runtime yet — fall back to the deploy-time
        # default, which is itself False unless explicitly set.
        return settings.WRITE_ENABLED
    try:
        return row["value"].strip().lower() in ("1", "true", "yes", "on")
    except (AttributeError, KeyError):
        # Corrupt/unexpected row shape: fail closed, do not guess.
        return False


def set_write_enabled(conn: sqlite3.Connection, enabled: bool, *, actor: str) -> None:
    now = _now_iso()
    conn.execute(
        "INSERT INTO system_settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (_KEY, "true" if enabled else "false", now),
    )
    conn.commit()
    audit.log_event(
        conn,
        "SYSTEM_WRITE_ENABLED" if enabled else "SYSTEM_WRITE_DISABLED",
        actor_role="human",
        actor_id=actor,
    )

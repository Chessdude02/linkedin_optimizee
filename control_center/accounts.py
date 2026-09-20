"""Account registry: maps a control-center account_id to the real
destination-platform id it publishes through (e.g. Publora's platformId,
like "linkedin-P0IF-kpN1N").

Registering an account is an operator/admin action, not something an
agent or the dashboard's approve/decline flow does. There is no route in
dashboard/ that calls register_account -- connecting a new LinkedIn
account is deliberately a step you take yourself, e.g. from a shell:

    python3 -c "
    from control_center import accounts, db
    conn = db.get_connection('control_center.db')
    accounts.register_account(conn, 'vedant-linkedin', 'Vedant (LinkedIn)', 'linkedin-P0IF-kpN1N')
    "
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_account(
    conn: sqlite3.Connection, account_id: str, display_name: str, platform_id: str
) -> None:
    conn.execute(
        "INSERT INTO accounts (id, display_name, platform_id, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET display_name = excluded.display_name, "
        "platform_id = excluded.platform_id",
        (account_id, display_name, platform_id, _now_iso()),
    )
    conn.commit()


def get_platform_id(conn: sqlite3.Connection, account_id: str) -> Optional[str]:
    row = conn.execute("SELECT platform_id FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return row["platform_id"] if row else None


def list_accounts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM accounts ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]

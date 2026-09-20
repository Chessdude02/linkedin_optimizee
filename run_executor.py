#!/usr/bin/env python3
"""The Execution Service, as its own process.

Run this separately from the dashboard (`python3 dashboard/app.py`). The
dashboard can approve and decline actions and flip the kill switch; it
cannot execute anything -- only this process imports
control_center.executor and calls execute_approved_action(caller_role=
"executor", ...). That is the actual agent != authorizer != executor
separation, enforced by which process holds which import, not just by a
comment.

Usage:
  python3 run_executor.py --once      # claim and run every currently
                                       # APPROVED action once, then exit
  python3 run_executor.py             # poll forever (Ctrl-C to stop)
"""
from __future__ import annotations

import argparse
import time
import uuid

from control_center import actions, db, executor, settings


def run_once(conn, worker_id: str) -> int:
    approved = actions.list_actions(conn, status="APPROVED")
    ran = 0
    for action in approved:
        outcome = executor.execute_approved_action(
            conn, caller_role="executor", action_id=action["id"], worker_id=worker_id
        )
        print(f"[{worker_id}] {action['action_type']} {action['id']}: {outcome}")
        ran += 1
    return ran


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one pass over APPROVED actions and exit")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="seconds between polls in loop mode")
    parser.add_argument("--db-path", default=None, help="override CONTROL_CENTER_DB_PATH")
    args = parser.parse_args()

    conn = db.get_connection(args.db_path or settings.DB_PATH)
    db.init_db(conn)
    worker_id = f"worker-{uuid.uuid4().hex[:8]}"

    print(f"Execution service starting as {worker_id}. MOCK_EXECUTION={settings.MOCK_EXECUTION}")
    if args.once:
        n = run_once(conn, worker_id)
        print(f"Done. Processed {n} approved action(s).")
        return

    try:
        while True:
            run_once(conn, worker_id)
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

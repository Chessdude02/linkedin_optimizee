#!/usr/bin/env python3
"""Add, list, or remove posts the Exploration Agent watches.

Usage:
  python3 scripts/manage_watchlist.py add
  python3 scripts/manage_watchlist.py list
  python3 scripts/manage_watchlist.py remove
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control_center import db, settings, watchlist  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("add", "list", "remove"):
        print(__doc__)
        raise SystemExit(1)

    conn = db.get_connection(settings.DB_PATH)
    db.init_db(conn)
    command = sys.argv[1]

    if command == "add":
        post_url = input("Post URL to watch: ").strip()
        account_id = input("Your account id (must already be registered): ").strip()
        label = input("Label (optional, blank ok): ").strip() or None
        target_id = watchlist.add_target(conn, post_url, account_id, label)
        print(f"Watching {post_url} as {target_id}")

    elif command == "list":
        targets = watchlist.list_targets(conn)
        if not targets:
            print("Watchlist is empty.")
        for t in targets:
            print(f"{t['id']}  {t['post_url']}  (label={t['label']}, "
                  f"last_checked={t['last_checked_at']}, account={t['account_id']})")

    elif command == "remove":
        target_id = input("Target id to remove: ").strip()
        watchlist.remove_target(conn, target_id)
        print(f"Removed {target_id}")


if __name__ == "__main__":
    main()

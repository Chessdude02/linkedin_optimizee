#!/usr/bin/env python3
"""Register a LinkedIn account's real Publora platform_id, interactively.

This is a deliberate, separate operator step -- nothing an agent or the
dashboard's approve/decline flow can trigger. Find your platform_id in
Publora's dashboard under Channels -> your LinkedIn account (format:
linkedin-XXXXXXX).

Usage: python3 scripts/register_account.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control_center import accounts, db, settings  # noqa: E402


def main() -> None:
    account_id = input("Account id (your own label, e.g. 'my-linkedin'): ").strip()
    display_name = input("Display name (e.g. 'My LinkedIn'): ").strip()
    platform_id = input("Publora platform_id (e.g. linkedin-XXXXXXX): ").strip()

    if not platform_id.startswith("linkedin-"):
        print("Warning: platform_id doesn't start with 'linkedin-' -- double-check "
              "you copied it from Publora's Channels page, not somewhere else.")

    conn = db.get_connection(settings.DB_PATH)
    db.init_db(conn)
    accounts.register_account(conn, account_id, display_name, platform_id)
    print(f"Registered '{account_id}' -> {platform_id}")


if __name__ == "__main__":
    main()

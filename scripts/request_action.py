#!/usr/bin/env python3
"""Create an action request interactively, as an agent would.

In a real deployment an agent calls control_center.actions.request_action
directly (see README's Quickstart / demo.py). This script is the manual
equivalent, for testing the pipeline end to end without wiring up an
actual agent: create a request here, approve it in the dashboard, then
run run_executor.py.

Usage: python3 scripts/request_action.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control_center import actions, db, settings  # noqa: E402
from control_center.risk import VALID_ACTION_TYPES  # noqa: E402


def main() -> None:
    print(f"Valid action types: {', '.join(sorted(VALID_ACTION_TYPES))}")
    action_type = input("Action type: ").strip().upper()
    if action_type not in VALID_ACTION_TYPES:
        print(f"Unknown action type: {action_type!r}")
        raise SystemExit(1)

    account_id = input("Account id (must already be registered -- see register_account.py): ").strip()
    target_id = input("Target id (post URN, or blank for a new post): ").strip() or None
    reason = input("Reason (why this action): ").strip()

    payload: dict[str, str] = {}
    if action_type in ("CREATE_POST", "SCHEDULE_POST"):
        payload["content"] = input("Post content: ").strip()
    elif action_type in ("CREATE_COMMENT", "CREATE_REPLY"):
        payload["message"] = input("Comment/reply text: ").strip()
        if action_type == "CREATE_REPLY":
            payload["parent_comment"] = input("Parent comment URN: ").strip()
    elif action_type == "CREATE_REACTION":
        payload["reaction_type"] = input("Reaction type (LIKE/PRAISE/EMPATHY/INTEREST/APPRECIATION/ENTERTAINMENT): ").strip().upper() or "LIKE"
    elif action_type == "RESHARE_POST":
        commentary = input("Commentary (optional, blank for a plain reshare): ").strip()
        if commentary:
            payload["commentary"] = commentary
    elif action_type == "DELETE_POST":
        pass  # target_id (postGroupId) is all that's needed
    elif action_type == "DELETE_COMMENT":
        payload["comment_id"] = input("Comment id to delete: ").strip()

    conn = db.get_connection(settings.DB_PATH)
    db.init_db(conn)
    result = actions.request_action(
        conn, caller_role="agent", agent_id="manual-cli", account_id=account_id,
        action_type=action_type, payload=payload, reason=reason, target_id=target_id,
    )
    print(result)
    print("Now go approve it in the dashboard, then run: python3 run_executor.py --once")


if __name__ == "__main__":
    main()

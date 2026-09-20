#!/usr/bin/env python3
"""End-to-end walkthrough of the Phase 1+2 flow, in mock mode:

  agent requests -> PENDING
  human approves -> APPROVED (hash-locked)
  executor executes -> EXECUTED (mock, no real network call)

Then shows a rejected path: an agent trying to approve or execute its own
request, and the kill switch blocking a second action.

Run: python3 demo.py
"""
from __future__ import annotations

from control_center import actions, approvals, db, executor, kill_switch
from control_center.exceptions import PermissionDeniedError


def main() -> None:
    conn = db.get_connection(":memory:")
    db.init_db(conn)

    print("== 1. Agent requests a post (no write happens yet) ==")
    request = actions.request_action(
        conn,
        caller_role="agent",
        agent_id="content-agent",
        account_id="vedant-linkedin",
        action_type="CREATE_POST",
        payload={"content": "Shipped Phase 1+2 of the control center today.", "media": [], "links": []},
        reason="User asked to share a project update.",
    )
    print(request)

    print("\n== 2. Agent tries to approve its own request (must fail) ==")
    action = actions.get_action(conn, request["action_id"])
    try:
        approvals.approve_action(
            conn, caller_role="agent", action_id=request["action_id"],
            approved_by="content-agent", expected_hash=action["payload_hash"],
        )
    except PermissionDeniedError as e:
        print(f"Correctly refused: {e}")

    print("\n== 3. Agent tries to execute directly (must fail) ==")
    try:
        executor.execute_approved_action(
            conn, caller_role="agent", action_id=request["action_id"], worker_id="content-agent"
        )
    except PermissionDeniedError as e:
        print(f"Correctly refused: {e}")

    print("\n== 4. Writes are off by default -- execution is blocked even once approved ==")
    approval = approvals.approve_action(
        conn, caller_role="human", action_id=request["action_id"],
        approved_by="vedant", expected_hash=action["payload_hash"],
    )
    print(approval)
    blocked = executor.execute_approved_action(
        conn, caller_role="executor", action_id=request["action_id"], worker_id="worker-1"
    )
    print(blocked)

    print("\n== 5. Human flips the kill switch on, execution now proceeds (mock) ==")
    kill_switch.set_write_enabled(conn, True, actor="vedant")
    result = executor.execute_approved_action(
        conn, caller_role="executor", action_id=request["action_id"], worker_id="worker-1"
    )
    print(result)

    print("\n== 6. Re-executing the same action is a safe no-op, not a double post ==")
    again = executor.execute_approved_action(
        conn, caller_role="executor", action_id=request["action_id"], worker_id="worker-1"
    )
    print(again)

    conn.close()


if __name__ == "__main__":
    main()

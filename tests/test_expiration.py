"""Scenario E: an expired approval must be rejected, not executed."""
import unittest
from datetime import datetime, timedelta, timezone

from control_center import actions, approvals, executor, kill_switch
from tests.helpers import fresh_conn, make_action


class TestExpiration(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        kill_switch.set_write_enabled(self.conn, True, actor="test")

    def test_expired_approval_rejected(self):
        result = make_action(self.conn, actions)
        action_id = result["action_id"]
        action = actions.get_action(self.conn, action_id)
        approval = approvals.approve_action(
            self.conn, caller_role="human", action_id=action_id,
            approved_by="human-1", expected_hash=action["payload_hash"],
        )

        # Force the approval into the past instead of sleeping in a test.
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.conn.execute(
            "UPDATE approvals SET expires_at = ? WHERE id = ?",
            (past, approval["approval_id"]),
        )
        self.conn.commit()

        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=action_id, worker_id="worker-1"
        )
        self.assertEqual(outcome["status"], "EXPIRED")

        final = actions.get_action(self.conn, action_id)
        self.assertEqual(final["status"], "EXPIRED")

    def test_stale_pending_action_auto_expires_before_approval(self):
        result = make_action(self.conn, actions)
        action_id = result["action_id"]
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.conn.execute("UPDATE actions SET expires_at = ? WHERE id = ?", (past, action_id))
        self.conn.commit()

        action = actions.get_action(self.conn, action_id)
        from control_center.exceptions import InvalidTransitionError

        with self.assertRaises(InvalidTransitionError):
            approvals.approve_action(
                self.conn, caller_role="human", action_id=action_id,
                approved_by="human-1", expected_hash=action["payload_hash"],
            )
        final = actions.get_action(self.conn, action_id)
        self.assertEqual(final["status"], "EXPIRED")


if __name__ == "__main__":
    unittest.main()

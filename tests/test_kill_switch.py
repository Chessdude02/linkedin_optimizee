"""Scenario G: kill switch blocks all writes, and fails closed on corrupt
or missing state rather than defaulting to enabled."""
import unittest

from control_center import actions, approvals, executor, kill_switch
from tests.helpers import fresh_conn, make_action


class TestKillSwitch(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()

    def test_writes_blocked_by_default(self):
        # settings.WRITE_ENABLED defaults False, and it was never toggled
        # at runtime in this fresh DB.
        self.assertFalse(kill_switch.get_write_enabled(self.conn))

        result = make_action(self.conn, actions)
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(
            self.conn, caller_role="human", action_id=result["action_id"],
            approved_by="h1", expected_hash=action["payload_hash"],
        )
        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=result["action_id"], worker_id="w1"
        )
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(outcome["reason"], "writes_disabled")

    def test_enabling_then_disabling_blocks_again(self):
        kill_switch.set_write_enabled(self.conn, True, actor="admin")
        self.assertTrue(kill_switch.get_write_enabled(self.conn))
        kill_switch.set_write_enabled(self.conn, False, actor="admin")
        self.assertFalse(kill_switch.get_write_enabled(self.conn))

    def test_kill_switch_overrides_existing_approval(self):
        kill_switch.set_write_enabled(self.conn, True, actor="admin")
        result = make_action(self.conn, actions)
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(
            self.conn, caller_role="human", action_id=result["action_id"],
            approved_by="h1", expected_hash=action["payload_hash"],
        )
        # Emergency: flip the switch off after approval, before execution.
        kill_switch.set_write_enabled(self.conn, False, actor="admin")

        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=result["action_id"], worker_id="w1"
        )
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(outcome["reason"], "writes_disabled")
        # The action itself is untouched (still APPROVED) -- the kill
        # switch check happens before the action row is even read, so it
        # is not marked BLOCKED permanently; flipping writes back on lets
        # it proceed.
        still_approved = actions.get_action(self.conn, result["action_id"])
        self.assertEqual(still_approved["status"], "APPROVED")

    def test_fail_closed_on_corrupt_stored_value(self):
        self.conn.execute(
            "INSERT INTO system_settings (key, value, updated_at) VALUES "
            "('write_enabled', 'not-a-boolean-at-all', '2026-01-01T00:00:00Z')"
        )
        self.conn.commit()
        self.assertFalse(kill_switch.get_write_enabled(self.conn))


if __name__ == "__main__":
    unittest.main()

"""Scenario D: payload/target/account tampering after approval must block
execution with CONTENT_HASH_MISMATCH, never silently execute the changed
content."""
import json
import unittest

from control_center import actions, approvals, executor, kill_switch
from tests.helpers import fresh_conn, make_action


class TestIntegrity(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        kill_switch.set_write_enabled(self.conn, True, actor="test")

    def _approve(self, action_id):
        action = actions.get_action(self.conn, action_id)
        return approvals.approve_action(
            self.conn, caller_role="human", action_id=action_id,
            approved_by="human-1", expected_hash=action["payload_hash"],
        )

    def test_tampered_payload_blocks_execution(self):
        result = make_action(self.conn, actions, payload={"content": "original text"})
        action_id = result["action_id"]
        self._approve(action_id)

        # Simulate tampering: mutate the stored payload directly, bypassing
        # the (deliberately absent) update API. payload_hash column is left
        # stale on purpose -- executor recomputes from payload, not from
        # trusting the stored hash column.
        self.conn.execute(
            "UPDATE actions SET payload_json = ? WHERE id = ?",
            (json.dumps({"content": "TAMPERED: totally different content"}), action_id),
        )
        self.conn.commit()

        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=action_id, worker_id="worker-1"
        )
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(outcome["reason"], "CONTENT_HASH_MISMATCH")

        final = actions.get_action(self.conn, action_id)
        self.assertEqual(final["status"], "BLOCKED")

    def test_tampered_target_blocks_execution(self):
        result = make_action(self.conn, actions, target_id="post-123")
        action_id = result["action_id"]
        self._approve(action_id)

        self.conn.execute("UPDATE actions SET target_id = ? WHERE id = ?", ("post-999", action_id))
        self.conn.commit()

        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=action_id, worker_id="worker-1"
        )
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(outcome["reason"], "CONTENT_HASH_MISMATCH")

    def test_tampered_account_blocks_execution(self):
        result = make_action(self.conn, actions, account_id="acct-real")
        action_id = result["action_id"]
        self._approve(action_id)

        self.conn.execute("UPDATE actions SET account_id = ? WHERE id = ?", ("acct-attacker", action_id))
        self.conn.commit()

        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=action_id, worker_id="worker-1"
        )
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(outcome["reason"], "CONTENT_HASH_MISMATCH")

    def test_untampered_action_executes_fine(self):
        # Control case: proves the hash check isn't just always failing.
        result = make_action(self.conn, actions)
        action_id = result["action_id"]
        self._approve(action_id)
        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=action_id, worker_id="worker-1"
        )
        self.assertEqual(outcome["status"], "EXECUTED")


if __name__ == "__main__":
    unittest.main()

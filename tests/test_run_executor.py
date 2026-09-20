"""Unit tests for run_executor.py's run_once() -- the loop body of the
standalone execution-service process."""
import unittest

from control_center import actions, approvals, kill_switch
from run_executor import run_once
from tests.helpers import fresh_conn, make_action


class TestRunOnce(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        kill_switch.set_write_enabled(self.conn, True, actor="test")

    def _approved_action(self, **overrides):
        result = make_action(self.conn, actions, **overrides)
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(
            self.conn, caller_role="human", action_id=result["action_id"],
            approved_by="h1", expected_hash=action["payload_hash"],
        )
        return result["action_id"]

    def test_processes_all_approved_actions(self):
        id1 = self._approved_action(account_id="acct-1", payload={"content": "post one"})
        id2 = self._approved_action(account_id="acct-2", payload={"content": "post two"})

        n = run_once(self.conn, "worker-test")
        self.assertEqual(n, 2)

        for action_id in (id1, id2):
            final = actions.get_action(self.conn, action_id)
            self.assertEqual(final["status"], "EXECUTED")

    def test_ignores_pending_actions(self):
        make_action(self.conn, actions)  # left PENDING, never approved
        n = run_once(self.conn, "worker-test")
        self.assertEqual(n, 0)

    def test_second_pass_is_a_no_op_for_already_executed(self):
        self._approved_action()
        first = run_once(self.conn, "worker-test")
        second = run_once(self.conn, "worker-test")
        self.assertEqual(first, 1)
        # Nothing is APPROVED anymore (it's EXECUTED now), so the second
        # pass has nothing to iterate over.
        self.assertEqual(second, 0)


if __name__ == "__main__":
    unittest.main()

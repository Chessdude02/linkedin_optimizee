"""Scenario B and the role-separation requirements: agent cannot execute,
agent cannot approve, dashboard cannot execute directly, executor rejects
an unapproved action."""
import unittest

from control_center import actions, approvals, executor
from control_center.exceptions import PermissionDeniedError
from tests.helpers import fresh_conn, make_action


class TestAuthorization(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()

    def test_agent_cannot_execute(self):
        result = make_action(self.conn, actions)
        with self.assertRaises(PermissionDeniedError):
            executor.execute_approved_action(
                self.conn, caller_role="agent", action_id=result["action_id"], worker_id="agent-1"
            )

    def test_agent_cannot_approve(self):
        result = make_action(self.conn, actions)
        action = actions.get_action(self.conn, result["action_id"])
        with self.assertRaises(PermissionDeniedError):
            approvals.approve_action(
                self.conn, caller_role="agent", action_id=result["action_id"],
                approved_by="content-agent", expected_hash=action["payload_hash"],
            )

    def test_dashboard_cannot_execute_directly(self):
        result = make_action(self.conn, actions)
        with self.assertRaises(PermissionDeniedError):
            executor.execute_approved_action(
                self.conn, caller_role="dashboard", action_id=result["action_id"], worker_id="dash-1"
            )

    def test_human_cannot_execute_directly(self):
        result = make_action(self.conn, actions)
        with self.assertRaises(PermissionDeniedError):
            executor.execute_approved_action(
                self.conn, caller_role="human", action_id=result["action_id"], worker_id="human-1"
            )

    def test_executor_rejects_unapproved_action(self):
        result = make_action(self.conn, actions)
        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=result["action_id"], worker_id="worker-1"
        )
        # writes are disabled by default in this test env, so the very
        # first gate (kill switch) is what blocks it -- that is also a
        # correct "did not execute" outcome and is covered separately in
        # test_kill_switch.py. Enable writes here to specifically exercise
        # the "not approved yet" branch.
        from control_center import kill_switch

        kill_switch.set_write_enabled(self.conn, True, actor="test")
        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=result["action_id"], worker_id="worker-1"
        )
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertIn("not_approved", outcome["reason"])

    def test_only_agent_role_can_create_actions(self):
        with self.assertRaises(PermissionDeniedError):
            make_action(self.conn, actions, caller_role="human")
        with self.assertRaises(PermissionDeniedError):
            make_action(self.conn, actions, caller_role="executor")


if __name__ == "__main__":
    unittest.main()

"""Scenario H and general fail-closed behavior: a timeout/unknown result
must never be blindly retried or guessed into success, and a raised
exception must mark the action FAILED, never EXECUTED."""
import unittest
from unittest.mock import patch

from control_center import actions, approvals, executor, kill_switch
from tests.helpers import fresh_conn, make_action


class TestFailureHandling(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        kill_switch.set_write_enabled(self.conn, True, actor="test")

    def _approve(self, action_id):
        action = actions.get_action(self.conn, action_id)
        return approvals.approve_action(
            self.conn, caller_role="human", action_id=action_id,
            approved_by="h1", expected_hash=action["payload_hash"],
        )

    def test_unknown_result_requires_investigation_not_retry(self):
        result = make_action(self.conn, actions)
        action_id = result["action_id"]
        self._approve(action_id)

        with patch.object(executor, "_run_backend", return_value={"result": "UNKNOWN"}):
            outcome = executor.execute_approved_action(
                self.conn, caller_role="executor", action_id=action_id, worker_id="w1"
            )

        self.assertEqual(outcome["status"], "UNKNOWN")
        final = actions.get_action(self.conn, action_id)
        # Deliberately not EXECUTED and not FAILED -- left mid-flight so a
        # human has to look, rather than the system guessing either way.
        self.assertEqual(final["status"], "EXECUTING")

    def test_exception_marks_failed_not_executed(self):
        result = make_action(self.conn, actions)
        action_id = result["action_id"]
        self._approve(action_id)

        with patch.object(executor, "_run_backend", side_effect=RuntimeError("simulated timeout")):
            outcome = executor.execute_approved_action(
                self.conn, caller_role="executor", action_id=action_id, worker_id="w1"
            )

        self.assertEqual(outcome["status"], "FAILED")
        final = actions.get_action(self.conn, action_id)
        self.assertEqual(final["status"], "FAILED")
        self.assertIn("simulated timeout", final["failure_code"])

    def test_real_backend_fails_closed_with_unregistered_account(self):
        # Phase 4/5: real execution is implemented, but it still must fail
        # closed -- an account nobody registered a platform_id for must
        # never fall back to guessing or skipping the check.
        result = make_action(self.conn, actions, account_id="unregistered-account")
        action_id = result["action_id"]
        self._approve(action_id)

        with patch("control_center.executor.settings.MOCK_EXECUTION", False):
            outcome = executor.execute_approved_action(
                self.conn, caller_role="executor", action_id=action_id, worker_id="w1"
            )
        self.assertEqual(outcome["status"], "FAILED")
        self.assertIn("no platform_id registered", outcome["error"].lower())


if __name__ == "__main__":
    unittest.main()

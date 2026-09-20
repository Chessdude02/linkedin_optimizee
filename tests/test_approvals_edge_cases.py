"""Edge cases in the human approval interface not covered elsewhere:
unknown action ids, and executor-side handling of unknown / not-yet-
implemented action types."""
import unittest

from control_center import actions, approvals, executor, kill_switch
from control_center.exceptions import ActionNotFoundError
from tests.helpers import fresh_conn, make_action


class TestApprovalsUnknownAction(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()

    def test_approve_unknown_action_id_raises(self):
        with self.assertRaises(ActionNotFoundError):
            approvals.approve_action(
                self.conn, caller_role="human", action_id="does-not-exist",
                approved_by="h1", expected_hash="irrelevant",
            )

    def test_decline_unknown_action_id_raises(self):
        with self.assertRaises(ActionNotFoundError):
            approvals.decline_action(
                self.conn, caller_role="human", action_id="does-not-exist", declined_by="h1",
            )


class TestExecutorActionTypeHandling(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        kill_switch.set_write_enabled(self.conn, True, actor="test")

    def test_execute_unknown_action_id_raises(self):
        from control_center.exceptions import ActionNotFoundError as ANF

        with self.assertRaises(ANF):
            executor.execute_approved_action(
                self.conn, caller_role="executor", action_id="does-not-exist", worker_id="w1"
            )

    def test_send_message_action_type_is_refused_not_executed(self):
        # SEND_MESSAGE is a valid, requestable, and approvable action type
        # (it has a risk level and can be reviewed/approved), but has no
        # execution backend -- executor must refuse it, not silently
        # succeed or crash.
        result = make_action(
            self.conn, actions, action_type="SEND_MESSAGE",
            payload={"recipient": "someone", "message": "hi"},
        )
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(
            self.conn, caller_role="human", action_id=result["action_id"],
            approved_by="h1", expected_hash=action["payload_hash"],
        )
        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=result["action_id"], worker_id="w1"
        )
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertIn("not_implemented", outcome["reason"])
        final = actions.get_action(self.conn, result["action_id"])
        self.assertEqual(final["status"], "BLOCKED")

    def test_modify_profile_action_type_is_refused_not_executed(self):
        result = make_action(
            self.conn, actions, action_type="MODIFY_PROFILE",
            payload={"field": "headline", "value": "New headline"},
        )
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(
            self.conn, caller_role="human", action_id=result["action_id"],
            approved_by="h1", expected_hash=action["payload_hash"],
        )
        outcome = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=result["action_id"], worker_id="w1"
        )
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertIn("not_implemented", outcome["reason"])


if __name__ == "__main__":
    unittest.main()

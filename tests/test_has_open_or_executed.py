import unittest

from control_center import actions, approvals, executor, kill_switch
from tests.helpers import fresh_conn, make_action


class TestHasOpenOrExecuted(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()

    def test_false_when_nothing_exists(self):
        self.assertFalse(
            actions.has_open_or_executed(self.conn, target_id="urn:li:activity:1", action_type="CREATE_REACTION")
        )

    def test_true_for_pending(self):
        make_action(self.conn, actions, action_type="CREATE_REACTION", target_id="urn:li:activity:1",
                    payload={"reaction_type": "LIKE"})
        self.assertTrue(
            actions.has_open_or_executed(self.conn, target_id="urn:li:activity:1", action_type="CREATE_REACTION")
        )

    def test_false_for_different_action_type_same_target(self):
        make_action(self.conn, actions, action_type="CREATE_REACTION", target_id="urn:li:activity:1",
                    payload={"reaction_type": "LIKE"})
        self.assertFalse(
            actions.has_open_or_executed(self.conn, target_id="urn:li:activity:1", action_type="CREATE_COMMENT")
        )

    def test_false_after_decline(self):
        result = make_action(self.conn, actions, action_type="CREATE_REACTION", target_id="urn:li:activity:1",
                              payload={"reaction_type": "LIKE"})
        approvals.decline_action(self.conn, caller_role="human", action_id=result["action_id"], declined_by="h1")
        self.assertFalse(
            actions.has_open_or_executed(self.conn, target_id="urn:li:activity:1", action_type="CREATE_REACTION")
        )

    def test_true_after_execution(self):
        kill_switch.set_write_enabled(self.conn, True, actor="test")
        result = make_action(self.conn, actions, action_type="CREATE_REACTION", target_id="urn:li:activity:1",
                              payload={"reaction_type": "LIKE"})
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(self.conn, caller_role="human", action_id=result["action_id"],
                                  approved_by="h1", expected_hash=action["payload_hash"])
        executor.execute_approved_action(self.conn, caller_role="executor",
                                          action_id=result["action_id"], worker_id="w1")
        self.assertTrue(
            actions.has_open_or_executed(self.conn, target_id="urn:li:activity:1", action_type="CREATE_REACTION")
        )


if __name__ == "__main__":
    unittest.main()

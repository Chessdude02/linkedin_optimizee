"""End-to-end test of the real execution path through executor.py:
register an account's platform_id, approve an action, execute it with
MOCK_EXECUTION off and the network mocked -- proving the full wiring
(executor -> accounts -> backends.publora) works together, not just each
piece in isolation."""
import os
import unittest
from unittest.mock import MagicMock, patch

from control_center import accounts, actions, approvals, executor, kill_switch
from tests.helpers import fresh_conn, make_action


class TestRealExecutionIntegration(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()
        kill_switch.set_write_enabled(self.conn, True, actor="test")
        accounts.register_account(self.conn, "vedant-linkedin", "Vedant", "linkedin-P0IF-kpN1N")

    def test_full_flow_with_mocked_network(self):
        result = make_action(
            self.conn, actions, account_id="vedant-linkedin",
            payload={"content": "Real path, mocked network"},
        )
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(
            self.conn, caller_role="human", action_id=result["action_id"],
            approved_by="vedant", expected_hash=action["payload_hash"],
        )

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"postGroupId": "pg_real_001"}
        fake_session = MagicMock()
        fake_session.post.return_value = fake_response

        with patch.dict(os.environ, {"PUBLORA_API_KEY": "sk_test_not_real"}):
            with patch("control_center.executor.settings.MOCK_EXECUTION", False):
                with patch("control_center.backends.publora._session", return_value=fake_session):
                    outcome = executor.execute_approved_action(
                        self.conn, caller_role="executor",
                        action_id=result["action_id"], worker_id="worker-1",
                    )

        self.assertEqual(outcome, {"status": "EXECUTED", "external_id": "pg_real_001"})
        final = actions.get_action(self.conn, result["action_id"])
        self.assertEqual(final["status"], "EXECUTED")
        self.assertEqual(final["external_id"], "pg_real_001")

        # The platform_id actually used came from the account registry,
        # not hardcoded or guessed.
        _, kwargs = fake_session.post.call_args
        self.assertEqual(kwargs["json"]["platforms"], ["linkedin-P0IF-kpN1N"])

    def test_missing_credential_fails_closed(self):
        result = make_action(self.conn, actions, account_id="vedant-linkedin")
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(
            self.conn, caller_role="human", action_id=result["action_id"],
            approved_by="vedant", expected_hash=action["payload_hash"],
        )

        env = dict(os.environ)
        env.pop("PUBLORA_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("control_center.executor.settings.MOCK_EXECUTION", False):
                outcome = executor.execute_approved_action(
                    self.conn, caller_role="executor",
                    action_id=result["action_id"], worker_id="worker-1",
                )
        self.assertEqual(outcome["status"], "FAILED")
        self.assertIn("PUBLORA_API_KEY", outcome["error"])
        final = actions.get_action(self.conn, result["action_id"])
        self.assertEqual(final["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()

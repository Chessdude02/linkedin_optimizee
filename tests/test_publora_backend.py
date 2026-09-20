"""Unit tests for the real (Publora-backed) execution backend.

No real network call is ever made here -- `_session()` is patched to
return a MagicMock, so these tests exercise the request-building and
response-handling logic in isolation, the way the equivalent tests in
sergebulaev/linkedin-skills test lib/publora_client.py.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from control_center.backends import publora

PLATFORM_ID = "linkedin-P0IF-kpN1N"


def _fake_response(status_code: int, json_body: dict | None = None, text: str = ""):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("no json body")
    return resp


class TestApiKeyIsolation(unittest.TestCase):
    def test_missing_api_key_raises_before_any_request(self):
        env = dict(os.environ)
        env.pop("PUBLORA_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(publora.PubloraBackendError) as ctx:
                publora.run(
                    {"action_type": "CREATE_POST", "target_id": None, "payload": {"content": "hi"}},
                    PLATFORM_ID,
                )
            self.assertIn("PUBLORA_API_KEY", str(ctx.exception))


class TestPubloraBackendRun(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {"PUBLORA_API_KEY": "sk_test_not_real"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _patched_session(self, mock_session):
        return patch("control_center.backends.publora._session", return_value=mock_session)

    def test_create_post_success(self):
        session = MagicMock()
        session.post.return_value = _fake_response(200, {"postGroupId": "pg_123"})
        with self._patched_session(session):
            result = publora.run(
                {"action_type": "CREATE_POST", "target_id": None, "payload": {"content": "Hello LinkedIn"}},
                PLATFORM_ID,
            )
        self.assertEqual(result, {"result": "SUCCESS", "external_id": "pg_123"})
        called_url, called_kwargs = session.post.call_args
        self.assertIn("/create-post", called_url[0])
        self.assertEqual(called_kwargs["json"]["content"], "Hello LinkedIn")
        self.assertEqual(called_kwargs["json"]["platforms"], [PLATFORM_ID])

    def test_scheduled_post_includes_scheduled_time(self):
        session = MagicMock()
        session.post.return_value = _fake_response(200, {"postGroupId": "pg_456"})
        with self._patched_session(session):
            publora.run(
                {
                    "action_type": "SCHEDULE_POST",
                    "target_id": None,
                    "payload": {"content": "later", "scheduled_time": "2026-01-01T12:00:00Z"},
                },
                PLATFORM_ID,
            )
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["json"]["scheduledTime"], "2026-01-01T12:00:00Z")

    def test_create_comment_success(self):
        session = MagicMock()
        session.post.return_value = _fake_response(200, {"comment": {"id": "c_1"}})
        with self._patched_session(session):
            result = publora.run(
                {
                    "action_type": "CREATE_COMMENT",
                    "target_id": "urn:li:activity:123",
                    "payload": {"message": "nice post"},
                },
                PLATFORM_ID,
            )
        self.assertEqual(result, {"result": "SUCCESS", "external_id": "c_1"})
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["json"]["postedId"], "urn:li:activity:123")
        self.assertNotIn("parentComment", kwargs["json"])

    def test_create_reply_includes_parent_comment(self):
        session = MagicMock()
        session.post.return_value = _fake_response(200, {"comment": {"id": "c_2"}})
        with self._patched_session(session):
            publora.run(
                {
                    "action_type": "CREATE_REPLY",
                    "target_id": "urn:li:activity:123",
                    "payload": {"message": "thanks!", "parent_comment": "urn:li:comment:(...)"},
                },
                PLATFORM_ID,
            )
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["json"]["parentComment"], "urn:li:comment:(...)")

    def test_reaction_type_alias_applied(self):
        session = MagicMock()
        session.post.return_value = _fake_response(200, {})
        with self._patched_session(session):
            publora.run(
                {
                    "action_type": "CREATE_REACTION",
                    "target_id": "urn:li:activity:123",
                    "payload": {"reaction_type": "insightful"},
                },
                PLATFORM_ID,
            )
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["json"]["reactionType"], "INTEREST")  # aliased, not raw

    def test_reshare_success(self):
        session = MagicMock()
        session.post.return_value = _fake_response(200, {"reshare": {"id": "urn:li:share:999"}})
        with self._patched_session(session):
            result = publora.run(
                {
                    "action_type": "RESHARE_POST",
                    "target_id": "urn:li:share:123",
                    "payload": {"commentary": "worth reading"},
                },
                PLATFORM_ID,
            )
        self.assertEqual(result["external_id"], "urn:li:share:999")

    def test_delete_post_success(self):
        session = MagicMock()
        session.delete.return_value = _fake_response(200, {})
        with self._patched_session(session):
            result = publora.run(
                {"action_type": "DELETE_POST", "target_id": "pg_123", "payload": {}}, PLATFORM_ID
            )
        self.assertEqual(result, {"result": "SUCCESS", "external_id": "pg_123"})
        called_url = session.delete.call_args[0][0]
        self.assertIn("/delete-post/pg_123", called_url)

    def test_delete_comment_success(self):
        session = MagicMock()
        session.delete.return_value = _fake_response(200, {})
        with self._patched_session(session):
            result = publora.run(
                {
                    "action_type": "DELETE_COMMENT",
                    "target_id": "urn:li:activity:123",
                    "payload": {"comment_id": "c_9"},
                },
                PLATFORM_ID,
            )
        self.assertEqual(result, {"result": "SUCCESS", "external_id": "c_9"})

    def test_http_error_raises_backend_error(self):
        session = MagicMock()
        session.post.return_value = _fake_response(400, {"error": "Invalid platform ID format"})
        with self._patched_session(session):
            with self.assertRaises(publora.PubloraBackendError) as ctx:
                publora.run(
                    {"action_type": "CREATE_POST", "target_id": None, "payload": {"content": "hi"}},
                    PLATFORM_ID,
                )
        self.assertIn("HTTP 400", str(ctx.exception))

    def test_timeout_returns_unknown_not_raise(self):
        session = MagicMock()
        session.post.side_effect = requests.Timeout("simulated timeout")
        with self._patched_session(session):
            result = publora.run(
                {"action_type": "CREATE_POST", "target_id": None, "payload": {"content": "hi"}},
                PLATFORM_ID,
            )
        self.assertEqual(result["result"], "UNKNOWN")
        self.assertIn("timeout", result["reason"])

    def test_connection_error_returns_unknown_not_raise(self):
        session = MagicMock()
        session.post.side_effect = requests.ConnectionError("simulated connection reset")
        with self._patched_session(session):
            result = publora.run(
                {"action_type": "CREATE_POST", "target_id": None, "payload": {"content": "hi"}},
                PLATFORM_ID,
            )
        self.assertEqual(result["result"], "UNKNOWN")
        self.assertIn("connection_error", result["reason"])

    def test_unimplemented_action_type_raises(self):
        session = MagicMock()
        with self._patched_session(session):
            with self.assertRaises(publora.PubloraBackendError):
                publora.run(
                    {"action_type": "SEND_MESSAGE", "target_id": None, "payload": {}}, PLATFORM_ID
                )


if __name__ == "__main__":
    unittest.main()

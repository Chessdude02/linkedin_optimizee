"""Section 62: WRITE_ENABLED=true + APPROVAL_REQUIRED=false must never be
supported. Also: audit log must never store a value under a secret-shaped
key verbatim."""
import importlib
import os
import unittest

from control_center import audit
from tests.helpers import fresh_conn


class TestUnsafeConfigRefused(unittest.TestCase):
    def test_write_enabled_without_approval_required_refuses_to_load(self):
        env = dict(os.environ)
        env["WRITE_ENABLED"] = "true"
        env["APPROVAL_REQUIRED"] = "false"
        old = dict(os.environ)
        os.environ.update(env)
        try:
            import control_center.settings as settings_mod

            with self.assertRaises(RuntimeError):
                importlib.reload(settings_mod)
        finally:
            os.environ.clear()
            os.environ.update(old)
            importlib.reload(settings_mod)  # restore normal state for other tests


class TestAuditLogSecretScrubbing(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()

    def test_secret_shaped_keys_are_redacted(self):
        audit.log_event(
            self.conn, "TEST_EVENT",
            details={
                "publora_api_key": "sk_should_never_appear",
                "apify_token": "apify_api_should_never_appear",
                "authorization": "Bearer should_never_appear",
                "safe_field": "this is fine to keep",
            },
        )
        rows = audit.list_events(self.conn, event_type="TEST_EVENT")
        self.assertEqual(len(rows), 1)
        blob = rows[0]["details_json"]
        self.assertNotIn("sk_should_never_appear", blob)
        self.assertNotIn("apify_api_should_never_appear", blob)
        self.assertNotIn("should_never_appear", blob.replace("Bearer", ""))
        self.assertIn("this is fine to keep", blob)


if __name__ == "__main__":
    unittest.main()

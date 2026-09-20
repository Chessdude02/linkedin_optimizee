"""Direct unit tests for the audit log: filtering, ordering, append-only
behaviour, and secret scrubbing (scrubbing already covered in
test_settings_and_secrets.py; this file covers query behaviour)."""
import time
import unittest

from control_center import audit
from tests.helpers import fresh_conn


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()

    def test_log_event_returns_a_row_id_and_persists(self):
        row_id = audit.log_event(self.conn, "ACTION_CREATED", action_id="a1", actor_role="agent", actor_id="agent-1")
        rows = audit.list_events(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], row_id)
        self.assertEqual(rows[0]["event_type"], "ACTION_CREATED")

    def test_filter_by_action_id(self):
        audit.log_event(self.conn, "ACTION_CREATED", action_id="a1")
        audit.log_event(self.conn, "ACTION_CREATED", action_id="a2")
        rows = audit.list_events(self.conn, action_id="a1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_id"], "a1")

    def test_filter_by_event_type(self):
        audit.log_event(self.conn, "ACTION_CREATED", action_id="a1")
        audit.log_event(self.conn, "ACTION_APPROVED", action_id="a1")
        rows = audit.list_events(self.conn, event_type="ACTION_APPROVED")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "ACTION_APPROVED")

    def test_filter_by_both(self):
        audit.log_event(self.conn, "ACTION_CREATED", action_id="a1")
        audit.log_event(self.conn, "ACTION_CREATED", action_id="a2")
        audit.log_event(self.conn, "ACTION_APPROVED", action_id="a1")
        rows = audit.list_events(self.conn, action_id="a1", event_type="ACTION_CREATED")
        self.assertEqual(len(rows), 1)

    def test_no_filters_returns_everything_up_to_limit(self):
        for i in range(5):
            audit.log_event(self.conn, "EVENT", action_id=f"a{i}")
        rows = audit.list_events(self.conn, limit=3)
        self.assertEqual(len(rows), 3)

    def test_most_recent_first(self):
        audit.log_event(self.conn, "FIRST")
        time.sleep(0.01)
        audit.log_event(self.conn, "SECOND")
        rows = audit.list_events(self.conn)
        self.assertEqual(rows[0]["event_type"], "SECOND")
        self.assertEqual(rows[1]["event_type"], "FIRST")

    def test_details_none_defaults_to_empty_object(self):
        audit.log_event(self.conn, "EVENT")
        rows = audit.list_events(self.conn)
        self.assertEqual(rows[0]["details_json"], "{}")


if __name__ == "__main__":
    unittest.main()

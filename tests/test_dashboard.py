"""Dashboard security tests: authentication, CSRF, role separation, and
the structural claim that the dashboard cannot execute anything.
"""
from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("DASHBOARD_SECRET_KEY", "test-secret-key-not-for-real-use")
os.environ.setdefault("DASHBOARD_USERNAME", "vedant")
# password: "correct-horse-battery" hashed at import time below instead of
# hardcoding a hash here, so the test doesn't silently rot if the hashing
# scheme changes.

from dashboard.app import create_app  # noqa: E402
from dashboard.security import hash_password, login_rate_limiter  # noqa: E402
from control_center import actions, approvals, db, kill_switch  # noqa: E402
from tests.helpers import make_action  # noqa: E402

TEST_PASSWORD = "correct-horse-battery-staple"
os.environ["DASHBOARD_PASSWORD_HASH"] = hash_password(TEST_PASSWORD)

_CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def _extract_csrf(html: str) -> str:
    m = _CSRF_RE.search(html)
    assert m, "no csrf token found in page"
    return m.group(1)


class DashboardTestCase(unittest.TestCase):
    def setUp(self):
        login_rate_limiter.reset()
        self.db_path = ":memory:"
        # Flask's dev server model doesn't share :memory: across requests in
        # the test client the way a real deployment would with a file-backed
        # DB, but Flask's test client reuses the same app/thread per test
        # method, and sqlite3 :memory: is per-connection anyway -- so we use
        # a real temp file to behave like production.
        import tempfile

        fd, self.db_file = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = db.get_connection(self.db_file)
        db.init_db(conn)
        conn.close()

        self.app = create_app(db_path=self.db_file)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        os.remove(self.db_file)
        for suffix in ("-wal", "-shm"):
            p = self.db_file + suffix
            if os.path.exists(p):
                os.remove(p)

    def _login(self):
        page = self.client.get("/login")
        token = _extract_csrf(page.get_data(as_text=True))
        return self.client.post(
            "/login",
            data={"username": "vedant", "password": TEST_PASSWORD, "csrf_token": token},
            follow_redirects=False,
        )

    # -- authentication --------------------------------------------------

    def test_unauthenticated_root_redirects_to_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_correct_login_redirects_to_dashboard(self):
        resp = self._login()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/", resp.headers["Location"])

    def test_wrong_password_rejected(self):
        page = self.client.get("/login")
        token = _extract_csrf(page.get_data(as_text=True))
        resp = self.client.post(
            "/login", data={"username": "vedant", "password": "wrong", "csrf_token": token}
        )
        self.assertEqual(resp.status_code, 401)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            page = self.client.get("/login")
            token = _extract_csrf(page.get_data(as_text=True))
            self.client.post(
                "/login", data={"username": "vedant", "password": "wrong", "csrf_token": token}
            )
        page = self.client.get("/login")
        token = _extract_csrf(page.get_data(as_text=True))
        resp = self.client.post(
            "/login", data={"username": "vedant", "password": TEST_PASSWORD, "csrf_token": token}
        )
        self.assertEqual(resp.status_code, 429)  # locked out, even with the right password

    # -- CSRF --------------------------------------------------------------

    def test_approve_without_csrf_token_is_refused(self):
        self._login()
        conn = db.get_connection(self.db_file)
        result = make_action(conn, actions)
        conn.close()

        resp = self.client.post(f"/actions/{result['action_id']}/approve", data={"expected_hash": "whatever"})
        self.assertEqual(resp.status_code, 403)

        conn = db.get_connection(self.db_file)
        action = actions.get_action(conn, result["action_id"])
        conn.close()
        self.assertEqual(action["status"], "PENDING")  # nothing happened

    # -- approve / decline flow --------------------------------------------

    def test_approve_with_correct_hash_transitions_to_approved(self):
        self._login()
        conn = db.get_connection(self.db_file)
        result = make_action(conn, actions)
        action = actions.get_action(conn, result["action_id"])
        conn.close()

        page = self.client.get(f"/actions/{result['action_id']}")
        token = _extract_csrf(page.get_data(as_text=True))
        resp = self.client.post(
            f"/actions/{result['action_id']}/approve",
            data={"csrf_token": token, "expected_hash": action["payload_hash"]},
        )
        self.assertEqual(resp.status_code, 302)

        conn = db.get_connection(self.db_file)
        final = actions.get_action(conn, result["action_id"])
        conn.close()
        self.assertEqual(final["status"], "APPROVED")

    def test_approve_with_wrong_hash_is_refused(self):
        self._login()
        conn = db.get_connection(self.db_file)
        result = make_action(conn, actions)
        conn.close()

        page = self.client.get(f"/actions/{result['action_id']}")
        token = _extract_csrf(page.get_data(as_text=True))
        self.client.post(
            f"/actions/{result['action_id']}/approve",
            data={"csrf_token": token, "expected_hash": "0" * 64},
        )

        conn = db.get_connection(self.db_file)
        final = actions.get_action(conn, result["action_id"])
        conn.close()
        self.assertEqual(final["status"], "PENDING")  # refused, not silently approved

    def test_decline_transitions_to_declined(self):
        self._login()
        conn = db.get_connection(self.db_file)
        result = make_action(conn, actions)
        conn.close()

        page = self.client.get(f"/actions/{result['action_id']}")
        token = _extract_csrf(page.get_data(as_text=True))
        self.client.post(f"/actions/{result['action_id']}/decline", data={"csrf_token": token})

        conn = db.get_connection(self.db_file)
        final = actions.get_action(conn, result["action_id"])
        conn.close()
        self.assertEqual(final["status"], "DECLINED")

    # -- kill switch ---------------------------------------------------

    def test_kill_switch_toggle_requires_login_and_csrf(self):
        resp = self.client.post("/system/write-enabled", data={"enabled": "true"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

        self._login()
        resp = self.client.post("/system/write-enabled", data={"enabled": "true"})
        self.assertEqual(resp.status_code, 403)  # no csrf token

        page = self.client.get("/system")
        token = _extract_csrf(page.get_data(as_text=True))
        self.client.post("/system/write-enabled", data={"csrf_token": token, "enabled": "true"})

        conn = db.get_connection(self.db_file)
        self.assertTrue(kill_switch.get_write_enabled(conn))
        conn.close()

    # -- structural: dashboard has no execution path at all ---------------

    def test_dashboard_has_no_execute_route(self):
        rules = [str(rule) for rule in self.app.url_map.iter_rules()]
        for rule in rules:
            self.assertNotIn("execute", rule.lower())

    def test_dashboard_module_never_imports_executor(self):
        import dashboard.app as app_module
        import dashboard.routes.pending as pending_module

        self.assertNotIn("executor", dir(app_module))
        self.assertNotIn("executor", dir(pending_module))


if __name__ == "__main__":
    unittest.main()

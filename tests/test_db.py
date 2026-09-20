"""Direct unit test that the schema actually creates the 8 required
tables, and that init_db is idempotent (safe to call repeatedly)."""
import unittest

from control_center import db


class TestDb(unittest.TestCase):
    def test_all_required_tables_exist(self):
        conn = db.get_connection(":memory:")
        db.init_db(conn)
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r["name"] for r in rows}
        required = {
            "users", "agents", "accounts", "actions", "approvals",
            "executions", "audit_logs", "system_settings",
        }
        self.assertTrue(required.issubset(names), f"missing: {required - names}")
        conn.close()

    def test_init_db_is_idempotent(self):
        conn = db.get_connection(":memory:")
        db.init_db(conn)
        db.init_db(conn)  # must not raise
        conn.close()


if __name__ == "__main__":
    unittest.main()

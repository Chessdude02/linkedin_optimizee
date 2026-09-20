"""Scenario F (concurrent execution -> exactly one wins) plus duplicate
request detection and exactly-once re-execution safety."""
import threading
import unittest

from control_center import actions, approvals, db, executor, kill_switch
from control_center.exceptions import DuplicateActionError
from tests.helpers import make_action


class TestDuplicateRequests(unittest.TestCase):
    def setUp(self):
        import sqlite3
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        db.init_db(self.conn)

    def test_identical_pending_request_is_rejected(self):
        make_action(self.conn, actions, account_id="acct-1", payload={"content": "same text"})
        with self.assertRaises(DuplicateActionError):
            make_action(self.conn, actions, account_id="acct-1", payload={"content": "same text"})

    def test_same_content_different_account_is_allowed(self):
        make_action(self.conn, actions, account_id="acct-1", payload={"content": "same text"})
        # Should not raise: different account, not a duplicate.
        make_action(self.conn, actions, account_id="acct-2", payload={"content": "same text"})

    def test_cannot_execute_same_action_twice(self):
        kill_switch.set_write_enabled(self.conn, True, actor="test")
        result = make_action(self.conn, actions, account_id="acct-1")
        action = actions.get_action(self.conn, result["action_id"])
        approvals.approve_action(
            self.conn, caller_role="human", action_id=result["action_id"],
            approved_by="h1", expected_hash=action["payload_hash"],
        )
        first = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=result["action_id"], worker_id="w1"
        )
        second = executor.execute_approved_action(
            self.conn, caller_role="executor", action_id=result["action_id"], worker_id="w1"
        )
        self.assertEqual(first["status"], "EXECUTED")
        self.assertEqual(second["status"], "EXECUTED")
        self.assertEqual(second["reason"], "already_executed")
        self.assertEqual(first["external_id"], second["external_id"])


class TestConcurrentExecution(unittest.TestCase):
    def test_two_workers_racing_only_one_executes(self):
        import os
        import tempfile

        # File-backed DB (not :memory:) so two independent connections in
        # two threads actually share state the way two real worker
        # processes would.
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            setup_conn = db.get_connection(path)
            db.init_db(setup_conn)
            kill_switch.set_write_enabled(setup_conn, True, actor="test")
            result = make_action(setup_conn, actions, account_id="acct-race")
            action = actions.get_action(setup_conn, result["action_id"])
            approvals.approve_action(
                setup_conn, caller_role="human", action_id=result["action_id"],
                approved_by="h1", expected_hash=action["payload_hash"],
            )
            setup_conn.close()

            outcomes: list[dict] = []
            barrier = threading.Barrier(2)

            def worker(worker_id: str):
                conn = db.get_connection(path)
                barrier.wait()
                outcome = executor.execute_approved_action(
                    conn, caller_role="executor", action_id=result["action_id"], worker_id=worker_id
                )
                outcomes.append(outcome)
                conn.close()

            threads = [
                threading.Thread(target=worker, args=("worker-A",)),
                threading.Thread(target=worker, args=("worker-B",)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            statuses = sorted(o["status"] for o in outcomes)
            # Exactly one EXECUTED, the other REJECTED as already claimed.
            self.assertEqual(statuses, ["EXECUTED", "REJECTED"])

            final_conn = db.get_connection(path)
            final = actions.get_action(final_conn, result["action_id"])
            self.assertEqual(final["status"], "EXECUTED")
            final_conn.close()
        finally:
            os.remove(path)
            wal = path + "-wal"
            shm = path + "-shm"
            for p in (wal, shm):
                if os.path.exists(p):
                    os.remove(p)


if __name__ == "__main__":
    unittest.main()

import unittest

from control_center import watchlist
from tests.helpers import fresh_conn


class TestWatchlist(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()

    def test_add_and_list(self):
        watchlist.add_target(self.conn, "https://linkedin.com/posts/x", "acct-1", "label")
        targets = watchlist.list_targets(self.conn)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["post_url"], "https://linkedin.com/posts/x")
        self.assertEqual(targets[0]["label"], "label")
        self.assertEqual(targets[0]["last_comment_count"], 0)
        self.assertIsNone(targets[0]["last_checked_at"])

    def test_adding_same_url_twice_is_idempotent(self):
        id1 = watchlist.add_target(self.conn, "https://linkedin.com/posts/x", "acct-1")
        id2 = watchlist.add_target(self.conn, "https://linkedin.com/posts/x", "acct-1")
        self.assertEqual(id1, id2)
        self.assertEqual(len(watchlist.list_targets(self.conn)), 1)

    def test_record_check_updates_state(self):
        target_id = watchlist.add_target(self.conn, "https://linkedin.com/posts/x", "acct-1")
        watchlist.record_check(self.conn, target_id, 5)
        target = watchlist.list_targets(self.conn)[0]
        self.assertEqual(target["last_comment_count"], 5)
        self.assertIsNotNone(target["last_checked_at"])

    def test_remove_target(self):
        target_id = watchlist.add_target(self.conn, "https://linkedin.com/posts/x", "acct-1")
        watchlist.remove_target(self.conn, target_id)
        self.assertEqual(watchlist.list_targets(self.conn), [])


if __name__ == "__main__":
    unittest.main()

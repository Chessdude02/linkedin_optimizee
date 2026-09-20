"""Direct unit tests for the account registry."""
import unittest

from control_center import accounts
from tests.helpers import fresh_conn


class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_conn()

    def test_unregistered_account_has_no_platform_id(self):
        self.assertIsNone(accounts.get_platform_id(self.conn, "never-registered"))

    def test_register_then_look_up(self):
        accounts.register_account(self.conn, "vedant-linkedin", "Vedant", "linkedin-P0IF-kpN1N")
        self.assertEqual(accounts.get_platform_id(self.conn, "vedant-linkedin"), "linkedin-P0IF-kpN1N")

    def test_re_registering_updates_platform_id(self):
        accounts.register_account(self.conn, "acct-1", "Old name", "linkedin-OLD")
        accounts.register_account(self.conn, "acct-1", "New name", "linkedin-NEW")
        self.assertEqual(accounts.get_platform_id(self.conn, "acct-1"), "linkedin-NEW")
        rows = accounts.list_accounts(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["display_name"], "New name")


if __name__ == "__main__":
    unittest.main()

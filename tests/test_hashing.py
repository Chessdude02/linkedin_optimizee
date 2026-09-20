"""Direct unit tests for canonical_payload_hash -- deterministic, and
sensitive to every execution-relevant field."""
import unittest

from control_center.hashing import canonical_payload_hash


class TestHashing(unittest.TestCase):
    def test_same_inputs_produce_same_hash(self):
        h1 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"content": "hi"})
        h2 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"content": "hi"})
        self.assertEqual(h1, h2)

    def test_key_order_in_payload_does_not_matter(self):
        h1 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"a": 1, "b": 2})
        h2 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"b": 2, "a": 1})
        self.assertEqual(h1, h2)

    def test_different_action_type_changes_hash(self):
        h1 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"content": "hi"})
        h2 = canonical_payload_hash("CREATE_COMMENT", "acct-1", None, {"content": "hi"})
        self.assertNotEqual(h1, h2)

    def test_different_account_changes_hash(self):
        h1 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"content": "hi"})
        h2 = canonical_payload_hash("CREATE_POST", "acct-2", None, {"content": "hi"})
        self.assertNotEqual(h1, h2)

    def test_different_target_changes_hash(self):
        h1 = canonical_payload_hash("CREATE_COMMENT", "acct-1", "post-1", {"content": "hi"})
        h2 = canonical_payload_hash("CREATE_COMMENT", "acct-1", "post-2", {"content": "hi"})
        self.assertNotEqual(h1, h2)

    def test_different_payload_value_changes_hash(self):
        h1 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"content": "hi"})
        h2 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"content": "bye"})
        self.assertNotEqual(h1, h2)

    def test_different_schedule_changes_hash(self):
        h1 = canonical_payload_hash("CREATE_POST", "acct-1", None, {"content": "hi"}, schedule=None)
        h2 = canonical_payload_hash(
            "CREATE_POST", "acct-1", None, {"content": "hi"}, schedule="2026-01-01T00:00:00Z"
        )
        self.assertNotEqual(h1, h2)

    def test_hash_is_hex_sha256_length(self):
        h = canonical_payload_hash("CREATE_POST", "acct-1", None, {"content": "hi"})
        self.assertEqual(len(h), 64)
        int(h, 16)  # raises if not valid hex


if __name__ == "__main__":
    unittest.main()

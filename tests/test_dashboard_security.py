"""Direct unit tests for password hashing and the login rate limiter,
isolated from Flask/HTTP (test_dashboard.py covers the HTTP-level
behaviour; this file covers the underlying primitives)."""
import time
import unittest

from dashboard.security import LoginRateLimiter, hash_password, verify_password


class TestPasswordHashing(unittest.TestCase):
    def test_correct_password_verifies(self):
        stored = hash_password("correct horse battery staple")
        self.assertTrue(verify_password("correct horse battery staple", stored))

    def test_wrong_password_fails(self):
        stored = hash_password("correct horse battery staple")
        self.assertFalse(verify_password("wrong password", stored))

    def test_two_hashes_of_the_same_password_differ(self):
        # Different random salt each time.
        h1 = hash_password("same password")
        h2 = hash_password("same password")
        self.assertNotEqual(h1, h2)
        self.assertTrue(verify_password("same password", h1))
        self.assertTrue(verify_password("same password", h2))

    def test_malformed_stored_hash_fails_closed(self):
        for bogus in ("", "not-a-hash-at-all", "scrypt$only$three$fields", "md5$deadbeef$deadbeef"):
            self.assertFalse(verify_password("anything", bogus))

    def test_hash_has_expected_shape(self):
        h = hash_password("whatever password")
        parts = h.split("$")
        self.assertEqual(len(parts), 6)
        self.assertEqual(parts[0], "scrypt")


class TestLoginRateLimiter(unittest.TestCase):
    def setUp(self):
        self.limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=60)

    def test_not_locked_initially(self):
        self.assertFalse(self.limiter.is_locked("user1"))

    def test_locks_after_max_attempts(self):
        for _ in range(3):
            self.limiter.record_failure("user1")
        self.assertTrue(self.limiter.is_locked("user1"))

    def test_below_threshold_not_locked(self):
        for _ in range(2):
            self.limiter.record_failure("user1")
        self.assertFalse(self.limiter.is_locked("user1"))

    def test_success_clears_failures(self):
        for _ in range(2):
            self.limiter.record_failure("user1")
        self.limiter.record_success("user1")
        self.limiter.record_failure("user1")
        self.assertFalse(self.limiter.is_locked("user1"))  # only 1 recorded after reset

    def test_lockout_expires(self):
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, lockout_seconds=0.05)
        limiter.record_failure("user1")
        limiter.record_failure("user1")
        self.assertTrue(limiter.is_locked("user1"))
        time.sleep(0.1)
        self.assertFalse(limiter.is_locked("user1"))

    def test_lockout_is_per_key(self):
        for _ in range(3):
            self.limiter.record_failure("user1")
        self.assertTrue(self.limiter.is_locked("user1"))
        self.assertFalse(self.limiter.is_locked("user2"))


if __name__ == "__main__":
    unittest.main()

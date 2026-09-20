"""Password hashing and login rate limiting.

Password hashing uses hashlib.scrypt: stdlib, no extra dependency, and a
memory-hard KDF appropriate for password storage (unlike a fast hash such
as sha256 on its own).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_DKLEN = 32


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Never raises on malformed `stored` -- a corrupt hash just fails
    verification, matching the project's fail-closed rule."""
    try:
        algo, n_s, r_s, p_s, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
    return hmac.compare_digest(derived, expected)


class LoginRateLimiter:
    """In-memory lockout after too many failed attempts in a window.

    Single-process only -- a real multi-worker deployment needs a shared
    store (Redis, the database itself) for this to hold across workers.
    Documented limitation, not a claim of distributed correctness.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, lockout_seconds: int = 300):
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._lock = threading.Lock()
        self._attempts: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def is_locked(self, key: str) -> bool:
        with self._lock:
            until = self._locked_until.get(key)
            if until is None:
                return False
            if time.time() >= until:
                del self._locked_until[key]
                self._attempts.pop(key, None)
                return False
            return True

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.time()
            attempts = [t for t in self._attempts.get(key, []) if now - t < self._window]
            attempts.append(now)
            self._attempts[key] = attempts
            if len(attempts) >= self._max_attempts:
                self._locked_until[key] = now + self._lockout

    def record_success(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self) -> None:
        """Test-only helper to clear all state between test cases."""
        with self._lock:
            self._attempts.clear()
            self._locked_until.clear()


login_rate_limiter = LoginRateLimiter()

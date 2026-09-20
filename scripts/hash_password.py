#!/usr/bin/env python3
"""Generate a DASHBOARD_PASSWORD_HASH value. Never prints the plaintext
password, never logs it, never writes it to a file -- just prints the
hash for you to paste into .env yourself.

Usage: python3 scripts/hash_password.py
"""
import getpass
import sys

sys.path.insert(0, ".")

from dashboard.security import hash_password  # noqa: E402


def main() -> None:
    password = getpass.getpass("New dashboard password: ")
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        print("Passwords did not match.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < 12:
        print("Refusing a password shorter than 12 characters.", file=sys.stderr)
        raise SystemExit(1)
    print("\nDASHBOARD_PASSWORD_HASH=" + hash_password(password))


if __name__ == "__main__":
    main()

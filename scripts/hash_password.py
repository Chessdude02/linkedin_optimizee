#!/usr/bin/env python3
"""Generate a DASHBOARD_PASSWORD_HASH and write it straight into .env.

Never prints or logs the plaintext password. Writes the hash directly to
avoid a real failure mode found during setup: printing the hash for the
user to copy-paste into .env is an easy step to silently skip -- the
script runs, looks successful, and .env is never actually updated. Direct
writing removes that gap entirely.

Usage: python3 scripts/hash_password.py
"""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.security import hash_password  # noqa: E402


def _write_env_value(env_path: Path, key: str, value: str) -> None:
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    pattern = rf"^#?\s*{re.escape(key)}=.*$"
    replacement = f"{key}={value}"
    if re.search(pattern, text, flags=re.MULTILINE):
        text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += replacement + "\n"
    env_path.write_text(text, encoding="utf-8")


def main() -> None:
    password = getpass.getpass("New dashboard password: ")
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        print("Passwords did not match. Nothing was changed. Run this again.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < 12:
        print("Refusing a password shorter than 12 characters. Nothing was changed.", file=sys.stderr)
        raise SystemExit(1)

    env_path = Path(".env")
    if not env_path.exists():
        print(
            "No .env file found in the current directory. Run this from the "
            "repo root, after `cp .env.example .env`.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    _write_env_value(env_path, "DASHBOARD_PASSWORD_HASH", hash_password(password))
    print(
        "Done. DASHBOARD_PASSWORD_HASH written directly to .env -- nothing to "
        "copy-paste. Restart the dashboard and log in with the password you "
        "just typed."
    )


if __name__ == "__main__":
    main()

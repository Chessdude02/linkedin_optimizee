#!/usr/bin/env python3
"""Sanity-check .env without ever printing a secret value.

Consolidates the checks that came up repeatedly while first setting this
project up on a real machine: is .env actually named .env (not .env.txt),
did each variable actually load, does each credential have the right
shape. Run this any time something that "should" work doesn't -- it's
almost always one of these.

Usage: python3 scripts/verify_env.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

OK = "[OK]"
MISSING = "[MISSING]"
WARN = "[WARN]"


def _mask(value: str, keep_start: int = 8, keep_end: int = 4) -> str:
    if len(value) <= keep_start + keep_end:
        return "*" * len(value)
    return f"{value[:keep_start]}...{value[-keep_end:]} (len={len(value)})"


def main() -> None:
    env_path = Path(".env")
    print("Environment file")
    print("-----------------")
    if not env_path.exists():
        print(f"{MISSING} .env not found in {Path.cwd()} -- did it save as .env.txt instead? "
              "Check with: Get-ChildItem -Force | Where-Object { $_.Name -like '.env*' }")
        raise SystemExit(1)
    print(f"{OK} .env found at {env_path.resolve()}")
    load_dotenv()

    print("\nDashboard")
    print("---------")
    secret_key = os.environ.get("DASHBOARD_SECRET_KEY")
    username = os.environ.get("DASHBOARD_USERNAME")
    password_hash = os.environ.get("DASHBOARD_PASSWORD_HASH")

    print(f"{OK if secret_key else MISSING} DASHBOARD_SECRET_KEY " +
          (_mask(secret_key) if secret_key else "not set"))
    print(f"{OK if username else MISSING} DASHBOARD_USERNAME " + (username or "not set"))
    if password_hash:
        shape_ok = password_hash.startswith("scrypt$") and password_hash.count("$") == 5
        print(f"{OK if shape_ok else WARN} DASHBOARD_PASSWORD_HASH " +
              (_mask(password_hash) if shape_ok else "set but does not look like a scrypt hash"))
    else:
        print(f"{MISSING} DASHBOARD_PASSWORD_HASH not set")

    print("\nExecution mode")
    print("--------------")
    mock = os.environ.get("MOCK_EXECUTION", "true")
    write_enabled = os.environ.get("WRITE_ENABLED", "false")
    print(f"{OK} MOCK_EXECUTION={mock} " +
          ("(safe: no real network calls)" if mock.strip().lower() != "false" else "(REAL execution armed)"))
    print(f"{OK} WRITE_ENABLED={write_enabled} (deploy-time default; the runtime kill switch in "
          "system_settings can override this -- check System Controls in the dashboard for the live state)")

    print("\nPublora (execution service only)")
    print("---------------------------------")
    api_key = os.environ.get("PUBLORA_API_KEY")
    if api_key:
        shape_ok = api_key.startswith("sk_")
        print(f"{OK if shape_ok else WARN} PUBLORA_API_KEY " +
              (_mask(api_key) if shape_ok else "set but does not start with 'sk_' -- check for a copy/paste error"))
    else:
        print(f"{MISSING if mock.strip().lower() == 'false' else OK} PUBLORA_API_KEY not set" +
              ("" if mock.strip().lower() != "false" else " -- required since MOCK_EXECUTION=false"))


if __name__ == "__main__":
    main()

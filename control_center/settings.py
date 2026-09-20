"""Environment configuration.

Every default here is chosen to fail closed: no real writes, no real
credentials required, human approval mandatory. Phase 1+2 (this module)
never talks to Publora/Apify/Pixfaro at all — that integration is Phase 4/5
and is not implemented yet, on purpose.
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; os.environ works fine without it


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Deny-by-default: no writes happen unless explicitly turned on.
WRITE_ENABLED = _bool_env("WRITE_ENABLED", False)

# Mock mode never contacts a real backend; it is the only backend Phase 1+2
# implements. Real execution is refused (not silently no-op'd) until the
# Phase 4/5 executor is built.
MOCK_EXECUTION = _bool_env("MOCK_EXECUTION", True)

# Whether a human approval is required before execution. This should
# never be false in any build this project ships.
APPROVAL_REQUIRED = _bool_env("APPROVAL_REQUIRED", True)

# How long a human's approval remains valid before it must be re-approved.
APPROVAL_TTL_MINUTES = int(os.getenv("APPROVAL_TTL_MINUTES", "15"))

# How long an unapproved (PENDING) action stays open before it auto-expires
# and must be re-requested.
PENDING_TTL_MINUTES = int(os.getenv("PENDING_TTL_MINUTES", str(24 * 60)))

DB_PATH = os.getenv("CONTROL_CENTER_DB_PATH", "control_center.db")

# Section 62 of the spec this project follows: WRITE_ENABLED=true with
# APPROVAL_REQUIRED=false must never be silently supported. Refuse to even
# import with that combination rather than build a bypass mode at all.
if WRITE_ENABLED and not APPROVAL_REQUIRED:
    raise RuntimeError(
        "Refusing to start: WRITE_ENABLED=true with APPROVAL_REQUIRED=false. "
        "This build does not support unattended publishing without human "
        "approval — that combination defeats the entire point of this "
        "system. Set APPROVAL_REQUIRED=true, or leave WRITE_ENABLED=false."
    )

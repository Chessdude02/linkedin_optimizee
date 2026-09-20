"""Canonical content hashing.

The hash covers every execution-relevant field. It is computed fresh from
the action's CURRENT stored fields at execution time and compared against
the hash that was frozen into the approval record at approval time. Any
divergence — a tampered payload, a swapped target, a changed account —
changes the hash and blocks execution with CONTENT_HASH_MISMATCH.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional


def canonical_payload_hash(
    action_type: str,
    account_id: str,
    target_id: Optional[str],
    payload: dict[str, Any],
    schedule: Optional[str] = None,
) -> str:
    canonical = {
        "action_type": action_type,
        "account_id": account_id,
        "target_id": target_id,
        "payload": payload,
        "schedule": schedule,
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

"""Explicit action state machine. No transition outside this table is legal.

PENDING → APPROVED | DECLINED | EXPIRED
APPROVED → EXECUTING | BLOCKED | EXPIRED
EXECUTING → EXECUTED | FAILED
DECLINED, EXPIRED, EXECUTED, FAILED, BLOCKED are all terminal.

In particular PENDING → EXECUTED, DECLINED → APPROVED, and EXECUTED →
APPROVED are all illegal and raise InvalidTransitionError.
"""
from __future__ import annotations

from .exceptions import InvalidTransitionError

PENDING = "PENDING"
APPROVED = "APPROVED"
DECLINED = "DECLINED"
EXPIRED = "EXPIRED"
EXECUTING = "EXECUTING"
EXECUTED = "EXECUTED"
FAILED = "FAILED"
BLOCKED = "BLOCKED"

ALL_STATUSES = {PENDING, APPROVED, DECLINED, EXPIRED, EXECUTING, EXECUTED, FAILED, BLOCKED}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    PENDING: {APPROVED, DECLINED, EXPIRED},
    APPROVED: {EXECUTING, BLOCKED, EXPIRED},
    EXECUTING: {EXECUTED, FAILED},
    DECLINED: set(),
    EXPIRED: set(),
    EXECUTED: set(),
    FAILED: set(),
    BLOCKED: set(),
}


def validate_transition(current: str, new: str) -> None:
    if current not in ALL_STATUSES:
        raise InvalidTransitionError(f"unknown current status {current!r}")
    if new not in ALL_STATUSES:
        raise InvalidTransitionError(f"unknown target status {new!r}")
    if new not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(f"{current} -> {new} is not an allowed transition")

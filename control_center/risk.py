"""Deterministic risk classification.

Risk level is metadata shown to the human reviewer. It never substitutes
for approval — every action type requires the same explicit human approval
regardless of risk level. There is no auto-approve-LOW-risk path.

The action-type set below is exhaustive and closed. request_action()
rejects any action_type not listed here, so there is no generic/unrestricted
action type (no RUN_LINKEDIN_COMMAND-style escape hatch).
"""
from __future__ import annotations

from .exceptions import UnknownActionTypeError

RISK_LEVELS: dict[str, str] = {
    "CREATE_POST": "LOW",
    "CREATE_COMMENT": "MEDIUM",
    "CREATE_REPLY": "MEDIUM",
    "CREATE_REACTION": "MEDIUM",
    "RESHARE_POST": "MEDIUM",
    "SCHEDULE_POST": "MEDIUM",
    "SEND_MESSAGE": "HIGH",
    "DELETE_POST": "HIGH",
    "DELETE_COMMENT": "HIGH",
    "MODIFY_PROFILE": "HIGH",
}

# SEND_MESSAGE and MODIFY_PROFILE have no implemented execution backend yet
# (linkedin-skills has no write path for either — LinkedIn has no public DM
# API and no automated profile-write path exists in that codebase). They are
# defined here so the schema has a home for them later, but executor.py
# refuses to execute them today rather than pretending to support them.
NOT_YET_IMPLEMENTED = {"SEND_MESSAGE", "MODIFY_PROFILE"}

VALID_ACTION_TYPES = frozenset(RISK_LEVELS)


def risk_for(action_type: str) -> str:
    if action_type not in RISK_LEVELS:
        raise UnknownActionTypeError(
            f"{action_type!r} is not a recognized action type; "
            f"valid types are {sorted(VALID_ACTION_TYPES)}"
        )
    return RISK_LEVELS[action_type]

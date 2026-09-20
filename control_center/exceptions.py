"""Exception hierarchy for the control center.

Every failure mode a caller needs to distinguish gets its own class rather
than a string reason, so tests and future callers (the Phase 3 dashboard,
the Phase 4 executor service) can catch precisely what they mean to handle.
"""


class ControlCenterError(Exception):
    """Base class for every control-center-specific error."""


class PermissionDeniedError(ControlCenterError):
    """Raised when a caller_role attempts an operation reserved for a
    different role (agent trying to approve/execute, dashboard trying to
    execute directly, etc.)."""


class UnknownActionTypeError(ControlCenterError):
    """Raised for any action_type outside the fixed, enumerated set.
    There is deliberately no generic/unrestricted action type."""


class ActionNotFoundError(ControlCenterError):
    """Raised when an action_id does not exist."""


class InvalidTransitionError(ControlCenterError):
    """Raised when a state transition is not in the allowed state machine."""


class ContentHashMismatchError(ControlCenterError):
    """Raised when an action's current payload hash no longer matches the
    hash that was approved."""


class DuplicateActionError(ControlCenterError):
    """Raised when a request would create an action that is substantially
    identical to one already active (pending/approved/executing/executed)."""


class ResearchItemNotFoundError(ControlCenterError):
    """Raised when a research_item id does not exist."""


class AlreadyConvertedError(ControlCenterError):
    """Raised when converting a research item that has already been
    converted to an action -- conversion is one-way and idempotent-safe,
    never silently creating a second action for the same finding."""

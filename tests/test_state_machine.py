"""No arbitrary state transitions: PENDING->EXECUTED, DECLINED->APPROVED,
and EXECUTED->APPROVED must all be rejected."""
import unittest

from control_center.exceptions import InvalidTransitionError
from control_center.state_machine import validate_transition


class TestStateMachine(unittest.TestCase):
    def test_forbidden_transitions_raise(self):
        forbidden = [
            ("PENDING", "EXECUTED"),
            ("DECLINED", "APPROVED"),
            ("EXECUTED", "APPROVED"),
            ("EXECUTED", "PENDING"),
            ("BLOCKED", "EXECUTED"),
            ("FAILED", "EXECUTED"),
        ]
        for current, new in forbidden:
            with self.assertRaises(InvalidTransitionError, msg=f"{current} -> {new} should be forbidden"):
                validate_transition(current, new)

    def test_allowed_transitions_pass(self):
        allowed = [
            ("PENDING", "APPROVED"),
            ("PENDING", "DECLINED"),
            ("PENDING", "EXPIRED"),
            ("APPROVED", "EXECUTING"),
            ("APPROVED", "BLOCKED"),
            ("APPROVED", "EXPIRED"),
            ("EXECUTING", "EXECUTED"),
            ("EXECUTING", "FAILED"),
        ]
        for current, new in allowed:
            validate_transition(current, new)  # should not raise

    def test_unknown_status_rejected(self):
        with self.assertRaises(InvalidTransitionError):
            validate_transition("PENDING", "TOTALLY_MADE_UP")
        with self.assertRaises(InvalidTransitionError):
            validate_transition("TOTALLY_MADE_UP", "APPROVED")


if __name__ == "__main__":
    unittest.main()

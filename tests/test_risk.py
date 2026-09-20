"""Direct unit tests for the risk classification table -- exhaustive and
closed, matching every action type the spec enumerates."""
import unittest

from control_center.exceptions import UnknownActionTypeError
from control_center.risk import NOT_YET_IMPLEMENTED, VALID_ACTION_TYPES, risk_for


class TestRisk(unittest.TestCase):
    def test_every_spec_action_type_is_known(self):
        expected = {
            "CREATE_POST", "CREATE_COMMENT", "CREATE_REPLY", "CREATE_REACTION",
            "RESHARE_POST", "DELETE_POST", "DELETE_COMMENT", "SCHEDULE_POST",
            "MODIFY_PROFILE", "SEND_MESSAGE",
        }
        self.assertEqual(VALID_ACTION_TYPES, frozenset(expected))

    def test_risk_levels_match_spec_table(self):
        self.assertEqual(risk_for("CREATE_POST"), "LOW")
        self.assertEqual(risk_for("CREATE_COMMENT"), "MEDIUM")
        self.assertEqual(risk_for("CREATE_REPLY"), "MEDIUM")
        self.assertEqual(risk_for("CREATE_REACTION"), "MEDIUM")
        self.assertEqual(risk_for("RESHARE_POST"), "MEDIUM")
        self.assertEqual(risk_for("SCHEDULE_POST"), "MEDIUM")
        self.assertEqual(risk_for("SEND_MESSAGE"), "HIGH")
        self.assertEqual(risk_for("DELETE_POST"), "HIGH")
        self.assertEqual(risk_for("DELETE_COMMENT"), "HIGH")
        self.assertEqual(risk_for("MODIFY_PROFILE"), "HIGH")

    def test_unknown_type_raises(self):
        with self.assertRaises(UnknownActionTypeError):
            risk_for("NOT_A_REAL_TYPE")

    def test_not_yet_implemented_types_are_a_subset_of_valid_types(self):
        self.assertTrue(NOT_YET_IMPLEMENTED.issubset(VALID_ACTION_TYPES))
        self.assertEqual(NOT_YET_IMPLEMENTED, {"SEND_MESSAGE", "MODIFY_PROFILE"})


if __name__ == "__main__":
    unittest.main()

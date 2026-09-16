import unittest
from pathlib import Path

from cultivation_life.migration import assess_default_matrix
from tools.audit_v1_v2 import BLOCKER_GROUPS, _frozen_operations, _v2_boundary_violations


SOURCE_ROOT = Path(__file__).resolve().parent.parent


class V1V2AuditTests(unittest.TestCase):
    def test_every_current_blocker_has_exactly_one_root_cause_group(self):
        blocker_ids = {
            row["id"] for row in assess_default_matrix(SOURCE_ROOT).to_dict()["blockers"]
        }
        classified = [
            feature_id
            for feature_ids in BLOCKER_GROUPS.values()
            for feature_id in feature_ids
        ]
        self.assertEqual(len(classified), len(set(classified)))
        self.assertEqual(set(classified), blocker_ids)

    def test_frozen_v1_surface_and_v2_dependency_boundary_match(self):
        expected, actual = _frozen_operations(SOURCE_ROOT)
        self.assertEqual(expected, actual)
        self.assertEqual(_v2_boundary_violations(SOURCE_ROOT), [])


if __name__ == "__main__":
    unittest.main()

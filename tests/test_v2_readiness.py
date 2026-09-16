import json
import tempfile
import unittest
from pathlib import Path

from cultivation_life.migration import (
    CutoverBlockedError,
    FeatureMatrix,
    assess_default_matrix,
    assert_ready_for_cutover,
)


SOURCE_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = SOURCE_ROOT / "docs" / "v2" / "feature_matrix.json"
INVENTORY_PATH = SOURCE_ROOT / "docs" / "v2" / "v1_behavior_inventory.json"


class V2ReadinessMatrixTests(unittest.TestCase):
    def test_default_matrix_covers_every_frozen_operation_exactly_once(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        report = assess_default_matrix(SOURCE_ROOT)
        self.assertEqual(report.structural_errors, ())
        self.assertEqual(report.operation_count, len(inventory["public_operations"]))
        self.assertEqual(report.covered_operation_count, report.operation_count)
        self.assertEqual(
            sum(report.status_counts.values()),
            report.feature_count,
        )

    def test_current_matrix_blocks_cutover_and_names_real_gaps(self):
        report = assess_default_matrix(SOURCE_ROOT)
        self.assertFalse(report.ready)
        blocker_ids = {row["id"] for row in report.blockers}
        self.assertIn("economy.auction", blocker_ids)
        self.assertIn("core.action_loop", blocker_ids)
        self.assertIn("interface.http_frontend", blocker_ids)
        with self.assertRaises(CutoverBlockedError):
            assert_ready_for_cutover(SOURCE_ROOT)

    def test_launcher_remains_on_v1_while_cutover_is_blocked(self):
        report = assess_default_matrix(SOURCE_ROOT)
        launcher = (SOURCE_ROOT / "launcher.py").read_text(encoding="utf-8")
        self.assertFalse(report.ready)
        self.assertIn("from cultivation_life.server import Handler", launcher)
        self.assertNotIn("cultivation_life.v2", launcher)

    def test_gate_opens_only_for_structurally_complete_all_pass_matrix(self):
        document = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        for feature in document["features"]:
            feature["status"] = "pass"
            feature["evidence"] = [
                "tests/test_v2_readiness.py::V2ReadinessMatrixTests::test_default_matrix_covers_every_frozen_operation_exactly_once"
            ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "all-pass.json"
            path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            report = FeatureMatrix.load(path, project_root=SOURCE_ROOT).assess()
        self.assertTrue(report.ready)
        report.require_ready()

    def test_missing_or_duplicate_operation_is_a_structural_failure(self):
        document = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        owner = next(
            feature for feature in document["features"]
            if "advance" in feature["v1_operations"]
        )
        owner["v1_operations"].remove("advance")
        duplicate_target = document["features"][0]
        duplicate_target["v1_operations"] = ["choice", "choice"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "broken.json"
            path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            report = FeatureMatrix.load(path, project_root=SOURCE_ROOT).assess()
        rendered = "\n".join(report.structural_errors)
        self.assertIn("矩阵遗漏V1公开操作", rendered)
        self.assertIn("功能项内操作重复", rendered)
        self.assertIn("V1公开操作被重复归属", rendered)
        self.assertFalse(report.ready)

    def test_pass_status_requires_existing_evidence(self):
        document = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        passed = next(feature for feature in document["features"] if feature["status"] == "pass")
        passed["evidence"] = ["tests/does-not-exist.py"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad-evidence.json"
            path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            report = FeatureMatrix.load(path, project_root=SOURCE_ROOT).assess()
        self.assertTrue(any("证据文件不存在" in error for error in report.structural_errors))
        self.assertFalse(report.ready)

    def test_passed_v1_operation_requires_a_real_test_node(self):
        document = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        passed = next(
            feature for feature in document["features"]
            if feature["status"] == "pass" and feature["v1_operations"]
        )
        passed["evidence"] = ["tests/test_v2_readiness.py::MissingClass::test_not_here"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad-node.json"
            path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            report = FeatureMatrix.load(path, project_root=SOURCE_ROOT).assess()
        self.assertTrue(any("测试证据节点不存在" in error for error in report.structural_errors))
        self.assertFalse(report.ready)


if __name__ == "__main__":
    unittest.main()

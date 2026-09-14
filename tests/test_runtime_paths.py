import tempfile
import unittest
from pathlib import Path

from cultivation_life.runtime import persistence_root


class PersistenceRootTests(unittest.TestCase):
    def test_repository_dist_build_uses_the_single_project_data_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content").mkdir()
            (root / "build").mkdir()
            (root / "build" / "launcher.spec").write_text("", encoding="utf-8")
            (root / "launcher.py").write_text("", encoding="utf-8")
            (root / "dist").mkdir()
            self.assertEqual(persistence_root(root / "dist"), root)

    def test_real_distribution_keeps_its_own_data_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dist"
            root.mkdir()
            self.assertEqual(persistence_root(root), root)


if __name__ == "__main__":
    unittest.main()

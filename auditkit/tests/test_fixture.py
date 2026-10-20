"""The synthetic fixture, end to end, through the real merge and the pinned codebook."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@unittest.skipUnless((ROOT / "fixtures" / "synthetic" / "expected.json").exists() and (ROOT / "codebook" / "codebook.json").exists(),
                     "fixture or codebook not built")
class TestSyntheticFixture(unittest.TestCase):
    def test_selftest(self):
        from auditkit.selftest import run
        self.assertEqual(run(verbose=False), 0)


if __name__ == "__main__":
    unittest.main()

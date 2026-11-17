"""full_protocol.py reads ctest's summary line in every form ctest prints it.

ctest 3.x always names the failures (`100% tests passed, 0 tests failed out of
65`); ctest 4.x leaves them out when there are none (`100% tests passed out of
65`). Reading only the first form failed a green CI run when `ubuntu-latest`
moved to cmake 4.2.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
from full_protocol import parse_ctest_summary  # noqa: E402


class CtestSummaryTest(unittest.TestCase):
    def _parse(self, text: str):
        fd, name = tempfile.mkstemp(suffix=".log")
        os.close(fd)
        path = Path(name)
        try:
            path.write_text(text)
            return parse_ctest_summary(path)
        finally:
            path.unlink()

    def test_ctest3_all_passed(self):
        self.assertEqual(self._parse("100% tests passed, 0 tests failed out of 65\n"), (0, 65))

    def test_ctest4_all_passed(self):
        self.assertEqual(self._parse("100% tests passed out of 65\n"), (0, 65))

    def test_some_failed(self):
        self.assertEqual(self._parse("97% tests passed, 2 tests failed out of 72\n"), (2, 72))

    def test_one_failed(self):
        self.assertEqual(self._parse("98% tests passed, 1 test failed out of 72\n"), (1, 72))

    def test_no_summary(self):
        self.assertIsNone(self._parse("      Start 1: test_gc\n"))


if __name__ == "__main__":
    unittest.main()

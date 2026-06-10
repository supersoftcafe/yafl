"""The `examples/findstr` parallel substring-search demo.

Builds the example and runs it against a small temp tree, checking it finds
matches across files and recurses into subdirectories. The point of the example
is to exercise `__parallel__` (the file list is searched divide-and-conquer), so
this is also light end-to-end coverage of parallel evaluation.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_to_binary, _RUN_ENV

_EXAMPLE = Path(__file__).parent.parent.parent / "examples" / "findstr.yafl"


class TestFindstr(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = compile_to_binary(_EXAMPLE.read_text())

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.binary)
        except OSError:
            pass

    def _run(self, needle: str, path: str):
        r = subprocess.run([self.binary, needle, path],
                           capture_output=True, timeout=30, text=True, env=_RUN_ENV)
        return r.returncode, r.stdout

    def test_finds_matches_across_a_tree(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "a.txt").write_text("alpha\nNEEDLE here\nbeta\n")
            Path(d, "b.txt").write_text("nothing to see\n")
            sub = Path(d, "sub")
            sub.mkdir()
            Path(sub, "c.txt").write_text("first\nsecond NEEDLE\nNEEDLE third\n")

            rc, out = self._run("NEEDLE", d)
            self.assertEqual(0, rc)
            lines = set(out.splitlines())
            # one match in a.txt, two in the recursed sub/c.txt, none in b.txt.
            self.assertIn(f"{d}/a.txt:2:NEEDLE here", lines)
            self.assertIn(f"{d}/sub/c.txt:2:second NEEDLE", lines)
            self.assertIn(f"{d}/sub/c.txt:3:NEEDLE third", lines)
            self.assertEqual(3, len(lines))
            self.assertFalse(any("b.txt" in ln for ln in lines))

    def test_no_match_is_silent_success(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "a.txt").write_text("nothing relevant here\n")
            rc, out = self._run("absent-substring", d)
            self.assertEqual(0, rc)
            self.assertEqual("", out)

    def test_usage_when_no_args(self):
        r = subprocess.run([self.binary], capture_output=True, timeout=10,
                           text=True, env=_RUN_ENV)
        self.assertEqual(2, r.returncode)
        self.assertIn("usage:", r.stdout)

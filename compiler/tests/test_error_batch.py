"""Programs that must FAIL to compile are batched with each other.

A bad program cannot share a unit with good ones — it takes them down. But bad
programs batch well together: the compiler reports every diagnostic in one pass
rather than stopping at the first, so N of them need ONE compile and each one's
messages come back by line range.

NOTHING USES THIS YET, deliberately. Measured 2026-08-21: converting a module
to it saved 1s of 30.6s, and the suite came out slower, because #22 (an
unqualified reference does not prefer its own namespace) forces
`collision_free_groups` to put same-named programs in separate units — and
these test programs nearly all declare `main`, `helper`, `f`, so the groups
come out near-singleton and a group of one is just an ordinary compile. The
earlier "3x faster" reading was measuring a bug: the unit had no `main`, so
compiler.py:578 returned before linearity, tail_loop and the lazy checks ran.
Fix #22 and this becomes worth wiring up; the harness class for doing so was
removed rather than left to rot untested.

The safety property is what these tests pin: a program whose diagnostics do not
appear must be reported as NOT failed, so the caller falls back to compiling it
alone. Some checks live in phases that never run once an earlier phase has
found errors, so "no diagnostics in range" cannot be read as "compiled fine".
"""
from __future__ import annotations

import unittest

from tests.testutil import (compile_error_batch, error_batch,
                            split_diagnostics)

_UNDEFINED = "import System\nfun main(): System::Int\n  ret undefinedThing()\n"
_BAD_TYPE = 'import System\nfun main(): System::Int\n  ret "not an Int"\n'
_GOOD = "import System\nfun main(): System::Int\n  ret 0\n"
# `[tail]` is verified by lower_tail_loops, which runs AFTER the check phase.
_NON_TAIL = ("import System\n"
             "fun [tail] countUp(n: System::Int): System::Int\n"
             "  ret n <= 0 ? 0 : 1 + countUp(n - 1)\n"
             "fun main(): System::Int\n  ret countUp(3)\n")


class TestErrorBatch(unittest.TestCase):

    def test_offsets_locate_each_program(self):
        unit, offsets = error_batch([_UNDEFINED, _BAD_TYPE])
        self.assertEqual(2, len(offsets))
        lines = unit.split("\n")
        # Each recorded offset is the first line of that program's own text.
        self.assertEqual("import System", lines[offsets[0] - 1])
        self.assertEqual("import System", lines[offsets[1] - 1])
        # Namespaced apart so they cannot collide.
        self.assertIn("namespace E0", unit)
        self.assertIn("namespace E1", unit)

    def test_diagnostics_are_made_program_relative(self):
        # A diagnostic at unit line 12 inside a program starting at line 10 is
        # that program's line 3 — what the test would have seen on its own.
        diag = "t.yafl[12:7] - Incorrect type\nt.yafl[4:1] - something earlier\n"
        per = split_diagnostics(diag, [1, 10], [_GOOD, _BAD_TYPE])
        self.assertIn("[4:1]", per[0])
        self.assertIn("[3:7]", per[1])
        self.assertNotIn("[12:7]", per[1])

    def test_one_compile_reports_each_bad_program(self):
        results = compile_error_batch([_UNDEFINED, _BAD_TYPE, _GOOD])
        self.assertTrue(results[0][0], "an undefined name must be reported")
        self.assertTrue(results[1][0], "a type error must be reported")
        self.assertFalse(results[2][0], "a valid program must not be reported")
        self.assertTrue(results[0][1].strip(), "diagnostics must come back")

    def test_an_error_from_a_later_phase_is_still_reported(self):
        # compiler.py:578 returns the moment the check phase has failures, so
        # every pass after it — linearity, tail_loop, the lazy checks — is
        # skipped. A unit with no `main` ALWAYS has "No main function found",
        # so those passes never run and this program comes back looking clean.
        results = compile_error_batch([_NON_TAIL, _GOOD])
        self.assertTrue(results[0][0],
                        "a non-tail self-call under [tail] must be reported")

    def test_a_program_without_diagnostics_is_not_claimed_to_fail(self):
        # THE SAFETY PROPERTY. Checks in later phases never run once an earlier
        # phase reports errors, so a genuinely-bad program can come back with no
        # diagnostics. It must be reported as not-failed so the caller compiles
        # it alone rather than trusting a verdict the batch could not reach.
        results = compile_error_batch([_UNDEFINED, _GOOD])
        self.assertFalse(results[1][0])
        self.assertEqual("", results[1][1].strip())


if __name__ == "__main__":
    unittest.main()

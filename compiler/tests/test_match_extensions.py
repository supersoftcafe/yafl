"""Match extensions: multi-literal arms (any-of, separated by `|`) and arm guards.

`(a, b, c) => body` — one arm matching any of several literals (all the same
kind: chars are Int32, so char classification lands here). `<arm> if cond =>
body` — a guard evaluated after the arm's binding; a failing guard falls
through to the NEXT arm. A guarded arm covers nothing for exhaustiveness, and
the else arm may not carry a guard (it must stay total).

The runtime behaviour is checked by compiler/yafl_tests/match_extensions.yafl;
these are the forms that must be rejected.

Runtime behaviour is checked by compiler/yafl_tests/match_extensions.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    return compile_errors(src)


_PRELUDE = "namespace Test\nimport System\n"


class TestMatchExtensionsErrors(TestCase):
    def test_range_on_string_subject_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(s: String): Int\n"
            + "  ret match(s)\n"
            + "    (\"a\" .. \"z\") => 0\n"
            + "    ()             => 1\n"
            + "fun main(): Int\n  ret f(\"q\")\n")
        self.assertTrue(errs.strip(), "expected an error for a string range")

    def test_empty_range_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(n: Int): Int\n"
            + "  ret match(n)\n"
            + "    (5 .. 1) => 0\n"
            + "    ()       => 1\n"
            + "fun main(): Int\n  ret f(3)\n")
        self.assertIn("range", errs.lower())

    def test_mixed_int_float_bounds_are_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(x: Float): Int\n"
            + "  ret match(x)\n"
            + "    (1 .. 2.0) => 0\n"
            + "    ()         => 1\n"
            + "fun main(): Int\n  ret f(1.5)\n")
        self.assertTrue(errs.strip(), "expected an error for mixed int/float bounds")

    def test_guard_on_else_arm_is_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(n: Int): Int\n"
            + "  ret match(n)\n"
            + "    (0) => 0\n"
            + "    () if n > 0 => 1\n"
            + "  ret 2\n"
            + "fun main(): Int\n  ret f(1)\n")
        self.assertIn("guard", errs.lower())

    def test_mixed_literal_kinds_in_one_arm_are_rejected(self):
        errs = _errors(_PRELUDE
            + "fun f(n: Int): Int\n"
            + "  ret match(n)\n"
            + "    (1 | \"a\") => 0\n"
            + "    ()        => 1\n"
            + "fun main(): Int\n  ret f(1)\n")
        self.assertTrue(errs.strip(), "expected an error for mixed literal kinds")

    def test_guarded_arms_do_not_satisfy_exhaustiveness(self):
        errs = _errors(_PRELUDE
            + "class A(x: Int)\nclass B(y: Int)\n"
            + "fun f(v: A|B): Int\n"
            + "  ret match(v)\n"
            + "    (a: A) if a.x > 0 => 0\n"
            + "    (b: B) => 1\n"
            + "fun main(): Int\n  ret f(B(1))\n")
        self.assertIn("non-exhaustive", errs)

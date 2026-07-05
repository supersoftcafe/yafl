"""The vanished-value warnings: no value disappears silently.

A warning is an Error with severity "warning" — reported, never build-failing.
Three producers, all in check() where the correctly-scoped resolver is in hand:
an unused block-local binding, a non-None value in statement position, and an
unused parameter. `_`-prefixed names (and `this`) are the explicit opt-out.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
import compiler as c


def _compile(source: str) -> tuple[str, list[str]]:
    code, _link, warns = c.compile_project(
        [c.Input(source, "test.yafl")], use_stdlib=True, just_testing=True)
    return code, [str(w) for w in warns]


class TestVanishedValueWarnings(TestCase):
    def test_vanishing_values_warn_and_build_succeeds(self):
        # One program, three vanishing values: an unused let, a discarded
        # non-None statement value, and an unused parameter. All warn; the
        # build still succeeds.
        code, warns = _compile(
            "namespace Main\n"
            "import System\n"
            "fun f(a: System::Int, b: System::Int): System::Int\n"
            "  ret a\n"
            "fun main(): System::Int\n"
            "  let x = 5\n"
            "  System::length(\"ab\")\n"
            "  ret f(1, 2)\n")
        self.assertTrue(code, "warnings must not fail the build")
        self.assertTrue(any("'x' is never used" in w for w in warns), warns)
        self.assertTrue(any("statement value is discarded" in w for w in warns), warns)
        self.assertTrue(any("parameter 'b' is never used" in w for w in warns), warns)

    def test_consumed_and_opted_out_values_are_silent(self):
        # The same shapes made intentional: `_`-prefixed binding and parameter,
        # `let _ =` for the discard, a genuinely used let, and a None-returning
        # call in statement position. Zero warnings.
        code, warns = _compile(
            "namespace Main\n"
            "import System\n"
            "fun f(a: System::Int, _b: System::Int): System::Int\n"
            "  ret a\n"
            "fun main(): System::Int\n"
            "  let x = 5\n"
            "  let _ = System::length(\"ab\")\n"
            "  System::print(\"\")\n"
            "  ret f(x, 2)\n")
        self.assertTrue(code)
        self.assertEqual([], warns)

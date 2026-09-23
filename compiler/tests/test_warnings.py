"""The vanished-value warnings: no value disappears silently.

A warning is an Error with severity "warning" — reported, never build-failing.
Four producers, all in check() where the correctly-scoped resolver is in hand:
an unused block-local binding, a non-None value in statement position, an
unused parameter, and a fragile-base override. `_`-prefixed names (and
`this`) are the explicit opt-out for the first two.

Each warning has a `category` (see warning_flags.py) gating whether it's
enabled. `unused-parameter` defaults off (noisy for trait-constrained
signatures); the rest default on. `compile_project`'s `enabled_warnings`
selects the set — see test_warning_flags.py for the flag-resolution rules.
"""
from __future__ import annotations

import warning_flags as wf
from tests.testutil import TimedTestCase as TestCase
import compiler as c


def _compile(source: str, enabled_warnings=None) -> tuple[str, list[str]]:
    kwargs = {} if enabled_warnings is None else {"enabled_warnings": enabled_warnings}
    code, _link, warns = c.compile_project(
        [c.Input(source, "test.yafl")], use_stdlib=True, just_testing=True, **kwargs)
    return code, [str(w) for w in warns]


_VANISHING_VALUES_SOURCE = (
    "namespace Main\n"
    "import System\n"
    "fun f(a: System::Int, b: System::Int): System::Int\n"
    "  ret a\n"
    "fun main(): System::Int\n"
    "  let x = 5\n"
    "  System::length(\"ab\")\n"
    "  ret f(1, 2)\n")


class TestVanishedValueWarnings(TestCase):
    def test_default_warnings_exclude_unused_parameter(self):
        # unused-parameter defaults off; the other two vanishing-value shapes
        # in this program still warn, and the build still succeeds.
        code, warns = _compile(_VANISHING_VALUES_SOURCE)
        self.assertTrue(code, "warnings must not fail the build")
        self.assertTrue(any("'x' is never used" in w for w in warns), warns)
        self.assertTrue(any("statement value is discarded" in w for w in warns), warns)
        self.assertFalse(any("parameter 'b' is never used" in w for w in warns), warns)

    def test_unused_parameter_is_opt_in(self):
        # Same program, with unused-parameter explicitly enabled: it now warns
        # too, alongside the two always-on ones.
        code, warns = _compile(_VANISHING_VALUES_SOURCE,
            enabled_warnings=wf.resolve_enabled_warnings(["unused-parameter"]))
        self.assertTrue(code)
        self.assertTrue(any("parameter 'b' is never used" in w for w in warns), warns)

    def test_wno_suppresses_a_default_on_warning(self):
        code, warns = _compile(_VANISHING_VALUES_SOURCE,
            enabled_warnings=wf.resolve_enabled_warnings(["no-unused-variable"]))
        self.assertTrue(code)
        self.assertFalse(any("'x' is never used" in w for w in warns), warns)
        self.assertTrue(any("statement value is discarded" in w for w in warns), warns)

    def test_consumed_and_opted_out_values_are_silent(self):
        # The same shapes made intentional: `_`-prefixed binding and parameter,
        # `let _ =` for the discard, a genuinely used let, and a None-returning
        # call in statement position. Zero warnings even with everything enabled.
        code, warns = _compile(
            "namespace Main\n"
            "import System\n"
            "fun f(a: System::Int, _b: System::Int): System::Int\n"
            "  ret a\n"
            "fun main(): System::Int\n"
            "  let x = 5\n"
            "  let _ = System::length(\"ab\")\n"
            "  System::print(\"\")\n"
            "  ret f(x, 2)\n",
            enabled_warnings=wf.resolve_enabled_warnings(["all"]))
        self.assertTrue(code)
        self.assertEqual([], warns)

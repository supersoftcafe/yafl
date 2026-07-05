"""Lambda lifting (lowering/lambda_lift.py): a nested function that captures
its parent's parameters but is only ever CALLED loses its closure — captures
become threaded parameters, and no closure object is ever allocated.

The C-inspection assertions are the acceptance criterion: naive idiomatic
code (nested helper reading the parent's parameter) must compile to exactly
what hand-threading produces. writeAll's captured `data` — once 93% of
json_pretty's allocations — is the pattern under test.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_CAPTURING_LOOP = (
    "namespace Main\n"
    "import System\n"
    "fun repeat(piece: System::String, n: System::Int): System::String\n"
    "  fun [tail] go(sb: System::StringBuilder, i: System::Int): System::StringBuilder\n"
    "    ret i <= 0 ? sb : go(System::append(sb, piece), i - 1)\n"
    "  ret System::toString(go(System::StringBuilder(), n))\n"
    "fun main(): System::Int\n"
    "  let s = repeat(\"ab\", 30)\n"
    "  System::print(System::slice(s, 0, 4))\n"
    "  ret System::length(s)\n")


class TestLambdaLift(TestCase):
    def test_captured_call_helper_has_no_closure(self):
        rc, out = compile_and_run_stdlib_capture(_CAPTURING_LOOP)
        self.assertEqual(60, rc)
        self.assertEqual("abab", out)
        c_code = c.compile([c.Input(_CAPTURING_LOOP, "test.yafl")],
                           use_stdlib=True, just_testing=True)
        # `go` captures `piece` but is only called → lifted, hoisted globally,
        # no closure class for it anywhere in the program.
        self.assertNotIn("lambda_Main__repeat", c_code)

    def test_mutual_recursion_lifts_as_a_unit(self):
        src = (
            "namespace Main\n"
            "import System\n"
            "fun parity(bias: System::Int, n: System::Int): System::Int\n"
            "  fun isEven(k: System::Int): System::Int\n"
            "    ret k <= 0 ? bias : isOdd(k - 1)\n"
            "  fun isOdd(k: System::Int): System::Int\n"
            "    ret k <= 0 ? 0 - bias : isEven(k - 1)\n"
            "  ret isEven(n)\n"
            "fun main(): System::Int\n"
            "  ret parity(7, 4) + parity(3, 3)\n")
        rc, _out = compile_and_run_stdlib_capture(src)
        self.assertEqual(4, rc)   # 7 + (-3)
        c_code = c.compile([c.Input(src, "test.yafl")],
                           use_stdlib=True, just_testing=True)
        self.assertNotIn("lambda_Main__parity", c_code)

    def test_value_position_reference_keeps_closure_semantics(self):
        # `f` is passed as a value → not liftable; behaviour must be intact
        # through the ordinary closure path.
        src = (
            "namespace Main\n"
            "import System\n"
            "fun apply(g: (:System::Int): System::Int, x: System::Int): System::Int\n"
            "  ret g(x)\n"
            "fun addTo(base: System::Int, x: System::Int): System::Int\n"
            "  fun f(k: System::Int): System::Int\n"
            "    ret k + base\n"
            "  ret apply(f, x) + f(1)\n"
            "fun main(): System::Int\n"
            "  ret addTo(10, 5)\n")
        rc, _out = compile_and_run_stdlib_capture(src)
        self.assertEqual(26, rc)   # (5+10) + (1+10)

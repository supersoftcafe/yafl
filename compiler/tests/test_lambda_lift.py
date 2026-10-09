"""Lambda lifting (lowering/lambda_lift.py): a nested function that captures
its parent's parameters but is only ever CALLED loses its closure — captures
become threaded parameters, and no closure object is ever allocated.

The C-inspection assertions are the acceptance criterion: naive idiomatic
code (nested helper reading the parent's parameter) must compile to exactly
what hand-threading produces. writeAll's captured `data` — once 93% of
json_pretty's allocations — is the pattern under test. That the lifted code
behaves the same is checked by compiler/yafl_tests/lambda_lift.yafl.

Runtime behaviour is checked by compiler/yafl_tests/lambda_lift.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c

_CAPTURING_LOOP = (
    "namespace Main\n"
    "import System\n"
    "fun repeat(piece: System::String, n: System::Int): System::String\n"
    "  fun [tail] go(acc: System::String, i: System::Int): System::String\n"
    "    ret i <= 0 ? acc : go(acc + piece, i - 1)\n"
    "  ret go(\"\", n)\n"
    "fun main(): System::Int\n"
    "  let s = repeat(\"ab\", 30)\n"
    "  System::print(System::slice(s, 0, 4))\n"
    "  ret System::length(s)\n")


class TestLambdaLift(TestCase):
    def test_captured_call_helper_has_no_closure(self):
        c_code = compile_c(_CAPTURING_LOOP)
        self.assertTrue(c_code)
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
        c_code = compile_c(src)
        self.assertTrue(c_code)
        self.assertNotIn("lambda_Main__parity", c_code)

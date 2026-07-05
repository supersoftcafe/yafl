"""A global `let` holding a lambda is lowered to a function
(lowering/lambda_globals.py): it compiles as an ordinary function — no lazy
stub, no fun_t through the async force path — and is transparent to callers
and to code that passes it as a value."""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestLambdaGlobals(TestCase):
    def test_called_directly(self):
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "let h: (:System::String): System::Int = (s: System::String) => System::length(s)\n"
            "fun main(): System::Int\n"
            "  ret h(\"abc\") + h(\"de\")\n")
        self.assertEqual(5, rc)

    def test_passed_as_a_value(self):
        # `dbl` is now a `fun`, but passing it to a higher-order function must
        # still work — fun and let-of-callable are indistinguishable at use.
        rc, _ = compile_and_run_stdlib_capture(
            "namespace Main\nimport System\n"
            "let dbl: (:System::Int): System::Int = (n: System::Int) => n * 2\n"
            "fun apply(f: (:System::Int): System::Int, x: System::Int): System::Int\n"
            "  ret f(x)\n"
            "fun main(): System::Int\n"
            "  ret apply(dbl, 20) + dbl(1)\n")
        self.assertEqual(42, rc)

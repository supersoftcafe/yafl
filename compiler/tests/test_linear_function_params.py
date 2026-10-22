"""`[linear]` function parameters: a promise to call the function exactly once.

The callee must call a `[linear]` parameter exactly once on every path — not
zero times, not twice — and may do nothing else with it (passing it on or
capturing it could run it any number of times). In exchange a lambda written
directly as that argument may capture linear values: it runs once, so each
captured value is consumed once, inside its body.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib
from tests.testutil import compile_errors

_HDR = "namespace Main\nimport System\n"

_TOKEN = """\
class [linear,final] Tok(v: System::Int)

fun spend([terminal] t: Tok): System::Int
  ret t.v
"""


def _program(callee_body: str, caller: str = "  ret once((n) => n + spend(t))\n") -> str:
    return (_HDR + _TOKEN
            + "fun once([linear] f: (:System::Int): System::Int): System::Int\n"
            + callee_body
            + "fun main(): System::Int\n  let t = Tok(40)\n" + caller)


class TestLinearFunctionParams(TestCase):
    def test_lambda_may_capture_a_linear_value(self):
        self.assertEqual(42, compile_and_run_stdlib(_program("  ret f(2)\n")))

    def test_calling_twice_is_an_error(self):
        errors = compile_errors(_program("  ret f(1) + f(2)\n"))
        self.assertIn("linear value 'f' is used 2 times", errors)

    def test_never_calling_is_an_error(self):
        errors = compile_errors(_program("  ret 0\n"))
        self.assertIn("linear value 'f' is never used", errors)

    def test_passing_it_on_is_an_error(self):
        callee = ("  ret apply(f)\n"
                  "fun apply(g: (:System::Int): System::Int): System::Int\n"
                  "  ret g(2)\n")
        self.assertIn("[linear] function 'f' may only be called", compile_errors(_program(callee)))

    def test_capture_into_an_ordinary_parameter_is_still_an_error(self):
        src = (_HDR + _TOKEN
               + "fun twice(f: (:System::Int): System::Int): System::Int\n"
               + "  ret f(1)\n"
               + "fun main(): System::Int\n  let t = Tok(40)\n"
               + "  ret twice((n) => n + spend(t))\n")
        self.assertIn("linear value 't' captured by a nested function or lambda", compile_errors(src))

    def test_linear_on_a_non_function_parameter_is_an_error(self):
        src = (_HDR + "fun f([linear] n: System::Int): System::Int\n  ret n\n"
               + "fun main(): System::Int\n  ret f(1)\n")
        self.assertIn("[linear] applies only to a function-typed parameter", compile_errors(src))

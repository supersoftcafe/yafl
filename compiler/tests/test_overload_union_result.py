"""Operator/function calls in union-result positions must still resolve.

`n / 2` inside an arm whose expected type is `Int|Oops` used to reject EVERY
`/` candidate: overload selection required the candidate's RESULT to be
bidirectionally equivalent to the expected `Int|Oops`, and `Int` is not.
That rule is correct for function VALUES (no implicit result thunks) but a
CALL owns its own result conversion — the argument types alone identify the
candidate, and the call's value then widens into the union like any other
expression. Found while adding the union `?>`; became visible with the
Complex64/32 overloads (before them the wrongly-rejected sole candidate
happened to still resolve by being alone).
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib

_SRC = """
namespace Main
import System

class [final] Oops(message: System::String)

fun half(n: System::Int): System::Int|Oops
  ret n % 2 == 0 ? n / 2 : Oops("odd: " + String(n))

fun main(): System::Int
  ret match(half(8))
    (v: System::Int) => v
    ()               => -1
"""


class TestOverloadUnionResult(TimedTestCase):
    def test_division_under_union_expected_type(self):
        self.assertEqual(4, compile_and_run_stdlib(_SRC))

    def test_float_comparison_under_union(self):
        # A second operator kind and a None-union: `<` in a Float|None position.
        self.assertEqual(1, compile_and_run_stdlib("""
namespace Main
import System

fun capped(x: System::Float): System::Float|System::None
  ret x < 10.0 ? x * 2.0 : None

fun main(): System::Int
  ret match(capped(0.5))
    (v: System::Float) => 1
    ()                 => 0
"""))

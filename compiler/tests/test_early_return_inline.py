"""Early returns survive inlining at every optimisation level.

A `return` branches to the end of its nearest enclosing block, so when a
function with an early return is inlined — its body substituted as a nested
block — the early return is scoped to that block and behaves as the call's
value. Before this, inlining an early-return function at a non-tail position
miscompiled (the spliced `return` left the *caller*) and failed SSA validation
at -O2.

`opaque(n)` is recursive, so it is never inlined; it keeps `maxi`'s arguments
out of reach of constant folding, so the early-return branch genuinely survives
to code generation at the higher optimisation levels.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun opaque(x: System::Int): System::Int
  if x < 0
    ret opaque(x - 1)
  ret x

fun maxi(a: System::Int, b: System::Int): System::Int
  if a < b
    ret b
  ret a

# early-return callee inlined at an expression position (operands of `+`)
fun sum_of_maxes(n: System::Int): System::Int
  ret maxi(n, n + 4) + maxi(n + 9, n + 2)

# early-return callee inlined at a statement position (whole let RHS)
fun via_let(n: System::Int): System::Int
  let x: System::Int = maxi(n, n + 4)
  ret x + 100

fun main(): System::Int
  let n: System::Int = opaque(3)
  print(sum_of_maxes(n))    # maxi(3,7)=7 + maxi(12,5)=12 -> 19
  print(via_let(n))         # maxi(3,7)=7 -> 107
  ret 0
"""


class TestEarlyReturnInline(TestCase):
    def test_all_optimisation_levels(self):
        for opt in (0, 1, 2, 3):
            with self.subTest(optimisation=opt):
                rc, stdout = compile_and_run_stdlib_capture(
                    _SRC, timeout=15, optimization_level=opt)
                self.assertEqual(0, rc, f"-O{opt}: exited {rc}; stdout:\n{stdout}")
                self.assertEqual("19107", stdout,
                                 f"-O{opt}: wrong result {stdout!r}")

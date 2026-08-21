"""Array bounds-check elimination + fill-loop closure inlining.

The clang loop vectoriser cannot vectorise any loop containing the
`array_bounds_check` abort branch ("control flow cannot be substituted for a
select") or an indirect `fun.f(fun.o, i)` call. So, at -O3:

1. A canonical counted loop over an array — induction variable from 0 by +1,
   guard against the SAME array's length — has its per-element checks
   ELIMINATED (proved in range). Anything not provable keeps its check:
   correctness first, the check is only dropped on proof.
2. The array fill loop's init-closure call is resolved to a direct call
   (when the closure is a known captureless function) and inlined, leaving a
   straight-line loop body.
"""
from __future__ import annotations

import compiler as c

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_DOT = """namespace Test
import System

fun [tail] dotLoop(a: Array<Float>, b: Array<Float>, i: Int32, n: Int32, acc: Float): Float
  ret i == n ? acc : dotLoop(a, b, i + 1i32, n, acc + a[i] * b[i])

fun dot(a: Array<Float>, b: Array<Float>): Float
  ret dotLoop(a, b, 0i32, a.length, 0.0)

fun main(): Int
  let n = 64i32
  let a = Array<Float>(n, (i: Int32) => Float(i))
  let b = Array<Float>(n, (i: Int32) => 2.0)
  ret dot(a, b) == 4032.0 ? 0 : 1
"""

_UNPROVABLE = """namespace Test
import System

# `i` arrives from outside — nothing relates it to a.length, so the read
# keeps its bounds check (and aborts at runtime when out of range).
fun peek(a: Array<Float>, i: Int32): Float
  ret a[i]

fun main(): Int
  let a = Array<Float>(4i32, (i: Int32) => Float(i))
  ret peek(a, 9i32) == 0.0 ? 0 : 1
"""


def _emit_c(src: str, level: int = 3) -> str:
    code = c.compile([c.Input(src, "test.yafl")], use_stdlib=True,
                     just_testing=False, optimization_level=level)
    assert code, "compilation failed"
    return code


class TestBoundsElimination(TestCase):
    def test_canonical_loop_drops_checks(self):
        code = _emit_c(_DOT)
        self.assertEqual(0, code.count("array_bounds_check("),
                         "provably in-range reads should carry no bounds check")

    def test_canonical_loop_still_computes_correctly(self):
        rc, out = compile_and_run_stdlib_capture(_DOT, timeout=60,
                                                 optimization_level=3)
        self.assertEqual(0, rc, f"dot kernel failed; stdout:\n{out}")

    def test_unprovable_read_keeps_check_and_aborts(self):
        code = _emit_c(_UNPROVABLE)
        self.assertGreater(code.count("array_bounds_check("), 0,
                           "an unprovable read must keep its bounds check")
        rc, _ = compile_and_run_stdlib_capture(_UNPROVABLE, timeout=60,
                                               optimization_level=3)
        self.assertNotEqual(0, rc, "out-of-range read must still abort")


class TestFillLoopInlining(TestCase):
    def test_fill_loop_closures_are_fused(self):
        code = _emit_c(_DOT)
        # The fill loops' init closures are known captureless lambdas: after
        # the indirect call is resolved to a direct one and inlined, no
        # lambda function remains in the program at all (the entrypoint's
        # continuation call is the only legitimate indirect call left).
        self.assertNotIn("_lambdas__lambda", code,
                         "array fill loop's init closure was not fused away")

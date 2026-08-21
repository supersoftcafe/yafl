"""An inferred type that WIDENS must propagate through every receiver that
inferred from it — chained undeclared functions and destructured lets included.

`one` infers `A | None` (its match arms are `A` and `A|None`), but only settles
there a pass after its first concrete view. `two` infers from `one`; its body
AST stabilises immediately, so any widening trigger keyed on "my source AST
changed this pass" misses the later widening of `one`'s TYPE and latches `two`
too narrow — an `Incorrect type` error (or, worse, a narrow codegen slot).
Both declaration orders are covered: convergence must not depend on statement
order. The destructure case covers the same latch inside
DestructureStatement's field refinement.
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

_COMMON = """\
namespace Main
import System

class A(v: System::Int)

fun mk(b: System::Bool): A | System::None => b ? A(1) : None

fun use(x: A | System::None): System::Int => match(x)
  (a: A)            => a.v
  (n: System::None) => 0
"""

_ONE = """\
fun one(x: A | System::None, b: System::Bool) => match(x)
  (a: A)            => a
  (n: System::None) => mk(b)
"""

_TWO = """\
fun two(x: A | System::None, b: System::Bool) => one(x, b)
"""

_MAIN = """\
fun main(): System::Int => use(two(A(5), true))
"""

# A tuple whose ENTRY type widens: `one` settles at `A|None` a pass late, so
# mkpair's inferred return goes (A, Int) → (A|None, Int) across passes — the
# destructure's targets must track that widening, not latch the narrow entry.
# (No field-wise arm-join is involved: a match's heterogeneous TUPLE arms are
# a set union by design, and converge only via a declared receiver type.)
_PAIR = """\
fun mkpair(x: A | System::None, b: System::Bool) => (one(x, b), 5)

fun main(): System::Int
  let (p, q) = mkpair(A(5), true)
  ret use(p) + q
"""


class TestWideningPropagation(TestCase):
    def test_chained_inference_callee_first(self):
        self.assertEqual(5, compile_and_run_stdlib(_COMMON + _ONE + _TWO + _MAIN))

    def test_chained_inference_caller_first(self):
        self.assertEqual(5, compile_and_run_stdlib(_COMMON + _TWO + _ONE + _MAIN))

    def test_destructured_widening_rhs(self):
        # mkpair(A(5), true) → (A(5), 5); use(A(5)) = 5; 5 + 5 = 10.
        self.assertEqual(10, compile_and_run_stdlib(_COMMON + _ONE + _PAIR))

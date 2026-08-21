"""Two drops/linearity gaps found during ListBuilder adoption (07-29).

1. GENERIC Drop instances don't discharge: a `[trait]` instance
   `_DropListBuilder<T> : Drop<ListBuilder<T>>` exists in the stdlib, but an
   implicitly-dropped ListBuilder<Int> fails to compile — the drops pass
   only recognises CONCRETE instance targets.

2. A ternary whose branches mix implicit drop with consumption is rejected
   ("linear value ... used inconsistently across branches") instead of the
   dropping branch receiving its drop, the way match arms and early returns
   do.
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

# An abandoned builder on an early-return path, no explicit discard: the
# generic Drop<ListBuilder<T>> instance must fire (and unpin the cell).
_GENERIC_DROP = """namespace Test
import System

fun f(flag: Bool): Int
  let b = push(builder<Int>(), 7)
  if flag
    ret 1
  ret match(head(build(b)))
    (v: Int) => v
    ()        => 0 - 1

fun main(): Int
  ret f(true) == 1 && f(false) == 7 ? 0 : 1
"""

# The dropping branch of a ternary: consumed on one side, abandoned on the
# other — must compile, with the drop inserted on the abandoning branch.
_TERNARY_MIX = """namespace Test
import System

fun g(flag: Bool): Int
  let b = push(builder<Int>(), 9)
  ret flag ? 1 : chainLength(chain(build(b)))

fun main(): Int
  ret g(true) == 1 && g(false) == 1 ? 0 : 1
"""


class TestDropGaps(TestCase):
    _TIMEOUT = 600

    def test_generic_drop_instance_discharges(self):
        code, _out = compile_and_run_stdlib_capture(_GENERIC_DROP)
        self.assertEqual(code, 0)

    def test_ternary_branch_gets_implicit_drop(self):
        code, _out = compile_and_run_stdlib_capture(_TERNARY_MIX)
        self.assertEqual(code, 0)

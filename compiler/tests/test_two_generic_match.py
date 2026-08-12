"""OPEN COMPILER BUG (2026-08-11): a function with TWO type parameters that
nests matches over two DIFFERENTLY-instantiated generic enums (Chain<T>
inside Chain<U>) miscompiles when T != U — the built binary aborts at
runtime (match fall-through), found when the no-length sweep's
sameLen<SEntry, String> co-walk crashed the bootstrap on every input.

Root shape (confirmed by A/B repro): the ledgered nested-generic inference
gap, third form — inside a two-type-param host, an INFERRED generic call
(or match arm resolution) latches one instantiation for both type params;
spelling the type arguments explicitly compiles and runs correctly. The
workaround in bootstrap/ast/classtools.yafl spells every call with explicit
<T>/<U>; the real fix lives in inference. Remove both when this passes.
"""
from __future__ import annotations

import unittest

from tests.testutil import compile_and_run_stdlib


_PROGRAM = """
import System

fun [tail] sameLen2<T, U>(a: Chain<T>, b: Chain<U>): Bool
  ret match(a)
    (nil: ChainEnd) => b is ChainEnd
    (la: ChainLink) => match(b)
      (nil2: ChainEnd) => false
      (lb: ChainLink)  => sameLen2(la.next, lb.next)

fun main(): Int
  let xs = append(append(List<Int>(), 1), 2)
  let ys = append(append(List<String>(), "a"), "b")
  ret sameLen2(chain(xs), chain(ys)) ? 0 : 1
"""


class TestTwoGenericMatch(unittest.TestCase):
    @unittest.expectedFailure
    def test_nested_match_over_two_generic_enums(self):
        code, _ = compile_and_run_stdlib(_PROGRAM)
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()

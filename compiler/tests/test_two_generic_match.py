"""Regression test (fixed 2026-08-12): a function with TWO type parameters
that nests matches over two DIFFERENTLY-instantiated generic enums (Chain<T>
inside Chain<U>) miscompiled when T != U — the built binary aborted at
runtime (match fall-through), found when the no-length sweep's
sameLen<SEntry, String> co-walk crashed the bootstrap on every input.

Root cause: a variant arm spelled bare (`(lb: ChainLink)`) inside a generic
host survived to monomorphisation with no type arguments, and mono's
identity completion filled it by matching the enum TEMPLATE's formal names
against the host's params — `Chain`'s formal `T` latched the host's `T`
binding for BOTH matches. Fix: MatchExpression.compile stamps the subject's
type arguments onto bare variant arms in generic context too (a placeholder
that resolves in scope is the host's own param passing through), so mono
substitutes each match's arms from its own subject.
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
  let xs = prepend(1, prepend(2, List<Int>()))
  let ys = prepend("a", prepend("b", List<String>()))
  ret sameLen2(chain(xs), chain(ys)) ? 0 : 1
"""


class TestTwoGenericMatch(unittest.TestCase):
    def test_nested_match_over_two_generic_enums(self):
        self.assertEqual(0, compile_and_run_stdlib(_PROGRAM))


if __name__ == "__main__":
    unittest.main()

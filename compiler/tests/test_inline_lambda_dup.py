"""Inlining a body that CONTAINS a lambda must give each copy its own
closure class.

ast_inline can duplicate an `[inline]` function's body within one host;
each copy's bindings are renamed with a distinct $inlN suffix — so the
copies' lambdas capture DIFFERENTLY-NAMED variables and need distinct
closure classes. But the lambda-path map is keyed by line_ref (clone-
stable, deliberately: search_and_replace hands the converter clones) with
first-occurrence-wins, so both copies minted ONE name: two classes
registered under it, find_type at the New site saw 2, and codegen died
with the misleading "Failed to resolve $lambdas::..." abort. The ledger's
inliner bug B.

The fix suffixes later same-name occurrences $dup2, $dup3… in traversal
order — deterministic, and every previously-compiling program keeps its
historic names (first occurrence unsuffixed).
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_PROGRAM = """namespace Test
import System

fun [inline] withLam(l: List<Int>, s: Int): List<Int>
  if s > 3
    ret l
  ret map(l, (v: Int) => v + s)

fun outer(flag: Bool, l: List<Int>): List<Int>
  let v = withLam(flag ? withLam(l, 1) : l, 2)
  ret v

fun main(): Int
  # withLam(l,1) then withLam(.,2): 7+1+2 = 10; the else path skips both.
  let a = match(head(outer(true, prepend(7, List<Int>()))))
    (x: Int) => x
    ()        => 0 - 1
  let b = match(head(outer(false, prepend(7, List<Int>()))))
    (x: Int) => x
    ()        => 0 - 1
  ret (a == 10 && b == 9) ? 0 : 1
"""


class TestInlineLambdaDup(TestCase):
    _TIMEOUT = 600

    def test_inlined_lambda_copies_get_distinct_classes(self):
        code, _out = compile_and_run_stdlib_capture(_PROGRAM,
                                                    optimization_level=1)
        self.assertEqual(code, 0)

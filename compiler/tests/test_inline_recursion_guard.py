"""The AST inliner must not inline a function that reaches itself.

`_build_catalog` prunes call-graph cycles, but it read the call graph off a
body's STATEMENT list. `ret <expr>` — every one-line function, and any body
that is a single match or call — compiles to a block with NO statements and
the whole body in the block's trailing value, so the graph came back empty and
every cycle survived the prune: the inliner then substituted mutually
recursive functions into each other until Python's stack gave out.

The pair below calls each other — a cycle the prune must see — while still
terminating at runtime: the answer is checked by
compiler/yafl_tests/inline_recursion_guard.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c


_MUTUAL = """
namespace Main
import System

enum Sp
  enum SA(sa: Int)
  enum SB(sb: Int)

fun pick(e)
  ret match(e)
    (a: SA) => a.sa
    (b: SB) => take(b)

fun take(v: SB)
  ret pick(SA(v.sb))

fun main(): Int
  ret pick(SA(1)) + take(SB(2))
"""


class TestInlineRecursionGuard(TestCase):
    _TIMEOUT = 300

    def test_mutually_recursive_one_liners_compile(self):
        for level in (0, 1):
            with self.subTest(optimization_level=level):
                self.assertNotEqual("", compile_c(_MUTUAL, optimization_level=level))

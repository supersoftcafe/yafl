"""Mixed literal kinds in a branch under an UNTYPED receiver infer the UNION.

User ruling (2026-07-07): `let x = b ? 1.5 : 0` gives `x: Float | Int` — the
join's honest answer. A bare int literal never silently adopts Float, matching
the language-wide stance (`let y: Float = 1` is an error); the programmer
narrows with a match, writes `0.0`, or declares the type. Guards against both
regressions: literal unification sneaking in (the match over the union would
stop compiling) and the old first-branch bias (x typed Float would break the
Int arm).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib

_SRC = """\
namespace Main
import System

fun pick(b: System::Bool): System::Int
  let x = b ? 1.5 : 7
  ret match(x)
    (f: System::Float) => System::truncateToInt(f)
    (i: System::Int)   => i

fun main(): System::Int => pick(true) * 10 + pick(false)
"""


class TestMixedLiteralBranch(TestCase):
    def test_mixed_literals_infer_the_union(self):
        # pick(true) → Float arm → truncate(1.5) = 1; pick(false) → Int arm → 7.
        self.assertEqual(17, compile_and_run_stdlib(_SRC))

"""Single-caller inline fold (-O3).

A function referenced exactly once can be inlined into that sole call site
regardless of its size — folding it away costs no code growth, since the
original then becomes unreferenced and is trimmed. This pass runs only at -O3,
after the small/always passes, to collapse the residual one-shot helpers a
fused pipeline leaves behind.

`solo` below is deliberately OVER the codegen size cutoff and is NOT marked
`[inline(always)]`, so neither the small pass nor the always pass ever touches
it — only the single-caller fold removes it, and only at -O3. `shared` is the
same size but called twice, so it is never a single-caller candidate and
survives even at -O3.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase


def _solo(level: int) -> str:
    # `solo` is over the size cutoff and called exactly once.
    src = (
        "namespace Main\nimport System\n"
        "fun solo(x: System::Int): System::Int\n"
        "  ret x==0?1:x==1?2:x==2?3:x==3?4:x==4?5:x==5?6:7\n"
        "fun main(): System::Int\n"
        "  ret solo(3) + 1\n")
    return c.compile([c.Input(src, "test.yafl")], use_stdlib=True, optimization_level=level)


def _shared(level: int) -> str:
    # `shared` is the same size but called from two sites.
    src = (
        "namespace Main\nimport System\n"
        "fun shared(x: System::Int): System::Int\n"
        "  ret x==0?1:x==1?2:x==2?3:x==3?4:x==4?5:x==5?6:7\n"
        "fun main(): System::Int\n"
        "  ret shared(3) + shared(4)\n")
    return c.compile([c.Input(src, "test.yafl")], use_stdlib=True, optimization_level=level)


class TestSingleCallerFold(TestCase):
    def test_single_caller_not_folded_below_O3(self):
        # -O2: small pass leaves it (over cutoff), single-caller fold is off.
        self.assertIn("solo", _solo(2))

    def test_single_caller_folded_at_O3(self):
        # -O3: folded into its sole caller, then trimmed — symbol vanishes.
        self.assertNotIn("solo", _solo(3))

    def test_multi_caller_survives_at_O3(self):
        # Two call sites → never a single-caller candidate; over the cutoff →
        # the small pass won't take it either, so it remains at -O3.
        self.assertIn("shared", _shared(3))

"""Optimisation-level gating of `[inline(always)]`.

`[inline(always)]` bypasses the inliner size cutoff, but only at -O3 — so a chain
of marked functions (e.g. the stream `next` stages) fuses into its consumer only
in a release build, never at -O0/-O1/-O2.

NB: ordinary small functions are inlined by the AST inliner at ALL levels (that
inlining is structurally load-bearing — gating it regresses -O0), so "no inlining
at -O0/-O1" cannot be applied to them. The level gate here governs the codegen
inliner: it runs at -O2+ (small) and inlines `[inline(always)]` only at -O3.
"""
from __future__ import annotations

import compiler as c
from tests.testutil import TimedTestCase as TestCase


def _c(level: int) -> str:
    # `big` is over the inliner's size cutoff and marked [inline(always)]; called
    # once, so if it inlines it is dead and trimmed and its symbol vanishes.
    src = (
        "namespace Main\nimport System\n"
        "fun [inline(always)] big(x: System::Int): System::Int\n"
        "  ret x == 0 ? 1 : x == 1 ? 2 : x == 2 ? 3 : x == 3 ? 4 : x == 4 ? 5 : 6\n"
        "fun caller(x: System::Int): System::Int\n"
        "  ret big(x) + 1\n"
        "fun main(): System::Int\n"
        "  ret caller(3)\n")
    return c.compile([c.Input(src, "test.yafl")], use_stdlib=True, optimization_level=level)


class TestInlineAlwaysLevel(TestCase):
    def test_not_inlined_below_O3(self):
        self.assertIn("big", _c(1))   # -O1: codegen inliner off
        self.assertIn("big", _c(2))   # -O2: small-only; [inline(always)] ignored despite the mark

    def test_inlined_at_O3(self):
        self.assertNotIn("big", _c(3))  # -O3: inlined despite size, then trimmed

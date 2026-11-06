"""The `[inline]` attribute: `[inline]`, `[inline(always)]` and `[inline(never)]`.

Bare `[inline]` is a structural hint: the AST inliner inlines the function at
every level regardless of size, so the lambdas handed to an operator such as
`?>` are beta-reduced rather than lifted to closures. The codegen inliner treats
it like an unmarked function.

`[inline(always)]` bypasses the codegen inliner's size cutoff, but only at -O3 —
so a chain of marked functions (e.g. the stream `next` stages) fuses into its
consumer only in a release build, never at -O0/-O1/-O2. Below -O3 it is treated
like an unmarked function.

`[inline(never)]` keeps a function out of every inliner at every level, size
rule included. Any other argument is a compile error.

NB: ordinary small functions are inlined by the AST inliner at ALL levels (that
inlining is structurally load-bearing — gating it regresses -O0), so "no inlining
at -O0/-O1" cannot be applied to them. The level gate here governs the codegen
inliner: it runs at -O2+ (small) and inlines `[inline(always)]` only at -O3.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c, compile_errors


def _big(mark: str, level: int) -> str:
    # `big` is over the inliner's size cutoff and carries `mark`; called once,
    # so if it inlines it is dead and trimmed and its symbol vanishes.
    src = (
        "namespace Main\nimport System\n"
        f"fun {mark} big(x: System::Int): System::Int\n"
        "  ret x == 0 ? 1 : x == 1 ? 2 : x == 2 ? 3 : x == 3 ? 4 : x == 4 ? 5 : 6\n"
        "fun caller(x: System::Int): System::Int\n"
        "  ret big(x) + 1\n"
        "fun main(): System::Int\n"
        "  ret caller(3)\n")
    return compile_c(src, optimization_level=level)


def _small(mark: str, level: int) -> str:
    # `tiny` is well under every size cutoff, so unmarked it is inlined at
    # every level and trimmed.
    src = (
        "namespace Main\nimport System\n"
        f"fun {mark} tiny(x: System::Int): System::Int\n"
        "  ret x + 1\n"
        "fun main(): System::Int\n"
        "  ret tiny(3)\n")
    return compile_c(src, optimization_level=level)


class TestInlineAlwaysLevel(TestCase):
    def test_not_inlined_below_O3(self):
        self.assertIn("big", _big("[inline(always)]", 1))   # -O1: codegen inliner off
        self.assertIn("big", _big("[inline(always)]", 2))   # -O2: small-only; the mark is ignored

    def test_inlined_at_O3(self):
        self.assertNotIn("big", _big("[inline(always)]", 3))  # -O3: inlined despite size, then trimmed


class TestBareInlineIsEarly(TestCase):
    def test_inlined_at_every_level(self):
        # The AST inliner takes it despite its size, at every level.
        for level in (0, 1, 2, 3):
            self.assertNotIn("Main::big", _big("[inline]", level), f"-O{level}")


class TestInlineNever(TestCase):
    def test_unmarked_small_function_is_inlined(self):
        # The control: without the mark the size rule inlines `tiny` away.
        for level in (0, 3):
            self.assertNotIn("tiny", _small("", level), f"-O{level}")

    def test_never_keeps_a_small_function_at_every_level(self):
        for level in (0, 1, 2, 3):
            self.assertIn("tiny", _small("[inline(never)]", level), f"-O{level}")


class TestInlineArgumentErrors(TestCase):
    def _errors(self, mark: str) -> str:
        return compile_errors(
            "namespace Main\nimport System\n"
            f"fun {mark} f(x: System::Int): System::Int\n"
            "  ret x + 1\n"
            "fun main(): System::Int\n"
            "  ret f(3)\n")

    def test_unknown_word_is_an_error(self):
        self.assertIn("[inline] takes `always` or `never`", self._errors("[inline(banana)]"))

    def test_string_is_an_error(self):
        self.assertIn("[inline] takes `always` or `never`", self._errors('[inline("always")]'))

    def test_two_words_is_an_error(self):
        self.assertIn("[inline] takes `always` or `never`", self._errors("[inline(always, never)]"))

    def test_always_and_never_are_accepted(self):
        self.assertEqual("", self._errors("[inline(always)]"))
        self.assertEqual("", self._errors("[inline(never)]"))
        self.assertEqual("", self._errors("[inline]"))

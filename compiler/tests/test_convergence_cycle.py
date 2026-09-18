"""Inference that never settles is the PROGRAM's problem, not the compiler's.

Two parameters can chase each other: each `match` arm is a NARROW lower bound
for its own parameter, and each forwarding call makes the OTHER parameter's
current type an upper bound. The lower bound fits, so both narrow; next pass
the two uppers disagree, so both widen to the enum root; repeat forever.

The fixpoint must notice the repeat and say which declarations are flipping,
so the author can annotate one of them — running to the pass limit and
reporting "this is a compiler bug" blames the wrong party.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c
from tests.testutil import TimedTestCase as TestCase


_OSCILLATOR = """
namespace Test
import System

enum Sp
  enum SA(sa: Int)
  enum SB(sb: Int)

fun fa(x)
  ret match(x)
    (a: SA) => fb(x)

fun fb(y)
  ret match(y)
    (b: SB) => fa(y)

fun main(): Int
  ret fa(SA(1)) + fb(SB(2))
"""

# The same shape with one parameter declared: the cycle has a fixed point.
_SETTLED = _OSCILLATOR.replace("fun fa(x)", "fun fa(x: Sp)")


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


class TestConvergenceCycle(TestCase):
    def test_flipping_parameters_are_named(self):
        out = _errors(_OSCILLATOR)
        self.assertIn("alternates", out)
        self.assertIn("Parameter 'x' of 'Test::fa' alternates between 'SA' and 'Sp'", out)
        self.assertIn("Parameter 'y' of 'Test::fb' alternates between 'SB' and 'Sp'", out)

    def test_the_cycle_is_not_reported_as_a_compiler_bug(self):
        self.assertNotIn("compiler bug", _errors(_OSCILLATOR))

    def test_a_settling_program_is_untouched(self):
        self.assertNotIn("alternates", _errors(_SETTLED))

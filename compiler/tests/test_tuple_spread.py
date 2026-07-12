"""Spread: `*expr` splices a tuple value's fields into a tuple literal.

A tuple-literal feature, not a call feature — `f(*t)` works because a call's
argument list IS a tuple literal, and `(1, *t)` works in any tuple position.
Spliced fields are positional; written named entries may still follow, and the
receiver's defaults fill whatever remains unbound (the ordinary tuple binding).
Spreading a non-tuple value is an error.
"""
from __future__ import annotations

import contextlib
import io

import compiler as c

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _errors(src: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c.compile([c.Input(src, "test.yafl")], use_stdlib=True, just_testing=True)
    return buf.getvalue()


_RUNTIME = """namespace Test
import System

fun scale(x: Int, factor: Int = 10, bias: Int = 1): Int
  ret x * factor + bias

fun triple(): (:Int, :Int, :Int)
  ret (5, 2, 3)

fun main(): Int
  let full = (5, 2, 3)
  print(String(scale(*full)) + "\\n")
  let pair = (5, 2)
  print(String(scale(*pair)) + "\\n")
  print(String(scale(*pair, bias = 7)) + "\\n")
  print(String(scale(4, *pair)) + "\\n")
  print(String(scale(*triple())) + "\\n")
  let q: (a: Int, b: Int, c: Int) = (1, *pair)
  print(String(q.a * 100 + q.b * 10 + q.c) + "\\n")
  ret 0
"""

# scale(*full)          = 5*2+3            = 13
# scale(*pair)          = 5*2+1 (bias dflt)= 11
# scale(*pair, bias=7)  = 5*2+7            = 17
# scale(4, *pair)       = 4*5+2            = 22
# scale(*triple())      = 13
# q = (1, 5, 2)         -> 152
_RUNTIME_EXPECTED = "13\n11\n17\n22\n13\n152\n"


class TestTupleSpreadRuntime(TestCase):
    def test_spread_forms(self):
        rc, out = compile_and_run_stdlib_capture(_RUNTIME, timeout=30)
        self.assertEqual(0, rc, f"program failed; stdout:\n{out}")
        self.assertEqual(_RUNTIME_EXPECTED, out)


class TestTupleSpreadErrors(TestCase):
    def test_spread_of_non_tuple_is_rejected(self):
        errs = _errors(
            "namespace Test\nimport System\n"
            "fun f(x: Int, y: Int): Int\n  ret x + y\n"
            "fun main(): Int\n"
            "  let n = 5\n"
            "  ret f(*n, 1)\n")
        self.assertIn("spread", errs.lower())

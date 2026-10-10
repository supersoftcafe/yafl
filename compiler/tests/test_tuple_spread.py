"""Spread: `*expr` splices a tuple value's fields into a tuple literal.

A tuple-literal feature, not a call feature — `f(*t)` works because a call's
argument list IS a tuple literal, and `(1, *t)` works in any tuple position.
Spliced fields are positional; written named entries may still follow, and the
receiver's defaults fill whatever remains unbound (the ordinary tuple binding).
Spreading a non-tuple value is an error. The runtime forms are checked by
compiler/yafl_tests/tuple_spread.yafl.
"""
from __future__ import annotations



from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_errors


def _errors(src: str) -> str:
    return compile_errors(src)


class TestTupleSpreadErrors(TestCase):
    def test_spread_of_non_tuple_is_rejected(self):
        errs = _errors(
            "namespace Test\nimport System\n"
            "fun f(x: Int, y: Int): Int\n  ret x + y\n"
            "fun main(): Int\n"
            "  let n = 5\n"
            "  ret f(*n, 1)\n")
        self.assertIn("spread", errs.lower())

"""`[const]` with a non-literal initialiser is a compile error.

The runtime float and [const] checks are [test]s in
compiler/yafl_tests/strings_floats.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c


class TestConstWithNonLiteralRejected(TestCase):
    """`[const]` requires a literal value; a function-call initialiser is
    rejected at compile time. Can't share a compile with the runtime
    tests because the compile here is *expected* to fail."""

    def test_const_with_non_literal_is_rejected(self):
        src = """namespace Main
import System
fun zero(): System::Float
  ret 0.0
let [const] BAD: System::Float = zero()
fun main(): System::Int
  ret truncateToInt(BAD)
"""
        result = compile_c(src)
        self.assertEqual("", result)

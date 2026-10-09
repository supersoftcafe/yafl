"""The derived comparison operators `!=`, `<=`, `>=`.

These are generic functions in stdlib/traits.yafl defined over the comparison
interfaces (BasicEquality for `!=`, BasicCompare for `<=`/`>=`), so every
numeric type and String gets them. The parser accepts the `!=`/`<=`/`>=`
tokens at the same precedence as `<`/`==`/`>`.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _ret(expr_lines: str) -> str:
    return f"""\
import System

fun main(): System::Int
{expr_lines}
"""


class TestComparisonOperators(TestCase):
    def test_int_ne_le_ge(self):
        # A batch of Int comparisons, each contributing a distinct bit so the
        # single exit code pins every branch at once.
        src = _ret("""\
  let a: System::Int = 3
  let b: System::Int = 2
  ret (a != b ? 1 : 0)
    + (a != a ? 2 : 0)
    + (a <= b ? 4 : 0)
    + (b <= b ? 8 : 0)
    + (a >= b ? 16 : 0)
    + (b >= a ? 32 : 0)
""")
        # expect 1 + 0 + 0 + 8 + 16 + 0 = 25
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(25, rc)

    def test_logical_not(self):
        # Unary `!` on Bool — prefix operator at the same level as unary `-`.
        src = _ret("""\
  let x: System::Bool = 3 > 2
  ret (!(3 > 2) ? 1 : 0)
    + (!(2 > 3) ? 2 : 0)
    + (!x ? 4 : 0)
    + (!(1 != 1) ? 8 : 0)
""")
        # !true=0, !false=2, !true=0, !(false)=8  → 10
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(10, rc)

    def test_string_and_float(self):
        src = _ret("""\
  ret ("abc" != "abd" ? 1 : 0)
    + ("abc" <= "abc" ? 2 : 0)
    + ("abd" >= "abc" ? 4 : 0)
    + (1.5 != 2.5 ? 8 : 0)
    + (1.5 <= 1.5 ? 16 : 0)
    + (2.5 >= 1.5 ? 32 : 0)
""")
        # all true except none → 1+2+4+8+16+32 = 63
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(63, rc)

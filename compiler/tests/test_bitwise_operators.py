"""Bitwise operators `~`, `&`, `|`, `^` and the `andNot` method.

Provided by the `Bitwise<T>` interface (stdlib/traits.yafl) with an instance
per integer type (stdlib/integer.yafl); `&`/`^`/`|` parse at a precedence
between arithmetic and comparison (so `a & b == c` is `(a & b) == c`), and `~`
is unary complement. `andNot(a, b)` is `a & ~b` — the parser folds that
spelling onto the single-pass method. Float and String have no Bitwise instance.
"""
from __future__ import annotations

import pyast.expression as e
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


def _ret(expr_lines: str) -> str:
    return f"""\
import System

fun main(): System::Int
{expr_lines}
"""


class TestBitwiseOperators(TestCase):
    def test_bigint(self):
        src = _ret("""\
  let a: System::Int = 12
  let b: System::Int = 10
  let neg: System::Int = -1
  ret ((a & b) == 8 ? 1 : 0)
    + ((a | b) == 14 ? 2 : 0)
    + ((a ^ b) == 6 ? 4 : 0)
    + (andNot(a, b) == 4 ? 8 : 0)
    + ((neg & 5) == 5 ? 16 : 0)
    + ((neg ^ 5) == -6 ? 32 : 0)
""")
        # all true → 1+2+4+8+16+32 = 63
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(63, rc)

    def test_bigint_heap_value(self):
        # A literal beyond the tagged range exercises the heap (full) path.
        src = _ret("""\
  let big: System::Int = 123456789012345678901234567890
  ret ((big & big) == big ? 1 : 0)
    + ((big | 0) == big ? 2 : 0)
    + ((big ^ big) == 0 ? 4 : 0)
    + (andNot(big, big) == 0 ? 8 : 0)
""")
        # 1+2+4+8 = 15
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(15, rc)

    def test_int32(self):
        src = _ret("""\
  let x: System::Int32 = 0xF0F0i32
  let y: System::Int32 = 0x0FF0i32
  ret ((x & y) == 0x00F0i32 ? 1 : 0)
    + ((x | y) == 0xFFF0i32 ? 2 : 0)
    + ((x ^ y) == 0xFF00i32 ? 4 : 0)
    + (andNot(x, y) == 0xF000i32 ? 8 : 0)
""")
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(15, rc)

    def test_precedence_below_comparison(self):
        # `a & b == 8` must parse as `(a & b) == 8`, not `a & (b == 8)`.
        src = _ret("""\
  let a: System::Int = 12
  let b: System::Int = 10
  ret a & b == 8 ? 100 : 0
""")
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(100, rc)

    def test_invert_and_andnot(self):
        src = _ret("""\
  let a: System::Int = 12
  let b: System::Int = 10
  let neg: System::Int = -1
  ret (~a == -13 ? 1 : 0)
    + (~neg == 0 ? 2 : 0)
    + ((a & ~b) == andNot(a, b) ? 4 : 0)
    + ((a & ~b) == 4 ? 8 : 0)
    + ((~a & b) == 2 ? 16 : 0)
""")
        # andNot(a,b)=4 but ~a & b = b & ~a = andNot(b,a) = 2, so 1+2+4+8+16 = 31
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(31, rc)

    def test_invert_int32(self):
        src = _ret("""\
  let x: System::Int32 = 0x0FF0i32
  ret ~x == -4081i32 ? 1 : 0
""")
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(1, rc)

    def test_shifts_bigint(self):
        src = _ret("""\
  ret ((1 << 10) == 1024 ? 1 : 0)
    + ((1024 >> 3) == 128 ? 2 : 0)
    + (((0 - 7) >> 1) == -4 ? 4 : 0)
    + ((1 << 64) == 18446744073709551616 ? 8 : 0)
""")
        # `>>` is arithmetic (floor): -7 >> 1 == -4. 1+2+4+8 = 15
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(15, rc)

    def test_shifts_int32(self):
        src = _ret("""\
  let x: System::Int32 = 1i32
  ret ((x << 4i32) == 16i32 ? 1 : 0)
    + (((0i32 - 16i32) >> 2i32) == -4i32 ? 2 : 0)
    + ((1i32 << 32i32) == 1i32 ? 4 : 0)
""")
        # arithmetic shift + count masked to width (32 & 31 == 0). 1+2+4 = 7
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(7, rc)

    def test_shift_precedence(self):
        # `1 + 1 << 4` is `(1 + 1) << 4` == 32; `1 << 3 == 8` is `(1 << 3) == 8`.
        src = _ret("""\
  ret ((1 + 1 << 4) == 32 ? 1 : 0) + ((1 << 3 == 8) ? 2 : 0)
""")
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(3, rc)

    def test_andnot_fold_at_parse_time(self):
        # `a & ~b` and (by commutativity) `~a & b` fold to a single andNot call,
        # not a complement-then-and; both-inverted and plain stay as-is.
        import parsing.parser as pp
        from parsing.tokenizer import tokenize

        def head(src: str) -> str:
            expr = pp.parse_expression(tokenize(src, "file")).value
            self.assertIsInstance(expr, e.CallExpression)
            return expr.function.name

        self.assertEqual("andNot", head("a & ~b"))   # andNot(a, b)
        self.assertEqual("andNot", head("~a & b"))    # andNot(b, a)
        self.assertEqual("andNot", head("~a & ~b"))   # andNot(~a, b) == ~a & ~b
        self.assertEqual("`&`", head("a & b"))        # no fold
        self.assertEqual("`~`", head("~a"))           # plain complement

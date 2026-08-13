"""A returned value whose type matches NO member of the declared result union
must be a check error.

Regression for a silent wrong-shape acceptance (found 2026-08-12 during the
no-length sweep): a fun DECLARED `(ls: List<String>, n: Int)|None` whose body
returned a helper's `List<String>|None` was accepted by BOTH compilers and the
mis-shaped value flowed to runtime. Root cause: `needs_conversion` treated ANY
two distinct union ids as a widening, so `converted()` wrapped the value in a
ConvertExpression whose get_type reports the TARGET — the receiver's own
"Incorrect type" check then compared declared against declared and could
never fire. Union→union now wraps only when every source member is assignable
into the target (a genuine widening); anything else reaches the receiver raw
and is reported there.
"""
from __future__ import annotations

import io
import contextlib

import compiler as c
from tests.testutil import TimedTestCase as TestCase


_BAD = """
import System

fun helper(): List<String>|None
  ret append(List<String>(), "x")

fun bad(): (ls: List<String>, n: Int)|None
  ret helper()

fun main(): Int
  ret match(bad())
    (tup: (ls: List<String>, n: Int)) => tup.n
    ()                                => 0
"""

_GOOD_WIDENING = """
import System

fun helper(): List<String>|None
  ret append(List<String>(), "x")

fun widened(): List<String>|None|Bool
  ret helper()

fun main(): Int
  ret match(widened())
    (ls: List<String>) => 0
    (b: Bool)          => 1
    ()                 => 2
"""


class TestUnionReturnShape(TestCase):
    def test_wrong_shape_through_union_is_a_check_error(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = c.compile([c.Input(_BAD, "t.yafl")], use_stdlib=True)
        self.assertEqual("", result)
        self.assertIn("incorrect type", buf.getvalue().lower())

    def test_genuine_union_widening_still_compiles(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = c.compile([c.Input(_GOOD_WIDENING, "t.yafl")], use_stdlib=True)
        self.assertNotEqual("", result, f"expected clean compile, got:\n{buf.getvalue()}")

"""Tests for nested function declarations inside function bodies."""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase

import compiler as c
from tests.testutil import compile_and_run, compile_and_run_stdlib


_PREAMBLE = """\
namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", left, right)
fun `-`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_sub", left, right)
fun `*`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_mul", left, right)
"""


def _compile(source: str) -> str:
    return c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)


def _run(source: str) -> int:
    exit_code, _ = compile_and_run(source)
    return exit_code


class TestNestedFunctions(TestCase):

    def test_simple_nested_function(self):
        """Non-recursive nested function compiles and produces the correct result."""
        self.assertEqual(7, _run(_PREAMBLE + """\
fun main(): System::Int
    fun double(x: System::Int): System::Int
        ret x + x
    ret double(3) + 1
"""))

    def test_nested_function_is_inlined(self):
        """A small non-recursive nested function is inlined: its name vanishes from the C output."""
        c_code = _compile(_PREAMBLE + """\
fun main(): System::Int
    fun double(x: System::Int): System::Int
        ret x + x
    ret double(3) + 1
""")
        self.assertIsNotNone(c_code)
        self.assertNotIn("double", c_code)

    def test_nested_function_multiple_call_sites(self):
        """A nested function called at several sites produces the correct result."""
        self.assertEqual(10, _run(_PREAMBLE + """\
fun main(): System::Int
    fun inc(n: System::Int): System::Int
        ret n + 1
    ret inc(inc(inc(inc(inc(5)))))
"""))

    def test_nested_function_multiple_call_sites_inlined(self):
        """After multi-site inlining the nested function name is absent from the C output."""
        c_code = _compile(_PREAMBLE + """\
fun main(): System::Int
    fun increment(n: System::Int): System::Int
        ret n + 1
    ret increment(increment(increment(5)))
""")
        self.assertIsNotNone(c_code)
        self.assertNotIn("increment", c_code)

    def test_nested_function_captures_outer_let(self):
        """A nested function may reference a let declared earlier in the enclosing body."""
        self.assertEqual(42, _run(_PREAMBLE + """\
fun main(): System::Int
    let base: System::Int = 40
    fun add_base(x: System::Int): System::Int
        ret x + base
    ret add_base(2)
"""))

    def test_nested_function_captures_outer_let_inlined(self):
        """A nested function that captures an outer let is still inlined away."""
        c_code = _compile(_PREAMBLE + """\
fun main(): System::Int
    let base: System::Int = 40
    fun add_base(x: System::Int): System::Int
        ret x + base
    ret add_base(2)
""")
        self.assertIsNotNone(c_code)
        self.assertNotIn("add_base", c_code)

    def test_two_independent_nested_functions(self):
        """Two independent nested functions both inline and produce the correct result."""
        self.assertEqual(15, _run(_PREAMBLE + """\
fun main(): System::Int
    fun double(x: System::Int): System::Int
        ret x + x
    fun triple(x: System::Int): System::Int
        ret x + x + x
    ret double(3) + triple(3)
"""))

    def test_two_independent_nested_functions_inlined(self):
        """Small non-recursive nested functions are inlined away (absent from C output)."""
        c_code = _compile(_PREAMBLE + """\
fun main(): System::Int
    fun doubler(x: System::Int): System::Int
        ret x + x
    fun tripler(x: System::Int): System::Int
        ret x + x + x
    ret doubler(3) + tripler(3)
""")
        self.assertIsNotNone(c_code)
        self.assertNotIn("doubler", c_code)

    def test_nested_calls_nested(self):
        """A nested function can call another nested function defined before it."""
        self.assertEqual(12, _run(_PREAMBLE + """\
fun main(): System::Int
    fun double(x: System::Int): System::Int
        ret x + x
    fun quadruple(x: System::Int): System::Int
        ret double(double(x))
    ret quadruple(3)
"""))

    def test_sibling_calls_capturing_helper(self):
        """A non-capturing nested fn that calls a capturing sibling must stay
        in the parent body alongside it — naively hoisting it to global scope
        leaves a dangling reference to the now-closure-bound sibling.
        """
        src = """\
import System
fun outer(f: String, pos: Int): Int
  fun capLen(extra: Int): Int
    ret length(f) + extra
  fun caller(x: Int): Int
    ret capLen(x)
  ret caller(pos)

fun main(): Int
  ret outer("hi", 3)
"""
        self.assertEqual(5, compile_and_run_stdlib(src))

    def test_mutual_recursion_in_capturing_nested_fns(self):
        """Two mutually-recursive nested fns that both capture an outer var
        must share a single closure object — independent closures would each
        capture a null reference to the other's not-yet-constructed binding.
        """
        src = """\
import System
fun outer(limit: Int, n: Int): Int
  fun isEven(x: Int): Int
    ret x < 1 ? 1 : (x > limit ? 99 : isOdd(x - 1))
  fun isOdd(x: Int): Int
    ret x < 1 ? 0 : (x > limit ? 99 : isEven(x - 1))
  ret isEven(n)

fun main(): Int
  ret outer(100, 4)
"""
        self.assertEqual(1, compile_and_run_stdlib(src))

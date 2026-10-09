"""Nested function declarations inside function bodies: small non-recursive
helpers are inlined away, so their names vanish from the C.

The runtime behaviour of nested functions (in free functions, inside closures,
and inside class members) is checked by compiler/yafl_tests/nested_functions.yafl.

Runtime behaviour is checked by compiler/yafl_tests/nested_functions.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase

import compiler as c


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


class TestNestedFunctionsInlined(TestCase):

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

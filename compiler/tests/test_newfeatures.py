from unittest import TestCase

import compiler as c
from tests.testutil import compile_and_run


def _compile_and_run(content: str, timeout: int = 5) -> int:
    code, _ = compile_and_run(content, timeout)
    return code


class TestNewFeatures(TestCase):
    """Tests for features not yet fully implemented or known to fail."""

    def test_pipeline(self):
        content = """namespace System
typealias Int : __builtin_type__<bigint>
fun main(): System::Int
    ret 1 |> (a: System::Int) => a
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_pipeline2(self):
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)
fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("add", left, right)
fun main(): System::Int
    ret (1, 2) |> (a: System::Int, b: System::Int) => a+b
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_none(self):
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias None : ()
let None:None = ()
fun testNone(value:None):Int
  ret 1
fun main(): Int
  ret testNone(None)
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_union_type(self):
        """Union type T|None should parse and compile; a function accepting String|None must work."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
typealias None : ()
let None:None = ()

fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)

fun maybe_print(in: String|None): System::Int
    ret __builtin_op__<bigint>("print", in)

fun main(): System::Int
    ret maybe_print("Hello")
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_match(self):
        """match expression should dispatch on the runtime variant of a union type."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
typealias None : ()
let None:None = ()

fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)

fun unwrap(in: String|None): System::Int
    ret match(in)
        (x:String) => print(x)
        (x:None) => 0

fun main(): System::Int
    ret unwrap("Hello")
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_bind_operator(self):
        """?> parses as a call operator: A ?> B desugars to `?>`(A, B)."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)

fun `?>`(val: System::String, f: (:System::String):System::Int): System::Int
    ret f(val)

fun main(): System::Int
    ret "Hello"
        ?> System::print
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_action_statement(self):
        """Bare expression statement: effectful call result is discarded, return value is unaffected."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun sideEffect(x: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", x, x)

fun main(): System::Int
    sideEffect(99)
    ret 7
"""
        code = _compile_and_run(content)
        self.assertEqual(7, code)

    def test_bind_operator_runs(self):
        """?> operator compiles and the binary produces the expected exit code."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun `?>`(val: System::Int, f: (:System::Int):System::Int): System::Int
    ret f(val)

fun double(x: System::Int): System::Int
    ret __builtin_op__<bigint>("integer_add", x, x)

fun main(): System::Int
    ret 3 ?> double
"""
        code = _compile_and_run(content)
        self.assertEqual(6, code)

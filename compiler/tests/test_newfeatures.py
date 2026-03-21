from unittest import TestCase

import compiler as c


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
    ret match in
        (x:String) => print(x)
        (x:None) => 0

fun main(): System::Int
    ret unwrap("Hello")
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_bind_operator(self):
        """The ?> bind operator should thread a T|None value through a function returning T|None."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>
fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)

fun main(): System::Int
    ret "Hello"
        ?> System::print
"""

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

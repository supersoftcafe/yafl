
from unittest import TestCase

import re

import tokenizer as t
import compiler as c
import parser as p

class TestTraits(TestCase):
    def test_stdlib_string_op(self):
        content = ("import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let result = System::Char(48) + System::Char(49)\n"
                   "    ret System::print(\"Fred\")\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_simple_trait(self):
        content = """namespace System

    typealias Int : __builtin_type__<bigint>

    interface Add<TValue>
        fun `+`(l:TValue,r:TValue): TValue

    class AddInt() : Add<System::Int>
        fun `+`(l:System::Int,r:System::Int): System::Int
            ret __builtin_op__<bigint>("add", l, r)

    let [trait] _add_int: AddInt = AddInt()

    fun testIt<TVal>(l:TVal,r:TVal): TVal where Add<TVal>
        ret l + r

    fun main(): System::Int
        ret testIt<System::Int>(1,2)
    """
        parts = re.split(r'\n\s*\n', content)
        for i in range(len(parts)):
            joined = '\n\n'.join(parts[:i + 1])
            result = p.parse(t.tokenize(joined, "file"))
            # print(result)
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_inherited_trait_method_disambiguation(self):
        # When interface Math<TVal> extends Plus<TVal>, and a function has
        # `where Math<Int> | Plus<String>`, there are two `+` in scope:
        # one for Int (inherited via Math->Plus<Int>) and one for String.
        # Disambiguation by argument type must work — `"a" + "b"` should
        # unambiguously resolve to string `+`.
        content = """namespace System
    typealias Int : __builtin_type__<bigint>
    typealias String : __builtin_type__<str>

    interface Plus<TVal>
        fun `+`(left: TVal, right: TVal): TVal

    interface Math<TVal> : Plus<TVal>
        fun `*`(left: TVal, right: TVal): TVal

    class MathInt() : Math<System::Int>
        fun `+`(left: System::Int, right: System::Int): System::Int
            ret __builtin_op__<bigint>("integer_add", left, right)
        fun `*`(left: System::Int, right: System::Int): System::Int
            ret __builtin_op__<bigint>("integer_mul", left, right)

    class PlusString() : Plus<System::String>
        fun `+`(left: System::String, right: System::String): System::String
            ret __builtin_op__<str>("string_append", left, right)

    let [trait] _math_int: MathInt = MathInt()
    let [trait] _plus_string: PlusString = PlusString()

    fun testIt(s: System::String): System::String where Math<System::Int> | Plus<System::String>
        ret s + "!"

    fun main(): System::Int
        ret 0
    """
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)

    def test_trait_result_passed_to_typed_function(self):
        # A trait method returns TVal; at check time the return type is unresolved
        # (NamedSpec("TVal")) in the calling context. Passing it to a function that
        # expects the concrete type should not produce "Parameters are not assignment
        # compatible" — trivially_assignable_from returning None (unknown) must not
        # be treated as False (incompatible).
        content = """namespace System
    typealias Int : __builtin_type__<bigint>

    interface Scale<TVal>
        fun double(x: TVal): TVal

    class ScaleInt() : Scale<System::Int>
        fun double(x: System::Int): System::Int
            ret __builtin_op__<bigint>("integer_add", x, x)

    let [trait] _scale_int: ScaleInt = ScaleInt()

    fun wrap(x: System::Int): System::Int
        ret x

    fun testIt(x: System::Int): System::Int where Scale<System::Int>
        ret wrap(double(x))

    fun main(): System::Int
        ret testIt(5)
    """
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)



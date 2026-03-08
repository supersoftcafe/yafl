from unittest import TestCase

import re


import tokenizer as t
import compiler as c
import parser as p


class Test(TestCase):
    def test_add(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "\n"
                   "fun `+`(left: System::Int32, right: System::Int32): System::Int32\n"
                   "    ret __builtin_op__<int32>(\"add\", left, right)\n # This add doesn't really exist"
                   "\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret 1 + 2 # Resolve correct plus method\n")

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_declare_let(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let x: System::Int = 2\n"
                   "    ret x\n")

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_declare_class(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "\n"
                   "class Pair(left: System::Int, right: System::Int)\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let x: System::Pair = System::Pair(1, 2)\n"
                   "    ret x.right\n")

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_string_literal(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias String : __builtin_type__<str>\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "\n"
                   "fun `+`(left: System::String, right: System::String): System::String\n"
                   "    ret __builtin_op__<str>(\"append\", left, right)\n"
                   "\n"
                   "fun print(str: System::String): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"print\", str)\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    System::print(\"fred and bill\" + \", bert\")\n"
                   "    ret 0\n")

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_lambda(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias String : __builtin_type__<str>\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
                   "\n"
                   "fun `+`(left: System::String, right: System::String): System::String\n"
                   "    ret __builtin_op__<str>(\"append\", left, right)\n"
                   "\n"
                   "fun do10(f: (:System::Int):System::Int):System::Int\n"
                   "    ret f(10)\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let v: System::Int = 20\n"
                   "    ret do10((x: System::Int) => x + v)\n")

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_class_with_function(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias String : __builtin_type__<str>\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "\n"
                   "class Class(value: System::Int)\n"
                   "    fun doit(): System::Int\n"
                   "        ret value\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let v: System::Class = Class(27)\n"
                   "    ret v.doit()\n"
                   )

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)


    def test_inherit(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"integer_add\", left, right)\n"
                   "\n"
                   "interface Parent1\n"
                   "    fun doit(): System::Int\n"
                   "        ret 10\n"
                   "    fun doit(other: System::Int): System::Int\n"
                   "        ret other\n"
                   "\n"
                   "interface Parent2\n"
                   "    fun doit(): System::Int\n"
                   "        ret 20\n"
                   "\n"
                   "class Child(value: System::Int): Parent1|Parent2\n"
                   "    fun doit(other: System::Int): System::Int\n"
                   "        ret other + value\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let v: System::Parent1 = Child(27)\n"
                   "    ret v.doit()\n"
                   )

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_ternery(self):
        content = ("namespace System\n"
                   "typealias Bool : __builtin_type__<bool>\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "fun `>`(left: System::Int, right: System::Int): System::Bool\n"
                   "    ret __builtin_op__<bool>(\"integer_test_gt\", left, right)\n"
                   "fun main(): System::Int\n"
                   "    ret 0 > 0 ? 1 : 2\n")

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_stdlib(self):
        content = ("import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret System::print(System::Char(48) + System::Char(49))\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_stdlib2(self):
        content = ("import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret System::print(\"Hello\")\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_pipeline(self):
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "fun main(): System::Int\n"
                   "    ret 1 |> (a: System::Int) => a\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_pipeline2(self):
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "typealias String : __builtin_type__<str>\n"
                   "fun print(str: System::String): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"print\", str)\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
                   "fun main(): System::Int\n"
                   "    ret (1, 2) |> (a: System::Int, b: System::Int) => a+b\n")
                   # "    ret (\"Hello\", \" there\", \"\n\") |> (a,b,c) => System::print(a + b + c)\n"

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_pipeline3(self):
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "typealias String : __builtin_type__<str>\n"
                   "fun print(str: System::String): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"print\", str)\n"
                   "fun main(): System::Int\n"
                   "    ret \"Hello\" |> System::print\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_pipeline4(self):
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "typealias String : __builtin_type__<str>\n"
                   "fun print(str: System::String): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"print\", str)\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
                   "fun `+`(left: System::String, right: System::String): System::String\n"
                   "    ret __builtin_op__<str>(\"append\", left, right)\n"
                   "fun main(): System::Int\n"
                   "    ret (\"Hello\", \"there\", \"\\n\") |> (a: System::String, b: System::String, c: System::String) => System::print(a + b + c)\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_complex_init(self):
        content = """
namespace System

typealias String : __builtin_type__<str>
typealias Int : __builtin_type__<bigint>

fun `+`(left: System::Int, right: System::Int): System::Int
    ret __builtin_op__<bigint>("add", left, right)

fun `+`(left: System::String, right: System::String): System::String
    ret __builtin_op__<str>("append", left, right)

fun print(str: System::String): System::Int
    ret __builtin_op__<bigint>("print", str)

fun append(a: System::String, b: System::String):System::String
    ret a + b
let x: System::String = append("one", "two")
fun main(): System::Int
    ret System::print(x)
"""

        result = c.compile([c.Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_simple_generic_function(self):
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "fun doNothing<TValue>(value: TValue): TValue\n"
                   "    ret value\n"
                   "fun main(): System::Int\n"
                   "    ret doNothing<System::Int>(1)\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_simple_interface(self):
        content = """namespace System
typealias Int : __builtin_type__<bigint>
interface IAdd
    fun `+`(l:System::Int,r:System::Int): System::Int
fun main(): System::Int
    ret 0
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
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

    def test_bind(self):
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "typealias String : __builtin_type__<str>\n"
                   "fun print(str: System::String): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"print\", str)\n"
                   "\n"
                   "fun bind(in: String|None, func: (String):Int): Int|None\n"
                   "    ret match in\n"
                   "        (x:String) => func(x)\n"
                   "        (x:None) => None\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret \"Hello\"\n"
                   "        ?> System::print\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)
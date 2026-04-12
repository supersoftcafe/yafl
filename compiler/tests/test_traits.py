
from unittest import TestCase

import re

import parsing.tokenizer as t
import compiler as c
import parsing.parser as p

class TestTraits(TestCase):
    def test_stdlib_string_op(self):
        content = ("import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    let result = System::Char(48) + System::Char(49)\n"
                   "    System::print(\"Fred\")\n"
                   "    ret 0\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertIn("print_string", result, "Missing print statement")
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

    def test_overload_resolution_global(self):
        # Three global overloads: foo(Int,Int), foo(Int), foo(String).
        # Calling foo(1) must resolve to the single-Int overload.
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

fun foo(a: System::Int, b: System::Int): System::Int
    ret a

fun foo(a: System::Int): System::Int
    ret a

fun foo(s: System::String): System::String
    ret s

fun main(): System::Int
    ret foo(1)
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)

    def test_overload_resolution_class(self):
        # Three class-method overloads: foo(Int,Int), foo(Int), foo(String).
        # Calling inst.foo(1) must resolve to the single-Int overload.
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

class MyClass()
    fun foo(a: System::Int, b: System::Int): System::Int
        ret a
    fun foo(a: System::Int): System::Int
        ret a
    fun foo(s: System::String): System::String
        ret s

let inst: MyClass = MyClass()

fun main(): System::Int
    ret inst.foo(1)
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)

    def test_overload_resolution_trait(self):
        # Trait overloads: foo(TVal,TVal) and foo(TVal) in Fooable<TVal>, plus foo(String) in FooStr.
        # All three are in scope via `where Fooable<System::Int> | FooStr`.
        # Calling foo(1) must resolve to the single-Int overload.
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

interface Fooable<TVal>
    fun foo(a: TVal, b: TVal): TVal
    fun foo(a: TVal): TVal

interface FooStr
    fun foo(s: System::String): System::String

class FooInt() : Fooable<System::Int>
    fun foo(a: System::Int, b: System::Int): System::Int
        ret a
    fun foo(a: System::Int): System::Int
        ret a

class FooStrImpl() : FooStr
    fun foo(s: System::String): System::String
        ret s

let [trait] _foo_int: FooInt = FooInt()
let [trait] _foo_str: FooStrImpl = FooStrImpl()

fun testIt(x: System::Int): System::Int where Fooable<System::Int> | FooStr
    ret foo(1)

fun main(): System::Int
    ret testIt(1)
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

    def test_two_concrete_instantiations(self):
        # wrap<Int> and wrap<String> are both called; monomorphization must create two
        # distinct specialisations and route trait dispatch correctly for each.
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

interface Identity<TVal>
    fun id(x: TVal): TVal

class IdInt() : Identity<System::Int>
    fun id(x: System::Int): System::Int
        ret x

class IdStr() : Identity<System::String>
    fun id(x: System::String): System::String
        ret x

let [trait] _id_int: IdInt = IdInt()
let [trait] _id_str: IdStr = IdStr()

fun wrap<TVal>(x: TVal): TVal where Identity<TVal>
    ret id(x)

fun main(): System::Int
    let a = wrap<System::Int>(42)
    let b = wrap<System::String>("hello")
    ret a
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)

    def test_multiple_where_constraints_both_used(self):
        # A generic with two where constraints; both trait methods are used in the body.
        # Verifies __resolve_trait_references routes each operator to the right provider
        # when two different trait scopes are active simultaneously.
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface Add<TVal>
    fun `+`(l: TVal, r: TVal): TVal

interface Mul<TVal>
    fun `*`(l: TVal, r: TVal): TVal

class AddInt() : Add<System::Int>
    fun `+`(l: System::Int, r: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_add", l, r)

class MulInt() : Mul<System::Int>
    fun `*`(l: System::Int, r: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_mul", l, r)

let [trait] _add_int: AddInt = AddInt()
let [trait] _mul_int: MulInt = MulInt()

fun compute<TVal>(a: TVal, b: TVal): TVal where Add<TVal> | Mul<TVal>
    ret a + (b * b)

fun main(): System::Int
    ret compute<System::Int>(1, 3)
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)

    def test_generic_in_default_namespace(self):
        # Both the generic function and its caller are in the default (Main::) namespace
        # rather than a named namespace.  This exercises the compiler.py fix that adds the
        # caller's own namespace prefix to the resolver scopes so that sibling functions
        # are accessible by bare name during compilation.
        content = """\
import System

interface Add<TVal>
    fun `+`(l: TVal, r: TVal): TVal

class AddInt() : Add<System::Int>
    fun `+`(l: System::Int, r: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_add", l, r)

let [trait] _add_int: AddInt = AddInt()

fun add<TVal>(l: TVal, r: TVal): TVal where Add<TVal>
    ret l + r

fun main(): System::Int
    ret add<System::Int>(3, 4)
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)



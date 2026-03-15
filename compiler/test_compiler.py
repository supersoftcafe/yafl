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


class TestNewFeatures(TestCase):
    """Tests for features not yet fully implemented or known to fail."""

    def test_stdlib(self):
        content = ("import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret System::print(System::Char(48) + System::Char(49))\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
        print(result)

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

    def test_static_init_simple(self):
        """NewObject with all-literal fields should become a static global."""
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
                   "class Pair(left: System::Int, right: System::Int)\n"
                   "fun getPair(): System::Int\n"
                   "    let p: Pair = Pair(1, 2)\n"
                   "    ret p.left + p.right\n"
                   "fun main(): System::Int\n"
                   "    ret getPair()\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # After static-init optimization, Pair(1,2) should be a C static global, not heap-allocated
        self.assertNotIn("object_create(obj_System", result)
        print(result)

    def test_static_init_global_let(self):
        """Global let with all-literal fields should become a C static initializer (no lazy-init)."""
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
                   "class Config(value: System::Int)\n"
                   "let defaultConfig: Config = Config(42)\n"
                   "fun main(): System::Int\n"
                   "    ret defaultConfig.value\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # After optimization, no runtime lazy-init call should be needed
        self.assertNotIn("lazy_global_init_complete", result)
        print(result)

    def test_dead_store_elim_removes_unused_trait_impls(self):
        """After inlining, trait objects whose methods are all inlined away should be eliminated.

        In `ret 1 + 3`, the BasicMath trait object is used only to resolve `+` at compile
        time. After inlining, the `this` StackVar holding the trait object becomes dead.
        Dead store elimination should remove it, which lets trim cascade and eliminate the
        entire vtable and all method implementations except the inlined call site.
        """
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface BasicPlus<TVal>
    fun `+`(left: TVal, right: TVal): TVal

interface BasicMath<TVal> : BasicPlus<TVal>
    fun `-`(left: TVal, right: TVal): TVal

class _BasicMathInt() : BasicMath<System::Int>
    fun `+`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_add", left, right)
    fun `-`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_sub", left, right)

let [trait] int_trait: _BasicMathInt = _BasicMathInt()

fun main(): System::Int where BasicMath<System::Int>
    ret 1 + 3
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # No vtable declarations — the entire _BasicMathInt implementation is dead
        self.assertNotIn("VTABLE_DECLARE", result)
        # No function bodies for the trait methods
        self.assertNotIn("integer_sub", result)

    def test_dead_store_elim_keeps_used_operations(self):
        """Dead store elimination must not remove operations whose results are observable.

        Both `+` and `-` are used in the return value.  After dead-store elimination the
        two direct C-level integer calls (`integer_add`, `integer_sub`) must still appear
        in the generated output; only the unreachable vtable method bodies for unused
        interface slots are allowed to disappear.
        """
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface BasicMath<TVal>
    fun `+`(left: TVal, right: TVal): TVal
    fun `-`(left: TVal, right: TVal): TVal

class _BasicMathInt() : BasicMath<System::Int>
    fun `+`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_add", left, right)
    fun `-`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_sub", left, right)

let [trait] int_trait: _BasicMathInt = _BasicMathInt()

fun main(): System::Int where BasicMath<System::Int>
    let a: System::Int = 10 + 3
    ret a - 2
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # Both arithmetic primitives must survive — they are the actual computation
        self.assertIn("integer_add", result)
        self.assertIn("integer_sub", result)

    def test_dead_store_elim_preserves_live_assignments(self):
        """StackVar assignments that ARE read must not be removed.

        In `ret 1 + 3`, the inlined code assigns integer-literal globals to StackVars
        (`left = p1`, `right = p3`) and then READS them as arguments to integer_add.
        Those assignments are live, not dead stores.

        If the pass incorrectly treated them as dead, each literal global would become
        unreferenced, be eliminated by the trim pass, and disappear from the C output.
        The assertions below would then fail, catching the bug.
        """
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface BasicPlus<TVal>
    fun `+`(left: TVal, right: TVal): TVal

class _BasicPlusInt() : BasicPlus<System::Int>
    fun `+`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_add", left, right)

let [trait] int_trait: _BasicPlusInt = _BasicPlusInt()

fun main(): System::Int where BasicPlus<System::Int>
    ret 1 + 3
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # Both integer literal globals must survive — their StackVar assignments are live
        # (read as arguments to integer_add).  Absence of either means a live store was dropped.
        self.assertIn("INTEGER_LITERAL_1(0, 1)", result)
        self.assertIn("INTEGER_LITERAL_1(0, 3)", result)


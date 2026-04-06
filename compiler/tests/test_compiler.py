from unittest import TestCase
from unittest.mock import patch

import re
import dataclasses


import parsing.tokenizer as t
import compiler as c
import parsing.parser as p
import pyast.statement as s
import parsing.tokenizer as tok


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

    def test_iterate_and_compile_raises_on_non_convergence(self):
        """__iterate_and_compile must raise RuntimeError with a descriptive message when
        the compile loop fails to converge, rather than recursing without bound."""
        line_ref = tok.LineRef("test.yafl", 0, 0)

        # A Statement whose compile() always returns a structurally different fresh copy
        # (counter increments), so new_statements != statements every iteration.
        call_count = {"n": 0}

        @dataclasses.dataclass
        class _DivergingStatement(s.Statement):
            counter: int = 0

            def compile(self, resolver, func_ret_type):
                call_count["n"] += 1
                return dataclasses.replace(self, counter=call_count["n"]), []

            def check(self, resolver, func_ret_type):
                return []

        stmt = _DivergingStatement(line_ref=line_ref, counter=0)

        # __iterate_and_compile is a module-level function stored under the literal key
        # "__iterate_and_compile" in the module dict (no name mangling at module scope).
        iterate_fn = c.__dict__["__iterate_and_compile"]

        # The fixed code must raise RuntimeError with a message that includes the iteration
        # count (not RecursionError from unbounded recursion).
        with self.assertRaises(RuntimeError) as ctx:
            iterate_fn([stmt])
        self.assertIn("iteration", str(ctx.exception).lower())


class TestTaskConvention(TestCase):
    """Compile-level checks for the task-based calling convention.

    These tests verify that the code generator produces well-formed C for
    scenarios that are structurally important but hard to exercise purely at
    runtime (e.g. TaskWrapper for primitive returns, Void state machines).
    """

    def test_int32_return_with_state_machine_compiles(self):
        """A function returning Int32 (fixed-width primitive) with a non-tail
        call triggers TaskWrapper wrapping of the return type.  Verifies that
        the generated C is accepted by clang (compile-only; no binary run).

        Int32 literals are not natively supported in yafl test syntax, so
        __builtin_op__<int32>("integer_literal", N) is used to produce one."""
        import subprocess, tempfile, os
        src = """\
namespace System
typealias Int : __builtin_type__<bigint>
typealias Int32 : __builtin_type__<int32>

fun [foreign("get_int32_value")] get_int32(): Int32

fun identity(x: Int32): Int32
    ret x

fun double_call(x: Int32): Int32
    let a: Int32 = identity(x)
    ret a

fun main(): Int
    let r: Int32 = double_call(get_int32())
    ret 0
"""
        c_code = c.compile([c.Input(src, "test.yafl")], use_stdlib=False, just_testing=False)
        self.assertTrue(c_code, "compilation produced no output")
        # A state machine should have been generated for double_call, and the
        # TaskWrapper struct (struct { int32_t value; object_t* task; }) for the return type.
        self.assertIn("double_call", c_code)
        self.assertIn("$async", c_code)
        self.assertIn("int32_t value", c_code)   # TaskWrapper inner field

        with tempfile.NamedTemporaryFile(suffix=".o", delete=False) as tmp:
            obj = tmp.name
        try:
            result = subprocess.run(
                ["clang", "-x", "c", "-c", "-O0", "-o", obj, "-"],
                input=c_code, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(0, result.returncode, f"clang rejected generated C:\n{result.stderr}")
        finally:
            try:
                os.unlink(obj)
            except OSError:
                pass

    def test_none_returning_function_with_state_machine_compiles(self):
        """A None-returning function (unit type ()) with non-tail calls generates
        a state machine.  None maps to Struct(fields=()) at the IR level, so the
        return type uses TaskWrapper(Struct(fields=())) for async signalling.
        Verifies that the generated C is accepted by clang."""
        import subprocess, tempfile, os
        src = """\
namespace System
typealias Int : __builtin_type__<bigint>
typealias None : ()
let None: None = ()

fun sideeffect(x: Int): Int
    ret x

fun effect(a: Int, b: Int): None
    let ra: Int = sideeffect(a)
    let rb: Int = sideeffect(b)
    ret None

fun main(): Int
    let discard: None = effect(3, 7)
    ret 13
"""
        c_code = c.compile([c.Input(src, "test.yafl")], use_stdlib=False, just_testing=False)
        self.assertTrue(c_code, "compilation produced no output")
        # effect has two non-tail calls → should generate effect$async
        self.assertIn("effect", c_code)
        self.assertIn("$async", c_code)

        with tempfile.NamedTemporaryFile(suffix=".o", delete=False) as tmp:
            obj = tmp.name
        try:
            result = subprocess.run(
                ["clang", "-x", "c", "-c", "-O0", "-o", obj, "-"],
                input=c_code, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(0, result.returncode, f"clang rejected generated C:\n{result.stderr}")
        finally:
            try:
                os.unlink(obj)
            except OSError:
                pass

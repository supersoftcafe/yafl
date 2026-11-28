"""Literal discovery (#159, lowering/literal_discovery.py).

A call whose arguments are all compile-time constants is run by the compiler.
When it finishes inside the budget, its value — every object it built
included, arrays and string-keyed dicts among them — is emitted as C static
data and the call becomes a load of it. Anything else stays where it is:
nothing is run ahead of where the program runs it.

What the programs compute is checked by compiler/yafl_tests/literal_discovery.yafl.
"""
from __future__ import annotations

import re

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c

_ARRAY_OF = "System__Containers__arrayOf"


def _elements(*values: int) -> str:
    """The regex for a static array's initialiser holding Int32 `values`."""
    return r"\{" + r",\s*".join(rf"\(\(int32_t\){v}\)" for v in values) + r"\}"

_IN_FUNCTION = """namespace Test
import System
import System::Containers

fun has(c: Int32, a: Array<Int32>): Bool
  ret size(a) > 0 && (a[0] == c || (size(a) > 1 && a[1] == c) || (size(a) > 2 && a[2] == c))

fun isVowelish(c: Int32): Bool
  ret has(c, arrayOf('a', 'e', 'i'))

fun main(): Int
  ret isVowelish(sizeAtLeast(args(), 2) ? 'x' : 'e') ? 0 : 1
"""

_IN_GLOBAL = """namespace Test
import System
import System::Containers

let table: Array<Int32> = arrayOf('x', 'y')

fun main(): Int
  ret size(table) == 2 ? 0 : 1
"""

# The interpreter does not build strings, so `shout("hi")` cannot be run at
# compile time — and nothing is run ahead of where the program runs it, so it
# stays a call.
_UNFINISHED = """namespace Test
import System
import System::Containers

fun [inline(never)] shout(s: String): Int
  ret length(s + "!")

fun [inline(never)] scaled(n: Int): Int
  ret n * shout("hi")

fun main(): Int
  ret scaled(sizeAtLeast(args(), 2) ? 2 : 1) == 3 ? 0 : 1
"""

# A Dict keyed by strings: the interpreter hashes and compares strings as the
# runtime does, so the whole tree is static data.
_STRING_DICT = """namespace Test
import System
import System::Containers

fun [inline(never)] colours(): Dict<String, String>
  ret put(put(put(put(Dict<String, String>(), "red", "#f00"), "green", "#0f0"), "blue", "#00f"), "red", "#e00")

fun main(): Int
  ret match(get(colours(), sizeAtLeast(args(), 2) ? "green" : "red"))
    (s: String) => s == "#e00" ? 0 : 1
    ()          => 2
"""

# Index 5 of a one-element array aborts: evaluating it ahead of time would
# abort the program before `main`, whether or not the branch ever runs.
_ABORTS = """namespace Test
import System
import System::Containers

fun [inline(never)] fifth(): Int32
  ret arrayOf(1i32)[5]

fun [inline(never)] pick(n: Int32): Int32
  ret n > 100i32 ? fifth() : 0i32

fun main(): Int
  ret pick(sizeAtLeast(args(), 2) ? 200i32 : 1i32) == 0i32 ? 0 : 1
"""


# A bigint beyond a machine word is a compound literal: stack storage when it
# appears in code. A value computed at compile time is read from a global.
_BIG_RESULT = """namespace Test
import System
import System::Containers

fun [inline(never)] big(n: Int): Int
  ret n + 100000000000000000000

fun main(): Int
  ret big(1) == 100000000000000000001 && sizeAtLeast(args(), 1) ? 0 : 1
"""


# Appends are a construction: each one, given a literal, makes the next
# literal. The array ends static; the list (whose nodes a later append may
# still link onto) ends as plain constructions in the code.
_APPENDS = """namespace Test
import System
import System::Containers

fun total(l: List<Int32>): Int => fold(l, 0, (acc, x) => acc + Int(x))

fun pick(a: Array<Int32>, l: List<Int32>, i: Int): Int => Int(a[i]) + total(l)

fun main(): Int
  let a = append(append(arrayOf(1i32), 2i32), 3i32)
  let l = append(append(List<Int32>(), 4i32), 5i32)
  ret pick(a, l, sizeAtLeast(args(), 2) ? 1 : 2) == 12 ? 0 : 1
"""

# Only inlining shows `arrayOf(97i32, 98i32)` its constants: in `near` they
# are its parameter.
_AFTER_INLINING = """namespace Test
import System
import System::Containers

fun has(c: Int32, a: Array<Int32>): Bool
  ret size(a) > 1 && (a[0] == c || a[1] == c)

fun [inline(always)] near(n: Int32, c: Int32): Bool
  ret has(c, arrayOf(n, n + 1i32))

fun main(): Int
  ret near(97i32, sizeAtLeast(args(), 2) ? 120i32 : 98i32) ? 0 : 1
"""

# A global whose initialiser is a constant — here a function — is settled by
# stage 2, which runs no calls, so it is settled with stage 1 turned off too.
_CONSTANT_GLOBAL = """namespace Test
import System

fun impl(s: String): Int
  ret length(s)

let h: (:String): Int = impl

fun main(): Int
  ret h("abc") + h("de") - 5
"""


def _body(code: str, fn: str) -> str:
    """The C body of the function whose definition starts `fn`."""
    m = re.search(r"\n" + re.escape(fn) + r"\w*\([^;{]*\)\n\{\n", code)
    assert m, f"no definition of {fn}"
    return code[m.end():code.index("\n}\n", m.end())]


def _c(src: str, level: int, args: tuple[str, ...] = ()) -> str:
    code = compile_c(src, optimization_level=level, args=args)
    assert code, "compilation failed"
    return code


class TestLiteralDiscovery(TestCase):
    def test_a_constant_array_in_a_function_is_static_data(self):
        for level in (1, 3):
            with self.subTest(level=level):
                code = _c(_IN_FUNCTION, level)
                self.assertNotIn(_ARRAY_OF, code, "the constant array is still built at run time")
                self.assertRegex(code, _elements(97, 101, 105), "its elements are not static data")

    def test_a_constant_array_global_is_static_data(self):
        code = _c(_IN_GLOBAL, 1)
        self.assertNotIn(_ARRAY_OF, code, "the global's array is still built at run time")
        self.assertNotIn("lambda_Test__table", code, "the global still has a run-time initialiser")
        self.assertRegex(code, _elements(120, 121))

    def test_a_call_it_cannot_finish_stays_a_call(self):
        code = _c(_UNFINISHED, 1)
        self.assertIn("Test__shout", _body(code, "object_t* Test__scaled"),
                      "a call the compiler could not finish was moved")
        self.assertNotIn("__start__", code, "something was run ahead of the program")

    def test_a_string_keyed_dict_is_static_data(self):
        code = _c(_STRING_DICT, 1)
        self.assertNotIn("Test__colours", _body(code, "object_t* Test__main"),
                         "the dict is still built at run time")
        self.assertNotIn("System__Containers__put", code, "a put survives")

    def test_a_call_that_aborts_is_left_alone(self):
        code = _c(_ABORTS, 1)
        self.assertIn("X5bX5d", _body(code, "struct_anon_0_t Test__fifth"),
                      "the aborting index was evaluated away")

    def test_a_big_int_value_is_read_from_a_global(self):
        code = _c(_BIG_RESULT, 1)
        self.assertNotIn("Test__big", _body(code, "object_t* Test__main"), "big(1) was not computed")
        self.assertNotIn("INTEGER_LITERAL_N", _body(code, "object_t* Test__main"),
                         "a big Int literal in code is stack storage")

    def test_appends_to_a_literal_make_literals(self):
        code = _c(_APPENDS, 1)
        body = _body(code, "object_t* Test__main")
        self.assertNotIn("System__Containers__append", body, "an append survives")
        self.assertRegex(code, _elements(1, 2, 3), "the array is not static data")
        self.assertIn("object_new(obj_System__Containers___ListNode", body,
                      "the list is not built from its nodes")

    def test_a_literal_inlining_reveals_is_static_data(self):
        code = _c(_AFTER_INLINING, 3)
        self.assertNotIn(_ARRAY_OF, code, "the array is still built at run time")
        self.assertRegex(code, _elements(97, 98), "its elements are not static data")

    def test_it_can_be_turned_off(self):
        # --no-literal-discovery: the array is built at run time again.
        code = _c(_IN_FUNCTION, 1, args=("--no-literal-discovery",))
        self.assertIn(_ARRAY_OF, code, "the constant call was still run by the compiler")

    def test_a_constant_global_is_settled_when_turned_off(self):
        # --no-literal-discovery turns off running calls, not settling.
        code = _c(_CONSTANT_GLOBAL, 1, args=("--no-literal-discovery",))
        self.assertNotIn("lambda_Test__h", code, "the global still has a run-time initialiser")

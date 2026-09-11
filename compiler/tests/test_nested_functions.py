"""Tests for nested function declarations inside function bodies."""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase

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


class TestNestedFunctionsInClassMembers(TestCase):
    """Nested functions inside CLASS MEMBER functions.

    A member function is a function; nothing about being a class member makes
    a nested declaration harder to lower. Which of the three strategies a
    helper gets depends only on what it reaches for:

      - nothing outside itself       → hoisted to global scope
      - `this` only                  → hoisted as a SIBLING MEMBER of the class
      - `this` plus enclosing locals → sibling member, locals threaded as
                                       extra parameters (lambda_lift)
      - reference travels as a value → its own closure class at global scope,
                                       capturing `this` under a renamed field

    The renamed field matters: a closure field literally called `this` would
    collide with the synthesised receiver that ClassStatement puts in scope
    for every method body, and the reference resolves to two candidates.
    """

    def test_member_nested_no_capture(self):
        """A helper reaching for nothing hoists to global scope, as it would
        inside a free function."""
        src = """\
import System
class Counter(base: Int)
  fun addTo(x: Int): Int
    fun twice(y: Int): Int
      ret y + y
    ret twice(x)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(10, compile_and_run_stdlib(src))

    def test_member_nested_reads_field(self):
        """A helper that reads a class field keeps `this` — it becomes a
        sibling member rather than a global."""
        src = """\
import System
class Counter(base: Int)
  fun addTo(x: Int): Int
    fun addBase(y: Int): Int
      ret y + base
    ret addBase(x)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(15, compile_and_run_stdlib(src))

    def test_member_nested_calls_sibling_member(self):
        """A helper may call another member of its own class."""
        src = """\
import System
class Counter(base: Int)
  fun scaled(): Int
    ret base + base
  fun addTo(x: Int): Int
    fun addScaled(y: Int): Int
      ret y + scaled()
    ret addScaled(x)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(25, compile_and_run_stdlib(src))

    def test_member_nested_reads_field_and_local(self):
        """Fields plus enclosing parameters: the parameters thread through as
        extra arguments, `this` stays implicit."""
        src = """\
import System
class Counter(base: Int)
  fun addTo(x: Int): Int
    fun combine(y: Int): Int
      ret y + base + x
    ret combine(1)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(16, compile_and_run_stdlib(src))

    def test_member_nested_reads_field_and_let(self):
        """A block let is not threadable, so this helper closes over both the
        let and `this` — the closure path, from inside a member."""
        src = """\
import System
class Counter(base: Int)
  fun addTo(x: Int): Int
    let bump: Int = x + x
    fun combine(y: Int): Int
      ret y + base + bump
    ret combine(1)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(21, compile_and_run_stdlib(src))

    def test_member_nested_escapes_as_value(self):
        """The reference travels as a value, so the helper needs a real
        closure object — one that captures `this` under a renamed field."""
        src = """\
import System
fun applyTo(f: (:Int): Int, v: Int): Int
  ret f(v)

class Counter(base: Int)
  fun addTo(x: Int): Int
    fun combine(y: Int): Int
      ret y + base + x
    ret applyTo(combine, 1)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(16, compile_and_run_stdlib(src))

    def test_member_lambda_captures_this(self):
        """The same capture, spelled as a lambda. This is the shape the
        `this`-rename exists for; it was broken independently of hoisting."""
        src = """\
import System
fun applyTo(f: (:Int): Int, v: Int): Int
  ret f(v)

class Counter(base: Int)
  fun addTo(x: Int): Int
    ret applyTo((y: Int) => y + base + x, 1)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(16, compile_and_run_stdlib(src))

    def test_member_nested_closure_calls_class_hoisted_sibling(self):
        """A closure-bound helper that calls a sibling which became a class
        member. The sibling is only reachable through a receiver now, so the
        closure has to capture `this` to make the call — which only works if
        the redirect happens before the capture set is computed."""
        src = """\
import System
fun applyTo(f: (:Int): Int, v: Int): Int
  ret f(v)

class Counter(base: Int)
  fun addTo(x: Int): Int
    fun onlyField(y: Int): Int
      ret y + base
    fun escapes(z: Int): Int
      ret onlyField(z) + x
    ret applyTo(escapes, 1)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(16, compile_and_run_stdlib(src))

    def test_member_nested_mutual_recursion_capturing_this(self):
        """Mutually-recursive capturing helpers coalesce into one closure
        class; reaching `this` must not break the coalescing."""
        src = """\
import System
class Counter(limit: Int)
  fun classify(n: Int): Int
    fun isEven(x: Int): Int
      ret x < 1 ? 1 : (x > limit ? 99 : isOdd(x - 1))
    fun isOdd(x: Int): Int
      ret x < 1 ? 0 : (x > limit ? 99 : isEven(x - 1))
    ret isEven(n)

fun main(): Int
  ret Counter(100).classify(4)
"""
        self.assertEqual(1, compile_and_run_stdlib(src))

    def test_member_nested_tail_recursive(self):
        """A `[tail]` helper inside a member lowers to a loop like any other —
        the hoist must run before tail_loop here too."""
        src = """\
import System
class Counter(base: Int)
  fun sumTo(n: Int): Int
    fun [tail] go(i: Int, acc: Int): Int
      ret i > n ? acc : go(i + 1, acc + base)
    ret go(1, 0)

fun main(): Int
  ret Counter(10).sumTo(4)
"""
        self.assertEqual(40, compile_and_run_stdlib(src))

    def test_member_nested_in_generic_class(self):
        """Classes are monomorphised before the hoist, so `this` is concrete
        by the time a helper claims it."""
        src = """\
import System
class Box<T>(value: T)
  fun pick(other: T, useOther: Bool): T
    fun choose(flag: Bool): T
      ret flag ? other : value
    ret choose(useOther)

fun main(): Int
  ret Box<Int>(7).pick(9, false) + Box<Int>(1).pick(20, true)
"""
        self.assertEqual(27, compile_and_run_stdlib(src))

    def test_member_nested_deeply_nested(self):
        """A helper inside a helper inside a member."""
        src = """\
import System
class Counter(base: Int)
  fun addTo(x: Int): Int
    fun outerHelper(y: Int): Int
      fun innerHelper(z: Int): Int
        ret z + base
      ret innerHelper(y) + innerHelper(y)
    ret outerHelper(x)

fun main(): Int
  ret Counter(10).addTo(5)
"""
        self.assertEqual(30, compile_and_run_stdlib(src))

    def test_member_nested_two_members_same_helper_name(self):
        """Two members may each nest a helper of the same source name; they
        become distinct siblings, not one clobbering the other."""
        src = """\
import System
class Counter(base: Int)
  fun addTo(x: Int): Int
    fun helper(y: Int): Int
      ret y + base
    ret helper(x)
  fun subFrom(x: Int): Int
    fun helper(y: Int): Int
      ret base - y
    ret helper(x)

fun main(): Int
  ret Counter(10).addTo(5) + Counter(10).subFrom(3)
"""
        self.assertEqual(22, compile_and_run_stdlib(src))

    def test_member_nested_in_non_final_class(self):
        """A helper on a class that is used polymorphically. It gets no vtable
        slot (the slot table is fixed before the hoist runs), so its call must
        be direct rather than a dispatch through a slot that does not exist."""
        src = """\
import System
interface Shape
  fun area(): Int

class Square(side: Int) : Shape
  fun area(): Int
    fun sq(n: Int): Int
      ret n * side
    ret sq(side)

fun totalArea(s: Shape): Int
  ret s.area()

fun main(): Int
  ret totalArea(Square(6))
"""
        self.assertEqual(36, compile_and_run_stdlib(src))

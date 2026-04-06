"""Simple-class lowering tests.

A "simple" class (no inheritance, not extended, ≤4 fields, all method
references immediately called) should be lowered to a flat struct + free
functions after the generics and lambda passes.  The tests here verify
correct runtime behaviour for the cases that drive the lowering design.

Tests in TestSimpleClassLowering are expected to fail until the lowering
pass is implemented.  Tests in TestNonSimpleClassUnaffected verify that
classes which do NOT qualify are still handled correctly as heap objects.
"""
from __future__ import annotations

from unittest import TestCase

from tests.testutil import compile_and_run


def _run(src: str) -> int:
    code, _ = compile_and_run(src)
    return code


_PREAMBLE = """\
namespace System
typealias Int : __builtin_type__<bigint>
typealias None : ()
let None: None = ()
"""

_ARITH = """\
fun `+`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_add", l, r)

fun `-`(l: Int, r: Int): Int
    ret __builtin_op__<bigint>("integer_sub", l, r)

"""


class TestSimpleClassLowering(TestCase):

    def test_single_field_method(self):
        """Method that returns its only field."""
        src = _PREAMBLE + """\
class Box(value: Int)
    fun get(): Int
        ret value

fun main(): Int
    let b: Box = Box(13)
    ret b.get()
"""
        self.assertEqual(13, _run(src))

    def test_two_field_method_arithmetic(self):
        """Method that combines two fields; value choice distinguishes field-swap corruption."""
        src = _PREAMBLE + _ARITH + """\
class Point(x: Int, y: Int)
    fun sum(): Int
        ret x + y

fun main(): Int
    let p: Point = Point(5, 8)
    ret p.sum()
"""
        self.assertEqual(13, _run(src))

    def test_method_with_parameter(self):
        """Method that takes an argument alongside a captured field."""
        src = _PREAMBLE + _ARITH + """\
class Counter(value: Int)
    fun add(n: Int): Int
        ret value + n

fun main(): Int
    let c: Counter = Counter(6)
    ret c.add(7)
"""
        self.assertEqual(13, _run(src))

    def test_class_passed_to_function(self):
        """Simple class instance passed to a free function."""
        src = _PREAMBLE + """\
class Box(value: Int)
    fun get(): Int
        ret value

fun unbox(b: Box): Int
    ret b.get()

fun main(): Int
    ret unbox(Box(13))
"""
        self.assertEqual(13, _run(src))

    def test_class_returned_from_function(self):
        """Simple class instance returned from a function then used."""
        src = _PREAMBLE + """\
class Box(value: Int)
    fun get(): Int
        ret value

fun wrap(n: Int): Box
    ret Box(n)

fun main(): Int
    let b: Box = wrap(13)
    ret b.get()
"""
        self.assertEqual(13, _run(src))

    def test_struct_returning_function_with_state_machine(self):
        """make_box has a non-tail call before constructing and returning a Box.
        Unlike test_class_returned_from_function (where the struct-returning
        callee is pure-sync), here the struct-returning function itself has a
        state machine.  Exercises the struct-typed hot-path and state machine."""
        src = _PREAMBLE + """\
class Box(value: Int)

fun bump(n: Int): Int
    ret n

fun make_box(n: Int): Box
    let v: Int = bump(n)
    ret Box(v)

fun main(): Int
    let b: Box = make_box(17)
    ret b.value
"""
        self.assertEqual(17, _run(src))

    def test_nested_simple_classes(self):
        """Class whose field is itself a simple class; both get lowered."""
        src = _PREAMBLE + _ARITH + """\
class Inner(value: Int)
    fun get(): Int
        ret value

class Outer(inner: Inner, extra: Int)
    fun total(): Int
        ret inner.get() + extra

fun main(): Int
    let o: Outer = Outer(Inner(6), 7)
    ret o.total()
"""
        self.assertEqual(13, _run(src))

    def test_simple_class_in_union(self):
        """Simple class as a non-null variant in a union; dispatched via match."""
        src = _PREAMBLE + """\
class Box(value: Int)
    fun get(): Int
        ret value

fun unwrap(b: Box|None): Int
    ret match(b)
        (x: Box) => x.get()
        (x: None) => 0

fun main(): Int
    ret unwrap(Box(13))
"""
        self.assertEqual(13, _run(src))

    def test_four_field_class(self):
        """Class with exactly 4 fields still qualifies for lowering."""
        src = _PREAMBLE + _ARITH + """\
class Quad(a: Int, b: Int, c: Int, d: Int)
    fun sum(): Int
        ret a + b + c + d

fun main(): Int
    let q: Quad = Quad(1, 2, 4, 6)
    ret q.sum()
"""
        self.assertEqual(13, _run(src))

    def test_field_order_not_swapped(self):
        """Subtraction detects field-order corruption that addition would mask."""
        src = _PREAMBLE + _ARITH + """\
class Diff(a: Int, b: Int)
    fun result(): Int
        ret a - b

fun main(): Int
    let d: Diff = Diff(10, 3)
    ret d.result()
"""
        self.assertEqual(7, _run(src))

    def test_two_instances_independent(self):
        """Two instances of the same simple class hold independent values."""
        src = _PREAMBLE + _ARITH + """\
class Box(value: Int)
    fun get(): Int
        ret value

fun main(): Int
    let a: Box = Box(9)
    let b: Box = Box(4)
    ret a.get() + b.get()
"""
        self.assertEqual(13, _run(src))

    def test_multiple_methods(self):
        """Class with two methods; both are exercised in the same run."""
        src = _PREAMBLE + _ARITH + """\
class Pair(x: Int, y: Int)
    fun first(): Int
        ret x
    fun second(): Int
        ret y

fun main(): Int
    let p: Pair = Pair(8, 5)
    ret p.first() + p.second()
"""
        self.assertEqual(13, _run(src))

    def test_simple_class_in_union_null_arm(self):
        """Union match: the unit-variant (null) arm fires when None is passed."""
        src = _PREAMBLE + """\
class Box(value: Int)
    fun get(): Int
        ret value

fun unwrap(b: Box|None): Int
    ret match(b)
        (x: Box) => x.get()
        (x: None) => 0

fun main(): Int
    ret unwrap(None)
"""
        self.assertEqual(0, _run(src))

    def test_lambda_alongside_simple_class(self):
        """Lambda closure is not incorrectly lowered when a simple class is present.

        The lambda's closure class has a standalone DotExpression method reference
        (to extract the function pointer when it is passed to a higher-order function).
        The DotExpression scan must detect this and exclude the closure class from
        simple-class lowering.  If the closure were lowered to a flat struct, vtable
        dispatch for the function pointer would break.
        """
        src = _PREAMBLE + _ARITH + """\
fun apply(f: (:Int):Int, n: Int): Int
    ret f(n)

class Box(value: Int)
    fun get(): Int
        ret value

fun main(): Int
    let b: Box = Box(6)
    let offset = b.get()
    ret apply((x: Int) => x + offset, 7)
"""
        self.assertEqual(13, _run(src))


class TestNonSimpleClassUnaffected(TestCase):
    """Classes that do not qualify must continue to work as heap objects."""

    def test_five_field_class_excluded(self):
        """5 fields exceeds the threshold; heap-object path must still work."""
        src = _PREAMBLE + _ARITH + """\
class Big(a: Int, b: Int, c: Int, d: Int, e: Int)
    fun sum(): Int
        ret a + b + c + d + e

fun main(): Int
    let x: Big = Big(1, 2, 3, 3, 4)
    ret x.sum()
"""
        self.assertEqual(13, _run(src))

    def test_class_with_inheritance_excluded(self):
        """Class implementing an interface must not be lowered; must still compile.

        Runtime check is skipped: VTABLE_IMPLEMENTS emits a compound-literal
        address as a C static initialiser, which clang rejects (pre-existing
        codegen bug, tracked separately).
        """
        import compiler as c
        src = _PREAMBLE + _ARITH + """\
interface Scalable
    fun scale(n: Int): Int

class Box(value: Int): Scalable
    fun scale(n: Int): Int
        ret value + n

fun main(): Int
    let b: Box = Box(7)
    ret b.scale(6)
"""
        result = c.compile([c.Input(src, "test.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)


class TestSimpleClassGlobalLet(TestCase):
    """Global 'let' whose value is a simple-class constructor expression."""

    def test_global_simple_class_runtime_value(self):
        """Global let of a simple class: binary runs and returns the correct field value.

        Verifies end-to-end correctness — not just that the C code lacks lazy-init
        boilerplate, but that the emitted binary actually returns the right value.
        """
        src = _PREAMBLE + """\
class Config(value: Int)

let defaultConfig: Config = Config(13)

fun main(): Int
    ret defaultConfig.value
"""
        self.assertEqual(13, _run(src))

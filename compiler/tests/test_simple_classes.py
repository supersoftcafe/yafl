"""Simple-class lowering tests.

A "simple" class (no inheritance, not extended, ≤4 fields, all method
references immediately called) should be lowered to a flat struct + free
functions after the generics and lambda passes.  The tests here verify
correct runtime behaviour for the cases that drive the lowering design.

Tests in TestSimpleClassLowering are expected to fail until the lowering
pass is implemented.  Tests in TestNonSimpleClassUnaffected verify that
classes which do NOT qualify are still handled correctly as heap objects.

Runtime behaviour is checked by compiler/yafl_tests/simple_classes.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase


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


class TestNonSimpleClassUnaffected(TestCase):
    """Classes that do not qualify must continue to work as heap objects."""


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



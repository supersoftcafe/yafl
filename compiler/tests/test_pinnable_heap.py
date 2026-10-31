"""A [pinnable] object always lives on the heap.

The runtime's late write (pin, store, unpin) assumes its target is a heap
object, so the compiler never gives a [pinnable] instance any other home:

  * a global whose initialiser is a constant constructor tree is normally
    emitted as a C static (test_static_globals.py) — a [pinnable] one goes
    lazy instead, built on the heap at first use;
  * a non-escaping object is normally dissolved into stack locals
    (lowering/stack_promotion.py) — a [pinnable] one is allocated anyway;
  * a construction from constants is normally hoisted into one shared static
    (lowering/staticinit.py) — a [pinnable] one is built afresh each time,
    or every caller would share its write-once slots.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_c

_STATIC = """namespace Test
import System

class [pinnable] Cell(value: Int32, next: Cell|None)

let cell: Cell = Cell(1i32, None)

fun main(): Int
  ret cell.value == 1i32 ? 0 : 1
"""

_LOCAL = """namespace Test
import System

class [pinnable] Cell(value: Int32, next: Cell|None)

fun first(v: Int32): Int32
  let c = Cell(v, None)
  ret c.value + 1i32

fun main(): Int
  ret first(41i32) == 42i32 ? 0 : 1
"""

_CONSTANT_CTOR = """namespace Test
import System

class [pinnable] Cell(value: Int32, other: Int32)

fun mk(): Cell => Cell(1i32, 2i32)

fun main(): Int
  let a = mk()
  let b = mk()
  ret a.value + b.other == 3i32 ? 0 : 1
"""


class TestPinnableOnHeap(TestCase):
    def test_constant_global_is_not_static(self):
        code = compile_c(_STATIC, optimization_level=1)
        self.assertTrue(code, "compilation failed")
        self.assertNotIn("(object_t*)((char*)obj_Test__Cell", code,
                         "a [pinnable] instance was emitted as a static")

    def test_constant_construction_is_not_a_shared_static(self):
        for level in (1, 3):
            with self.subTest(level=level):
                code = compile_c(_CONSTANT_CTOR, optimization_level=level)
                self.assertTrue(code, "compilation failed")
                self.assertIn("object_new(obj_Test__Cell", code,
                              "a [pinnable] construction from constants became one shared static")

    def test_local_is_not_stack_promoted(self):
        code = compile_c(_LOCAL, optimization_level=3)
        self.assertTrue(code, "compilation failed")
        self.assertIn("object_new(obj_Test__Cell", code,
                      "a non-escaping [pinnable] instance was dissolved into stack locals")

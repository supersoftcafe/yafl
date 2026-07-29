"""Call-site inference for members of GENERIC `[trait]` instances.

A concrete call to a member of a generic trait instance (e.g. `drop(b)` where
the witness is `_DropListBuilder<T> : Drop<ListBuilder<T>>`) must bind the
INSTANCE's type parameters from the argument shape. Resolution substitutes the
owner interface's placeholders through the instance's declared type, but that
still contains the instance's own free placeholder — nothing unifies it
against the argument, so the call dies with "Parameters are not assignment
compatible". Found via the drops pass (which routes around it with the
dropIndirect trampoline — deleted once this passes).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

# The stdlib shape that motivated the gap: an explicit drop of a builder.
_EXPLICIT_DROP = """namespace Test
import System

fun main(): Int
  let b = push(builder<Int>(), 7)
  let _ = drop(b)
  ret 0
"""

# The gap is general, not Drop-specific: any generic instance member called
# with concrete arguments must latch the instance's T the same way.
_OWN_TRAIT = """namespace Test
import System

interface Sized<T>
  fun sizeOf(v: T): Int

class _SizedList<T>() : Sized<List<T>>
  fun sizeOf(v: List<T>): Int
    ret chainLength(chain(v))

let [trait,where] _sizedList<T>: _SizedList<T> = _SizedList<T>()

fun main(): Int
  let l = append(append(List<Int>(), 4), 5)
  ret sizeOf(l) == 2 ? 0 : 1
"""


class TestGenericTraitMember(TestCase):
    _TIMEOUT = 600

    def test_explicit_drop_of_builder(self):
        code, _out = compile_and_run_stdlib_capture(_EXPLICIT_DROP)
        self.assertEqual(code, 0)

    def test_own_generic_instance_member(self):
        code, _out = compile_and_run_stdlib_capture(_OWN_TRAIT)
        self.assertEqual(code, 0)

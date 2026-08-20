"""Call-site binding for members of GENERIC ambient instances.

A concrete call to a member of a generic `instance [ambient]` (e.g.
`drop(b)` where the instance is `instance [ambient]<T> Drop<ListBuilder<T>>`)
binds the INSTANCE's type parameters from the argument shape — the
generic-function-candidate rule applied to instances. This was the original
gap the drops pass routed around with a `dropIndirect` trampoline, both
deleted once the instance statement and ambient resolution landed.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

# The stdlib shape that motivated the gap: an explicit drop of a builder,
# resolving through list.yafl's `instance [ambient]<T> Drop<ListBuilder<T>>`.
_EXPLICIT_DROP = """namespace Test
import System

fun main(): Int
  let b = push(builder<Int>(), 7)
  let _ = drop(b)
  ret 0
"""

# The rule is general, not Drop-specific: any generic ambient instance member
# called with concrete arguments latches the instance's T the same way.
_OWN_TRAIT = """namespace Test
import System

interface Sized<T>
  fun sizeOf(v: T): Int

instance [ambient]<T> Sized<List<T>>
  fun sizeOf(v: List<T>): Int
    ret chainLength(chain(v))

fun main(): Int
  let l = prepend(4, prepend(5, List<Int>()))
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

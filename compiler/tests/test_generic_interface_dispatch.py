"""A GENERIC class implementing a non-generic interface must override its
methods in every instantiation.

Monomorphisation suffixes a generic class's own members with the type
signature (`slots@hash` becomes `slots@hash@bigint`), and the specialised
class recomputes its slots from those members. The override match must
compare the member's DECLARED name — up to the first `@` — or the suffix
hides the override: the interface's slot is left with no provider. With no
non-generic implementor anywhere, devirtualisation then crashed the
compiler (KeyError on the slot); with one, the program compiled and the
generic instance's vtable lacked the interface's id, so the virtual call
aborted at run time.

Matching the override then COMPARES the two signatures, after
monomorphisation. A signature naming a generic class (`Array<Node>`) is
spelt by the specialisation's name in the instance and, in the interface's
CACHED slot table, by the template's — a template monomorphisation removed.
The redirect that renames every type reference must rename those cached
slot types too, or the comparison cannot resolve the template and the
compiler crashed (IndexError in find_class).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase, compile_and_run_stdlib_capture


class TestGenericInterfaceDispatch(TestCase):
    def test_generic_implementors_dispatch_through_the_interface(self):
        # `Sized` has ONLY generic implementors (the compiler crash);
        # `Counted` has a generic AND a plain one (the run-time abort).
        src = """\
namespace Test
import System

interface Sized
  fun size(): Int32

interface Counted
  fun count(): Int32

class [final] Box<T>(n: Int32, x: T) : Sized | Counted
  fun size(): Int32
    ret n
  fun count(): Int32
    ret n + 100i32

class [final] Plain(n: Int32) : Counted
  fun count(): Int32
    ret n

fun sizeOf(s: Sized): Int32
  ret s.size()

fun countOf(c: Counted): Int32
  ret c.count()

fun main(): Int
  println(String(Int(sizeOf(Box<Int>(1i32, 9)))) + " "
          + String(Int(sizeOf(Box<String>(2i32, "s")))) + " "
          + String(Int(countOf(Box<Int>(3i32, 9)))) + " "
          + String(Int(countOf(Plain(4i32)))))
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("1 2 103 4\n", out)

    def test_override_signature_naming_a_generic_class(self):
        src = """\
namespace Test
import System

interface Sink
  fun take(xs: Array<Int32>): Int32

class [final] Keep<T>(x: T) : Sink
  fun take(xs: Array<Int32>): Int32
    ret xs.length

fun takeVia(s: Sink, xs: Array<Int32>): Int32
  ret s.take(xs)

fun main(): Int
  let xs = Array<Int32>(3i32, (i: Int32) => i)
  println(String(Int(takeVia(Keep<Int>(1), xs))) + " "
          + String(Int(takeVia(Keep<String>("s"), xs))))
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("3 3\n", out)

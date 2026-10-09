"""Generic enums as type ARGUMENTS of other generics, with the inner type
still a placeholder of the enclosing function.

`List<List<String>>` (fully concrete nesting) has always worked; the failing
shape is `List<_N<T>>` inside a generic function `f<T>`, where monomorphising
`f<Int>` must substitute T through BOTH generic layers. Found writing the
stdlib natural mergesort (runs queue = List<_ListNode<T>>); previously
crashed codegen with "GenericPlaceholderSpec should be replaced with a
concrete type".
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
namespace Main
import System

enum _N<T>
  enum _X()
  enum _C(v: T, n: _N<T>)

# A generic function whose body instantiates a generic enum (List) with a
# generic-enum argument (_N<T>) over its own placeholder.
fun mk<T>(x: T): List<_N<T> >
  ret prepend<_N<T> >(_C<T>(x, _X<T>()), List<_N<T> >())

fun headValue<T>(l: List<_N<T> >, dflt: T): T
  ret match(head<_N<T> >(l))
    (n: _N<T>) => match(n)
      (c: _C)  => c.v
      (e: _X)  => dflt
    (e: None)  => dflt

fun main(): System::Int
  let one = mk<Int>(7)
  let two = prepend<_N<Int> >(_C<Int>(3, _X<Int>()), one)
  System::print(String(headValue<Int>(two, -1)) + "," + String(headValue<Int>(one, -1)) + "\\n")
  ret 0
"""


class Test(TestCase):
    def test_generic_enum_as_generic_argument(self):
        code, out = compile_and_run_stdlib_capture(_SRC)
        self.assertEqual(0, code, out)
        self.assertIn("3,7", out)

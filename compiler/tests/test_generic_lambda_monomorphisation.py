"""A lambda inside a GENERIC function must be specialised per instantiation.

`stdlib/list.yafl`'s `concat<T>` is the shape:

    fun concat<T>(a: List<T>, b: List<T>): List<T>
      ret fold<T, List<T>>(b, a, (acc: List<T>, x: T) => append<T>(acc, x))

— a generic lambda inside a generic function. Monomorphisation copies the body
per `T`, but every copy keeps the SAME `line_ref`, so the lifted lambda class
must be named per instantiation or the copies collide onto one class and
whichever `T` was lowered first wins.

When they collide, `concat<A>` runs the lambda specialised for `B`: it calls
`append<B>`, builds a `ChainEnd<B>`, and the resulting chain is matched against
`ChainEnd<A>`/`ChainLink<A>` vtables — matching NEITHER, so codegen's fallback
fires and the program aborts with no diagnostic. A SILENT MISCOMPILE.

Found by the self-hosted compiler port, which is the first program to call
`concat` at many different element types.
"""
from __future__ import annotations

import re

import compiler as c

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_TWO_INSTANTIATIONS = """namespace Test
import System

class [final] A2(aname: String)
class [final] B2(bnum: Int)

fun countA(l: List<A2>): Int
  ret walkA(chain(l), 0)

fun [tail] walkA(c: Chain<A2>, n: Int): Int
  ret match(c)
    (nil: ChainEnd) => n
    (x: ChainLink)  => walkA(x.next, n + 1)

fun countB(l: List<B2>): Int
  ret walkB(chain(l), 0)

fun [tail] walkB(c: Chain<B2>, n: Int): Int
  ret match(c)
    (nil: ChainEnd) => n
    (x: ChainLink)  => walkB(x.next, n + 1)

fun main(): Int
  let a = concat(append(List<A2>(), A2("p")), append(List<A2>(), A2("q")))
  let b = concat(append(List<B2>(), B2(1)), append(List<B2>(), B2(2)))
  print(String(countA(a)) + "|" + String(countB(b)) + "\\n")
  ret 0
"""


class TestGenericLambdaMonomorphisation(TestCase):
    def test_two_instantiations_run_correctly(self):
        self.assertEqual((0, "2|2\n"),
                         compile_and_run_stdlib_capture(_TWO_INSTANTIATIONS))

    def test_each_instantiation_gets_its_own_lambda_class(self):
        """The direct check: two instantiations of a generic function holding a
        lambda must lift TWO lambda classes, not one."""
        code = c.compile([c.Input(_TWO_INSTANTIATIONS, "t.yafl")],
                         use_stdlib=True, just_testing=False,
                         optimization_level=1)
        self.assertTrue(code)
        classes = set(re.findall(r"_lambdas__lambda_[A-Za-z0-9_]+", code))
        self.assertGreaterEqual(
            len(classes), 2,
            f"concat<A2> and concat<B2> collapsed onto {len(classes)} lambda "
            f"class(es): {sorted(classes)}")

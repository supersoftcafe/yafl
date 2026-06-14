"""Matching a CONCRETE generic-enum instantiation from non-generic code must
substitute the subject's type arguments into the arm binder's field types.

Regression: matching `Chain<String>` and binding `(link: ChainLink)` left
`link.value` typed as the enum placeholder `T` instead of `String`, so using it
where a `String` is expected failed with "Parameters are not assignment
compatible". Matching in GENERIC context (the stdlib's own sort/chainNext)
always worked, which hid this. See MatchExpression.compile.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestGenericMatchBinder(TestCase):
    def test_concrete_chain_match_binds_string_field(self):
        src = """
namespace Main
import System
fun probe(c: Chain<String>): Int
  ret match(c)
    (link: ChainLink) => length(link.value)
    (e: ChainEnd)     => 0
fun main(): System::Int
  let c = ChainLink<String>("hi", ChainEnd<String>())
  System::print(String(probe(c)) + "\\n")
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("2", out.strip())

    def test_concrete_chain_match_int_field(self):
        # Same shape with Int payload, exercising the other arm too.
        src = """
namespace Main
import System
fun sumFirst(c: Chain<Int>): Int
  ret match(c)
    (link: ChainLink) => link.value + 1
    (e: ChainEnd)     => 0
fun main(): System::Int
  System::print(String(sumFirst(ChainLink<Int>(41, ChainEnd<Int>()))) + " "
              + String(sumFirst(ChainEnd<Int>())) + "\\n")
  ret 0
"""
        rc, out = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)
        self.assertEqual("42 0", out.strip())

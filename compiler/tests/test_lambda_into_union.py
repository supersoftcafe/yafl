"""A lambda flowing into a union-typed sink is converted into the union.

Every expression's compile wraps itself in a ConvertExpression when its sink
needs a representation change (conversion.converted) — except the lambda,
which returned itself bare. A lambda returned from `fun f(): ((:Int): Int)|String`
(or taken as a ternary branch into that union) therefore reached generate
unconverted, and generate refuses to convert: "conversion required at
generate — compile failed to insert a ConvertExpression". The same lambda
bound by `let` first worked, since the let's name is converted at the sink.
(Top-level names are unique across this class: batched compiles share one flat
name pool.)
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestLambdaIntoUnion(TestCase):
    def test_lambda_returned_into_union(self):
        src = """
namespace Main
import System
fun luAdder(k: Int): ((:Int): Int)|String
  ret (x: Int) => x + k
fun luUse(v: ((:Int): Int)|String): Int
  ret match(v)
    (f: (:Int): Int) => f(1)
    (s: String)      => 0
fun main(): System::Int
  ret luUse(luAdder(41))
"""
        rc, _out = compile_and_run_stdlib_capture(src)
        self.assertEqual(42, rc)

    def test_lambda_as_ternary_branch_into_union(self):
        src = """
namespace Main
import System
fun ltPick(k: Int): ((:Int): Int)|String
  ret k > 0 ? (x: Int) => x * k : "none"
fun ltUse(v: ((:Int): Int)|String): Int
  ret match(v)
    (f: (:Int): Int) => f(7)
    (s: String)      => length(s)
fun main(): System::Int
  ret ltUse(ltPick(3)) + ltUse(ltPick(0))
"""
        rc, _out = compile_and_run_stdlib_capture(src)
        self.assertEqual(25, rc)   # 21 + length("none")

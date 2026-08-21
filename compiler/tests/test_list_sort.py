"""stdlib sort<T> — stable natural ping-pong mergesort.

Covers: empty, singleton, already-sorted (one ascending run), reverse-sorted
(one descending run), random with duplicates, strings, and stability (equal
keys keep their original order, checked via a record type whose BasicCompare
instance compares the key only).
"""
from __future__ import annotations

from tests.testutil import BatchedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
namespace Main
import System

fun fromTo(i: Int, n: Int, step: Int, acc: List<Int>): List<Int>
  ret build<Int>(fromToB(i, n, step,
                         _pushChain<Int>(builder<Int>(), chain<Int>(acc))))

fun [tail] fromToB(i: Int, n: Int, step: Int,
                   [terminal] b: ListBuilder<Int>): ListBuilder<Int>
  ret i == n ? b : fromToB(i + step, n, step, push<Int>(b, i))

fun joinInts(l: List<Int>): String
  ret fold<Int, String>(l, "", (acc: String, x: Int) => acc + String(x) + ".")

fun joinStrs(l: List<String>): String
  ret fold<String, String>(l, "", (acc: String, x: String) => acc + x + ".")

# Stability witness: compare on key only; payload identifies original order.
class Rec(key: Int, tag: String)

# Hoisted: inside the class the member `<`(Rec,Rec) would shadow Int's `<`.
fun recLt(a: Rec, b: Rec): Bool
  ret a.key < b.key
fun recGt(a: Rec, b: Rec): Bool
  ret a.key > b.key
fun recEq(a: Rec, b: Rec): Bool
  ret a.key == b.key

instance [ambient] BasicCompare<Rec>
  fun `<`(left: Rec, right: Rec): Bool
    ret recLt(left, right)
  fun `>`(left: Rec, right: Rec): Bool
    ret recGt(left, right)
  fun `==`(left: Rec, right: Rec): Bool
    ret recEq(left, right)
  fun hashOf(value: Rec): Int
    ret value.key


fun joinRecs(l: List<Rec>): String
  ret fold<Rec, String>(l, "", (acc: String, r: Rec) => acc + String(r.key) + r.tag + ".")

fun main(): System::Int
  let empty  = sort<Int>(List<Int>())
  let single = sort<Int>(prepend<Int>(5, List<Int>()))
  let two    = sort<Int>(prepend<Int>(2, prepend<Int>(1, List<Int>())))
  let equal  = sort<Int>(prepend<Int>(7, prepend<Int>(7, prepend<Int>(7, prepend<Int>(7, List<Int>())))))
  let sorted = sort<Int>(fromTo(0, 8, 1, List<Int>()))
  let revs   = sort<Int>(fromTo(8, 0, -1, List<Int>()))
  let l0 = prepend<Int>(3, prepend<Int>(1, prepend<Int>(4, List<Int>())))
  let l1 = build<Int>(push<Int>(push<Int>(push<Int>(
      _pushChain<Int>(builder<Int>(), chain<Int>(l0)), 1), 5), 9))
  let l2 = build<Int>(push<Int>(push<Int>(push<Int>(
      _pushChain<Int>(builder<Int>(), chain<Int>(l1)), 2), 6), 5))
  let mixed = sort<Int>(l2)
  let strs = sort<String>(prepend<String>("pear", prepend<String>("apple", prepend<String>("fig", prepend<String>("banana", List<String>())))))
  let r0 = prepend<Rec>(Rec(2, "a"), prepend<Rec>(Rec(1, "b"), prepend<Rec>(Rec(2, "c"), prepend<Rec>(Rec(1, "d"), prepend<Rec>(Rec(2, "e"), List<Rec>())))))
  let recs = sort<Rec>(r0)
  System::print("empty=[" + joinInts(empty) + "]\\n")
  System::print("single=[" + joinInts(single) + "]\\n")
  System::print("two=[" + joinInts(two) + "]\\n")
  System::print("equal=[" + joinInts(equal) + "]\\n")
  System::print("sorted=[" + joinInts(sorted) + "]\\n")
  System::print("revs=[" + joinInts(revs) + "]\\n")
  System::print("mixed=[" + joinInts(mixed) + "]\\n")
  System::print("strs=[" + joinStrs(strs) + "]\\n")
  System::print("recs=[" + joinRecs(recs) + "]\\n")
  ret 0
"""


class Test(TestCase):
    def test_sort(self):
        code, out = compile_and_run_stdlib_capture(_SRC)
        self.assertEqual(0, code, out)
        self.assertIn("empty=[]", out)
        self.assertIn("single=[5.]", out)
        self.assertIn("two=[1.2.]", out)        # smallest real merge
        self.assertIn("equal=[7.7.7.7.]", out)  # all-ties path
        self.assertIn("sorted=[0.1.2.3.4.5.6.7.]", out)
        self.assertIn("revs=[1.2.3.4.5.6.7.8.]", out)
        self.assertIn("mixed=[1.1.2.3.4.5.5.6.9.]", out)
        self.assertIn("strs=[apple.banana.fig.pear.]", out)
        # Stability: 1b before 1d, 2a before 2c before 2e.
        self.assertIn("recs=[1b.1d.2a.2c.2e.]", out)

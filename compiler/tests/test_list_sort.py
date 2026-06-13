"""stdlib sort<T> — stable natural ping-pong mergesort.

Covers: empty, singleton, already-sorted (one ascending run), reverse-sorted
(one descending run), random with duplicates, strings, and stability (equal
keys keep their original order, checked via a record type whose BasicCompare
instance compares the key only).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
namespace Main
import System

fun fromTo(i: Int, n: Int, step: Int, acc: List<Int>): List<Int>
  ret i == n ? acc : fromTo(i + step, n, step, append<Int>(acc, i))

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

class RecCompare() : BasicCompare<Rec>
  fun `<`(left: Rec, right: Rec): Bool
    ret recLt(left, right)
  fun `>`(left: Rec, right: Rec): Bool
    ret recGt(left, right)
  fun `==`(left: Rec, right: Rec): Bool
    ret recEq(left, right)
  fun hashOf(value: Rec): Int
    ret value.key

let [trait] _rec_cmp: RecCompare = RecCompare()
typealias [where] _WhereBasicCompareRec : BasicCompare<Rec>

fun joinRecs(l: List<Rec>): String
  ret fold<Rec, String>(l, "", (acc: String, r: Rec) => acc + String(r.key) + r.tag + ".")

fun main(): System::Int
  let empty  = sort<Int>(List<Int>())
  let single = sort<Int>(append<Int>(List<Int>(), 5))
  let two    = sort<Int>(append<Int>(append<Int>(List<Int>(), 2), 1))
  let equal  = sort<Int>(append<Int>(append<Int>(append<Int>(append<Int>(List<Int>(), 7), 7), 7), 7))
  let sorted = sort<Int>(fromTo(0, 8, 1, List<Int>()))
  let revs   = sort<Int>(fromTo(8, 0, -1, List<Int>()))
  let l0 = append<Int>(append<Int>(append<Int>(List<Int>(), 3), 1), 4)
  let l1 = append<Int>(append<Int>(append<Int>(l0, 1), 5), 9)
  let l2 = append<Int>(append<Int>(append<Int>(l1, 2), 6), 5)
  let mixed = sort<Int>(l2)
  let strs = sort<String>(append<String>(append<String>(append<String>(append<String>(
      List<String>(), "pear"), "apple"), "fig"), "banana"))
  let r0 = append<Rec>(append<Rec>(append<Rec>(append<Rec>(append<Rec>(
      List<Rec>(), Rec(2, "a")), Rec(1, "b")), Rec(2, "c")), Rec(1, "d")), Rec(2, "e"))
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

"""Consolidated List<T> runtime test.

Covers empty/head/append/prepend/fold-order/sort/sortBy/map/filter/get/
large_append in one program.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
namespace System
import System

fun emit(label: System::String, value: System::Int): System::None
  System::print(label + "=" + System::String(value) + "\\n")
  ret None

fun unwrap(v: Int|None): Int
  ret match(v)
    (x: Int)  => x
    (n: None) => -1

# Built front-to-back with a ListBuilder — the in-order, O(1)-per-push path
# that replaced append. Yields the same [1,2,3,4,5].
fun buildAppend(): List<Int>
  ret build<Int>(push<Int>(push<Int>(push<Int>(push<Int>(push<Int>(
        builder<Int>(), 1), 2), 3), 4), 5))

fun buildPrepend(): List<Int>
  ret prepend<Int>(1, prepend<Int>(2, prepend<Int>(3, List<Int>())))

# A prepended head, then the rest pushed on behind it. There is no longer a
# rear chain for this to be "mixed" with — the builder simply seeds from the
# one-element list. Yields [0,1,2,3].
fun buildMixed(): List<Int>
  ret build<Int>(push<Int>(push<Int>(push<Int>(
        _pushChain<Int>(builder<Int>(),
                        chain<Int>(prepend<Int>(0, List<Int>()))),
        1), 2), 3))

fun build50(l: List<Int>, i: Int): List<Int>
  ret build<Int>(build50B(_pushChain<Int>(builder<Int>(), chain<Int>(l)), i))

fun [tail] build50B([terminal] b: ListBuilder<Int>, i: Int): ListBuilder<Int>
  ret i > 50 ? b : build50B(push<Int>(b, i), i + 1)

fun main(): Int
  # ─── empty (count via fold; List has no length by design) ──────────────
  emit("empty_length", fold<Int,Int>(List<Int>(), 0, (a: Int, x: Int) => a + 1))

  # ─── prepend / head ────────────────────────────────────────────────────
  let single = prepend<Int>(42, List<Int>())
  emit("prepend_head", unwrap(head<Int>(single)))

  # ─── append, fold ──────────────────────────────────────────────────────
  let appended = buildAppend()
  emit("append_fold_sum", fold<Int,Int>(appended, 0, (acc: Int, x: Int) => acc + x))

  # ─── prepend, fold (sum is order-independent here) ─────────────────────
  let prepended = buildPrepend()
  emit("prepend_fold_sum", fold<Int,Int>(prepended, 0, (acc: Int, x: Int) => acc + x))

  # ─── mixed prepend/append: count + fold sum ────────────────────────────
  let mixed = buildMixed()
  emit("mixed_length",   fold<Int,Int>(mixed, 0, (a: Int, x: Int) => a + 1))
  emit("mixed_fold_sum", fold<Int,Int>(mixed, 0, (acc: Int, x: Int) => acc + x))

  # ─── sort: the only way to impose an order ─────────────────────────────
  # `reverse` is gone. On a front-normal list it could only be a rebuilt
  # copy — a chain reversal under another name — so an ordering is named
  # explicitly instead. sortBy with the comparison flipped is what "reversed"
  # used to mean.
  let ascending = sort<Int>(prepended)
  emit("sort_head", unwrap(head<Int>(ascending)))
  let descending = sortBy<Int>(prepended, (a: Int, b: Int) => b < a)
  emit("sortBy_desc_head", unwrap(head<Int>(descending)))

  # ─── map ───────────────────────────────────────────────────────────────
  let mapped = map<Int,Int>(prepended, (x: Int) => x * x)
  emit("map_sum_of_squares", fold<Int,Int>(mapped, 0, (acc: Int, x: Int) => acc + x))

  # ─── filter ────────────────────────────────────────────────────────────
  let five = prepend<Int>(1, prepend<Int>(2, prepend<Int>(3, prepend<Int>(4, prepend<Int>(5, List<Int>())))))
  let filtered = filter<Int>(five, (x: Int) => x > 2)
  emit("filter_sum", fold<Int,Int>(filtered, 0, (acc: Int, x: Int) => acc + x))

  # ─── 50-element list, sum 1..50 = 1275 ────────────────────────────────
  emit("large_append_sum", fold<Int,Int>(build50(List<Int>(), 1), 0, (acc: Int, x: Int) => acc + x))

  ret 0
"""


_EXPECTED_LINES = [
    "empty_length=0",
    "prepend_head=42",
    "append_fold_sum=15",
    "prepend_fold_sum=6",
    "mixed_length=4",
    "mixed_fold_sum=6",
    "sort_head=1",
    "sortBy_desc_head=3",
    "map_sum_of_squares=14",
    "filter_sum=12",
    "large_append_sum=1275",
]


class TestAllListOps(TestCase):
    def test_all_list_ops(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

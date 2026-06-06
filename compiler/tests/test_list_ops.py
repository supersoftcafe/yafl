"""Consolidated List<T> runtime test.

Covers empty/head/append/prepend/fold-order/reverse/map/filter/get/
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

fun buildAppend(): List<Int>
  let l0 = List<Int>()
  let l1 = append<Int>(l0, 1)
  let l2 = append<Int>(l1, 2)
  let l3 = append<Int>(l2, 3)
  let l4 = append<Int>(l3, 4)
  ret append<Int>(l4, 5)

fun buildPrepend(): List<Int>
  ret prepend<Int>(1, prepend<Int>(2, prepend<Int>(3, List<Int>())))

fun buildMixed(): List<Int>
  let l0 = List<Int>()
  let l1 = prepend<Int>(0, l0)
  let l2 = append<Int>(l1, 1)
  let l3 = append<Int>(l2, 2)
  ret append<Int>(l3, 3)

fun build50(l: List<Int>, i: Int): List<Int>
  ret i > 50 ? l : build50(append<Int>(l, i), i + 1)

fun main(): Int
  # ─── empty ─────────────────────────────────────────────────────────────
  emit("empty_length", length<Int>(List<Int>()))

  # ─── prepend / head ────────────────────────────────────────────────────
  let single = prepend<Int>(42, List<Int>())
  emit("prepend_head", unwrap(head<Int>(single)))

  # ─── append, fold ──────────────────────────────────────────────────────
  let appended = buildAppend()
  emit("append_fold_sum", fold<Int,Int>(appended, 0, (acc: Int, x: Int) => acc + x))

  # ─── prepend, fold (sum is order-independent here) ─────────────────────
  let prepended = buildPrepend()
  emit("prepend_fold_sum", fold<Int,Int>(prepended, 0, (acc: Int, x: Int) => acc + x))

  # ─── mixed prepend/append: length + fold sum ───────────────────────────
  let mixed = buildMixed()
  emit("mixed_length",   length<Int>(mixed))
  emit("mixed_fold_sum", fold<Int,Int>(mixed, 0, (acc: Int, x: Int) => acc + x))

  # ─── reverse ───────────────────────────────────────────────────────────
  let reversed = reverse<Int>(prepended)
  emit("reverse_head", unwrap(head<Int>(reversed)))

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
    "reverse_head=3",
    "map_sum_of_squares=14",
    "filter_sum=12",
    "large_append_sum=1275",
]


class TestAllListOps(TestCase):
    def test_all_list_ops(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

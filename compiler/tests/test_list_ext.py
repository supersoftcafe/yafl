"""Runtime tests for the List<T> additions: isEmpty, last, concat, take, drop,
splitHalf, any, all, contains, flatMap.

`length` was deliberately removed (a list is a sequence, not an indexable
buffer); where a count is needed here it is taken with an explicit fold.
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

fun emitBool(label: System::String, value: System::Bool): System::None
  ret emit(label, value ? 1 : 0)

fun unwrap(v: Int|None): Int
  ret match(v)
    (x: Int)  => x
    (n: None) => -1

fun count(l: List<Int>): Int
  ret fold<Int,Int>(l, 0, (a: Int, x: Int) => a + 1)

fun sum(l: List<Int>): Int
  ret fold<Int,Int>(l, 0, (a: Int, x: Int) => a + x)

# [1,2,3,4,5]
fun nums(): List<Int>
  ret append<Int>(append<Int>(append<Int>(append<Int>(append<Int>(List<Int>(), 1), 2), 3), 4), 5)

fun main(): Int
  let l = nums()

  # ─── isEmpty ───────────────────────────────────────────────────────────
  emitBool("empty_yes", isEmpty<Int>(List<Int>()))
  emitBool("empty_no",  isEmpty<Int>(l))

  # ─── last ──────────────────────────────────────────────────────────────
  emit("last",       unwrap(last<Int>(l)))
  emit("last_empty", unwrap(last<Int>(List<Int>())))

  # ─── concat ────────────────────────────────────────────────────────────
  let a = append<Int>(List<Int>(), 1)
  let b = append<Int>(append<Int>(List<Int>(), 2), 3)
  let c = concat<Int>(a, b)
  emit("concat_count", count(c))
  emit("concat_head",  unwrap(head<Int>(c)))
  emit("concat_last",  unwrap(last<Int>(c)))
  emit("concat_sum",   sum(c))
  emit("concat_empty_l", sum(concat<Int>(List<Int>(), b)))
  emit("concat_empty_r", sum(concat<Int>(a, List<Int>())))

  # ─── take / drop ───────────────────────────────────────────────────────
  emit("take_sum",  sum(take<Int>(l, 2)))
  emit("take_over", count(take<Int>(l, 99)))
  emit("take_zero", count(take<Int>(l, 0)))
  emit("drop_sum",  sum(drop<Int>(l, 2)))
  emit("drop_over", count(drop<Int>(l, 99)))
  emit("drop_head", unwrap(head<Int>(drop<Int>(l, 2))))

  # ─── splitHalf ─────────────────────────────────────────────────────────
  let sp = splitHalf<Int>(l)
  emit("split_left_count",  count(sp.left))
  emit("split_right_count", count(sp.right))
  emit("split_left_head",   unwrap(head<Int>(sp.left)))
  emit("split_left_last",   unwrap(last<Int>(sp.left)))
  emit("split_right_head",  unwrap(head<Int>(sp.right)))
  emit("split_right_last",  unwrap(last<Int>(sp.right)))
  let s1 = splitHalf<Int>(append<Int>(List<Int>(), 7))
  emitBool("split1_left_empty", isEmpty<Int>(s1.left))
  emit("split1_right_head", unwrap(head<Int>(s1.right)))

  # ─── any / all ─────────────────────────────────────────────────────────
  emitBool("any_yes",   any<Int>(l, (x: Int) => x > 4))
  emitBool("any_no",    any<Int>(l, (x: Int) => x > 9))
  emitBool("all_yes",   all<Int>(l, (x: Int) => x > 0))
  emitBool("all_no",    all<Int>(l, (x: Int) => x > 1))
  emitBool("any_empty", any<Int>(List<Int>(), (x: Int) => x > 0))
  emitBool("all_empty", all<Int>(List<Int>(), (x: Int) => x > 0))

  # ─── contains ──────────────────────────────────────────────────────────
  emitBool("contains_yes", contains<Int>(l, 3))
  emitBool("contains_no",  contains<Int>(l, 99))

  # ─── flatMap ───────────────────────────────────────────────────────────
  let fm = flatMap<Int,Int>(b, (x: Int) => append<Int>(append<Int>(List<Int>(), x), x))
  emit("flatmap_count", count(fm))
  emit("flatmap_sum",   sum(fm))

  ret 0
"""


_EXPECTED_LINES = [
    "empty_yes=1",
    "empty_no=0",
    "last=5",
    "last_empty=-1",
    "concat_count=3",
    "concat_head=1",
    "concat_last=3",
    "concat_sum=6",
    "concat_empty_l=5",
    "concat_empty_r=1",
    "take_sum=3",
    "take_over=5",
    "take_zero=0",
    "drop_sum=12",
    "drop_over=0",
    "drop_head=3",
    "split_left_count=2",
    "split_right_count=3",
    "split_left_head=1",
    "split_left_last=2",
    "split_right_head=3",
    "split_right_last=5",
    "split1_left_empty=1",
    "split1_right_head=7",
    "any_yes=1",
    "any_no=0",
    "all_yes=1",
    "all_no=0",
    "any_empty=0",
    "all_empty=1",
    "contains_yes=1",
    "contains_no=0",
    "flatmap_count=4",
    "flatmap_sum=10",
]


class TestListExtensions(TestCase):
    def test_all_list_extensions(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

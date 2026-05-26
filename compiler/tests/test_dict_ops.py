"""Consolidated Dict<K,V> runtime test.

One program exercising empty/put/get/overwrite/remove/size/contains
on Dict<Int,Int> and Dict<String,Int>, plus an AVL-balance check
(20 ordered inserts).
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

fun insert_range(d: Dict<Int,Int>, i: Int, n: Int): Dict<Int,Int>
  ret i > n ? d : insert_range(put<Int,Int>(d, i, i), i + 1, n)

fun main(): Int
  # ─── empty get ─────────────────────────────────────────────────────────
  let empty = Dict<Int,Int>()
  emit("empty_get", unwrap(get<Int,Int>(empty, 1)))

  # ─── put then get ──────────────────────────────────────────────────────
  let d1 = put<Int,Int>(Dict<Int,Int>(), 7, 42)
  emit("put_get", unwrap(get<Int,Int>(d1, 7)))

  # ─── overwrite ─────────────────────────────────────────────────────────
  let d2 = put<Int,Int>(put<Int,Int>(Dict<Int,Int>(), 7, 11), 7, 99)
  emit("put_overwrites", unwrap(get<Int,Int>(d2, 7)))

  # ─── remove ────────────────────────────────────────────────────────────
  let d3 = remove<Int,Int>(put<Int,Int>(Dict<Int,Int>(), 5, 77), 5)
  emit("remove_then_get", unwrap(get<Int,Int>(d3, 5)))

  # ─── size ──────────────────────────────────────────────────────────────
  let d4 = put<Int,Int>(put<Int,Int>(put<Int,Int>(put<Int,Int>(put<Int,Int>(
      Dict<Int,Int>(), 1, 10), 2, 20), 3, 30), 4, 40), 5, 50)
  emit("size", size<Int,Int>(d4))

  # ─── contains true then false (after remove) ───────────────────────────
  let d5 = put<Int,Int>(Dict<Int,Int>(), 3, 99)
  emit("contains_after_put",    contains<Int,Int>(d5, 3) ? 1 : 0)
  emit("contains_after_remove", contains<Int,Int>(remove<Int,Int>(d5, 3), 3) ? 1 : 0)

  # ─── String-keyed dict ────────────────────────────────────────────────
  let s1 = put<String,Int>(put<String,Int>(Dict<String,Int>(), "hello", 7), "world", 13)
  emit("string_key_hello", unwrap(get<String,Int>(s1, "hello")))
  emit("string_key_world", unwrap(get<String,Int>(s1, "world")))

  # ─── AVL balance: 20 ordered inserts ──────────────────────────────────
  emit("avl_balance_size", size<Int,Int>(insert_range(Dict<Int,Int>(), 1, 20)))

  ret 0
"""


_EXPECTED_LINES = [
    "empty_get=-1",
    "put_get=42",
    "put_overwrites=99",
    "remove_then_get=-1",
    "size=5",
    "contains_after_put=1",
    "contains_after_remove=0",
    "string_key_hello=7",
    "string_key_world=13",
    "avl_balance_size=20",
]


class TestAllDictOps(TestCase):
    def test_all_dict_ops(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

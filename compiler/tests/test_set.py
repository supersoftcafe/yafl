"""Consolidated Set<T> runtime test.

All semantics — empty/add/contains/size, duplicate-idempotence,
remove-present/absent, persistent input invariance, String keys — in
one program.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

fun build3(): Set<Int>
  ret add<Int>(add<Int>(add<Int>(Set<Int>(), 1), 2), 3)

fun main(): Int
  # ─── empty ─────────────────────────────────────────────────────────────
  emit("empty_size",            size<Int>(Set<Int>()))
  emit("empty_contains",        contains<Int>(Set<Int>(), 42) ? 1 : 0)

  # ─── add / contains / size ────────────────────────────────────────────
  emit("after_add_contains",    contains<Int>(add<Int>(Set<Int>(), 42), 42) ? 1 : 0)
  emit("after_3_adds_size",     size<Int>(build3()))

  # ─── duplicate-add idempotence ────────────────────────────────────────
  emit("dup_add_size",          size<Int>(add<Int>(add<Int>(Set<Int>(), 5), 5)))

  # ─── remove ───────────────────────────────────────────────────────────
  emit("remove_present_then_contains",
       contains<Int>(remove<Int>(add<Int>(Set<Int>(), 7), 7), 7) ? 1 : 0)
  emit("remove_absent_size",
       size<Int>(remove<Int>(add<Int>(Set<Int>(), 1), 99)))
  emit("remove_one_then_size",
       size<Int>(remove<Int>(build3(), 2)))

  # ─── persistent: removing from a copy leaves the original intact ──────
  let s0 = add<Int>(Set<Int>(), 1)
  let s1 = remove<Int>(s0, 1)
  emit("original_unchanged_after_remove", contains<Int>(s0, 1) ? 1 : 0)

  # ─── String keys ──────────────────────────────────────────────────────
  emit("string_add_then_contains",
       contains<String>(add<String>(Set<String>(), "hello"), "hello") ? 1 : 0)
  emit("string_two_distinct_size",
       size<String>(add<String>(add<String>(Set<String>(), "a"), "b")))

  ret 0
"""


_EXPECTED_LINES = [
    "empty_size=0",
    "empty_contains=0",
    "after_add_contains=1",
    "after_3_adds_size=3",
    "dup_add_size=1",
    "remove_present_then_contains=0",
    "remove_absent_size=1",
    "remove_one_then_size=2",
    "original_unchanged_after_remove=1",
    "string_add_then_contains=1",
    "string_two_distinct_size=2",
]


class TestAllSetOps(TestCase):
    def test_all_set_ops(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

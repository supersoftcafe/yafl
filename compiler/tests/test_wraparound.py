"""Consolidated wrap-around test for Int8/16/32/64.

Each width's INT_MAX+1, INT_MIN-1, -INT_MIN, INT_MIN/-1, INT_MIN%-1
behaviours. All operations use unsigned wrap (or the explicit b==-1
paper-over for div/rem so x86 idiv doesn't SIGFPE on INT_MIN/-1).
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

fun main(): System::Int
  # ─── Int8 ──────────────────────────────────────────────────────────────
  emit("Int8_add_max_plus_1_is_min",   (INT8_MAX + 1i8) == INT8_MIN ? 1 : 0)
  emit("Int8_sub_min_minus_1_is_max",  (INT8_MIN - 1i8) == INT8_MAX ? 1 : 0)
  emit("Int8_neg_min_stays_min",       (-INT8_MIN) == INT8_MIN ? 1 : 0)
  emit("Int8_div_min_by_neg1",         (INT8_MIN / -1i8) == INT8_MIN ? 1 : 0)
  emit("Int8_rem_min_by_neg1",         Int(INT8_MIN % -1i8))

  # ─── Int16 ─────────────────────────────────────────────────────────────
  emit("Int16_add_max_plus_1_is_min",  (INT16_MAX + 1i16) == INT16_MIN ? 1 : 0)
  emit("Int16_sub_min_minus_1_is_max", (INT16_MIN - 1i16) == INT16_MAX ? 1 : 0)
  emit("Int16_neg_min_stays_min",      (-INT16_MIN) == INT16_MIN ? 1 : 0)
  emit("Int16_div_min_by_neg1",        (INT16_MIN / -1i16) == INT16_MIN ? 1 : 0)
  emit("Int16_rem_min_by_neg1",        Int(INT16_MIN % -1i16))

  # ─── Int32 ─────────────────────────────────────────────────────────────
  emit("Int32_add_max_plus_1_is_min",  (INT32_MAX + 1i32) == INT32_MIN ? 1 : 0)
  emit("Int32_sub_min_minus_1_is_max", (INT32_MIN - 1i32) == INT32_MAX ? 1 : 0)
  emit("Int32_neg_min_stays_min",      (-INT32_MIN) == INT32_MIN ? 1 : 0)
  emit("Int32_div_min_by_neg1",        (INT32_MIN / -1i32) == INT32_MIN ? 1 : 0)
  emit("Int32_rem_min_by_neg1",        Int(INT32_MIN % -1i32))

  # ─── Int64 ─────────────────────────────────────────────────────────────
  emit("Int64_add_max_plus_1_is_min",  (INT64_MAX + 1i64) == INT64_MIN ? 1 : 0)
  emit("Int64_sub_min_minus_1_is_max", (INT64_MIN - 1i64) == INT64_MAX ? 1 : 0)
  emit("Int64_neg_min_stays_min",      (-INT64_MIN) == INT64_MIN ? 1 : 0)
  emit("Int64_div_min_by_neg1",        (INT64_MIN / -1i64) == INT64_MIN ? 1 : 0)
  emit("Int64_rem_min_by_neg1",        Int(INT64_MIN % -1i64))

  ret 0
"""


_EXPECTED_LINES = [
    # Int8
    "Int8_add_max_plus_1_is_min=1",
    "Int8_sub_min_minus_1_is_max=1",
    "Int8_neg_min_stays_min=1",
    "Int8_div_min_by_neg1=1",
    "Int8_rem_min_by_neg1=0",
    # Int16
    "Int16_add_max_plus_1_is_min=1",
    "Int16_sub_min_minus_1_is_max=1",
    "Int16_neg_min_stays_min=1",
    "Int16_div_min_by_neg1=1",
    "Int16_rem_min_by_neg1=0",
    # Int32
    "Int32_add_max_plus_1_is_min=1",
    "Int32_sub_min_minus_1_is_max=1",
    "Int32_neg_min_stays_min=1",
    "Int32_div_min_by_neg1=1",
    "Int32_rem_min_by_neg1=0",
    # Int64
    "Int64_add_max_plus_1_is_min=1",
    "Int64_sub_min_minus_1_is_max=1",
    "Int64_neg_min_stays_min=1",
    "Int64_div_min_by_neg1=1",
    "Int64_rem_min_by_neg1=0",
]


class TestAllWraparound(TestCase):
    def test_all_wraparound_invariants(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout was:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

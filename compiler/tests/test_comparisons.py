"""Consolidated comparison test: < == > for every numeric width.

One yafl program checks lt/eq/gt across Int / Int8 / Int16 / Int32 /
Int64 / Float / Float32 with at least one true + one false case for
each operator.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun emit(label: System::String, value: System::Bool): System::None
  print(label + "=" + (value ? "1" : "0") + "\\n")
  ret None

fun main(): System::Int
  # ─── Int (bigint) ──────────────────────────────────────────────────────
  emit("Int_lt_true",   3 < 4)
  emit("Int_lt_false",  4 < 3)
  emit("Int_eq_true",   42 == 42)
  emit("Int_eq_false",  42 == 41)
  emit("Int_gt_true",   5 > 3)
  emit("Int_gt_false",  3 > 5)

  # ─── Int8 ──────────────────────────────────────────────────────────────
  emit("Int8_lt_true",  3i8 < 4i8)
  emit("Int8_eq_true",  42i8 == 42i8)
  emit("Int8_eq_false", 42i8 == 41i8)
  emit("Int8_gt_true",  5i8 > 3i8)
  emit("Int8_min_lt_max", INT8_MIN < INT8_MAX)

  # ─── Int16 ─────────────────────────────────────────────────────────────
  emit("Int16_lt_true",  3i16 < 4i16)
  emit("Int16_eq_true",  42i16 == 42i16)
  emit("Int16_eq_false", 42i16 == 41i16)
  emit("Int16_gt_true",  5i16 > 3i16)
  emit("Int16_min_lt_max", INT16_MIN < INT16_MAX)

  # ─── Int32 ─────────────────────────────────────────────────────────────
  emit("Int32_lt_true",  3i32 < 4i32)
  emit("Int32_eq_true",  42i32 == 42i32)
  emit("Int32_eq_false", 42i32 == 41i32)
  emit("Int32_gt_true",  5i32 > 3i32)
  emit("Int32_min_lt_max", INT32_MIN < INT32_MAX)

  # ─── Int64 ─────────────────────────────────────────────────────────────
  emit("Int64_lt_true",  3i64 < 4i64)
  emit("Int64_eq_true",  42i64 == 42i64)
  emit("Int64_eq_false", 42i64 == 41i64)
  emit("Int64_gt_true",  5i64 > 3i64)
  emit("Int64_min_lt_max", INT64_MIN < INT64_MAX)

  # ─── Float ─────────────────────────────────────────────────────────────
  emit("Float_lt_true",  1.5 < 2.5)
  emit("Float_eq_true",  3.0 == 3.0)
  emit("Float_eq_false", 3.0 == 4.0)
  emit("Float_gt_true",  5.0 > 3.0)

  # ─── Float32 ───────────────────────────────────────────────────────────
  emit("Float32_lt_true",  1.5f32 < 2.5f32)
  emit("Float32_eq_true",  3.0f32 == 3.0f32)
  emit("Float32_eq_false", 3.0f32 == 4.0f32)
  emit("Float32_gt_true",  5.0f32 > 3.0f32)

  ret 0
"""


# Every line ends with =1 except the explicit false cases.
_EXPECTED_LINES = [
    "Int_lt_true=1",   "Int_lt_false=0", "Int_eq_true=1",  "Int_eq_false=0",
    "Int_gt_true=1",   "Int_gt_false=0",
    "Int8_lt_true=1",  "Int8_eq_true=1", "Int8_eq_false=0", "Int8_gt_true=1",
    "Int8_min_lt_max=1",
    "Int16_lt_true=1", "Int16_eq_true=1","Int16_eq_false=0","Int16_gt_true=1",
    "Int16_min_lt_max=1",
    "Int32_lt_true=1", "Int32_eq_true=1","Int32_eq_false=0","Int32_gt_true=1",
    "Int32_min_lt_max=1",
    "Int64_lt_true=1", "Int64_eq_true=1","Int64_eq_false=0","Int64_gt_true=1",
    "Int64_min_lt_max=1",
    "Float_lt_true=1", "Float_eq_true=1","Float_eq_false=0","Float_gt_true=1",
    "Float32_lt_true=1","Float32_eq_true=1","Float32_eq_false=0","Float32_gt_true=1",
]


class TestAllComparisons(TestCase):
    def test_all_comparison_ops(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout was:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

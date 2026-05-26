"""Consolidated arithmetic test: +  -  *  /  %  unary-neg across
Int8/Int16/Int32/Int64/Int/Float/Float32 — one compile, every op
exercised.

Result rendering: each line prints the result as an integer string.
For float ops we round-trip through truncateToInt so the expected
output is platform-independent.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

# Per-type emit helpers. Each one widens its operand back to Int and prints
# a labelled line. Pinning every output to an integer string keeps the
# expected text independent of float-formatting subtleties.

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

fun e8(label: System::String, value: System::Int8): System::None
  emit(label, Int(value))
  ret None
fun e16(label: System::String, value: System::Int16): System::None
  emit(label, Int(value))
  ret None
fun e32(label: System::String, value: System::Int32): System::None
  emit(label, Int(value))
  ret None
fun e64(label: System::String, value: System::Int64): System::None
  emit(label, Int(value))
  ret None
fun ef(label: System::String, value: System::Float): System::None
  # truncate float to int for output stability.
  emit(label, truncateToInt(value))
  ret None
fun ef32(label: System::String, value: System::Float32): System::None
  emit(label, truncateToInt(value))
  ret None

fun main(): System::Int
  # ─── Int (bigint) ──────────────────────────────────────────────────────
  emit("Int_add",  40 + 2)
  emit("Int_sub",  10 - 7)
  emit("Int_mul",  6 * 7)
  emit("Int_div",  20 / 3)
  emit("Int_rem",  20 % 3)
  emit("Int_neg",  -42 + 100)

  # ─── Int8 ──────────────────────────────────────────────────────────────
  e8("Int8_add",  40i8 + 2i8)
  e8("Int8_sub",  10i8 - 7i8)
  e8("Int8_mul",  6i8 * 7i8)
  e8("Int8_div",  20i8 / 3i8)
  e8("Int8_rem",  20i8 % 3i8)
  e8("Int8_neg",  -42i8 + 100i8)

  # ─── Int16 ─────────────────────────────────────────────────────────────
  e16("Int16_add",  40i16 + 2i16)
  e16("Int16_sub",  1000i16 - 234i16)
  e16("Int16_mul",  6i16 * 7i16)
  e16("Int16_div",  20i16 / 3i16)
  e16("Int16_rem",  20i16 % 3i16)
  e16("Int16_neg",  -42i16 + 100i16)

  # ─── Int32 ─────────────────────────────────────────────────────────────
  e32("Int32_add",  2i32 + 3i32)
  e32("Int32_sub",  10i32 - 7i32)
  e32("Int32_mul",  6i32 * 7i32)
  e32("Int32_div",  20i32 / 3i32)
  e32("Int32_rem",  20i32 % 3i32)
  e32("Int32_neg",  -7i32 + 100i32)

  # ─── Int64 ─────────────────────────────────────────────────────────────
  e64("Int64_add",  40i64 + 2i64)
  e64("Int64_sub",  10i64 - 7i64)
  e64("Int64_mul",  6i64 * 7i64)
  e64("Int64_div",  20i64 / 3i64)
  e64("Int64_rem",  20i64 % 3i64)
  e64("Int64_neg",  -42i64 + 100i64)

  # ─── Float (Float64) ───────────────────────────────────────────────────
  ef("Float_add",  1.5 + 2.25)        # 3.75 → trunc → 3
  ef("Float_sub",  10.5 - 4.5)        # 6
  ef("Float_mul",  2.5 * 4.0)         # 10
  ef("Float_div",  7.0 / 2.0)         # 3.5 → 3
  ef("Float_rem",  10.0 % 3.0)        # 1
  ef("Float_neg",  -(7.5) + 100.0)    # 92.5 → 92

  # ─── Float32 ───────────────────────────────────────────────────────────
  ef32("Float32_add",  2.5f32 + 3.5f32)     # 6
  ef32("Float32_sub",  10.5f32 - 4.5f32)    # 6
  ef32("Float32_mul",  2.5f32 * 4.0f32)     # 10
  ef32("Float32_div",  15.0f32 / 4.0f32)    # 3.75 → 3
  ef32("Float32_rem",  10.0f32 % 3.0f32)    # 1
  ef32("Float32_neg",  -(7.5f32) + 100.0f32) # 92.5 → 92

  ret 0
"""


_EXPECTED_LINES = [
    # Int (bigint)
    "Int_add=42", "Int_sub=3", "Int_mul=42", "Int_div=6", "Int_rem=2", "Int_neg=58",
    # Int8
    "Int8_add=42", "Int8_sub=3", "Int8_mul=42", "Int8_div=6", "Int8_rem=2", "Int8_neg=58",
    # Int16
    "Int16_add=42", "Int16_sub=766", "Int16_mul=42", "Int16_div=6", "Int16_rem=2", "Int16_neg=58",
    # Int32
    "Int32_add=5", "Int32_sub=3", "Int32_mul=42", "Int32_div=6", "Int32_rem=2", "Int32_neg=93",
    # Int64
    "Int64_add=42", "Int64_sub=3", "Int64_mul=42", "Int64_div=6", "Int64_rem=2", "Int64_neg=58",
    # Float
    "Float_add=3", "Float_sub=6", "Float_mul=10", "Float_div=3", "Float_rem=1", "Float_neg=92",
    # Float32
    "Float32_add=6", "Float32_sub=6", "Float32_mul=10", "Float32_div=3", "Float32_rem=1", "Float32_neg=92",
]


class TestAllArithmetic(TestCase):
    def test_all_arithmetic_ops_produce_expected_output(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=10)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout was:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

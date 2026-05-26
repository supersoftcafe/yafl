"""Int32-specific extras not covered by the mega-tests.

Arithmetic, wrap-around, comparison, parsing, hash, and most
conversions / String rendering are covered elsewhere
(test_arithmetic, test_wraparound, test_comparisons, test_parse,
test_hash, test_conversions, test_format_show).

What's left and Int32-specific:
  * Float→Int32 trunc-toward-zero for the negative side
  * Float→Int32 clamp_low (`-1e20` → INT32_MIN)
  * Float→Int32 NaN → 0
  * String(Int32) byte-level / length checks (positive, zero, negative,
    INT32_MIN)
  * Show<Int32> via format

All in one program.
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
  # ─── Float→Int32 trunc / clamp / NaN edge cases ────────────────────────
  emit("trunc_negative",  Int(truncateToInt32(-3.7)))           # -3
  emit("clamp_low",       truncateToInt32(-1e20) == INT32_MIN ? 1 : 0)
  emit("nan_to_int32",    Int(truncateToInt32(0.0 / 0.0)))       # 0

  # ─── String(Int32) shape checks ────────────────────────────────────────
  emit("string_positive_len", length(String(42i32)))            # "42" → 2
  emit("string_zero_byte0",   byteAt(String(0i32), 0))          # '0'
  emit("string_negative_b0",  byteAt(String(-42i32), 0))        # '-'
  emit("string_int32_min_len", length(String(INT32_MIN)))       # "-2147483648" → 11

  # ─── Show<Int32> via format ────────────────────────────────────────────
  emit("format_int32_len", length(format<Int32>("v={1}", 42i32)))  # "v=42" → 4

  ret 0
"""


_EXPECTED_LINES = [
    "trunc_negative=-3",
    "clamp_low=1",
    "nan_to_int32=0",
    "string_positive_len=2",
    f"string_zero_byte0={ord('0')}",
    f"string_negative_b0={ord('-')}",
    "string_int32_min_len=11",
    "format_int32_len=4",
]


class TestInt32Extras(TestCase):
    def test_int32_extras(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

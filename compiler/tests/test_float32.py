"""Float32 extras not covered by the mega-tests.

Arithmetic, comparisons, parsing, hash, conversions, and most String
rendering are covered by the corresponding mega-tests
(test_arithmetic, test_comparisons, test_parse, test_hash,
test_conversions, test_format_show). What's left and width-specific:

  * NaN behaviour: nan != nan, isNaN(nan), isNaN(real)
  * Float32-only conversion edge cases not in test_conversions:
      - truncateToInt32(-1e20f32) clamps to INT32_MIN
      - truncateToInt32(NaN) → 0
  * String(Float32) byte-level checks (first byte for positive / negative)
  * Show<Float32> dispatch through format

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
  let nan: Float32 = 0.0f32 / 0.0f32

  # ─── NaN behaviour ─────────────────────────────────────────────────────
  emit("nan_neq_nan",   nan == nan ? 0 : 1)
  emit("isNaN_on_nan",  isNaN(nan) ? 1 : 0)
  emit("isNaN_on_real", isNaN(1.5f32) ? 1 : 0)

  # ─── Conversion edge cases not in test_conversions ────────────────────
  emit("clamp_low",     truncateToInt32(-1e20f32) == INT32_MIN ? 1 : 0)
  emit("nan_to_int32",  Int(truncateToInt32(nan)))

  # ─── String / Show byte checks ────────────────────────────────────────
  emit("string_positive_first_byte", Int(byteAt(String(3.5f32), 0)))
  emit("string_negative_first_byte", Int(byteAt(String(-3.5f32), 0)))
  emit("format_first_byte_v",        Int(byteAt(format<Float32>("v={1}", 7.0f32), 0)))

  ret 0
"""


_EXPECTED_LINES = [
    "nan_neq_nan=1",
    "isNaN_on_nan=1",
    "isNaN_on_real=0",
    "clamp_low=1",
    "nan_to_int32=0",
    f"string_positive_first_byte={ord('3')}",
    f"string_negative_first_byte={ord('-')}",
    f"format_first_byte_v={ord('v')}",
]


class TestFloat32Extras(TestCase):
    def test_float32_extras(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

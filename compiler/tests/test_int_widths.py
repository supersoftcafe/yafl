"""Width-specific extras for Int8/Int16/Int64 not already covered by the
mega-tests (arithmetic, wraparound, conversions, comparisons, parse,
hash). One compile checks: widening with a non-conversion-mega value,
String(INT<N>_MIN) byte counts, and Show via format dispatch.
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
  # ─── A widening case not pinned in test_conversions ────────────────────
  emit("Int8_to_Int_100",  Int(100i8))

  # ─── String(INT<N>_MIN) byte counts — exercises the snprintf paths ─────
  emit("string_int8_min_len",  length(String(INT8_MIN)))    # "-128"
  emit("string_int16_min_len", length(String(INT16_MIN)))   # "-32768"
  emit("string_int64_min_len", length(String(INT64_MIN)))   # "-9223372036854775808"

  # ─── format dispatch via Show<IntN> ────────────────────────────────────
  emit("format_int8",  length(format<Int8>("v={1}",  -5i8)))    # "v=-5"
  emit("format_int64", length(format<Int64>("v={1}", 42i64)))    # "v=42"

  # ─── Cross-width chain Int8 → Int16 → Int32 → Int64 ────────────────────
  let a: Int16 = Int16(-5i8)
  let b: Int32 = Int32(a)
  let c: Int64 = Int64(b)
  emit("chain_widen_eq_neg5", c == -5i64 ? 1 : 0)

  ret 0
"""


_EXPECTED_LINES = [
    "Int8_to_Int_100=100",
    "string_int8_min_len=4",
    "string_int16_min_len=6",
    "string_int64_min_len=20",
    "format_int8=4",
    "format_int64=4",
    "chain_widen_eq_neg5=1",
]


class TestIntWidthExtras(TestCase):
    def test_int_width_extras(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

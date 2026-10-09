"""Consolidated parse* test.

Covers parseInt / parseInt8 / parseInt16 / parseInt32 / parseInt64 /
parseFloat / parseFloat32 — every parser, every code path (valid /
negative / max / min / overflow / invalid).

The yafl program prints `<label>=<int>` lines where `<int>` is the
parsed value (or -1 as a sentinel for None / parse failure). Python
checks the line set.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

# Sentinel -1 for None / failure.

fun parsedInt(s: System::String): System::Int
  ret match(parseInt(s))
    (i: System::Int) => i
    (n: System::None) => -1

fun parsedInt8(s: System::String): System::Int
  ret match(parseInt8(s))
    (v: System::Int8) => Int(v)
    (n: System::None) => -1

fun parsedInt16(s: System::String): System::Int
  ret match(parseInt16(s))
    (v: System::Int16) => Int(v)
    (n: System::None) => -1

fun parsedInt32(s: System::String): System::Int
  ret match(parseInt32(s))
    (v: System::Int32) => Int(v)
    (n: System::None) => -1

fun parsedInt64(s: System::String): System::Int
  ret match(parseInt64(s))
    (v: System::Int64) => Int(v)
    (n: System::None) => -1

# For Float / Float32 we truncate the parsed value back to Int so the
# output is platform-independent.
fun parsedFloat(s: System::String): System::Int
  ret match(parseFloat(s))
    (f: System::Float) => truncateToInt(f)
    (n: System::None) => -1

fun parsedFloat32(s: System::String): System::Int
  ret match(parseFloat32(s))
    (f: System::Float32) => truncateToInt(f)
    (n: System::None) => -1

fun main(): System::Int
  # ─── parseInt (bigint) ─────────────────────────────────────────────────
  emit("parseInt_valid",     parsedInt("42"))
  emit("parseInt_negative",  parsedInt("-7"))
  emit("parseInt_invalid",   parsedInt("notanumber"))

  # ─── parseInt8 ─────────────────────────────────────────────────────────
  emit("parseInt8_valid",    parsedInt8("42"))
  emit("parseInt8_overflow", parsedInt8("500"))

  # ─── parseInt16 ────────────────────────────────────────────────────────
  emit("parseInt16_valid",    parsedInt16("12345"))
  emit("parseInt16_overflow", parsedInt16("999999"))

  # ─── parseInt32 ────────────────────────────────────────────────────────
  emit("parseInt32_valid",    parsedInt32("42"))
  emit("parseInt32_negative", parsedInt32("-7"))
  emit("parseInt32_max",      parsedInt32("2147483647"))
  emit("parseInt32_min",      parsedInt32("-2147483648"))
  emit("parseInt32_overflow", parsedInt32("99999999999"))
  emit("parseInt32_invalid",  parsedInt32("abc"))

  # ─── parseInt64 ────────────────────────────────────────────────────────
  emit("parseInt64_valid",    parsedInt64("9223372036854775807"))
  emit("parseInt64_overflow", parsedInt64("99999999999999999999999"))

  # ─── parseFloat (Float64) ──────────────────────────────────────────────
  emit("parseFloat_valid",   parsedFloat("2.5"))
  emit("parseFloat_invalid", parsedFloat("not a number"))

  # ─── parseFloat32 ──────────────────────────────────────────────────────
  emit("parseFloat32_simple",   parsedFloat32("2.5"))
  emit("parseFloat32_negative", parsedFloat32("-7.0"))
  emit("parseFloat32_invalid",  parsedFloat32("abc"))

  ret 0
"""


_EXPECTED_LINES = [
    "parseInt_valid=42",
    "parseInt_negative=-7",
    "parseInt_invalid=-1",
    "parseInt8_valid=42",
    "parseInt8_overflow=-1",
    "parseInt16_valid=12345",
    "parseInt16_overflow=-1",
    "parseInt32_valid=42",
    "parseInt32_negative=-7",
    "parseInt32_max=2147483647",
    "parseInt32_min=-2147483648",
    "parseInt32_overflow=-1",
    "parseInt32_invalid=-1",
    "parseInt64_valid=9223372036854775807",
    "parseInt64_overflow=-1",
    "parseFloat_valid=2",   # truncateToInt(2.5) = 2
    "parseFloat_invalid=-1",
    "parseFloat32_simple=2",
    "parseFloat32_negative=-7",
    "parseFloat32_invalid=-1",
]


class TestAllParsers(TestCase):
    def test_all_parsers_produce_expected_output(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout was:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

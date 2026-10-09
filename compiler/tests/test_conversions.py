"""Consolidated conversion test: every Int/Float conversion function in
the stdlib, every per-width `String(_)`, and `print` of `String` — all
exercised in a single compiled program.

The program prints one `name=value` line per conversion, all values
rendered as integers (we always round-trip floats back to Int so the
expected output is platform-independent — no `%.17g` rendering of
floats to worry about). Python compares the full stdout against the
precomputed expected lines.

What this single test replaces, by feature:
  * `String(IntN)` for every width N — exercised on every line.
  * `print(String)` — every line is a print call.
  * `Int(IntN)` widenings — used on every IntN value to print it.
  * `truncateToIntN(Int)` and `truncateToIntN(IntM)` for N<M.
  * `Float(IntN)` and `Float32(IntN)` round-trips back to Int.
  * `truncateToInt(Float)` and `truncateToInt(Float32)` round-trips.
  * `Float32(Float)` and `Float(Float32)` round-trips.
  * `truncateToInt32(Float)` / `truncateToInt32(Float32)` / etc.

A single compile (~10–12 s) replaces dozens of per-case compiles.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


# ─── yafl source ─────────────────────────────────────────────────────────────

_SRC = """\
import System

# Each emit prints "label=integer\\n". We pin everything to integer-valued
# output so the test is platform-independent (no %g float rendering).

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

fun emitInt32(label: System::String, value: System::Int32): System::None
  emit(label, Int(value))
  ret None
fun emitInt8(label: System::String, value: System::Int8): System::None
  emit(label, Int(value))
  ret None
fun emitInt16(label: System::String, value: System::Int16): System::None
  emit(label, Int(value))
  ret None
fun emitInt64(label: System::String, value: System::Int64): System::None
  emit(label, Int(value))
  ret None

fun main(): System::Int
  # ─── String(_) per width via emit's `String(value)` ────────────────────
  # (Exercised implicitly on every line below — emit prints String(value).)

  # ─── Widening to bigint (Int8/16/32/64 -> Int) ─────────────────────────
  emit("Int_from_Int8",  Int(-5i8))
  emit("Int_from_Int16", Int(-1234i16))
  emit("Int_from_Int32", Int(2147483647i32))
  emit("Int_from_Int64", Int(9223372036854775807i64))

  # ─── Widening across fixed widths (exact) ──────────────────────────────
  emitInt16("Int16_from_Int8",  Int16(-5i8))
  emitInt32("Int32_from_Int8",  Int32(-5i8))
  emitInt32("Int32_from_Int16", Int32(INT16_MAX))
  emitInt64("Int64_from_Int8",  Int64(-5i8))
  emitInt64("Int64_from_Int16", Int64(INT16_MAX))
  emitInt64("Int64_from_Int32", Int64(INT32_MAX))

  # ─── Narrowing into fixed widths (truncate, wraps) ─────────────────────
  emitInt8("truncateToInt8_Int",    truncateToInt8(300))
  emitInt8("truncateToInt8_Int16",  truncateToInt8(INT16_MAX))
  emitInt8("truncateToInt8_Int32",  truncateToInt8(257i32))
  emitInt8("truncateToInt8_Int64",  truncateToInt8(INT64_MAX))
  emitInt8("truncateToInt8_Float",  truncateToInt8(1000.0))
  emitInt8("truncateToInt8_Float32", truncateToInt8(-1000.0f32))

  emitInt16("truncateToInt16_Int",     truncateToInt16(70000))
  emitInt16("truncateToInt16_Int32",   truncateToInt16(65537i32))
  emitInt16("truncateToInt16_Int64",   truncateToInt16(INT64_MAX))
  emitInt16("truncateToInt16_Float",   truncateToInt16(1e10))
  emitInt16("truncateToInt16_Float32", truncateToInt16(-1e10f32))

  emitInt32("truncateToInt32_Int",     truncateToInt32(4294967295))
  emitInt32("truncateToInt32_Int64",   truncateToInt32(INT64_MAX))
  emitInt32("truncateToInt32_Float",   truncateToInt32(1e20))
  emitInt32("truncateToInt32_Float32", truncateToInt32(1e20f32))

  emitInt64("truncateToInt64_Int",     truncateToInt64(18446744073709551616))
  emitInt64("truncateToInt64_Float",   truncateToInt64(1e30))
  emitInt64("truncateToInt64_Float32", truncateToInt64(-1e30f32))

  # ─── Float/Float32 -> Int (bigint, truncate) ───────────────────────────
  emit("truncateToInt_Float_pos",   truncateToInt(3.7))
  emit("truncateToInt_Float_neg",   truncateToInt(-3.7))
  emit("truncateToInt_Float32_pos", truncateToInt(3.7f32))
  emit("truncateToInt_Float32_neg", truncateToInt(-3.7f32))

  # ─── Int -> Float -> Int round-trips (small enough to be exact) ────────
  emit("Float_round_trip_Int",   truncateToInt(Float(42)))
  emit("Float_round_trip_Int8",  truncateToInt(Float(-5i8)))
  emit("Float_round_trip_Int16", truncateToInt(Float(INT16_MAX)))
  emit("Float_round_trip_Int32", truncateToInt(Float(INT32_MAX)))

  emit("Float32_round_trip_Int",   truncateToInt(Float32(42)))
  emit("Float32_round_trip_Int8",  truncateToInt(Float32(-5i8)))
  emit("Float32_round_trip_Int16", truncateToInt(Float32(INT16_MAX)))

  # ─── Float64 <-> Float32 ───────────────────────────────────────────────
  emit("Float32_then_Float_round_trip", truncateToInt(Float(Float32(3.0))))
  emit("Float_then_Float32_round_trip", truncateToInt(Float32(Float(3.0f32))))

  ret 0
"""


# Hand-computed expected outputs — one per emit() above, in source order.
_EXPECTED_LINES = [
    # Widening to bigint
    "Int_from_Int8=-5",
    "Int_from_Int16=-1234",
    "Int_from_Int32=2147483647",
    "Int_from_Int64=9223372036854775807",
    # Widening across fixed widths
    "Int16_from_Int8=-5",
    "Int32_from_Int8=-5",
    "Int32_from_Int16=32767",
    "Int64_from_Int8=-5",
    "Int64_from_Int16=32767",
    "Int64_from_Int32=2147483647",
    # Narrowing — every result computed by hand
    "truncateToInt8_Int=44",                # 300 & 0xff
    "truncateToInt8_Int16=-1",              # INT16_MAX (0x7fff) → low 8 bits 0xff = -1
    "truncateToInt8_Int32=1",               # 257 & 0xff
    "truncateToInt8_Int64=-1",              # INT64_MAX → 0xff = -1
    "truncateToInt8_Float=127",             # 1000.0 clamps to INT8_MAX
    "truncateToInt8_Float32=-128",          # -1000.0 clamps to INT8_MIN
    "truncateToInt16_Int=4464",             # 70000 & 0xffff
    "truncateToInt16_Int32=1",              # 65537 & 0xffff
    "truncateToInt16_Int64=-1",             # INT64_MAX → 0xffff = -1
    "truncateToInt16_Float=32767",          # 1e10 clamps to INT16_MAX
    "truncateToInt16_Float32=-32768",       # -1e10 clamps to INT16_MIN
    "truncateToInt32_Int=-1",               # 4294967295 → low 32 bits = -1
    "truncateToInt32_Int64=-1",             # INT64_MAX → low 32 bits = -1
    "truncateToInt32_Float=2147483647",     # 1e20 clamps to INT32_MAX
    "truncateToInt32_Float32=2147483647",   # 1e20 clamps to INT32_MAX
    "truncateToInt64_Int=0",                # 2^64 mod 2^64 = 0
    "truncateToInt64_Float=9223372036854775807",    # 1e30 clamps to INT64_MAX
    "truncateToInt64_Float32=-9223372036854775808", # -1e30 clamps to INT64_MIN
    # Float -> Int truncate
    "truncateToInt_Float_pos=3",
    "truncateToInt_Float_neg=-3",
    "truncateToInt_Float32_pos=3",
    "truncateToInt_Float32_neg=-3",
    # Int -> Float -> Int round trips
    "Float_round_trip_Int=42",
    "Float_round_trip_Int8=-5",
    "Float_round_trip_Int16=32767",
    "Float_round_trip_Int32=2147483647",
    "Float32_round_trip_Int=42",
    "Float32_round_trip_Int8=-5",
    "Float32_round_trip_Int16=32767",
    # Float64 <-> Float32
    "Float32_then_Float_round_trip=3",
    "Float_then_Float32_round_trip=3",
]


class TestAllNumericConversions(TestCase):
    """One compile, every conversion line.

    Failure mode: prints both expected and actual stdout so the diff is
    obvious. The exit code from the program is 0 on success; we ignore
    it and rely on the stdout content match — that way a missing line
    fails the test even if the program happens to exit 0."""

    def test_all_conversions_produce_expected_output(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=10)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout was:\n{stdout}")
        actual_lines = stdout.splitlines()
        # Order matters — emit() is called in deterministic order in the
        # yafl source, so the stdout lines should appear in that order.
        # Comparing full lists makes any divergence (missing line, wrong
        # value, reordering) show up directly in the diff.
        self.assertEqual(_EXPECTED_LINES, actual_lines)

"""Consolidated string operation test.

Covers length / slice / compare / `==` / `<` / asciiToString — every
case from the old test_strings_floats.TestStringOps in one compile.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

fun emitBool(label: System::String, value: System::Bool): System::None
  print(label + "=" + (value ? "1" : "0") + "\\n")
  ret None

fun main(): System::Int
  # ─── length ────────────────────────────────────────────────────────────
  emit("length_empty", length(""))
  emit("length_short", length("hello"))
  emit("length_long",  length("hello, world!!"))

  # ─── slice ─────────────────────────────────────────────────────────────
  emit("slice_round_trip_len", length(slice("abcdef", 1, 4)))

  # ─── compare ───────────────────────────────────────────────────────────
  emit("compare_equal", compare("abc", "abc"))
  emit("compare_lt_is_negative", compare("abc", "abd") < 0 ? 1 : 0)

  # ─── operator overloads ───────────────────────────────────────────────
  emitBool("string_eq_same",  "hi"  == "hi")
  emitBool("string_eq_diff",  "hi"  == "ho")
  emitBool("string_lt_abc_abd", "abc" < "abd")

  # ─── asciiToString ─────────────────────────────────────────────────────
  emit("ascii_A_len",   length(asciiToString(65)))
  emit("ascii_A_byte",  byteAt(asciiToString(65), 0))
  emit("ascii_0_byte",  byteAt(asciiToString(0), 0))
  emit("ascii_0_len",   length(asciiToString(0)))
  emit("ascii_200_byte",byteAt(asciiToString(200), 0))

  ret 0
"""


_EXPECTED_LINES = [
    "length_empty=0",
    "length_short=5",
    "length_long=14",
    "slice_round_trip_len=3",
    "compare_equal=0",
    "compare_lt_is_negative=1",
    "string_eq_same=1",
    "string_eq_diff=0",
    "string_lt_abc_abd=1",
    "ascii_A_len=1",
    "ascii_A_byte=65",
    "ascii_0_byte=0",
    "ascii_0_len=1",
    "ascii_200_byte=200",
]


class TestAllStringOps(TestCase):
    def test_all_string_ops(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

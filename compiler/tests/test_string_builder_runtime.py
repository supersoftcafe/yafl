"""Consolidated StringBuilder runtime test.

Builds many builders in one program and prints labelled length/byte
results. Covers TestStringBuilderRuntime (11 tests) and
TestStringBuilderIntAppend (7 tests) from the old test_string_builder.py.

Linearity tests still live in test_string_builder.py — they check
compile-time *rejection*, so they can't share a compile with anything.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


_SRC = """\
import System

fun emit(label: System::String, value: System::Int): System::None
  print(label + "=" + String(value) + "\\n")
  ret None

# Build, materialise, and report length of a builder produced by `make`.
# Each helper hides the StringBuilder behind a single call so the linear-
# type rules don't trip — each builder is consumed exactly once inside
# its own scope.

fun lenOf(b: System::StringBuilder): System::Int
  ret System::length(System::toString(b))

fun byteOf(b: System::StringBuilder, at: System::Int): System::Int
  ret System::byteAt(System::toString(b), at)

fun lastByteOf(b: System::StringBuilder): System::Int
  let s = System::toString(b)
  ret System::byteAt(s, System::length(s) - 1)

# A small recursive append loop used by the regrowth cases.
fun loop4(sb: System::StringBuilder, n: System::Int): System::StringBuilder
  ret n == 0 ? sb : loop4(System::append(sb, "abcd"), n - 1)

fun main(): System::Int
  # ─── Single-append / empty cases ──────────────────────────────────────
  emit("empty_len",                lenOf(System::StringBuilder()))
  emit("short_append_len",         lenOf(System::append(System::StringBuilder(), "hello")))
  emit("short_append_first_byte",  byteOf(System::append(System::StringBuilder(), "hello"), 0))
  emit("short_append_last_byte",   byteOf(System::append(System::StringBuilder(), "hello"), 4))
  emit("heap_append_len",          lenOf(System::append(System::StringBuilder(), "abcdefghijklmnop")))
  emit("append_empty_value_len",   lenOf(System::append(System::StringBuilder(), "")))

  # ─── Two-append cases ─────────────────────────────────────────────────
  emit("two_append_len",           lenOf(System::append(System::append(System::StringBuilder(), "foo"), "bar")))
  emit("two_append_join_byte",     byteOf(System::append(System::append(System::StringBuilder(), "foo"), "bar"), 3))

  # ─── Regrowth: many appends past the 16-byte initial capacity ──────────
  emit("regrow_len_7x4",           lenOf(loop4(System::StringBuilder(), 7)))                                  # 28
  emit("regrow_preserves_byte0",   byteOf(loop4(System::append(System::StringBuilder(), "X"), 30), 0))         # 'X'
  emit("regrow_preserves_last",    lastByteOf(loop4(System::StringBuilder(), 10)))                             # 'd'

  # ─── Int appends ──────────────────────────────────────────────────────
  emit("int_single_digit_len",     lenOf(System::append(System::StringBuilder(), 7)))
  emit("int_single_digit_byte0",   byteOf(System::append(System::StringBuilder(), 7), 0))
  emit("int_multi_digit_len",      lenOf(System::append(System::StringBuilder(), 12345)))
  emit("int_negative_len",         lenOf(System::append(System::StringBuilder(), -7)))
  emit("int_negative_byte0",       byteOf(System::append(System::StringBuilder(), -42), 0))
  emit("int_zero_len",             lenOf(System::append(System::StringBuilder(), 0)))
  emit("int_mixed_str_then_int_len", lenOf(System::append(System::append(System::StringBuilder(), "x="), 123)))

  ret 0
"""


_EXPECTED_LINES = [
    "empty_len=0",
    "short_append_len=5",
    f"short_append_first_byte={ord('h')}",
    f"short_append_last_byte={ord('o')}",
    "heap_append_len=16",
    "append_empty_value_len=0",
    "two_append_len=6",
    f"two_append_join_byte={ord('b')}",
    "regrow_len_7x4=28",
    f"regrow_preserves_byte0={ord('X')}",
    f"regrow_preserves_last={ord('d')}",
    "int_single_digit_len=1",
    f"int_single_digit_byte0={ord('7')}",
    "int_multi_digit_len=5",
    "int_negative_len=2",
    f"int_negative_byte0={ord('-')}",
    "int_zero_len=1",
    "int_mixed_str_then_int_len=5",
]


class TestAllStringBuilderRuntime(TestCase):
    def test_all_stringbuilder_runtime(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=15)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

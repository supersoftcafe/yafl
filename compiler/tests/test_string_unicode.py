"""Codepoint / Unicode layer over byte-indexed UTF-8 strings.

Exercises codepointAt / decode / codepointCount / codepoints / isValidUtf8
on a mixed-width string ("héllo🎉": h=1 byte, é=2, l/l/o=1 each, 🎉=4 →
10 bytes, 6 codepoints). length stays byte-based; the codepoint layer rides
on top of the strict UTF-8 decoder.
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

# codepointAt, collapsing None to a -1 sentinel so it is easy to print.
# Codepoints are Int32; widen to Int for printing.
fun cpOr(s: System::String, off: System::Int): System::Int
  ret match(codepointAt(s, off))
    (cp: System::Int32) => Int(cp)
    (n: System::None)   => -1

# Rebuild a string from its codepoints — round-trips decode against Char.
fun rebuild(s: System::String): System::String
  ret fold<System::Int32, System::String>(codepoints(s), "", (acc: System::String, cp: System::Int32) => acc + Char(cp))

fun main(): System::Int
  let s = "héllo🎉"

  # ─── byte length vs codepoint count ──────────────────────────────────
  emit("byte_length",     length(s))
  emit("codepoint_count", codepointCount(s))
  emit("cp_count_empty",  codepointCount(""))

  # ─── literal is encoded as UTF-8: 'é' (U+00E9) is the two bytes C3 A9, ──
  #     not a single Latin-1 0xE9. ────────────────────────────────────────
  emit("e_acute_byte_lead", Int(byteAt(s, 1)))   # 0xC3 = 195
  emit("e_acute_byte_cont", Int(byteAt(s, 2)))   # 0xA9 = 169

  # ─── codepointAt by byte offset ──────────────────────────────────────
  emit("cp_at_0", cpOr(s, 0))   # 'h'
  emit("cp_at_1", cpOr(s, 1))   # 'é'  (U+00E9, bytes 1..2)
  emit("cp_at_2", cpOr(s, 2))   # inside 'é' → None → -1
  emit("cp_at_3", cpOr(s, 3))   # 'l'
  emit("cp_at_6", cpOr(s, 6))   # '🎉' (U+1F389, bytes 6..9)
  emit("cp_at_end", cpOr(s, 10))  # past the end → -1
  emit("cp_at_neg", cpOr(s, -1))  # out of range → -1

  # ─── codepoints / round-trip ─────────────────────────────────────────
  emit("codepoints_len", length<System::Int32>(codepoints(s)))
  emitBool("rebuild_round_trips", rebuild(s) == s)

  # ─── validation: full string valid, a split multibyte slice is not ───
  emitBool("valid_full",  isValidUtf8(s))
  emitBool("valid_split", isValidUtf8(slice(s, 0, 2)))  # cuts 'é' in half

  ret 0
"""


_EXPECTED_LINES = [
    "byte_length=10",
    "codepoint_count=6",
    "cp_count_empty=0",
    "e_acute_byte_lead=195",
    "e_acute_byte_cont=169",
    "cp_at_0=104",
    "cp_at_1=233",
    "cp_at_2=-1",
    "cp_at_3=108",
    "cp_at_6=127881",
    "cp_at_end=-1",
    "cp_at_neg=-1",
    "codepoints_len=6",
    "rebuild_round_trips=1",
    "valid_full=1",
    "valid_split=0",
]


class TestStringUnicode(TestCase):
    def test_codepoint_layer(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=20)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

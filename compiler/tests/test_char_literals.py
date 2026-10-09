"""Single-quote char literals.

A char literal is sugar for an Int32 codepoint: `'A'` is identical to `65i32`.
Escapes are decoded exactly like string escapes (`\\n`, `\\\\`, `\\'`, …), literal
non-ASCII works directly (source is UTF-8), and char literals are usable as
match-arm literals (dispatching on a character).
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

# Classify a codepoint by matching char literals — char literals are Int32,
# so they line up with an Int32 subject.
fun classify(c: System::Int32): System::String
  ret match(c)
    ('\\n') => "newline"
    ('0')   => "zero"
    ('A')   => "cap-A"
    (other) => "other"

fun main(): System::Int
  # ─── codepoint values ────────────────────────────────────────────────
  emit("cap_A",     Int('A'))      # 65
  emit("digit_0",   Int('0'))      # 48
  emit("newline",   Int('\\n'))    # 10
  emit("tab",       Int('\\t'))    # 9
  emit("nul",       Int('\\0'))    # 0
  emit("backslash", Int('\\\\'))   # 92
  emit("squote",    Int('\\''))    # 39
  emit("dquote",    Int('"'))      # 34
  emit("e_acute",   Int('é'))      # 233  (literal, source is UTF-8)
  emit("party",     Int('🎉'))     # 127881

  # ─── a char literal IS an Int32 literal ──────────────────────────────
  emitBool("A_eq_65i32", 'A' == 65i32)
  emit("A_plus_1", Int('A' + 1i32))   # 66

  # ─── char literals as match-arm literals ─────────────────────────────
  print("classify_A=" + classify('A') + "\\n")
  print("classify_nl=" + classify('\\n') + "\\n")
  print("classify_other=" + classify('z') + "\\n")

  ret 0
"""


_EXPECTED_LINES = [
    "cap_A=65",
    "digit_0=48",
    "newline=10",
    "tab=9",
    "nul=0",
    "backslash=92",
    "squote=39",
    "dquote=34",
    "e_acute=233",
    "party=127881",
    "A_eq_65i32=1",
    "A_plus_1=66",
    "classify_A=cap-A",
    "classify_nl=newline",
    "classify_other=other",
]


class TestCharLiterals(TestCase):
    def test_char_literals(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=20)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

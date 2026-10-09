"""findAny / skipAny treat `accept` as a set of CODEPOINTS, not bytes.

A byte-set implementation decomposes a non-ASCII `accept` into UTF-8 bytes and
scans `s` byte-by-byte, which can match a continuation byte and return an
offset in the middle of a codepoint. These check codepoint semantics: returned
offsets are codepoint boundaries, and membership is by codepoint.
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
  # ─── findAny: codepoint membership, boundary offsets ─────────────────
  # 'Â' (U+00C2 = C3 82) is NOT in "€" (U+20AC = E2 82 AC). A byte scan would
  # match the shared 0x82 at offset 1; codepoint-correct is not-found = 3.
  emit("findAny_absent_nonascii", findAny("€", "Â", 0))   # 3
  emit("findAny_present_multibyte", findAny("a€b", "€", 0)) # 1 (€ starts at byte 1)
  emit("findAny_ascii", findAny("abc", "c", 0))            # 2
  emit("findAny_none",  findAny("abc", "xyz", 0))          # 3

  # ─── skipAny: skip member codepoints, stop at first non-member ───────
  # 'Ã' (C3 83) shares lead byte 0xC3 with 'é' (C3 A9); a byte scan steps into
  # 'é' and stops at offset 1. Codepoint-correct: 'é' is not 'Ã', stop at 0.
  emit("skipAny_collide", skipAny("éx", "Ã", 0))           # 0
  emit("skipAny_multibyte_run", skipAny("ααx", "α", 0))    # 4 (two 2-byte α's)
  emit("skipAny_ascii_ws", skipAny("  a", " ", 0))         # 2

  ret 0
"""


_EXPECTED_LINES = [
    "findAny_absent_nonascii=3",
    "findAny_present_multibyte=1",
    "findAny_ascii=2",
    "findAny_none=3",
    "skipAny_collide=0",
    "skipAny_multibyte_run=4",
    "skipAny_ascii_ws=2",
]


class TestStringFindAny(TestCase):
    def test_find_skip_any_codepoints(self):
        rc, stdout = compile_and_run_stdlib_capture(_SRC, timeout=20)
        self.assertEqual(0, rc, f"program exited with {rc}; stdout:\n{stdout}")
        self.assertEqual(_EXPECTED_LINES, stdout.splitlines())

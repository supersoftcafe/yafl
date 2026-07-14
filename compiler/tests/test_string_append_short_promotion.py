"""String append must not lose data when a SHORT (pointer-packed) string is
promoted to a heap string.

`slice`-ing a string one BYTE at a time and appending — the ordinary way to
copy a buffer with escapes — silently destroyed everything accumulated so far
once the result crossed the short-string capacity, but only when the appended
byte was part of a multi-byte character. Pure-ASCII growth of any length is
fine, which is why this hid: the corpus only trips it on strings containing
non-ASCII text (the bootstrap compiler's own error messages).
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib_capture

_SRC = """
namespace Main
import System

fun [tail] copyBytes(src: System::String, i: System::Int,
                     acc: System::String): System::String
  if i >= System::length(src)
    ret acc
  ret copyBytes(src, i + 1, acc + System::slice(src, i, i + 1))

fun main(): System::Int
  # ASCII past the short-string boundary (was always fine).
  print("[" + copyBytes("abcdefghijkl", 0, "") + "]\\n")
  # The same copy where the byte crossing the boundary is a UTF-8 continuation.
  print("[" + copyBytes("abcdef…gh", 0, "") + "]\\n")
  # And a short multi-byte string that never crosses it.
  print("[" + copyBytes("a…b", 0, "") + "]\\n")
  ret 0
"""


class TestStringAppendShortPromotion(TimedTestCase):
    def test_byte_copy_survives_promotion(self):
        rc, out = compile_and_run_stdlib_capture(_SRC)
        self.assertEqual(0, rc)
        self.assertEqual("[abcdefghijkl]\n[abcdef…gh]\n[a…b]\n", out)

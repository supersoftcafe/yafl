"""A [tail] loop whose return type is a [final] class must not lose its
string accumulator.

Byte-copying a string that contains a multi-byte character, in a [tail] loop
returning a class, silently RESET the accumulator: everything appended before
the multi-byte char vanished. The identical loop returning a bare String is
correct, so the class return (its structural in-loop representation) is the
trigger. Found by the bootstrap compiler's string-unescape port, whose error
messages contain '…'.
"""
from tests.testutil import TimedTestCase, compile_and_run_stdlib_capture

_SRC = """
namespace Main
import System

class [final] Res(rText: System::String, rErr: System::String)

fun [tail] walk(src: System::String, i: System::Int, acc: System::String): Res
  if i >= System::length(src)
    ret Res(acc, "")
  let c = System::byteAt(src, i)
  if c == 'X'
    ret walk(src, i + 2, acc + "!")
  ret walk(src, i + 1, acc + System::slice(src, i, i + 1))

fun main(): System::Int
  # 'aXb…c' — the X consumes two bytes; the ellipsis is three bytes.
  let r = walk("aXb…c", 0, "")
  print("[" + r.rText + "]\\n")
  ret 0
"""


class TestTailClassAccumulator(TimedTestCase):
    def test_accumulator_survives_multibyte(self):
        rc, out = compile_and_run_stdlib_capture(_SRC)
        self.assertEqual(0, rc)
        self.assertEqual("[a!…c]\n", out)

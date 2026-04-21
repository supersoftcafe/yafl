"""Clean-compilation tests.

Each test verifies that the generated C code compiles with clang producing
zero warnings, zero errors, and zero notes (-Werror, -fsyntax-only).
"""
from __future__ import annotations

from unittest import TestCase
from tests.testutil import assert_clean_compile


_PREAMBLE = """\
namespace Test
import System
import System::IO
"""


class TestCleanCompile(TestCase):

    def test_async_io_read_chain(self):
        """Three chained ?> reads: exercises the async state struct and
        the TASK_UNTAG assignment that previously emitted an
        incompatible-pointer-types warning."""
        src = _PREAMBLE + """\
class Triple(a: System::String, b: System::String, c: System::String)

fun readThree(io: IO): (io: IO, v: Triple|IOError)
  ret io.read(10) ?> (io: IO, a: System::String) =>
      io.read(12) ?> (io: IO, b: System::String) =>
      io.read(16) ?> (io: IO, c: System::String) =>
      (io=io, v=Triple(a, b, c))

fun main(): System::Int
  ret 0
"""
        assert_clean_compile(src)

    def test_async_state_struct_pointer_mask(self):
        """A function whose async state struct has many pointer-bearing fields
        must not trigger a shift-count-overflow warning from the maskof macro."""
        src = _PREAMBLE + """\
class Big(
  a: System::String, b: System::String, c: System::String,
  d: System::String, e: System::String, f: System::String)

fun readSix(io: IO): (io: IO, v: Big|IOError)
  ret io.read(1) ?> (io: IO, a: System::String) =>
      io.read(2) ?> (io: IO, b: System::String) =>
      io.read(3) ?> (io: IO, c: System::String) =>
      io.read(4) ?> (io: IO, d: System::String) =>
      io.read(5) ?> (io: IO, e: System::String) =>
      io.read(6) ?> (io: IO, f: System::String) =>
      (io=io, v=Big(a, b, c, d, e, f))

fun main(): System::Int
  ret 0
"""
        assert_clean_compile(src)

    def test_destructure_io_result_in_main(self):
        """Destructuring an async IO result in main must not produce an
        undeclared-identifier error for the generated discard variable."""
        src = _PREAMBLE + """\
class Pair(a: System::String, b: System::String)

fun readPair(io: IO): (io: IO, v: Pair|IOError)
  ret io.read(5) ?> (io: IO, a: System::String) =>
      io.read(5) ?> (io: IO, b: System::String) =>
      (io=io, v=Pair(a, b))

fun main(): System::Int
  let (io, value) = readPair(stdin())
  io.close()
  ret 0
"""
        assert_clean_compile(src)

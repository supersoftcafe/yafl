"""Streaming readLine: returns each line verbatim (terminator kept), bounded to
maxLen bytes per call so huge or newline-free files stay within bounded memory.

See yafllib/io.c (io_take_line / io_refill) and stdlib/io.yafl (readLine).
"""
from __future__ import annotations

import os
import tempfile

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


_DONE = """fun _done(h: IO, code: System::Int): System::Int
  ret match(h.close())
    (e: IOError)      => code
    (n: System::None) => code
"""

# Count the lines in a file with a streaming readLine loop, returning the count
# as the exit code. `[tail]` (direct self-recursion) so it is a loop.
_COUNT = """fun [tail] count(io: IO, n: System::Int): (io: IO, v: System::Int)
  let r = readLine(io)
  ret match(r.v)
    (line: System::String) => count(r.io, n + 1)
    (e: IOError)           => (r.io, n)

fun run(io: IO): System::Int
  let r = count(io, 0)
  ret _done(r.io, r.v)
"""


class TestReadLine(TestCase):
    def _count(self, content: bytes) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "f")
            with open(path, "wb") as f:
                f.write(content)
            src = (f"namespace Main\nimport System\nimport System::IO\n\n"
                   f"{_DONE}\n{_COUNT}\n"
                   f'fun main(): System::Int\n'
                   f'  ret match(open_read("{path}"))\n'
                   f"    (io: IO) => run(io)\n"
                   f"    (e: IOError) => 88\n")
            return compile_and_run_stdlib(src)

    def test_counts_lines(self):
        # 3 newlines + a final newline-less line = 4 readLine results.
        self.assertEqual(4, self._count(b"a\nb\nc\nd"))

    def test_trailing_newline(self):
        # "a\nb\n" -> "a\n", "b\n", then EOF: 2 lines (no phantom empty line).
        self.assertEqual(2, self._count(b"a\nb\n"))

    def test_empty_file_is_zero_lines(self):
        self.assertEqual(0, self._count(b""))

    def test_huge_no_newline_file_is_chunked(self):
        # 100000 bytes, no newline: returned in 4K (default maxLen) pieces, so it
        # completes in bounded memory rather than loading the whole "line".
        # ceil(100000 / 4096) = 25 chunks.
        self.assertEqual(25, self._count(b"x" * 100000))

    def test_line_kept_verbatim(self):
        """The terminator is preserved exactly: 'hi\\r\\n' comes back as-is."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "crlf")
            with open(path, "wb") as f:
                f.write(b"hi\r\nbye\n")
            src = f"""namespace Main
import System
import System::IO

{_DONE}
fun check(io: IO): System::Int
  let r = readLine(io)
  ret match(r.v)
    ("hi\\r\\n") => _done(r.io, 0)
    (s: System::String) => _done(r.io, 1)
    (e: IOError) => _done(r.io, 2)

fun main(): System::Int
  ret match(open_read("{path}"))
    (io: IO) => check(io)
    (e: IOError) => 88
"""
            self.assertEqual(0, compile_and_run_stdlib(src))

    def test_maxlen_cap(self):
        """readLine(io, 3) returns at most 3 bytes even within a long line."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "long")
            with open(path, "wb") as f:
                f.write(b"abcdefgh\n")
            src = f"""namespace Main
import System
import System::IO

{_DONE}
fun check(io: IO): System::Int
  let r = readLine(io, 3)
  ret match(r.v)
    ("abc") => _done(r.io, 0)
    (s: System::String) => _done(r.io, 1)
    (e: IOError) => _done(r.io, 2)

fun main(): System::Int
  ret match(open_read("{path}"))
    (io: IO) => check(io)
    (e: IOError) => 88
"""
            self.assertEqual(0, compile_and_run_stdlib(src))

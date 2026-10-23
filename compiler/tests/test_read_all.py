"""readAll: an IO handle's remaining content as one String.

File contents are parsed by reading the file whole and streaming its text —
`once(text)` into `toLines`, `tokenize`, … These run against real files, which
a [test] cannot create, so they live here.

See stdlib/System/IO/io.yafl (readAll).
"""
from __future__ import annotations

import os
import tempfile

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


_PRELUDE = "namespace Main\nimport System\nimport System::IO\n\n"


class TestReadAll(TestCase):
    def _run(self, content: bytes, helpers: str) -> int:
        """`helpers` must define `run(io: IO): System::Int`."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "f")
            with open(path, "wb") as fh:
                fh.write(content)
            src = (_PRELUDE + helpers +
                   "fun main(): System::Int\n"
                   f'  ret match(open_read("{path}"))\n'
                   "    (io: IO) => run(io)\n"
                   "    (e: IOError) => 88\n")
            return compile_and_run_stdlib(src)

    # The length read, or 200 on a read error / 201 on a close error. A length
    # past 255 is checked in-program, to avoid 8-bit exit-code truncation.
    _LENGTH = """fun run(io: IO): System::Int
  let r = readAll(io)
  let closed = r.io.close()
  ret match(r.v)
    (text: System::String) => closed !is None ? 201 : System::length(text)
    (e: IOError)           => 200
"""

    def test_reads_all_bytes(self):
        self.assertEqual(11, self._run(b"hello world", self._LENGTH))

    def test_reads_across_many_chunks(self):
        # 2500 bytes is several runtime reads (IO_READ_MAX); all of it arrives.
        helpers = """fun run(io: IO): System::Int
  let r = readAll(io)
  let closed = r.io.close()
  ret match(r.v)
    (text: System::String) => closed is None && System::length(text) == 2500
                              && System::byteAt(text, 0) == 'x' && System::byteAt(text, 2499) == 'x' ? 7 : 99
    (e: IOError)           => 200
"""
        self.assertEqual(7, self._run(b"x" * 2500, helpers))

    def test_empty_file_is_the_empty_string(self):
        self.assertEqual(0, self._run(b"", self._LENGTH))

    # ── read whole, then stream the text: once |> toLines |> number |> file ───

    _PIPELINE = r'''fun number(text: System::String, ioOut: IO): System::Int
  let w = writeStream(ioOut, System::once(text) |> toLines |> prependLineNumbers)
  ret match(w.io.close())
    (e: IOError)      => 51
    (n: System::None) => w.v is None ? 0 : 50

fun run(ioIn: IO, ioOut: IO): System::Int
  let r = readAll(ioIn)
  let closed = r.io.close()
  ret match(r.v)
    (text: System::String) => closed !is None ? (ioOut.close() |> (c) => 53) : number(text, ioOut)
    (e: IOError)           => match(ioOut.close())
      (e2: IOError)      => 52
      (n: System::None)  => 52
'''

    def _pipeline(self, content: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "in")
            out = os.path.join(tmp, "out")
            with open(inp, "wb") as fh:
                fh.write(content)
            src = (_PRELUDE + self._PIPELINE +
                   "fun main(): System::Int\n"
                   f'  ret match(open_read("{inp}"))\n'
                   "    (e: IOError) => 88\n"
                   f'    (ioIn: IO)   => match(create("{out}"))\n'
                   "      (e2: IOError) => ioIn.close() |> (c) => 89\n"
                   "      (ioOut: IO)   => run(ioIn, ioOut)\n")
            rc = compile_and_run_stdlib(src)
            self.assertEqual(0, rc, "pipeline program exited non-zero")
            with open(out, "rb") as fh:
                return fh.read()

    def test_pipeline_crlf_lines_numbered(self):
        # CRLF terminators stripped; final line has no terminator; 1-based
        # numbering; each numbered line re-terminated with '\n'.
        self.assertEqual(
            b"1: hello\n2: world\n3: final\n",
            self._pipeline(b"hello\r\nworld\r\nfinal"))

    def test_pipeline_lf_only_and_trailing_newline(self):
        # LF-only input with a trailing newline: no phantom empty final line.
        self.assertEqual(
            b"1: alpha\n2: beta\n",
            self._pipeline(b"alpha\nbeta\n"))

    def test_pipeline_empty_file(self):
        # No lines in, nothing out.
        self.assertEqual(b"", self._pipeline(b""))

    def test_pipeline_long_line(self):
        # A line longer than one runtime read comes out whole.
        long_line = b"z" * 3000
        self.assertEqual(
            b"1: " + long_line + b"\n",
            self._pipeline(long_line + b"\n"))

"""StreamIO: a pure, memoised, lazy view over an IO handle.

`asStream` hands back a non-linear `StreamIO` aliasing the same handle; `next()`
yields the next chunk plus the successor stream, memoised so a node revisited
returns the same result without re-touching the handle. `None` is EOF; an
`IOError` (including a closed backing handle) is terminal.

See stdlib/io.yafl (StreamIO / asStream / _streamNode / _streamPull) and
yafllib/io.c (io_as_stream / stream_read).
"""
from __future__ import annotations

import os
import tempfile

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


_PRELUDE = "namespace Main\nimport System\nimport System::IO\n\n"

# Length of a stream element, or a distinct negative sentinel for the non-data
# cases so a test can tell them apart through the exit code.
_LEN = """fun _len(v: System::Result<System::String|System::None, IOError>): System::Int
  ret match(v)
    (ok: System::Ok<System::String|System::None, IOError>) => match(ok.value)
      (s: System::String) => System::length(s)
      (n: System::None)   => 90
    (er: System::Error<System::String|System::None, IOError>) => 100
"""


class TestStreamIO(TestCase):
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

    # ── draining ─────────────────────────────────────────────────────────────

    _DRAIN = """fun [tail] drain(s: StreamIO, total: System::Int): System::Int
  let r = System::streamNext<StreamIO, System::String, IOError>(s)
  ret match(r.value)
    (ok: System::Ok<System::String|System::None, IOError>) => match(ok.value)
      (chunk: System::String) => drain(r.stream, total + System::length(chunk))
      (n: System::None)       => total
    (er: System::Error<System::String|System::None, IOError>) => 200
fun run(io: IO): System::Int
  let a = io.asStream()
  let total = drain(a.stream, 0)
  ret match(a.io.close())
    (e: IOError)      => 201
    (n: System::None) => total
"""

    def test_drains_all_bytes(self):
        self.assertEqual(11, self._run(b"hello world", self._DRAIN))

    _DRAIN_BIG = """fun [tail] drain(s: StreamIO, total: System::Int): System::Int
  let r = System::streamNext<StreamIO, System::String, IOError>(s)
  ret match(r.value)
    (ok: System::Ok<System::String|System::None, IOError>) => match(ok.value)
      (chunk: System::String) => drain(r.stream, total + System::length(chunk))
      (n: System::None)       => total
    (er: System::Error<System::String|System::None, IOError>) => 200
fun run(io: IO): System::Int
  let a = io.asStream()
  let total = drain(a.stream, 0)
  ret match(a.io.close())
    (e: IOError)      => 201
    (n: System::None) => total == 2500 ? 7 : 99
"""

    def test_multichunk_drain_total(self):
        # 2500 bytes exceeds IO_READ_MAX, so draining spans several lazily-
        # forced nodes/refills; the accumulated total must still be exact.
        # Checked in-program (== 2500) to avoid 8-bit exit-code truncation.
        self.assertEqual(7, self._run(b"x" * 2500, self._DRAIN_BIG))

    def test_empty_file_is_zero_bytes(self):
        # First read hits EOF immediately -> None, total stays 0.
        self.assertEqual(0, self._run(b"", self._DRAIN))

    # ── memoisation / referential transparency ───────────────────────────────

    _MEMO = _LEN + """fun run(io: IO): System::Int
  let a = io.asStream()
  let r1 = System::streamNext<StreamIO, System::String, IOError>(a.stream)
  let r2 = System::streamNext<StreamIO, System::String, IOError>(a.stream)
  let n = _len(r1.value) + _len(r2.value)
  ret match(a.io.close())
    (e: IOError)      => 201
    (n2: System::None) => n
"""

    def test_node_is_memoised(self):
        # The 5-byte file is one chunk. next() on the SAME node twice must yield
        # the same chunk (5+5=10). Without memoisation the second next() would
        # re-read the (now exhausted) handle and see EOF.
        self.assertEqual(10, self._run(b"hello", self._MEMO))

    # ── closed backing handle -> IOError (the escape case) ───────────────────

    _CLOSED = """fun _afterClose(s: StreamIO): System::Int
  let r = System::streamNext<StreamIO, System::String, IOError>(s)
  ret match(r.value)
    (ok: System::Ok<System::String|System::None, IOError>) => match(ok.value)
      (chunk: System::String) => 1
      (n: System::None)       => 2
    (er: System::Error<System::String|System::None, IOError>) => 42
fun run(io: IO): System::Int
  let a = io.asStream()
  ret match(a.io.close())
    (ce: IOError)     => 202
    (n: System::None) => _afterClose(a.stream)
"""

    def test_read_after_close_is_ioerror(self):
        # Close the linear handle first; a not-yet-realised stream read against
        # the closed handle must surface as IOError, not EOF.
        self.assertEqual(42, self._run(b"hello", self._CLOSED))

    # ── StreamIO IS a System::Stream: compose the GENERIC combinators over IO ──

    # StreamIO now witnesses System::Stream<StreamIO, String, IOError>, so the
    # IO line stream drops straight into the generic transducers. Here a real
    # file is read, split into lines, then run through the *generic* System::Map
    # (the same one that works over Count in test_generic_trait_instance) — the
    # IO leaf and the generic stream world meeting on one trait.
    _GENERIC_MAP = """fun tag(s: System::String): System::String
  ret s + "X"

fun [tail] count<S>(s: S, acc: System::Int): System::Int where System::Stream<S, System::String, IOError>
  let r = System::streamNext<S, System::String, IOError>(s)
  ret match(r.value)
    (ok: System::Ok<System::String|System::None, IOError>) => match(ok.value)
      (line: System::String) => count<S>(r.stream, acc + System::length(line))
      (n: System::None)       => acc
    (er: System::Error<System::String|System::None, IOError>) => 0 - 1

fun run(io: IO): System::Int
  let a = io.asStream()
  let stream: StreamIO = a.stream
  let mapped = System::Map<System::Lines<StreamIO>, System::String, System::String>(stream |> toLines, tag)
  let total = count<System::Map<System::Lines<StreamIO>, System::String, System::String>>(mapped, 0)
  ret match(a.io.close())
    (e: IOError)      => 201
    (n: System::None) => total
"""

    def test_generic_map_over_io_lines(self):
        # "ab\\ncd\\n" -> lines "ab","cd" -> tagged "abX","cdX" -> 3+3 = 6.
        self.assertEqual(6, self._run(b"ab\ncd\n", self._GENERIC_MAP))

    # ── pipeline: source |> toLines |> prependLineNumbers |> writeToFile ──────

    # A whole-file transform built by piping the StreamIO through transformers
    # and into a file sink. Exercises asStream, toLines (CRLF stripping + cross-
    # chunk line assembly + final unterminated line), prependLineNumbers, and
    # writeToFile together.
    _PIPELINE = r'''fun processFile(ioIn: IO, ioOut: IO): (ioIn: IO, ioOut: IO, v: IOError|System::None)
  let a = ioIn.asStream()
  let stream: StreamIO = a.stream
  let w = writeToFile(ioOut, stream |> toLines |> prependLineNumbers)
  ret (a.io, w.io, w.v)

fun _closeOne(io: IO, code: System::Int): System::Int
  ret match(io.close())
    (e: IOError)      => code
    (n: System::None) => code

fun run(ioIn: IO, ioOut: IO): System::Int
  let p = processFile(ioIn, ioOut)
  let c1 = _closeOne(p.ioIn, 0)
  ret match(p.ioOut.close())
    (e: IOError)      => 51
    (n: System::None) => match(p.v)
      (er: IOError)      => 50
      (nn: System::None) => 0
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
                   "      (e2: IOError) => _closeOne(ioIn, 89)\n"
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

    def test_pipeline_long_line_spans_chunks(self):
        # A single line longer than IO_READ_MAX must be assembled across several
        # source chunks before the newline is found.
        long_line = b"z" * 3000
        self.assertEqual(
            b"1: " + long_line + b"\n",
            self._pipeline(long_line + b"\n"))

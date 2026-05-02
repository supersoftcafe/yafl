"""End-to-end tests for the System::IO stdlib: real file read/write, close,
error-code mapping, and operation-after-close behaviour."""
from __future__ import annotations

import os
import tempfile
from tests.testutil import TimedTestCase as TestCase

import compiler as c
from tests.testutil import compile_and_run_stdlib


class TestIO(TestCase):

    def test_file_not_found_returns_file_not_found_error(self):
        """open_read on a missing path returns FileNotFoundError specifically."""
        src = """namespace Main
import System
import System::IO

fun main(): System::Int
  ret match(open_read("/nonexistent/yafl_test_ypr0qZ_987654321"))
    (h: IO) => 99
    (e: IOError) => match(e)
      (x: FileNotFoundError) => 0
      () => 1
"""
        code = compile_and_run_stdlib(src)
        self.assertEqual(0, code,
            "expected FileNotFoundError arm; got different exit code")

    def test_round_trip_write_then_read(self):
        """create/write/close followed by open_read/read round-trips the
        exact bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rt.txt")
            src = f"""namespace Main
import System
import System::IO

fun doWrite(h: IO): System::Int
  let r = h.write("hello")
  ret match(r.v)
    (n: System::Int) =>
      match(r.io.close())
        (e: IOError)      => 1
        (n: System::None) => 0
    (e: IOError) => 2

fun doRead(h: IO): System::Int
  let r = h.read(5)
  ret match(r.v)
    (s: System::String) => match(s)
      ("hello") => 0
      (x) => 11
    (e: IOError) => 12

fun writePhase(): System::Int
  ret match(create("{path}"))
    (h: IO) => doWrite(h)
    (e: IOError) => 99

fun readPhase(): System::Int
  ret match(open_read("{path}"))
    (h: IO) => doRead(h)
    (e: IOError) => 88

fun main(): System::Int
  ret match(writePhase())
    (0) => readPhase()
    (x) => 50
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code,
                "expected successful round-trip")
            # File should be present with exactly "hello".
            with open(path, "rb") as f:
                self.assertEqual(b"hello", f.read())

    def test_read_after_close_returns_error(self):
        """A read on a closed handle returns an IOError, not a String."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "closed.txt")
            # seed the file with some content
            with open(path, "w") as f:
                f.write("data")
            src = f"""namespace Main
import System
import System::IO

fun readAfterClose(h: IO): System::Int
  let r = h.read(4)
  ret match(r.v)
    (s: System::String) => 20
    (e: IOError) => 0

fun tryReadClosed(h: IO): System::Int
  ret match(h.close())
    (e: IOError) => 9
    (n: System::None) => readAfterClose(h)

fun main(): System::Int
  ret match(open_read("{path}"))
    (h: IO) => tryReadClosed(h)
    (e: IOError) => 88
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code,
                "expected IOError after read on closed handle")

    def test_write_then_read_via_monadic_chain(self):
        """The (io, v: T|IOError) pair shape composes through nested match
        destructuring that mirrors a future `?>` chain."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "chain.txt")
            src = f"""namespace Main
import System
import System::IO

fun closeOk(h: IO): System::Int
  ret match(h.close())
    (e: IOError)      => 1
    (n: System::None) => 0

fun writeSecond(h: IO): System::Int
  let r = h.write("cd")
  ret match(r.v)
    (n: System::Int) => closeOk(r.io)
    (e: IOError) => 2

fun writeTwice(h: IO): System::Int
  let r = h.write("ab")
  ret match(r.v)
    (n: System::Int) => writeSecond(r.io)
    (e: IOError) => 3

fun main(): System::Int
  ret match(create("{path}"))
    (h: IO) => writeTwice(h)
    (e: IOError) => 99
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code, "expected successful chained write")
            with open(path, "rb") as f:
                self.assertEqual(b"abcd", f.read())

    def test_read_line_reads_one_line(self):
        """readLine returns the first line (without the newline) from a
        file containing several lines."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lines.txt")
            with open(path, "w") as f:
                f.write("hello\nworld\n")
            src = f"""namespace Main
import System
import System::IO

fun pickLine(h: IO): System::Int
  let r = h.readLine()
  ret match(r.v)
    ("hello") => 0
    (s: System::String) => 1
    (e: IOError) => 2

fun main(): System::Int
  ret match(open_read("{path}"))
    (h: IO) => pickLine(h)
    (e: IOError) => 88
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code, "readLine must return first line without newline")

    def test_read_line_strips_crlf(self):
        """readLine strips both '\\r' and '\\n' from the trailing line terminator."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "crlf.txt")
            with open(path, "wb") as f:
                f.write(b"hi\r\n")
            src = f"""namespace Main
import System
import System::IO

fun pickLine(h: IO): System::Int
  let r = h.readLine()
  ret match(r.v)
    ("hi") => 0
    (s: System::String) => 1
    (e: IOError) => 2

fun main(): System::Int
  ret match(open_read("{path}"))
    (h: IO) => pickLine(h)
    (e: IOError) => 88
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code, "readLine must strip \\r\\n")

    def test_read_line_eof_on_empty_file(self):
        """readLine on an empty file returns EOFError."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.txt")
            with open(path, "w") as f:
                pass
            src = f"""namespace Main
import System
import System::IO

fun pickLine(h: IO): System::Int
  let r = h.readLine()
  ret match(r.v)
    (s: System::String) => 1
    (e: IOError) => match(e)
      (eof: EOFError) => 0
      ()              => 2

fun main(): System::Int
  ret match(open_read("{path}"))
    (h: IO) => pickLine(h)
    (e: IOError) => 88
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code, "readLine on empty file must return EOFError")

    def test_bind_operator_reads_three_lines_into_triple(self):
        """Read three lines via `?>`-chained lambdas and assemble a Triple.

        Each `?>` is followed by a lambda whose body greedily extends over the
        next `?>` — the effect is right-associative bind. The three captured
        line values (`a`, `b`, `c`) are in scope at the innermost body where
        the Triple is constructed; errors short-circuit through the chain.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "three.txt")
            with open(path, "w") as f:
                f.write("one\ntwo\nthree\n")
            src = f"""namespace Main
import System
import System::IO

class Triple(a: System::String, b: System::String, c: System::String)

fun readThree(io: IO): (io: IO, v: Triple|IOError)
  ret io.readLine() ?> (io: IO, a: System::String) =>
      io.readLine() ?> (io: IO, b: System::String) =>
      io.readLine() ?> (io: IO, c: System::String) =>
      (io=io, v=Triple(a, b, c))

fun check(h: IO): System::Int
  let r = readThree(h)
  ret match(r.v)
    (t: Triple) => match(t.a)
      ("one") => match(t.b)
        ("two") => match(t.c)
          ("three") => 0
          (x) => 31
        (x) => 22
      (x) => 11
    (e: IOError) => 42

fun main(): System::Int
  ret match(open_read("{path}"))
    (h: IO) => check(h)
    (e: IOError) => 88
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code,
                "bind chain must read three lines and assemble Triple(one,two,three)")

    def test_read_line_partial_final_line(self):
        """A final line with no trailing newline is returned as the partial line."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "partial.txt")
            with open(path, "wb") as f:
                f.write(b"abc")
            src = f"""namespace Main
import System
import System::IO

fun pickLine(h: IO): System::Int
  let r = h.readLine()
  ret match(r.v)
    ("abc") => 0
    (s: System::String) => 1
    (e: IOError) => 2

fun main(): System::Int
  ret match(open_read("{path}"))
    (h: IO) => pickLine(h)
    (e: IOError) => 88
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code,
                "readLine at EOF with partial data must return the partial line")

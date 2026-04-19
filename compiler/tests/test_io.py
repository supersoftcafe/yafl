"""End-to-end tests for the System::IO stdlib: real file read/write, close,
error-code mapping, and operation-after-close behaviour."""
from __future__ import annotations

import os
import tempfile
from unittest import TestCase

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

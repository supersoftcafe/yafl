"""Interactive (TTY/pipe) reads must not over-read.

A `read(n)` must return as soon as some input is available, not block until the
whole 8 KB buffer fills or EOF arrives. The old REFILL used `fread(.., 8192, ..)`,
which loops until the buffer is full — so an interactive caller hung until 8 KB
was typed or Ctrl-D. The fix reads with a single `read()` syscall (which returns
on first available data) while keeping the read-ahead buffer for files. See
yafllib/io_thread.c (IO_OP_REFILL).
"""
from __future__ import annotations

import os
import subprocess

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_to_binary, _RUN_ENV


# Reads 5 bytes from stdin and prints them, then exits — without waiting for EOF.
_READ5 = """\
import System
import System::IO

fun emit(s: System::String): System::Int
  System::print(s)
  ret 0

fun main(): System::Int
  let io = System::IO::stdin()
  let r = io.read(5)
  let closed = r.io.close()
  ret match(r.v)
    (s: System::String)      => emit(s)
    (e: System::IO::IOError) => 1
"""


class TestInteractiveRead(TestCase):
    def test_read_returns_before_buffer_fills(self):
        binary = compile_to_binary(_READ5)
        try:
            proc = subprocess.Popen(
                [binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=_RUN_ENV)
            # Write fewer bytes than the 8 KB buffer and DO NOT close stdin: the
            # program must still come back with what's available. With the old
            # fill-the-buffer read it blocks here forever.
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(b"hello\n")
            proc.stdin.flush()
            try:
                rc = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                self.fail("read(5) blocked waiting to fill the buffer "
                          "instead of returning available input")
            out = proc.stdout.read()
            for stream in (proc.stdin, proc.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
            self.assertEqual(0, rc)
            self.assertEqual(b"hello", out)
        finally:
            try:
                os.unlink(binary)
            except OSError:
                pass

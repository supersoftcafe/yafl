"""Subprocess spawn: System::IO::run.

`run(program, args)` spawns an external program (resolved on PATH) through the
IO threadpool, with stdin = /dev/null, capturing stdout, stderr, and the exit
code into a ProcessResult. A non-zero child exit is a successful result (carried
in exitCode), not an IOError; only a failure to *start* the program is an
IOError. See yafllib/io.c (process_run) and stdlib/process.yafl.
"""
from __future__ import annotations

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture


class TestProcessRun(TestCase):
    def test_captures_stdout_and_zero_exit(self):
        src = """\
import System
import System::IO

fun main(): System::Int
  ret match(System::IO::run("/bin/echo", prepend<System::String>("hello", List<System::String>())))
    (r: System::IO::ProcessResult) => r.out == "hello\\n" ? (r.exitCode == 0 ? 0 : 1) : 2
    (e: System::IO::IOError)        => 3
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)

    def test_nonzero_exit_is_success_not_error(self):
        # `false` exits 1; that must come back as a ProcessResult, not IOError.
        src = """\
import System
import System::IO

fun main(): System::Int
  ret match(System::IO::run("/bin/false", List<System::String>()))
    (r: System::IO::ProcessResult) => r.exitCode == 1 ? 0 : 1
    (e: System::IO::IOError)        => 2
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)

    def test_captures_stderr(self):
        # `sh -c 'echo oops 1>&2'` writes only to stderr.
        src = """\
import System
import System::IO

fun _args(): List<System::String>
  ret prepend<System::String>("-c",
        prepend<System::String>("echo oops 1>&2", List<System::String>()))

fun main(): System::Int
  ret match(System::IO::run("/bin/sh", _args()))
    (r: System::IO::ProcessResult) => r.err == "oops\\n" ? (r.out == "" ? 0 : 1) : 2
    (e: System::IO::IOError)        => 3
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)

    def test_missing_program_is_ioerror(self):
        src = """\
import System
import System::IO

fun main(): System::Int
  ret match(System::IO::run("/no/such/program/xyzzy", List<System::String>()))
    (r: System::IO::ProcessResult) => 1
    (e: System::IO::IOError)        => 0
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)

    def test_large_output_exceeds_buffer(self):
        # `seq 1 20000` produces well over the 8 KB io buffer / 4 KB read chunk,
        # exercising the growable capture buffer. Check the last line is present.
        src = """\
import System
import System::IO

fun main(): System::Int
  ret match(System::IO::run("/usr/bin/seq", prepend<System::String>("20000", List<System::String>())))
    (r: System::IO::ProcessResult) => System::length(r.out) > 80000 ? 0 : 1
    (e: System::IO::IOError)        => 2
"""
        rc, _ = compile_and_run_stdlib_capture(src)
        self.assertEqual(0, rc)

"""End-to-end test for System::IO::copy — stream one file into another until
the source is depleted, threading BOTH linear handles and closing both.

`IO` is linear and the whole library is built around the single-handle
`(io, v)` pair convention (read/write/`?>`). `copy` needs *two* live handles
at once, so this is the first place that convention is stretched."""
from __future__ import annotations

import os
import tempfile
from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestIOCopy(TestCase):
    def test_copy_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            srcp = os.path.join(tmp, "src.bin")
            dstp = os.path.join(tmp, "dst.bin")
            # Multi-chunk content so the copy loop iterates several times.
            content = ("The quick brown fox jumps over the lazy dog.\n" * 500)
            with open(srcp, "w") as f:
                f.write(content)

            src = f"""namespace Main
import System
import System::IO

# The whole "open both, copy, close both" story in one expression: withFiles
# acquires both handles, runs copy, and closes both on every path.
fun copyFiles(srcPath: System::String, dstPath: System::String): System::Int|IOError
  ret withFiles(open_read(srcPath), create(dstPath), (s, d) => copy(s, d, 64))

fun main(): System::Int
  ret match(copyFiles("{srcp}", "{dstp}"))
    (n: System::Int) => 0
    (e: IOError)     => 1
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code, "copy should succeed and close both handles")
            with open(dstp, "rb") as f:
                self.assertEqual(content.encode(), f.read(),
                                 "destination must be a byte-for-byte copy")

    def test_with_file_writes_and_closes(self):
        """Single-handle bracket: acquire, write, auto-close in one expression."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "wf.txt")
            src = f"""namespace Main
import System
import System::IO

fun writeAndClose(path: System::String): System::Int|IOError
  ret withFile(create(path), (io) => writeAll(io, "bracketed"))

fun main(): System::Int
  ret match(writeAndClose("{path}"))
    (n: System::Int) => 0
    (e: IOError)     => 1
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code, "withFile should write and close the handle")
            with open(path, "rb") as f:
                self.assertEqual(b"bracketed", f.read())

    def test_with_files_missing_source_is_error(self):
        """Failure path: a missing source makes withFiles return the IOError
        (and still discharge the destination it did open) rather than crash or
        leak a linear handle."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "nope.bin")
            dstp = os.path.join(tmp, "out.bin")
            src = f"""namespace Main
import System
import System::IO

fun copyFiles(srcPath: System::String, dstPath: System::String): System::Int|IOError
  ret withFiles(open_read(srcPath), create(dstPath), (s, d) => copy(s, d, 64))

fun main(): System::Int
  ret match(copyFiles("{missing}", "{dstp}"))
    (n: System::Int) => 1
    (e: IOError)     => 0
"""
            code = compile_and_run_stdlib(src)
            self.assertEqual(0, code, "missing source must surface as IOError")

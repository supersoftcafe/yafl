"""End-to-end tests for the System::IO filesystem ops: `exists`, `stat`,
and (in later patches) the `Dir` cursor + `listDir` convenience.

Each test compiles a short YAFL program and runs it; the exit code carries
the assertion result.  `tempfile.TemporaryDirectory` gives every test its
own path namespace so the suite stays parallel-safe under `unittest-parallel`.
"""
from __future__ import annotations

import os
import tempfile

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib


class TestExists(TestCase):

    def test_existing_file_returns_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "present.txt")
            with open(path, "w") as f:
                f.write("hi")
            src = f"""namespace Main
import System
import System::IO

fun main(): System::Int
  ret exists("{path}") ? 1 : 0
"""
            self.assertEqual(1, compile_and_run_stdlib(src))

    def test_missing_path_returns_false(self):
        # /nonexistent_yafl_fs_test_xyz is overwhelmingly unlikely to exist.
        src = """namespace Main
import System
import System::IO

fun main(): System::Int
  ret exists("/nonexistent_yafl_fs_test_xyz_777") ? 1 : 0
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_existing_directory_returns_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = f"""namespace Main
import System
import System::IO

fun main(): System::Int
  ret exists("{tmp}") ? 1 : 0
"""
            self.assertEqual(1, compile_and_run_stdlib(src))


class TestStat(TestCase):

    def test_regular_file_is_regular(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "regular.txt")
            with open(path, "w") as f:
                f.write("contents")
            src = f"""namespace Main
import System
import System::IO

fun main(): System::Int
  ret match(stat("{path}"))
    (fi: FileInfo)  => fi.isRegular ? 1 : 0
    (e: IOError)    => -1
"""
            self.assertEqual(1, compile_and_run_stdlib(src))

    def test_directory_is_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = f"""namespace Main
import System
import System::IO

fun main(): System::Int
  ret match(stat("{tmp}"))
    (fi: FileInfo)  => fi.isDir ? 1 : 0
    (e: IOError)    => -1
"""
            self.assertEqual(1, compile_and_run_stdlib(src))

    def test_missing_path_returns_file_not_found_error(self):
        src = """namespace Main
import System
import System::IO

fun main(): System::Int
  ret match(stat("/nonexistent_yafl_fs_test_xyz_888"))
    (fi: FileInfo)               => 9
    (e: IOError)                 => match(e)
      (n: FileNotFoundError)     => 0
      ()                         => 7
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

    def test_regular_file_size_matches(self):
        """stat returns the file's byte length in `size`."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sized.bin")
            with open(path, "w") as f:
                f.write("0123456789")  # 10 bytes
            src = f"""namespace Main
import System
import System::IO

fun main(): System::Int
  ret match(stat("{path}"))
    (fi: FileInfo)  => fi.size
    (e: IOError)    => -1
"""
            self.assertEqual(10, compile_and_run_stdlib(src))


class TestListDir(TestCase):

    def test_listDir_counts_entries(self):
        """A directory with three files yields three entry names plus
        `.` and `..` — readdir surfaces those.  We check the count
        modulo the dotfiles to keep the assertion stable."""
        with tempfile.TemporaryDirectory() as tmp:
            for nm in ("a.txt", "b.txt", "c.txt"):
                with open(os.path.join(tmp, nm), "w") as f:
                    f.write("x")
            src = f"""namespace Main
import System
import System::IO

# Strip "." and ".." from a list — readdir includes them.
fun keep(s: String): Bool
  ret match(s)
    (".")  => 1 == 0
    ("..") => 1 == 0
    ()     => 1 == 1

fun main(): System::Int
  ret match(listDir("{tmp}"))
    (l: List<String>) => fold<String,Int>(filter<String>(l, keep), 0, (a: Int, x: String) => a + 1)
    (e: IOError)      => -1
"""
            self.assertEqual(3, compile_and_run_stdlib(src))

    def test_listDir_on_missing_dir_returns_error(self):
        src = """namespace Main
import System
import System::IO

fun main(): System::Int
  ret match(listDir("/nonexistent_yafl_fs_test_xyz_999"))
    (l: List<String>)         => 9
    (e: IOError)              => match(e)
      (n: FileNotFoundError)  => 0
      ()                      => 7
"""
        self.assertEqual(0, compile_and_run_stdlib(src))

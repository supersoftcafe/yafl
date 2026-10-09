"""The port's COMMAND LINE does main.py's job — exactly.

Every case runs `python main.py ARGS` and `ybootstrap ARGS` side by side, in the
same directory and environment, and requires the SAME exit code, the SAME
stdout, the SAME stderr (the program's own name normalised — argparse prints
`main.py`, the port prints its own), the SAME C written by `-c`, and binaries
built by `-o` that behave the same. The port had no command line at all until
this was written: it read a pre-assembled stream on stdin and Python scripts
drove it.

Both compilers are pointed at the SAME packaged libraries with `-L`: a
`system.yl` built exactly as the CMake `package_system_library` target builds
it, and the System::Test library directory.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import libraries
from tests.testutil import TimedTestCase, shared_bootstrap_binary

_HERE = Path(__file__).resolve().parent.parent            # .../compiler
_REPO = _HERE.parent
_MAIN = _HERE / "main.py"


_HELLO = """\
import System

fun main(): System::Int
  print("hello from " + "yafl\\n")
  ret 0
"""

_TWO_A = """\
namespace Two::A

import System

fun greeting(): System::String => "two units"
"""

_TWO_MAIN = """\
import System
import Two::A

fun main(): System::Int
  print(Two::A::greeting() + "\\n")
  ret 0
"""

_UNUSED = """\
import System

fun main(): System::Int
  let unused = 3
  ret 0
"""

_TYPE_ERROR = """\
import System

fun main(): System::Int
  ret "not an int"
"""

_PARSE_ERROR_A = "fun broken(: System::Int\n"
_PARSE_ERROR_B = "import System\n\nfun main(): System::Int\n  ret (1 +\n"

_RECOVERY = """\
import System

fun good1(): System::Int => 1
fun bad1(): System::Int => f(1 2)
fun good2(): System::Int => 2

fun main(): System::Int
  let a = 1
  let b = 2
  ret a b
fun good3(): System::Int => 3
"""

# A match arm owns its whole line block: anything left after the arm body,
# here the rest of the call the match sits in, is an error, not the call's
# next argument.
_ARM_LEFTOVERS = """\
import System

fun check(b: System::Bool, why: System::String): System::Int => b ? 0 : 1

fun main(): System::Int
  let e: System::Int|System::None = 3
  ret check(match(e)
    (i: System::Int) => true
    ()               => false, "an Int")
"""

_TESTS = """\
namespace Cli::Tests

import System
import System::Test

fun [test("adds")] adds(): None|TestFailure
    ret assertEqInt(1 + 1, 2, "1+1")

fun [test("fails on purpose")] fails(): None|TestFailure
    ret assertEqInt(1 + 1, 3, "1+1 is not 3")
"""

_NO_TESTS = """\
import System

fun main(): System::Int
  ret 0
"""


class TestBootstrapCli(TimedTestCase):
    _TIMEOUT = 1800

    @classmethod
    def setUpClass(cls):
        assert os.environ.get("PYTHONHASHSEED") == "0", (
            "byte-identical C is only deterministic under PYTHONHASHSEED=0")
        cls.binary = shared_bootstrap_binary()
        cls._libs_tmp = tempfile.TemporaryDirectory()
        cls.libs = Path(cls._libs_tmp.name)
        libraries.package_system_library(
            cls.libs / "system.yl", _HERE / "stdlib", _REPO / "yafllib" / "yafl.h",
            Path(libraries._find_dev_static_lib()))
        shutil.copytree(_HERE / "libs" / "system-test", cls.libs / "system-test")

    @classmethod
    def tearDownClass(cls):
        cls._libs_tmp.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ── harness ─────────────────────────────────────────────────────────────

    def _write(self, rel: str, text: str) -> Path:
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def _env(self) -> dict:
        env = dict(os.environ)
        env.pop("YAFL_PATH", None)
        env["COLUMNS"] = "1000"    # argparse wraps usage at the terminal width
        return env

    def _run(self, argv: list[str], prog: str) -> tuple[int, str, str]:
        r = subprocess.run(argv, cwd=self.dir, env=self._env(), capture_output=True,
                           text=True, timeout=1800)
        # The program's name is the one thing that legitimately differs.
        return (r.returncode, r.stdout.replace(prog, "PROG"),
                r.stderr.replace(prog, "PROG"))

    def _both(self, *args: str, libs: bool = True) -> tuple[int, str, str]:
        """Run both compilers; assert they agree; return Python's result."""
        lib_args = ["-L", str(self.libs)] if libs else []
        py = self._run([sys.executable, str(_MAIN), *lib_args, *args], "main.py")
        port = self._run([self.binary, *lib_args, *args], Path(self.binary).name)
        self.assertEqual(py[0], port[0], f"exit codes differ\npython: {py}\nport:   {port}")
        self.assertEqual(py[1], port[1], "stdout differs")
        self.assertEqual(py[2], port[2], "stderr differs")
        return py

    def _both_c(self, *args: str) -> str:
        """Both compilers write -c; the C must be byte-identical."""
        lib_args = ["-L", str(self.libs)]
        py = self._run([sys.executable, str(_MAIN), *lib_args, "-c", "py.c", *args], "main.py")
        port = self._run([self.binary, *lib_args, "-c", "port.c", *args], Path(self.binary).name)
        self.assertEqual(py, port, "exit/stdout/stderr differ")
        self.assertEqual(0, py[0], py)
        py_c, port_c = (self.dir / "py.c").read_text(), (self.dir / "port.c").read_text()
        self.assertTrue(py_c)
        self.assertEqual(py_c.splitlines(), port_c.splitlines())
        return py_c

    def _both_binaries(self, *args: str, run_args: tuple = ()) -> tuple[int, str]:
        """Both compilers build with -o; the two binaries must behave the same."""
        lib_args = ["-L", str(self.libs)]
        py = self._run([sys.executable, str(_MAIN), *lib_args, "-o", "py.bin", *args], "main.py")
        port = self._run([self.binary, *lib_args, "-o", "port.bin", *args], Path(self.binary).name)
        self.assertEqual(py, port, "exit/stdout/stderr differ")
        self.assertEqual(0, py[0], py)
        ran = [subprocess.run([str(self.dir / b), *run_args], capture_output=True,
                              text=True, timeout=60) for b in ("py.bin", "port.bin")]
        self.assertEqual((ran[0].returncode, ran[0].stdout),
                         (ran[1].returncode, ran[1].stdout))
        return ran[0].returncode, ran[0].stdout

    # ── argparse: the same words mean the same thing ────────────────────────

    def test_argument_errors_and_help(self):
        for args in ([], ["-O5", "x"], ["-O"], ["x", "-o"], ["--lib-path"], ["-L"],
                     ["a.yafl", "-O1", "b.yafl"], ["--bogus", "a.yafl"],
                     ["a.yafl", "--bogus", "b.yafl"], ["-Wbogus", "a.yafl"],
                     ["-Wno-bogus", "a.yafl"], ["-h"], ["--he"], ["-O=7", "a.yafl"],
                     ["--profile=1", "a.yafl"], ["--test=x", "a.yafl"],
                     ["-O3", "-h", "-O9"], ["-O9", "-h"], ["-hx"]):
            with self.subTest(args=args):
                self._both(*args, libs=False)

    def test_unreadable_input(self):
        self._both("missing.yafl")
        self._write("real.yafl", _HELLO)
        self._both("real.yafl", "missing.yafl")

    # ── compiling: the same C ───────────────────────────────────────────────

    def test_single_file_c_at_every_level(self):
        self._write("hello.yafl", _HELLO)
        for level in ("0", "1", "2", "3"):
            with self.subTest(level=level):
                self._both_c("-O" + level, "hello.yafl")

    def test_profile_c(self):
        self._write("hello.yafl", _HELLO)
        self._both_c("--profile", "hello.yafl")

    def test_files_named_by_basename(self):
        self._write("sub/a.yafl", _TWO_A)
        self._write("main.yafl", _TWO_MAIN)
        self._both_c("main.yafl", "sub/a.yafl")

    def test_project_directory_named_by_relative_path(self):
        self._write("proj/deep/a.yafl", _TWO_A)
        self._write("proj/main.yafl", _TWO_MAIN)
        self._both_c("proj")

    def test_warnings_on_stderr(self):
        self._write("unused.yafl", _UNUSED)
        self._both_c("unused.yafl")
        self._both_c("-Wall", "unused.yafl")
        self._both_c("-Wno-unused-variable", "unused.yafl")

    def test_compile_errors(self):
        self._write("bad.yafl", _TYPE_ERROR)
        rc, out, _ = self._both("bad.yafl")
        self.assertEqual(1, rc)
        self.assertTrue(out)

    # The port's parser RECOVERS: a broken statement is reported and skipped,
    # and parsing resumes at the next statement block. Python's combinator
    # parser reports different (and fewer useful) diagnostics; bringing it
    # onto the port's model is deferred (USER 10-08), so exact agreement is
    # an expected failure until then — it will report the day they agree.

    @unittest.expectedFailure
    def test_parse_errors_identical(self):
        self._write("pa.yafl", _PARSE_ERROR_A)
        self._write("pb.yafl", _PARSE_ERROR_B)
        self._both("pa.yafl", "pb.yafl")

    def test_match_arm_leftovers(self):
        self._write("arm.yafl", _ARM_LEFTOVERS)
        rc, out, _ = self._both("arm.yafl")
        self.assertEqual(1, rc)
        self.assertEqual(["arm.yafl[9:30] - extra unexpected characters"], out.splitlines())

    def _port(self, *args: str) -> tuple[int, str, str]:
        return self._run([self.binary, "-L", str(self.libs), *args], Path(self.binary).name)

    def test_parse_errors_from_every_file(self):
        self._write("pa.yafl", _PARSE_ERROR_A)
        self._write("pb.yafl", _PARSE_ERROR_B)
        rc, out, err = self._port("pa.yafl", "pb.yafl")
        self.assertEqual((1, ""), (rc, err))
        self.assertEqual(["pa.yafl[1:12] - expected binding",
                          "pb.yafl[4:10] - expected ',' or ')' in argument list"],
                         out.splitlines())

    def test_parse_recovers_at_the_next_statement(self):
        # Two broken statements among good ones, one at top level and one deep
        # in a function body: both are reported, each once, in source order —
        # and the good functions between them do not report anything.
        self._write("r.yafl", _RECOVERY)
        rc, out, _ = self._port("r.yafl")
        self.assertEqual(1, rc)
        self.assertEqual(["r.yafl[4:32] - expected ',' or ')' in argument list",
                          "r.yafl[10:9] - extra unexpected characters"],
                         out.splitlines())

    # ── --test ──────────────────────────────────────────────────────────────

    def test_test_binary(self):
        self._write("t/sub/cli_tests.yafl", _TESTS)
        self._both_c("--test", "t")
        rc, out = self._both_binaries("--test", "t")
        self.assertNotEqual(0, rc)
        self.assertIn("1 passed, 1 failed", out)
        self.assertIn("cli_tests.yafl", out)

    def test_test_without_tests(self):
        self._write("none.yafl", _NO_TESTS)
        rc, out, _ = self._both("--test", "none.yafl")
        self.assertEqual(1, rc)

    # ── linking: the same program ───────────────────────────────────────────

    def test_binaries_behave_the_same(self):
        self._write("hello.yafl", _HELLO)
        for level in ("0", "2"):
            with self.subTest(level=level):
                _, out = self._both_binaries("-O" + level, "hello.yafl")
                self.assertEqual("hello from yafl\n", out)

    def test_assembly_output(self):
        # -a passed the link inputs to `clang -S`, which -Werror rejects as
        # unused: it failed on every program, in both compilers.
        self._write("hello.yafl", _HELLO)
        rc, _, _ = self._both("-a", "out.s", "hello.yafl")
        self.assertEqual(0, rc)
        self.assertTrue((self.dir / "out.s").read_text())

    def test_clang_failure(self):
        self._write("hello.yafl", _HELLO)
        rc, out, _ = self._both("-o", "no/such/dir/out", "hello.yafl")
        self.assertEqual(1, rc)
        self.assertTrue(out.startswith("Compilation failed:"))

    def test_unwritable_c_output(self):
        self._write("hello.yafl", _HELLO)
        rc, _, err = self._both("-c", "no/such/dir/out.c", "hello.yafl")
        self.assertEqual(1, rc)


if __name__ == "__main__":
    unittest.main()

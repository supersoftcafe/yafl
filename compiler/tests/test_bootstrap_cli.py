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

# Something for each inline option to change: a mid-sized helper called
# twice, and a function called once.
_INLINED = """\
namespace Main

import System

# Called twice: inlined only under a generous threshold.
fun mix(a: Int, b: Int): Int
  let c = a * 3 + b
  let d = c * c - a
  let e = d / 7 + c
  ret e % 1000 + a * b - d

# Called once, and too big for the small-function inliner.
fun report(n: Int): Int
  let m = mix(n, 2) + mix(n, 5)
  let a = m * 31 + n
  let b = a / 3 - m
  let c = b * b % 977 + a
  ret c - b + a * 2

fun main(): Int => report(41) % 100
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

# Passes the diagnostics (one warning) and fails LATER, at the [tail] check:
# the warning must still be reported.
_WARNING_THEN_TAIL_ERROR = """\
import System

fun [tail] f(n: System::Int): System::Int
  ret 1 + f(n - 1)

fun main(): System::Int
  let unused = 5
  ret f(3)
"""

# The same, failing at the linearity check instead.
_WARNING_THEN_LINEARITY_ERROR = """\
import System

class [linear,final] Res(y: System::Int)

fun main(): System::Int
  let unused = 5
  let q = Res(3)
  ret 0
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
        # ...and colours it by these: none may leak in from the caller.
        for k in ("FORCE_COLOR", "NO_COLOR", "PYTHON_COLORS"):
            env.pop(k, None)
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

    # ── the command line: the same words mean the same thing ────────────────
    #
    # Each case's OUTCOME, for both compilers: the exit code (0 help, 1 an
    # input that cannot be read, 2 a usage error), the stream it writes, and
    # the word the error names. Not argparse's wording, which changes between
    # Python releases (quoting, colour, wrapping) and is not the contract.

    _CASES = (
        # (args, exit code, a word stderr must contain; None for help)
        ([], 2, "files"),
        (["-O5", "x"], 2, "-O"), (["-O=7", "a.yafl"], 2, "-O"), (["-Ox"], 2, "-O"),
        (["-O9h"], 2, "-O"), (["-O9", "-h"], 2, "-O"),
        (["-O"], 2, "-O"), (["-O", "--", "a"], 2, "-O"),
        (["x", "-o"], 2, "-o"), (["-o", "--", "a"], 2, "-o"),
        (["--lib-path"], 2, "--lib-path"), (["-L"], 2, "--lib-path"),
        (["-W", "-Wall"], 2, "-W"), (["-hc"], 2, "-c"),
        (["a.yafl", "-O1", "b.yafl"], 2, "b.yafl"), (["a", "-", "-O1", "stray.yafl"], 2, "stray.yafl"),
        (["--bogus", "a.yafl"], 2, "--bogus"), (["a.yafl", "--bogus", "b.yafl"], 2, "--bogus"),
        (["a", "--bogus=1"], 2, "--bogus=1"),
        (["a", "-O0", "--", "b"], 2, "--"), (["a", "-O0", "b", "--"], 2, "--"),
        (["-Wbogus", "a.yafl"], 2, "-Wbogus"), (["-Wno-bogus", "a.yafl"], 2, "-Wno-bogus"),
        (["--profile=1", "a.yafl"], 2, "--profile"), (["--profile=it's"], 2, "--profile"),
        (["--test=x", "a.yafl"], 2, "--test"), (["--test=a\\b"], 2, "--test"),
        (["--help=x"], 2, "--help"), (["-h=x"], 2, "--help"),
        (["--=x", "a"], 2, "--=x"),
        (["--inline-threshold", "x", "a"], 2, "--inline-threshold"),
        (["--inline-threshold=1.5", "a"], 2, "--inline-threshold"),
        (["--inline-threshold"], 2, "--inline-threshold"),
        (["--inline-threshold", " 1_0 ", "a"], 1, "a"), (["--no", "a"], 2, "--no"),
        (["-h"], 0, None), (["--he"], 0, None), (["-hx"], 0, None), (["-hxyz"], 0, None),
        (["-hO3"], 0, None), (["-hO9"], 0, None), (["-hc", "x"], 0, None),
        (["-O3", "-h", "-O9"], 0, None), (["-o=x", "-hx"], 0, None),
        (["--", "a"], 1, "a"), (["-O1", "--", "a", "-x"], 1, "a"), (["-o", "-x y", "a"], 1, "a"),
        (["--pro", "a"], 1, "a"), (["--l=d", "a"], 1, "a"), (["-"], 1, "-"), (["-.5"], 1, "-.5"),
    )

    def _run_plain(self, argv: list[str], env: dict | None = None):
        r = subprocess.run(argv, cwd=self.dir, env=env or self._env(), capture_output=True,
                           text=True, timeout=600)
        return r.returncode, r.stdout, r.stderr

    def test_command_line_outcomes(self):
        for args, code, word in self._CASES:
            with self.subTest(args=args):
                for name, argv in (("python", [sys.executable, str(_MAIN), *args]),
                                   ("port", [self.binary, *args])):
                    rc, out, err = self._run_plain(argv)
                    self.assertEqual(code, rc, f"{name}: exit code\n{out}{err}")
                    if code == 0:
                        self.assertTrue(out.startswith("usage:"), f"{name}: help on stdout\n{out}")
                        self.assertEqual("", err, f"{name}: help writes no stderr")
                    else:
                        self.assertEqual("", out, f"{name}: an error writes no stdout")
                        # An unreadable input is named as the file it is.
                        named = f"{word}: cannot be read" if code == 1 else word
                        self.assertIn(named, err, f"{name}: the error names {word!r}")

    _OPTIONS = ("-h", "-O", "-a", "-c", "-o", "-L", "--lib-path", "--profile", "-W", "--test",
                "--inline-threshold")

    def test_help_lists_every_option_at_any_width(self):
        # COLUMNS unset: not a terminal, so the help falls back to 80 columns.
        for columns in ("1000", "80", "20", "1", None):
            env = self._env()
            env.pop("COLUMNS")
            if columns is not None:
                env["COLUMNS"] = columns
            with self.subTest(columns=columns):
                for name, argv in (("python", [sys.executable, str(_MAIN), "-h"]),
                                   ("port", [self.binary, "-h"])):
                    rc, out, err = self._run_plain(argv, env)
                    self.assertEqual((0, ""), (rc, err), name)
                    for option in self._OPTIONS:
                        self.assertIn(option, out, f"{name}: -h lists {option}")

    def test_no_colour_unless_asked(self):
        # Output to a pipe is plain, and NO_COLOR keeps it plain even when
        # colour is forced. (Python before 3.14 never colours its help.)
        for colour in ({}, {"NO_COLOR": "1"}, {"NO_COLOR": "1", "FORCE_COLOR": "1"},
                       {"TERM": "dumb"}, {"PYTHON_COLORS": "0", "FORCE_COLOR": "1"}):
            with self.subTest(colour=colour):
                for name, argv in (("python", [sys.executable, str(_MAIN), "-h"]),
                                   ("port", [self.binary, "-h"])):
                    rc, out, err = self._run_plain(argv, {**self._env(), **colour})
                    self.assertEqual(0, rc, name)
                    self.assertNotIn("\x1b", out + err, f"{name}: no escape codes")

    def test_builds_from_the_build_tree_without_a_search_path(self):
        # No -L, no YAFL_PATH, no YAFL_LIBYAFL_A: both compilers fall back to
        # the build tree's System library — its stdlib sources, yafl.h, and the
        # runtime archive CMake built (build/yafllib/libyafl.a).
        self._write("hello.yafl", _HELLO)
        env = {**self._env()}
        env.pop("YAFL_LIBYAFL_A", None)
        runs = [subprocess.run([*argv, "-o", out, "hello.yafl"], cwd=self.dir, env=env,
                               capture_output=True, text=True, timeout=1800)
                for argv, out in (([sys.executable, str(_MAIN)], "py.bin"),
                                  ([self.binary], "port.bin"))]
        for r in runs:
            self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        ran = [subprocess.run([str(self.dir / b)], capture_output=True, text=True, timeout=60)
               for b in ("py.bin", "port.bin")]
        self.assertEqual((ran[0].returncode, ran[0].stdout), (ran[1].returncode, ran[1].stdout))

    def test_unreadable_input(self):
        self._both("missing.yafl")
        self._write("real.yafl", _HELLO)
        self._both("real.yafl", "missing.yafl")
        # Reported as pathlib spells the path: `.` parts and doubled or
        # trailing slashes go.
        self._both("./missing.yafl")
        self._both("sub//./missing.yafl")
        self._both("./real.yafl", "./missing.yafl")

    # ── compiling: the same C ───────────────────────────────────────────────

    def test_single_file_c_at_every_level(self):
        self._write("hello.yafl", _HELLO)
        for level in ("0", "1", "2", "3"):
            with self.subTest(level=level):
                self._both_c("-O" + level, "hello.yafl")

    def test_profile_c(self):
        self._write("hello.yafl", _HELLO)
        self._both_c("--profile", "hello.yafl")

    def test_inline_options_c(self):
        self._write("inl.yafl", _INLINED)
        default = self._both_c("-O3", "inl.yafl")
        for opts in (("--inline-threshold", "0"), ("--inline-threshold=40",)):
            with self.subTest(opts=opts):
                self.assertNotEqual(default, self._both_c("-O3", *opts, "inl.yafl"))

    def test_files_named_by_basename(self):
        self._write("sub/a.yafl", _TWO_A)
        self._write("main.yafl", _TWO_MAIN)
        self._both_c("main.yafl", "sub/a.yafl")

    def test_project_directory_named_by_relative_path(self):
        self._write("proj/deep/a.yafl", _TWO_A)
        self._write("proj/main.yafl", _TWO_MAIN)
        self._both_c("proj")
        self._both_c("proj/")
        self._both_c("./proj")

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

    def test_warnings_survive_a_later_failure(self):
        self._write("wt.yafl", _WARNING_THEN_TAIL_ERROR)
        rc, out, err = self._both("wt.yafl")
        self.assertEqual(1, rc)
        self.assertIn("[tail] function has a call to itself", out)
        self.assertIn("warning: 'unused' is never used", err)
        self._write("wl.yafl", _WARNING_THEN_LINEARITY_ERROR)
        rc, out, err = self._both("wl.yafl")
        self.assertEqual(1, rc)
        self.assertIn("it must be consumed once", out)
        self.assertIn("warning: 'unused' is never used", err)

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

"""Shared helpers for compiler integration tests."""
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path

import compiler as c


class TimedTestCase(unittest.TestCase):
    """TestCase that fails any individual test exceeding _TIMEOUT seconds.

    Uses SIGALRM so the timeout applies to Python compilation time as well as
    subprocess execution, catching infinite loops in the compiler itself.
    """
    _TIMEOUT = 120

    def run(self, result=None):
        def _handler(signum, frame):
            raise TimeoutError(f"test exceeded {self._TIMEOUT}s")
        old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(self._TIMEOUT)
        try:
            super().run(result)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

_YAFLLIB_DIR = Path(__file__).parent.parent.parent / "yafllib"
_YAFLLIB_BUILD_DIR = _YAFLLIB_DIR / "build" / "debug-unix"
# The static archive to link. Defaults to the in-tree preset build, but the
# CMake `check`/CTest target overrides it via YAFL_LIBYAFL_A so the suite runs
# against the archive that build just produced (not a stale one).
_LIBYAFL_A = os.environ.get("YAFL_LIBYAFL_A", str(_YAFLLIB_BUILD_DIR / "libyafl.a"))
# Compile against the in-tree yafl.h, in strict ISO C to match the build.
_CLANG_BUILD_FLAGS = [
    "-std=c11",   # ISO C, matching the compiler/runtime build (not gnu11)
    "-Wall", "-Wextra", "-Werror",   # generated C is held to the strict bar too
    "-ffunction-sections", "-fdata-sections",   # enable --gc-sections below
    "-I", str(_YAFLLIB_DIR),
]
# Link the runtime statically (there is no libyafl.so). `-x none` resets the
# language from the `-x c -` stdin so the archive is treated as a library.
# --gc-sections drops unreached runtime/program code, exercising that path on
# every test (a guard against it removing something still needed).
_STATIC_LINK = ["-x", "none", _LIBYAFL_A, "-lpthread", "-lm", "-ldl", "-Wl,--gc-sections"]
_RUN_ENV = {**os.environ}   # static binaries need no LD_LIBRARY_PATH


def assert_clean_compile(source: str, *, use_stdlib: bool = True) -> None:
    """Assert that the yafl source compiles to C and clang accepts it with zero
    warnings, zero errors, and zero notes.  Fails the test if clang emits
    anything on stderr."""
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=use_stdlib, just_testing=False)
    assert c_code, "yafl compilation produced no output"

    result = subprocess.run(
        ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-x", "c", "-", "-O0", "-fsyntax-only",
         "-I", str(_YAFLLIB_DIR)],
        input=c_code, text=True, capture_output=True, timeout=30,
    )
    assert result.stderr == "", f"clang emitted diagnostics:\n{result.stderr}"
    assert result.returncode == 0, f"clang failed:\n{result.stderr}"


def compile_and_run(source: str, timeout: int = 5) -> tuple[int, str]:
    """Compile yafl source to a binary, run it, return (exit_code, clang_stderr).

    Raises AssertionError if compilation to C fails or clang rejects the output.
    """
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)
    assert c_code, "yafl compilation produced no output (type errors?)"

    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name

    try:
        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, *_STATIC_LINK, "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"

        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV)
        return run.returncode, ""
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


def compile_and_run_stdlib(source: str, timeout: int = 5,
                           args: list[str] | None = None) -> int:
    """Compile yafl source with stdlib, link against libyafl, run, return exit code.

    `args`, when provided, are passed as the program's CLI arguments (so
    `System::args()` in the yafl source sees them).
    """
    rc, _ = compile_and_run_stdlib_capture(source, timeout=timeout, args=args)
    return rc


def compile_and_run_stdlib_capture(source: str, timeout: int = 5,
                                   args: list[str] | None = None) -> tuple[int, str]:
    """Same as compile_and_run_stdlib but also returns the program's stdout
    (decoded as UTF-8). Used by tests that batch several checks into one
    program and verify the printed output, sidestepping the per-test
    compile+link wall-clock."""
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False)
    assert c_code, "yafl compilation produced no output (type errors?)"

    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    try:
        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, *_STATIC_LINK, "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"
        run = subprocess.run([binary, *(args or [])], capture_output=True, timeout=timeout, env=_RUN_ENV)
        return run.returncode, run.stdout.decode("utf-8", errors="replace")
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


def compile_to_binary(source: str) -> str:
    """Compile yafl source (with stdlib) to a runnable binary and return its
    path. The caller owns the file and must unlink it. For tests that need to
    drive the process directly — e.g. an interactive stdin pipe held open — rather
    than the one-shot compile_and_run helpers."""
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False)
    assert c_code, "yafl compilation produced no output (type errors?)"
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    result = subprocess.run(
        ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, *_STATIC_LINK, "-o", binary],
        input=c_code, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, f"clang failed:\n{result.stderr}"
    return binary


def compile_and_run_with_c_library(source: str, c_library: str, timeout: int = 5) -> int:
    """Compile yafl source alongside a C library, link, run, return exit code.

    c_library is C source code (as a string) that will be compiled to an object
    file and linked with the yafl output and libyafl.

    Raises AssertionError if any compilation or link step fails.
    """
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)
    assert c_code, "yafl compilation produced no output (type errors?)"

    with tempfile.TemporaryDirectory() as tmpdir:
        lib_src = os.path.join(tmpdir, "lib.c")
        lib_obj = os.path.join(tmpdir, "lib.o")
        binary = os.path.join(tmpdir, "prog")

        with open(lib_src, "w") as f:
            f.write(c_library)

        result = subprocess.run(
            ["clang", "-g", "-O0", "-I", str(_YAFLLIB_DIR), "-c", lib_src, "-o", lib_obj],
            capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"C library compile failed:\n{result.stderr.decode()}"

        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS,
             "-x", "none", lib_obj, _LIBYAFL_A, "-lpthread", "-lm", "-ldl", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang link failed:\n{result.stderr}"

        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV)
        return run.returncode

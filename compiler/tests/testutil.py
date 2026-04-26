"""Shared helpers for compiler integration tests."""
import os
import subprocess
import tempfile
from pathlib import Path

import compiler as c

# Ensure compiled test binaries can find libyafl.so at runtime.
_YAFLLIB_DIR = Path(__file__).parent.parent.parent / "yafllib"
_YAFLLIB_BUILD_DIR = _YAFLLIB_DIR / "build" / "debug-unix"
# Point clang at the in-tree yafl.h and libyafl.so so tests use whatever is
# checked out right now, not whatever is installed system-wide.
_CLANG_BUILD_FLAGS = [
    "-I", str(_YAFLLIB_DIR),
    "-L", str(_YAFLLIB_BUILD_DIR),
]
_RUN_ENV = {
    **os.environ,
    "LD_LIBRARY_PATH": os.pathsep.join(filter(None, [
        str(_YAFLLIB_DIR),
        str(_YAFLLIB_DIR / "build" / "debug-unix"),
        os.environ.get("LD_LIBRARY_PATH", ""),
    ])),
}


def assert_clean_compile(source: str, *, use_stdlib: bool = True) -> None:
    """Assert that the yafl source compiles to C and clang accepts it with zero
    warnings, zero errors, and zero notes.  Fails the test if clang emits
    anything on stderr."""
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=use_stdlib, just_testing=False)
    assert c_code, "yafl compilation produced no output"

    result = subprocess.run(
        ["clang", "-Werror", "-x", "c", "-", "-O0", "-fsyntax-only",
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
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, "-l", "yafl", "-o", binary],
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


def compile_and_run_stdlib(source: str, timeout: int = 5) -> int:
    """Compile yafl source with stdlib, link against libyafl, run, return exit code."""
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False)
    assert c_code, "yafl compilation produced no output (type errors?)"

    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    try:
        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, "-l", "yafl", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"
        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV)
        return run.returncode
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


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
             "-x", "none", lib_obj, "-l", "yafl", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang link failed:\n{result.stderr}"

        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV)
        return run.returncode

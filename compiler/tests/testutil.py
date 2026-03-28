"""Shared helpers for compiler integration tests."""
import os
import subprocess
import tempfile

import compiler as c


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
            ["clang", "-g", "-x", "c", "-", "-O0", "-l", "yafl", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"

        run = subprocess.run([binary], capture_output=True, timeout=timeout)
        return run.returncode, ""
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
            ["clang", "-g", "-O0", "-c", lib_src, "-o", lib_obj],
            capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"C library compile failed:\n{result.stderr.decode()}"

        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", "-x", "none", lib_obj, "-l", "yafl", "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang link failed:\n{result.stderr}"

        run = subprocess.run([binary], capture_output=True, timeout=timeout)
        return run.returncode

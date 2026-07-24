"""Shared helpers for compiler integration tests."""
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path

import compiler as c


class TimedTestCase(unittest.TestCase):
    """TestCase that fails any individual test exceeding _TIMEOUT seconds of
    CPU time.

    CPU time (ITIMER_PROF: user + system), NOT wall clock: the guard exists to
    catch infinite loops in the compiler itself, and those burn CPU no matter
    what else the machine is doing. A wall-clock alarm made every heavy test's
    verdict depend on neighbour load (this box is a shared VM — the parallel
    suite flaked whichever multi-compile test drew the busiest slot), which is
    exactly the instability a test suite must not have. Hung SUBPROCESSES don't
    consume our CPU and so never trip this timer — every subprocess.run in this
    file carries its own wall-clock timeout for that.
    """
    _TIMEOUT = 120

    def run(self, result=None):
        def _handler(signum, frame):
            raise TimeoutError(f"test exceeded {self._TIMEOUT}s of CPU time")
        old_handler = signal.signal(signal.SIGPROF, _handler)
        signal.setitimer(signal.ITIMER_PROF, self._TIMEOUT)
        try:
            super().run(result)
        finally:
            signal.setitimer(signal.ITIMER_PROF, 0)
            signal.signal(signal.SIGPROF, old_handler)

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

# The port keeps non-suspending calls on the C stack (heap frames only where
# a call can suspend), so compiler-sized inputs recurse deeper than the 8MB
# default — at -O3 the fatter post-inline op lists overflow it (stackguard
# exit 134). Give port subprocesses a 1GiB stack; the real fix (iterative
# walks / [tail] steppers) is a tracked investigation.
_STACK_BYTES = 1 << 30

def raise_stack_limit() -> None:
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    want = _STACK_BYTES if hard == resource.RLIM_INFINITY else min(_STACK_BYTES, hard)
    resource.setrlimit(resource.RLIMIT_STACK, (want, hard))


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
                           args: list[str] | None = None,
                           optimization_level: int = 0,
                           env: dict[str, str] | None = None) -> int:
    """Compile yafl source with stdlib, link against libyafl, run, return exit code.

    `args`, when provided, are passed as the program's CLI arguments (so
    `System::args()` in the yafl source sees them). `optimization_level` selects
    the yafl optimisation level (>0 enables inlining etc.). `env` adds/overrides
    environment variables for the RUN (e.g. YAFL_TASK_BACKLOG)."""
    rc, _ = compile_and_run_stdlib_capture(source, timeout=timeout, args=args,
                                           optimization_level=optimization_level, env=env)
    return rc


def compile_and_run_stdlib_capture(source: str, timeout: int = 5,
                                   args: list[str] | None = None,
                                   optimization_level: int = 0,
                                   env: dict[str, str] | None = None) -> tuple[int, str]:
    """Same as compile_and_run_stdlib but also returns the program's stdout
    (decoded as UTF-8). Used by tests that batch several checks into one
    program and verify the printed output, sidestepping the per-test
    compile+link wall-clock. `optimization_level` selects the yafl optimisation
    level (>0 enables inlining etc.); `env` adds/overrides run environment."""
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False,
                       optimization_level=optimization_level)
    assert c_code, "yafl compilation produced no output (type errors?)"

    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    try:
        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS, *_STATIC_LINK, "-o", binary],
            input=c_code, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, f"clang failed:\n{result.stderr}"
        run_env = {**_RUN_ENV, **env} if env else _RUN_ENV
        run = subprocess.run([binary, *(args or [])], capture_output=True, timeout=timeout, env=run_env)
        return run.returncode, run.stdout.decode("utf-8", errors="replace")
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


def compile_to_binary(source: str, optimization_level: int = 0) -> str:
    """Compile yafl source (with stdlib) to a runnable binary and return its
    path. The caller owns the file and must unlink it. For tests that need to
    drive the process directly — e.g. an interactive stdin pipe held open — rather
    than the one-shot compile_and_run helpers. `optimization_level` selects the
    yafl optimisation level (>0 enables inlining etc.)."""
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False,
                       optimization_level=optimization_level)
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


# ─────────────────────────────────────────────────────────────────────────────
# Shared bootstrap binary — built ONCE per source-tree state, reused by every
# bootstrap contract module (and safely across the unittest-parallel worker
# processes: the first taker holds an flock while building, the rest wait and
# reuse). Previously each module's setUpClass rebuilt the identical binary,
# ~3.5 minutes apiece.
# ─────────────────────────────────────────────────────────────────────────────

import fcntl
import hashlib
import subprocess as _sp
import sys as _sys
import tempfile as _tf
from pathlib import Path as _Path

_BOOT_DIR = _Path(__file__).parent.parent.parent / "bootstrap"
_STDLIB_DIR = _Path(__file__).parent.parent / "stdlib"
_COMPILER_DIR = _Path(__file__).parent.parent


def _bootstrap_tree_hash() -> str:
    """Everything the binary depends on: bootstrap sources, stdlib, the
    Python compiler itself, and the RUNTIME the binary links (a yafllib
    change must invalidate the cache — a stale binary silently runs the old
    allocator/GC)."""
    h = hashlib.sha256()
    roots = [sorted(_BOOT_DIR.glob("*.yafl")),
             sorted(_STDLIB_DIR.glob("*.yafl")),
             sorted(_COMPILER_DIR.rglob("*.py")),
             sorted(_YAFLLIB_DIR.glob("*.c")) + sorted(_YAFLLIB_DIR.glob("*.h"))]
    for group in roots:
        for p in group:
            if "__pycache__" in str(p) or "/tests/" in str(p):
                continue
            h.update(str(p).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def shared_bootstrap_binary() -> str:
    """Path to a bootstrap binary for the CURRENT tree, building it at most
    once across processes."""
    _sys.setrecursionlimit(20000)
    tree = _bootstrap_tree_hash()
    cache_dir = _Path(_tf.gettempdir()) / f"yafl-bootstrap-cache-{os.getuid()}"
    cache_dir.mkdir(exist_ok=True)
    binary = cache_dir / f"bootstrap-{tree}"
    lock_path = cache_dir / f"bootstrap-{tree}.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if binary.exists():
                return str(binary)
            import compiler as _c
            inputs = [_c.Input(p.read_text(), p.name)
                      for p in sorted(_BOOT_DIR.glob("*.yafl"))]
            c_code = _c.compile(inputs, use_stdlib=True, just_testing=False,
                                optimization_level=1)
            assert c_code, "bootstrap compilation failed"
            tmp = binary.with_suffix(".tmp")
            r = _sp.run(["clang", "-g", "-x", "c", "-", "-O0",
                         *_CLANG_BUILD_FLAGS, *_STATIC_LINK, "-o", str(tmp)],
                        input=c_code, text=True, capture_output=True,
                        timeout=180)
            assert r.returncode == 0, f"clang failed:\n{r.stderr[:2000]}"
            tmp.rename(binary)
            # Keep the cache small: drop binaries for other tree states.
            for old in cache_dir.glob("bootstrap-*"):
                if old.suffix in (".lock", ".tmp"):
                    continue
                if old.name != binary.name:
                    try:
                        old.unlink()
                    except OSError:
                        pass
            return str(binary)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

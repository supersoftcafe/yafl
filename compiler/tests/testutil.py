"""Shared helpers for compiler integration tests."""
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path

import compiler as c

_STDLIB_ROOT = Path(__file__).parent.parent / "stdlib"


_BOOTSTRAP_ROOT = Path(__file__).parent.parent.parent / "bootstrap"


def stdlib_unit_name(p: Path) -> str:
    """A stdlib file's unit NAME — `System/IO/fs.yafl`. The same name
    `Library.yafl_sources` gives it, so a harness that builds its own stream
    names units exactly as production does; the name feeds hash6 and so feeds
    the emitted C."""
    from libraries import unit_name
    return unit_name(p, _STDLIB_ROOT)


def bootstrap_unit_name(p: Path) -> str:
    """A port source's unit name — `driver/main.yafl`, matching
    build_bootstrap.py and selfcompile.py."""
    from libraries import unit_name
    return unit_name(p, _BOOTSTRAP_ROOT)


def bootstrap_files() -> list[Path]:
    """The port's `.yafl` sources, in unit-name order."""
    return sorted(_BOOTSTRAP_ROOT.rglob("*.yafl"), key=bootstrap_unit_name)


def stdlib_files() -> list[Path]:
    """The stdlib's `.yafl` units, in the order a library loads them.

    RECURSIVE, and ordered by UNIT NAME — the path relative to the stdlib root
    (`System/IO/fs.yafl`), which is how `Library.yafl_sources` identifies and
    orders a unit. A flat `glob("*.yafl")` here reads NOTHING, silently: an
    empty stdlib is not an error, so the port simply fails to resolve `String`.
    """
    return sorted(_STDLIB_ROOT.rglob("*.yafl"), key=stdlib_unit_name)


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
_YAFLLIB_RELEASE_DIR = _YAFLLIB_DIR / "build" / "release"


def libyafl_for(optimization_level: int) -> str:
    """Optimised builds (-O1..-O3) link the RELEASE runtime — measuring or
    shipping against a Debug archive (no optimisation, NOINLINE_DEBUG)
    silently misstates every runtime cost. -O0 keeps the Debug archive:
    its asserts and poison hooks are what the correctness tests are for.
    YAFL_LIBYAFL_A still overrides both."""
    if "YAFL_LIBYAFL_A" in os.environ:
        return os.environ["YAFL_LIBYAFL_A"]
    if optimization_level >= 1:
        rel = _YAFLLIB_RELEASE_DIR / "libyafl.a"
        if rel.exists():
            return str(rel)
    return _LIBYAFL_A


def static_link_for(optimization_level: int) -> list[str]:
    return ["-x", "none", libyafl_for(optimization_level),
            "-lpthread", "-lm", "-ldl", "-Wl,--gc-sections"]
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

# The port runs within the standard 8MB stack: every deep walk is a [tail]
# loop or dict-indexed iteration (verified 2026-07-26 — yspell at c1/c3 and
# a full self-host compile all complete at ulimit -s 8192; sampled depths
# 23-84 frames). raise_stack_limit stays as a no-op shim only so external
# callers need no change if a regression ever demands it back.
def raise_stack_limit() -> None:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# THE COMPILER UNDER TEST.
#
# Behaviour tests drive a compiler through its COMMAND LINE — the same words,
# `-L <libs> [-O N] [--profile] -c out.c | -o out file.yafl`, whichever compiler
# it is. YAFL_COMPILER picks which:
#
#     port    (default)  the self-hosted compiler, build/ybootstrap
#                        (YAFL_BOOTSTRAP_BIN overrides — see shared_bootstrap_binary)
#     python             compiler/main.py, under this interpreter
#
# The two have parity, so either is a drop-in replacement for the other and
# every behaviour test means the same thing on both. Nothing here reaches into
# a compiler's internals: tests that do (pyast, lowering, …) are unit tests of
# the PYTHON implementation and call it directly.
#
# Both are handed the SAME libraries with -L: `test_libraries()`, built once
# per process from the live sources, so an edit to the stdlib is seen at once
# and neither compiler can pick up a stale package.
# ─────────────────────────────────────────────────────────────────────────────

import shutil
import sys as _sys0

_MAIN_PY = Path(__file__).parent.parent / "main.py"
_SYSTEM_TEST_LIB = Path(__file__).parent.parent / "libs" / "system-test"


def compiler_under_test() -> str:
    """'port' or 'python' — YAFL_COMPILER, default port."""
    name = os.environ.get("YAFL_COMPILER", "port")
    if name not in ("port", "python"):
        raise AssertionError(f"YAFL_COMPILER must be 'port' or 'python', not {name!r}")
    return name


def compiler_command() -> list[str]:
    """argv[0..] of the compiler under test, before its arguments."""
    if compiler_under_test() == "python":
        return [_sys0.executable, str(_MAIN_PY)]
    return [shared_bootstrap_binary()]


_TEST_LIBS: "tempfile.TemporaryDirectory | None" = None


def test_libraries() -> Path:
    """A library search path holding System and System::Test, as directories.

    `system/` is the System library exactly as `package_system_library`
    describes it — the same generated manifest, the stdlib units under the same
    relative names, `yafl.h` and the runtime archive beside them — taken from
    the live sources when the process first asks, so it is never stale. The
    units are COPIES: Python's `unit_name` resolves symlinks, and a linked unit
    would resolve out of the library root. `system-test/` links the
    System::Test library directory, which resolves inside itself."""
    global _TEST_LIBS
    if _TEST_LIBS is None:
        import libraries
        tmp = tempfile.TemporaryDirectory(prefix="yafl-test-libs-")
        root = Path(tmp.name)
        system = root / "system"
        system.mkdir()
        sources = stdlib_files()
        names = libraries._scan_namespaces(sources) or ("System",)
        (system / "yafl.toml").write_text(
            'name = "system"\nnamespaces = [%s]\n'
            'headers = ["yafl.h"]\nstatic_libs = ["libyafl.a"]\n'
            % ", ".join(f'"{n}"' for n in names))
        for src in sources:
            dest = system / stdlib_unit_name(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        (system / "yafl.h").symlink_to((_YAFLLIB_DIR / "yafl.h").resolve())
        (system / "libyafl.a").symlink_to(Path(_LIBYAFL_A).resolve())
        (root / "system-test").symlink_to(_SYSTEM_TEST_LIB.resolve())
        _TEST_LIBS = tmp
    return Path(_TEST_LIBS.name)


class Compiled:
    """One run of the compiler under test: exit code, its stdout (where both
    compilers print diagnostics) and stderr (warnings), and — with `-c` — the C."""
    def __init__(self, rc: int, stdout: str, stderr: str, c: str):
        self.rc, self.stdout, self.stderr, self.c = rc, stdout, stderr, c

    def describe(self) -> str:
        return f"exit {self.rc}\n{self.stdout}{self.stderr}"


def run_compiler(args: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """The compiler under test with `-L <test libraries>` and `args`, in `cwd`.
    YAFL_PATH is cleared so nothing but the test libraries is found."""
    env = {k: v for k, v in os.environ.items() if k != "YAFL_PATH"}
    return subprocess.run([*compiler_command(), "-L", str(test_libraries()), *args],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def _compile(source: "str | list[tuple[str, str]]", filename: str, out_args: list[str],
             optimization_level: int, profile: bool,
             warnings: "list[str] | tuple[str, ...]", test: bool, tmp: Path) -> subprocess.CompletedProcess:
    """`source` is one program text (written as `filename`), or several
    `(filename, text)` units compiled together."""
    units = [(filename, source)] if isinstance(source, str) else source
    for name, text in units:
        (tmp / name).write_text(text)
    args = [f"-O{optimization_level}", *(f"-W{w}" for w in warnings),
            *(["--profile"] if profile else []), *(["--test"] if test else []),
            *out_args, *(name for name, _ in units)]
    return run_compiler(args, tmp)


def compile_c_result(source: "str | list[tuple[str, str]]", filename: str = "test.yafl", *,
                     optimization_level: int = 0, profile: bool = False,
                     warnings: "list[str] | tuple[str, ...]" = (),
                     test: bool = False) -> Compiled:
    """Compile `source` (with the stdlib on the path) to C. `c` is "" on failure.
    `source` is one program, or a list of `(filename, text)` units."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = _compile(source, filename, ["-c", "out.c"], optimization_level, profile,
                     warnings, test, tmp)
        c_path = tmp / "out.c"
        c_text = c_path.read_text() if r.returncode == 0 and c_path.exists() else ""
        return Compiled(r.returncode, r.stdout, r.stderr, c_text)


def compile_c(source: str, filename: str = "test.yafl", **kw) -> str:
    """The C for `source`, or "" if it does not compile."""
    return compile_c_result(source, filename, **kw).c


def compile_errors(source: str, filename: str = "test.yafl", **kw) -> str:
    """What the compiler under test prints on stdout for `source` — its
    diagnostics — and nothing if it compiles cleanly."""
    return compile_c_result(source, filename, **kw).stdout


def assert_clean_compile(source: str, *, use_stdlib: bool = True) -> None:
    """Assert that the yafl source compiles to C and clang accepts it with zero
    warnings, zero errors, and zero notes.  Fails the test if clang emits
    anything on stderr. `use_stdlib=False` sources declare their own System and
    so use the Python compiler's API directly (neither command line has a
    no-library mode)."""
    if use_stdlib:
        r = compile_c_result(source)
        assert r.c, f"yafl compilation produced no output\n{r.describe()}"
        c_code = r.c
    else:
        c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=False, just_testing=False)
        assert c_code, "yafl compilation produced no output"

    result = subprocess.run(
        ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-x", "c", "-", "-O0", "-fsyntax-only",
         "-I", str(_YAFLLIB_DIR)],
        input=c_code, text=True, capture_output=True, timeout=30,
    )
    assert result.stderr == "", f"clang emitted diagnostics:\n{result.stderr}"
    assert result.returncode == 0, f"clang failed:\n{result.stderr}"


def compile_and_run(source: str, timeout: int = 5) -> tuple[int, str]:
    """Compile a SELF-CONTAINED yafl source (it declares its own System, no
    stdlib) to a binary, run it, return (exit_code, clang_stderr). Python's API:
    neither command line has a no-library mode.

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

        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV, stdin=subprocess.DEVNULL)
        return run.returncode, ""
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


def compile_and_run_stdlib(source: str, timeout: int = 5,
                           args: list[str] | None = None,
                           optimization_level: int = 0,
                           env: dict[str, str] | None = None,
                           profile: bool = False) -> int:
    """Compile yafl source with stdlib, link against libyafl, run, return exit code.

    `args`, when provided, are passed as the program's CLI arguments (so
    `System::args()` in the yafl source sees them). `optimization_level` selects
    the yafl optimisation level (>0 enables inlining etc.). `env` adds/overrides
    environment variables for the RUN (e.g. YAFL_TASK_BACKLOG). `profile`
    compiles with --profile instrumentation (the run then writes a profile to
    YAFL_PROF_FILE — pass one via `env` or the CWD gets callgrind.out.<pid>)."""
    rc, _ = compile_and_run_stdlib_capture(source, timeout=timeout, args=args,
                                           optimization_level=optimization_level, env=env,
                                           profile=profile)
    return rc


def compile_and_run_stdlib_capture(source: str, timeout: int = 5,
                                   args: list[str] | None = None,
                                   optimization_level: int = 0,
                                   env: dict[str, str] | None = None,
                                   profile: bool = False) -> tuple[int, str]:
    """Same as compile_and_run_stdlib but also returns the program's stdout
    (decoded as UTF-8)."""
    binary = compile_to_binary(source, optimization_level=optimization_level, profile=profile)
    try:
        run_env = {**_RUN_ENV, **env} if env else _RUN_ENV
        run = subprocess.run([binary, *(args or [])], capture_output=True, timeout=timeout,
                             env=run_env, stdin=subprocess.DEVNULL)
        return run.returncode, run.stdout.decode("utf-8", errors="replace")
    finally:
        try:
            os.unlink(binary)
        except OSError:
            pass


def compile_to_binary(source: str, optimization_level: int = 0, profile: bool = False) -> str:
    """Compile yafl source (with stdlib) to a runnable binary with the compiler
    under test (`-o`), and return its path. The caller owns the file and must
    unlink it. For tests that need to drive the process directly — e.g. an
    interactive stdin pipe held open — rather than the one-shot helpers."""
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    with tempfile.TemporaryDirectory() as td:
        r = _compile(source, "test.yafl", ["-o", binary], optimization_level, profile,
                     (), False, Path(td))
    if r.returncode != 0:
        os.unlink(binary)
        raise AssertionError(f"compilation failed (exit {r.returncode}):\n{r.stdout}{r.stderr}")
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

        run = subprocess.run([binary], capture_output=True, timeout=timeout, env=_RUN_ENV, stdin=subprocess.DEVNULL)
        return run.returncode


# ─────────────────────────────────────────────────────────────────────────────
# The bootstrap binary — an INPUT to the tests, produced by
# compiler/build_bootstrap.py before the suite runs. Tests look it up; they do
# not build it. Which binary is tested is the operator's choice
# (YAFL_BOOTSTRAP_BIN), the same way the runtime archive is.
# ─────────────────────────────────────────────────────────────────────────────

import hashlib
import subprocess as _sp
import sys as _sys
import tempfile as _tf
from pathlib import Path as _Path

_BOOT_DIR = _Path(__file__).parent.parent.parent / "bootstrap"
_DEFAULT_BOOTSTRAP_BIN = (_Path(__file__).parent.parent.parent
                          / "build" / "ybootstrap")


# NO SOURCE-TREE HASHING. Reference outputs are an ARTEFACT, like the
# bootstrap binary: generated from the current tree, reused until you decide
# to regenerate them. Hashing the compiler on every call meant any edit —
# including a harness edit — invalidated every cached reference, so the cache
# never hit during the fix/test loop it exists to serve. Refresh explicitly:
#
#     python build_bootstrap.py --refresh-references     (clears the cache)
#     rm -rf ${TMPDIR:-/tmp}/yafl-bootstrap-cache-$(id -u)
#
# The key below is the INPUT to the reference — file text, kind, and the
# PYTHONHASHSEED the Python compiler's determinism depends on. Nothing about
# the compiler's own source.

def cached_reference(kind: str, text: str, compute, extra: str = "") -> str:
    """Disk-cache a deterministic reference string.

    Keyed on the INPUT — kind, extra, the text itself, and PYTHONHASHSEED
    (Python's C output is only deterministic under it). NOT on the compiler's
    source: see the note above. Concurrent writers race benignly (same key,
    same bytes, atomic rename). Entries older than three days are evicted
    opportunistically on a miss; `build_bootstrap.py --refresh-references`
    clears them outright."""
    key = hashlib.sha256(
        f"{os.environ.get('PYTHONHASHSEED','')}|{kind}|{extra}|"
        f"{hashlib.sha256(text.encode()).hexdigest()}".encode()).hexdigest()[:24]
    cache_dir = _Path(_tf.gettempdir()) / f"yafl-bootstrap-cache-{os.getuid()}"
    cache_dir.mkdir(exist_ok=True)
    path = cache_dir / f"ref-{kind}-{key}"
    try:
        return path.read_text()
    except FileNotFoundError:
        pass
    out = compute()
    try:
        import time as _time
        cutoff = _time.time() - 3 * 86400
        for stale in cache_dir.glob("ref-*"):
            if stale.stat().st_mtime < cutoff:
                stale.unlink(missing_ok=True)
        tmp = path.with_suffix(".tmp%d" % os.getpid())
        tmp.write_text(out)
        tmp.rename(path)
    except OSError:
        pass    # cache is best-effort; never fail the test over it
    return out


def shared_bootstrap_binary() -> str:
    """Path to the bootstrap (port) compiler binary.

    A test CONSUMES this binary; it does not build it. Building is
    `compiler/build_bootstrap.py`, run once before the suite — see that file
    for why. Override with YAFL_BOOTSTRAP_BIN to test a release or worktree
    build without touching test code.

    This used to compile the port lazily on first use, under an exclusive
    flock so ~25 bootstrap modules would not each redo the same ten-minute
    build. That serialised the parallel suite behind one build, and every
    other module paid a lock acquisition just to stat a file that was already
    there.
    """
    _sys.setrecursionlimit(5000)   # see compiler.py — parser needs ~1.5k
    env = os.environ.get("YAFL_BOOTSTRAP_BIN")
    binary = _Path(env) if env else _DEFAULT_BOOTSTRAP_BIN
    if not binary.is_file():
        raise AssertionError(
            f"bootstrap binary not found at {binary}.\n"
            f"Build it first:  python build_bootstrap.py\n"
            f"or point YAFL_BOOTSTRAP_BIN at one.")
    return str(binary)

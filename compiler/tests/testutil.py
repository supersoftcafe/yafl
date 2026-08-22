"""Shared helpers for compiler integration tests."""
import os
import re
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
    (decoded as UTF-8). Used by tests that batch several checks into one
    program and verify the printed output, sidestepping the per-test
    compile+link wall-clock. `optimization_level` selects the yafl optimisation
    level (>0 enables inlining etc.); `env` adds/overrides run environment."""
    # Batched? Only the plain form can be served from a batch — per-test args,
    # env, optimisation level or profiling mean the program cannot share a unit.
    if args is None and env is None and optimization_level == 0 and not profile:
        hit = _batch_lookup(source)
        if hit is not None:
            return hit
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False,
                       optimization_level=optimization_level, profile=profile)
    assert c_code, "yafl compilation produced no output (type errors?)"

    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    try:
        result = subprocess.run(
            ["clang", "-g", "-x", "c", "-", "-O0", *_CLANG_BUILD_FLAGS,
             *static_link_for(optimization_level), "-o", binary],
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


def compile_to_binary(source: str, optimization_level: int = 0, profile: bool = False) -> str:
    """Compile yafl source (with stdlib) to a runnable binary and return its
    path. The caller owns the file and must unlink it. For tests that need to
    drive the process directly — e.g. an interactive stdin pipe held open — rather
    than the one-shot compile_and_run helpers. `optimization_level` selects the
    yafl optimisation level (>0 enables inlining etc.); `profile` instruments
    for profiling (run with YAFL_PROF_FILE set to collect the output)."""
    c_code = c.compile([c.Input(source, "test.yafl")], use_stdlib=True, just_testing=False,
                       optimization_level=optimization_level, profile=profile)
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

# ─────────────────────────────────────────────────────────────────────────────
# Batched compile-and-run.
#
# MEASURED: compiling one trivial program with the stdlib takes ~37s; compiling
# twenty-one programs with the stdlib takes ~35s. The marginal cost of an extra
# program is ZERO — essentially all of it is the stdlib. So N tests that each
# compile their own program pay N x 37s for work that costs 37s once.
#
# run_batch puts every program in its OWN namespace (so each may keep its own
# `main` — no renaming, no textual surgery on user source) and generates a
# driver that calls them in turn, printing a marker around each result. One
# compile, one process.
#
# The markers do the attribution: the runner splits stdout on them, so a
# program that aborts mid-batch is identified by the LAST marker printed.
# ─────────────────────────────────────────────────────────────────────────────

_BATCH_MARK = "##YAFLBATCH"
_MAIN_DEF = re.compile(r"(?m)^(fun\s+)(\[[^\]]*\]\s*)?main\s*\(")
_NS_DECL = re.compile(r"(?m)^namespace\s+\S+\s*$")


def batch_program(sources: list[str]) -> "str | None":
    """The single compilation unit for `sources`, each in namespace T<i>.

    None if any program cannot be batched — one without a `fun main(` has no
    entry point to call, and guessing would produce a unit that fails to
    compile and takes every other program down with it.
    """
    parts, bodies = [], []
    for i, src in enumerate(sources):
        # `main` is THE entry point wherever it is declared — its own namespace
        # is not enough ("Too many main functions defined"). Rename the
        # DEFINITION only, anchored at line start, so `main` inside a string or
        # comment is untouched.
        body, n = _MAIN_DEF.subn(r"\1\2entry(", src, count=1)
        if n != 1:
            return None
        bodies.append(body)
    for i, body in enumerate(bodies):
        # A source that declares its OWN namespace overrides a prepended one,
        # so `entry` would land somewhere other than T<i> and the driver could
        # not name it. Rewrite the declaration instead of prepending. More than
        # one namespace in a single program cannot be placed at all.
        decls = _NS_DECL.findall(body)
        if len(decls) > 1:
            return None
        if decls:
            body = _NS_DECL.sub(f"namespace T{i}", body, count=1)
            parts.append(body.rstrip() + "\n")
        else:
            parts.append(f"namespace T{i}\n{body.rstrip()}\n")
    driver = ["namespace Main", "import System"]
    driver += [f"import T{i}" for i in range(len(bodies))]
    driver.append("fun main(): System::Int")
    for i in range(len(bodies)):
        # Marker BEFORE the call: if the program aborts, the marker is already
        # out, and that is how the runner knows WHICH one died.
        driver.append(f'  let m{i} = System::print("{_BATCH_MARK} {i} start\\n")')
        # Explicitly typed: `String(...)` is heavily overloaded, and an
        # unannotated result left the call ambiguous.
        driver.append(f'  let r{i}: System::Int = T{i}::entry()')
        driver.append(f'  let d{i} = System::print("{_BATCH_MARK} {i} rc=" '
                      f'+ System::String(r{i}) + "\\n")')
    driver.append("  ret 0")
    parts.append("\n".join(driver) + "\n")
    return "".join(parts)


_MARK_RE = re.compile(r"(?m)^" + re.escape(_BATCH_MARK) + r" (\d+) (start|rc=-?\d+)\n")


def parse_batch_output(out: str, n: int) -> "list[tuple[int, str] | None]":
    """Per-program (exit-code, stdout) from a batch run; None where a program
    never reported.

    The text between program i's `start` marker and its `rc=` marker is taken
    RAW — sliced out of the stream, not split into lines and rejoined, because
    rejoining silently dropped the trailing newline and every test comparing
    against a literal ending in "\n" then failed by one character.
    """
    results: "list[tuple[int, str] | None]" = [None] * n
    marks = [(m.start(), m.end(), int(m.group(1)), m.group(2))
             for m in _MARK_RE.finditer(out)]
    starts: "dict[int, int]" = {}
    for _s, e, idx, kind in marks:
        if kind == "start":
            starts[idx] = e
        elif idx in starts and 0 <= idx < n:
            body_end = next(ms for ms, me, i2, k2 in marks
                            if ms >= starts[idx] and i2 == idx and k2 != "start")
            results[idx] = (int(kind[3:]), out[starts[idx]:body_end])
    return results


_COLLECTING: "list[str] | None" = None
_BATCH_RESULTS: "dict[str, tuple[int, str]]" = {}


def _batch_lookup(source: str):
    """(rc, out) for `source` if a batch computed it, else None.

    In COLLECT mode it instead records the program and hands back a benign
    result — the test's assertions on that are meaningless and its exception is
    discarded; only the program text matters.
    """
    if _COLLECTING is not None:
        _COLLECTING.append(source)
        return (0, "")
    return _BATCH_RESULTS.get(source)


def _batch_into(sources: "list[str]", results: dict, depth: int = 0) -> None:
    """Compile `sources` as one unit and record each program's result.

    A program that must FAIL to compile takes the whole unit with it, and
    modules routinely mix those in with normal ones. On failure, binary-search
    the LONGEST COMPILING PREFIX: everything before the first bad program
    batches in one go, the bad one is isolated and left to compile alone, and
    the remainder recurses. Each non-compiling program therefore costs
    O(log n) compiles instead of forfeiting the batch — and if the bad ones sit
    at the END, the very first prefix probe already covers all the good ones.
    """
    if not sources or depth > 16:
        return
    if _try_batch(sources, results):
        return
    if len(sources) == 1:
        return                       # this one cannot batch; it compiles alone
    lo, hi = 0, len(sources)          # largest k < hi with sources[:k] batchable
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if mid >= len(sources):
            break
        if _try_batch(sources[:mid], results):
            lo = mid
        else:
            hi = mid - 1
    _batch_into(sources[lo + 1:], results, depth + 1)   # skip the culprit


def _try_batch(sources: "list[str]", results: dict) -> bool:
    """Compile+run `sources` as one unit; record results. False if it failed."""
    if not sources:
        return True
    unit = batch_program(sources)
    if unit is None:
        return False
    try:
        _rc, out = compile_and_run_stdlib_capture(unit, timeout=300)
    except Exception:
        return False
    got = parse_batch_output(out, len(sources))
    if not any(r is not None for r in got):
        return False
    for src, res in zip(sources, got):
        if res is not None:
            results[src] = res
    return True


class BatchedTestCase(TimedTestCase):
    """TimedTestCase that compiles its class's programs in one unit.

    Opt in by changing only the base class. Do NOT use where tests pass
    per-test args/env/optimisation levels (they cannot share a unit), or where
    a test expects compilation to FAIL.
    """
    _TIMEOUT = 600

    @classmethod
    def setUpClass(cls):
        global _COLLECTING, _BATCH_RESULTS
        names = [n for n in dir(cls) if n.startswith("test")]
        _COLLECTING = []
        for n in names:
            try:
                inst = cls(n)
                inst.setUp()
                getattr(inst, n)()
            except Exception:
                pass                      # collect mode: only the sources matter
            finally:
                try:
                    inst.tearDown()
                except Exception:
                    pass
        sources, _COLLECTING = _COLLECTING, None
        seen, uniq = set(), []
        for src in sources:
            if src not in seen:
                seen.add(src); uniq.append(src)
        if not uniq:
            return
        _batch_into(uniq, _BATCH_RESULTS)

    @classmethod
    def tearDownClass(cls):
        _BATCH_RESULTS.clear()

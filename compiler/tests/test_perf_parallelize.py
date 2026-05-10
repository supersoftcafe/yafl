"""Performance comparison test for the auto-parallelise pass.

Compiles the same source twice — once with the auto-parallelise pass enabled
(at -O2), once with --no-auto-parallel — runs each binary, asserts they
produce the same exit code, and reports their wall-clock timings.

Currently the test does NOT assert parallel < serial. The implementation is
early; spawn cost calibration and capture-cost penalties are still TODO. This
test is the harness for future calibration: a clear before/after measurement
that lets us tune T_CPU/T_IO/SPAWN_W against real workloads.

Catastrophic regressions still trip the test — if `parallel > 10× serial`
something is badly wrong (e.g. a spawn-storm bug) and we want to know.
"""
from __future__ import annotations

import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from tests.testutil import TimedTestCase as TestCase

import compiler as c


_YAFLLIB_DIR = Path(__file__).parent.parent.parent / "yafllib"
_YAFLLIB_BUILD_DIR = _YAFLLIB_DIR / "build" / "debug-unix"
_CLANG_BUILD_FLAGS = [
    "-I", str(_YAFLLIB_DIR),
    "-L", str(_YAFLLIB_BUILD_DIR),
]
_RUN_ENV = {
    **os.environ,
    "LD_LIBRARY_PATH": os.pathsep.join(filter(None, [
        str(_YAFLLIB_DIR),
        str(_YAFLLIB_BUILD_DIR),
        os.environ.get("LD_LIBRARY_PATH", ""),
    ])),
}


def _build_binary(source: str, *, disable_auto_parallel: bool) -> tuple[str, int]:
    """Compile + link the source; return (binary_path, rewrite_count).
    rewrite_count is the number of TupleExpressions auto-parallelise
    converted (always 0 when disabled)."""
    rewrite_count = 0
    if not disable_auto_parallel:
        import lowering.parallelize_tuples as pt
        original = pt._maybe_parallelise
        def counting(node, cm, resolver):
            nonlocal rewrite_count
            result = original(node, cm, resolver)
            if result is not node:
                rewrite_count += 1
            return result
        pt._maybe_parallelise = counting
    try:
        c_code = c.compile(
            [c.Input(source, "perf.yafl")],
            use_stdlib=True,
            just_testing=False,
            optimization_level=2,
            disable_auto_parallel=disable_auto_parallel,
        )
    finally:
        if not disable_auto_parallel:
            pt._maybe_parallelise = original

    assert c_code, "yafl compilation produced no output"
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as tmp:
        binary = tmp.name
    result = subprocess.run(
        ["clang", "-g", "-x", "c", "-", "-O2", *_CLANG_BUILD_FLAGS,
         "-l", "yafl", "-l", "m", "-o", binary],
        input=c_code, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, f"clang failed:\n{result.stderr}"
    return binary, rewrite_count


def _time_binary(binary: str, runs: int) -> tuple[int, float]:
    """Run the binary `runs` times. Return (last_exit_code, min_seconds)."""
    times: list[float] = []
    last_rc: int | None = None
    for _ in range(runs):
        t0 = time.perf_counter()
        run = subprocess.run([binary], capture_output=True, timeout=120, env=_RUN_ENV)
        t1 = time.perf_counter()
        times.append(t1 - t0)
        last_rc = run.returncode
    assert last_rc is not None
    return last_rc, min(times)


class TestPerfParallelize(TestCase):
    # Allow up to 10× slowdown before failing — well above realistic perf
    # variance, but catches spawn-storm-style bugs.
    MAX_SLOWDOWN_FACTOR = 10.0

    # Run a few times and take the minimum to reduce variance.
    RUNS_PER_BINARY = 3

    def _compare(self, source: str) -> None:
        serial_bin, _ = _build_binary(source, disable_auto_parallel=True)
        parallel_bin, rewrites = _build_binary(source, disable_auto_parallel=False)
        try:
            # Test would be vacuous if the pass didn't fire.
            self.assertGreater(
                rewrites, 0,
                "auto-parallelise rewrote no tuples — workload doesn't exercise the pass")

            serial_rc, serial_t = _time_binary(serial_bin, self.RUNS_PER_BINARY)
            parallel_rc, parallel_t = _time_binary(parallel_bin, self.RUNS_PER_BINARY)
        finally:
            for b in (serial_bin, parallel_bin):
                try: os.unlink(b)
                except OSError: pass

        # Correctness must match.
        self.assertEqual(serial_rc, parallel_rc,
                         f"serial and parallel produced different results: "
                         f"serial={serial_rc} parallel={parallel_rc}")

        ratio = parallel_t / serial_t if serial_t > 0 else float("inf")
        # Print to stderr so unittest -v shows it; this is informational.
        print(
            f"\n  rewrites: {rewrites}"
            f"\n  serial:   {serial_t*1000:.2f} ms"
            f"\n  parallel: {parallel_t*1000:.2f} ms"
            f"\n  ratio:    {ratio:.2f}× ({'faster' if ratio < 1 else 'slower'})",
            file=sys.stderr,
        )

        # Soft upper bound — only fails on catastrophic regression.
        self.assertLess(
            ratio, self.MAX_SLOWDOWN_FACTOR,
            f"parallel build is {ratio:.1f}× slower than serial — likely a bug")

    # -----------------------------------------------------------------
    # CPU-bound workload: two recursive Fibonacci computations in a tuple.
    # `fib` is recursive → cost-model lifts its summary above T_CPU.
    # Two qualifying children → auto-parallelise rewrites the tuple.
    # -----------------------------------------------------------------

    def test_cpu_bound_dual_count(self):
        # `count` has exactly one recursive arg per call (the other is a
        # literal), so it stays sequential — only the outer (count, count)
        # tuple in main qualifies. This avoids the spawn-explosion that
        # would happen if `count`'s own body kept auto-parallelising at every
        # recursion level (a known limitation we'll address later with depth
        # cutoffs).
        src = """\
namespace Test
import System

fun count(n: System::Int): System::Int
    ret n < 1 ? 0 : 1 + count(n - 1)

fun main(): System::Int
    let (a, b) = (count(800000), count(800000))
    ret a + b
"""
        # count is deterministic — both runs must produce the same exit code,
        # giving us a correctness check on the parallel join.
        self._compare(src)

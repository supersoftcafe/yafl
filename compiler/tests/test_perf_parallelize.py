"""Performance comparison test for the auto-parallelise pass.

Compiles the same source twice — once with the auto-parallelise pass enabled
(at -O2), once with --no-auto-parallel — runs each binary, asserts each
produces the *expected* exit code (not merely that the two agree — a crash
that hits both builds would otherwise sail through), and reports their
wall-clock timings.

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
from tests.testutil import _CLANG_BUILD_FLAGS, _STATIC_LINK, _RUN_ENV

import compiler as c


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
        ["clang", "-g", "-x", "c", "-", "-O2", *_CLANG_BUILD_FLAGS, *_STATIC_LINK, "-o", binary],
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

    def _compare(self, source: str, *, expected_rc: int) -> None:
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

        # Both builds must produce the *expected* exit code. Checking only
        # that serial == parallel is not enough: a workload that crashes
        # (e.g. a stack-overflow → SIGSEGV → 139) crashes both builds
        # identically, so the comparison passes while measuring nothing but
        # time-to-crash.
        self.assertEqual(serial_rc, expected_rc,
                         f"serial build exited {serial_rc}, expected {expected_rc}")
        self.assertEqual(parallel_rc, expected_rc,
                         f"parallel build exited {parallel_rc}, expected {expected_rc}")

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
    # CPU-bound workload: two heavy nested loops in a tuple.
    #
    #   inner(n, acc)  — n iterations of integer arithmetic; returns 0.
    #   outer(k, acc)  — k iterations, each running inner(...) once.
    #   main           — (outer(...), outer(...)) in a tuple.
    #
    # Both `inner` and `outer` are recursive, so the cost model lifts their
    # summaries above T_CPU. Only the (outer, outer) tuple in main has two
    # qualifying children, so that's the one tuple auto-parallelise rewrites:
    # `outer`'s body has just one heavy child per call (inner(...)), the loop
    # index is trivial, so it stays sequential and there's no spawn explosion.
    #
    # Crucially the recursion depth is bounded (outer ≤ k frames, inner ≤ n),
    # so the workload runs to completion instead of overflowing the stack —
    # which is what makes the before/after timing meaningful at all.
    # -----------------------------------------------------------------

    def test_cpu_bound_dual_loop(self):
        src = """\
namespace Test
import System

fun inner(n: System::Int, acc: System::Int): System::Int
    ret n < 1 ? 0 : inner(n - 1, acc + n)

fun outer(k: System::Int, acc: System::Int): System::Int
    ret k < 1 ? acc : outer(k - 1, acc + inner(15000, 0))

fun main(): System::Int
    let (a, b) = (outer(3000, 0), outer(3000, 0))
    ret a + b
"""
        # inner(...) returns 0, so outer(k, 0) == 0 and main returns 0 — a
        # deterministic result that doubles as a correctness check on the
        # parallel join.
        self._compare(src, expected_rc=0)

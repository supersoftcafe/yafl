#!/usr/bin/env python3
"""Soak the GC's C tests: many runs, across builds and runtime settings.

A single CTest pass runs each GC test once, built at -O0 with the build's
default compiler. Races in the collector are timing-dependent and show up once
in hundreds or thousands of runs, and which interleavings are possible depends
on the instruction schedule (compiler, optimisation level) and, on a
weakly-ordered machine such as aarch64, on the memory model too. This script
builds the tests in several variants and runs each test repeatedly under a
matrix of collector settings, several runs at once so workers are preempted
inside critical windows.

    python3 tests/gc_soak.py                        # default matrix, 20 runs each
    python3 tests/gc_soak.py -n 200 -j 4            # longer
    python3 tests/gc_soak.py --builds clang-O2 --tests test_gc_mesh --profiles hot -n 1000
    python3 tests/gc_soak.py --list                 # show builds/tests/profiles

Builds go to yafllib/build/soak-<variant>/, failure logs to
yafllib/build/soak-logs/<timestamp>/. Exit status is the number of failing
(build, test, profile) combinations, capped at 255.
"""

import argparse
import concurrent.futures as cf
import datetime
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

YAFLLIB = Path(__file__).resolve().parent.parent

# Variant -> (C compiler, extra flags). Asserts stay on in every variant (no
# NDEBUG): they are half the checking. The C tests compile the runtime sources
# into each test binary, so the flags apply to the runtime as well.
BUILDS = {
    "gcc-O0":   ("gcc",   "-O0 -g"),
    "gcc-O2":   ("gcc",   "-O2 -g"),
    "clang-O0": ("clang", "-O0 -g"),
    "clang-O2": ("clang", "-O2 -g"),
}

# The tests that exercise the collector, with a per-run timeout (seconds) and
# any test-specific environment.
#
# ONLY_PROFILES: tests that step the collector to an exact state depend on its
# settings, and fail by design under other profiles. test_gc_gen and
# test_gc_late_pin_race need generations at their default floor (the nursery
# knobs change which cycle promotes); the other stepped tests stay with them. test_gc_pressure under `hot` does 16x the
# collector work and outlasts any sane timeout on a small machine.
ONLY_PROFILES = {
    "test_gc_gen":           {"default", "global"},
    "test_gc_late_pin_race": {"default", "global"},
    "test_gc_publish_step":  {"default", "global"},
    "test_gc_lazy_step":     {"default", "global"},
    "test_gc_pressure":      {"default", "nursery1", "nursery4", "global", "nogen", "oversub"},
}
TESTS = {
    "test_gc":               (120, {}),
    "test_gc_stress":        (120, {}),
    "test_gc_ring":          (300, {}),
    "test_gc_min":           (120, {}),
    "test_gc_min2":          (120, {}),
    "test_gc_min2_window":   (120, {}),
    "test_gc_publish_step":  (60,  {}),
    "test_gc_lazy_step":     (60,  {}),
    "test_gc_pressure":      (600, {}),
    "test_gc_gen":           (60,  {}),
    "test_gc_stale_mark":    (120, {}),
    "test_gc_fwd_chain":     (60,  {}),
    "test_gc_late_pin_race": (60,  {}),
    "test_gc_mesh":          (300, {"MESH_STEPS": "100000"}),
    "test_pin":              (60,  {}),
    "test_large_objects":    (120, {}),
    "test_io_stress":        (300, {}),
    "test_parallel":         (60,  {}),
    "test_str":              (60,  {}),
    # Compiled YAFL (tests/gc_stress.yafl): the builders, futures and memoize
    # that generated code uses. Linked against the variant's libyafl.a, which
    # takes the variant's COMPILER but is always the shipped -O3 NDEBUG build.
    "gc_stress":             (300, {}),
}
# Tests that are YAFL programs, not C test targets: source, then arguments.
YAFL_TESTS = {"gc_stress": ("tests/gc_stress.yafl", ["500"])}

# Collector settings. Every profile poisons reclaimed memory, so a
# use-after-free aborts instead of reading stale data.
P = {"YAFL_GC_POISON": "1"}
PROFILES = {
    # The defaults: nursery on, one worker per core.
    "default":   {**P},
    # A nursery collection every 2 pages, on one worker and on four.
    "nursery1":  {**P, "YAFL_LOCAL_GC_PAGES": "2", "YAFL_THREADS": "1"},
    "nursery4":  {**P, "YAFL_LOCAL_GC_PAGES": "2", "YAFL_THREADS": "4"},
    # Nursery off: the global collector alone.
    "global":    {**P, "YAFL_LOCAL_GC": "0"},
    # Generations off.
    "nogen":     {**P, "YAFL_GC_GEN": "0"},
    # Everything turned up: 16x the scan/prune work per page, every survivor
    # page evacuated, promotion from 16 pages, so cycles, compaction,
    # forwarding and majors overlap the mutator as much as possible.
    "hot":       {**P, "YAFL_GC_STEP_PAGES": "64", "YAFL_GC_PRUNE_PAGES": "1024",
                  "YAFL_GC_COMPACT_PERCENT": "100", "YAFL_GC_PROMOTE_FLOOR": "16",
                  "YAFL_LOCAL_GC_PAGES": "4"},
    # Twice as many workers as cores: preemption lands inside the collector's
    # check-then-act windows.
    "oversub":   {**P, "YAFL_THREADS": "8", "YAFL_LOCAL_GC_PAGES": "4"},
}

DEFAULT_PROFILES = list(PROFILES)


def build_yafl(bdir, name):
    """Compile a YAFL test program with the Python compiler against this
    variant's runtime archive. Slow (minutes); rebuilt only when stale."""
    src, _ = YAFL_TESTS[name]
    src = YAFLLIB / src
    out = bdir / name
    lib = bdir / "libyafl.a"
    if out.exists() and out.stat().st_mtime > max(src.stat().st_mtime, lib.stat().st_mtime):
        return
    main_py = YAFLLIB.parent / "compiler" / "main.py"
    r = subprocess.run([sys.executable, str(main_py), "-O2", str(src), "-o", str(out)],
                       env={**os.environ, "YAFL_LIBYAFL_A": str(lib)},
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"gc_soak: compiling {src.name} failed:\n{r.stdout[-4000:]}{r.stderr[-4000:]}")


def build(variant, tests, jobs):
    cc, flags = BUILDS[variant]
    if shutil.which(cc) is None:
        sys.exit(f"gc_soak: {cc} not found (needed for {variant})")
    bdir = YAFLLIB / "build" / f"soak-{variant}"
    if not (bdir / "CMakeCache.txt").exists():
        subprocess.run(["cmake", "-S", str(YAFLLIB), "-B", str(bdir),
                        f"-DCMAKE_C_COMPILER={cc}", f"-DCMAKE_C_FLAGS={flags}"],
                       check=True, stdout=subprocess.DEVNULL)
    yafl = [t for t in tests if t in YAFL_TESTS]
    targets = [t for t in tests if t not in YAFL_TESTS] + (["yafl_static"] if yafl else [])
    r = subprocess.run(["cmake", "--build", str(bdir), "-j", str(jobs), "--target", *targets],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"gc_soak: build {variant} failed:\n{r.stdout[-4000:]}{r.stderr[-4000:]}")
    for t in yafl:
        print(f"  compiling {t} for {variant} ...", flush=True)
        build_yafl(bdir, t)
    return bdir


def run_one(binary, env, timeout, args=()):
    t0 = time.monotonic()
    try:
        r = subprocess.run([str(binary), *args], env=env, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        rc, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        rc = "timeout"
        out = ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + \
              ((e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""))
    return rc, out, time.monotonic() - t0


def describe(rc):
    if rc == "timeout":
        return "timeout"
    if isinstance(rc, int) and rc < 0:
        import signal
        try:
            return signal.Signals(-rc).name
        except ValueError:
            return f"signal {-rc}"
    return f"rc={rc}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--runs", type=int, default=20, help="runs per (build, test, profile)")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4, help="runs at once")
    ap.add_argument("--builds", default=",".join(BUILDS), help="comma-separated build variants")
    ap.add_argument("--tests", default=",".join(TESTS), help="comma-separated tests")
    ap.add_argument("--profiles", default=",".join(DEFAULT_PROFILES), help="comma-separated profiles")
    ap.add_argument("--stop-on-fail", action="store_true", help="stop a combination at its first failure")
    ap.add_argument("--list", action="store_true", help="list builds, tests and profiles, then exit")
    a = ap.parse_args()

    if a.list:
        print("builds:  ", " ".join(BUILDS))
        print("tests:   ", " ".join(TESTS))
        for k, v in PROFILES.items():
            print(f"profile {k:9} {' '.join(f'{x}={y}' for x, y in v.items())}")
        return 0

    def pick(arg, table, what):
        names = [s for s in arg.split(",") if s]
        bad = [s for s in names if s not in table]
        if bad:
            sys.exit(f"gc_soak: unknown {what}: {', '.join(bad)}")
        return names

    builds = pick(a.builds, BUILDS, "build")
    tests = pick(a.tests, TESTS, "test")
    profiles = pick(a.profiles, PROFILES, "profile")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    logdir = YAFLLIB / "build" / "soak-logs" / stamp

    dirs = {}
    for b in builds:
        print(f"building {b} ...", flush=True)
        dirs[b] = build(b, tests, a.jobs)

    combos = [(b, t, p) for b in builds for t in tests for p in profiles
              if p in ONLY_PROFILES.get(t, PROFILES)]
    total = len(combos) * a.runs
    print(f"{len(combos)} combinations x {a.runs} runs = {total} runs, {a.jobs} at a time; "
          f"failure logs -> {logdir}", flush=True)

    fails = {c: [] for c in combos}
    runs_done = {c: 0 for c in combos}
    secs = {c: 0.0 for c in combos}
    stopped = set()
    t_start = time.monotonic()

    def env_for(t, p):
        e = dict(os.environ)
        for k in list(e):
            if k.startswith("YAFL_") or k == "MESH_STEPS":
                del e[k]
        e.update(TESTS[t][1])
        e.update(PROFILES[p])
        return e

    # Interleave combinations so concurrent runs are of different tests.
    work = [(c, i) for i in range(a.runs) for c in combos]
    done = 0
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        pending = {}
        it = iter(work)

        def submit_next():
            for c, i in it:
                if c in stopped:
                    continue
                b, t, p = c
                f = ex.submit(run_one, dirs[b] / t, env_for(t, p), TESTS[t][0],
                              YAFL_TESTS.get(t, (None, []))[1])
                pending[f] = (c, i)
                return True
            return False

        for _ in range(a.jobs):
            if not submit_next():
                break
        while pending:
            finished, _ = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            for f in finished:
                c, i = pending.pop(f)
                rc, out, dt = f.result()
                runs_done[c] += 1
                secs[c] += dt
                done += 1
                if rc != 0:
                    fails[c].append(describe(rc))
                    logdir.mkdir(parents=True, exist_ok=True)
                    b, t, p = c
                    (logdir / f"{b}.{t}.{p}.run{i}.log").write_text(
                        f"# {b} {t} {p} run {i}: {describe(rc)} after {dt:.1f}s\n"
                        f"# env: {' '.join(f'{k}={v}' for k, v in {**TESTS[t][1], **PROFILES[p]}.items())}\n"
                        + out[-20000:])
                    print(f"FAIL {b} {t} {p} run {i}: {describe(rc)} ({dt:.1f}s) "
                          f"{(out.strip().splitlines() or [''])[-1][:160]}", flush=True)
                    if a.stop_on_fail:
                        stopped.add(c)
                if done % 50 == 0:
                    el = time.monotonic() - t_start
                    print(f"  {done}/{total} runs, {sum(len(v) for v in fails.values())} failures, "
                          f"{el / 60:.1f} min", flush=True)
                submit_next()

    print()
    print(f"{'build':9} {'test':22} {'profile':9} {'runs':>5} {'fail':>5} {'avg s':>7}  failures")
    bad = 0
    for c in combos:
        b, t, p = c
        n, fl = runs_done[c], fails[c]
        if fl:
            bad += 1
        kinds = {}
        for k in fl:
            kinds[k] = kinds.get(k, 0) + 1
        avg = secs[c] / n if n else 0
        mark = "  " + ", ".join(f"{v}x {k}" for k, v in kinds.items()) if fl else ""
        print(f"{b:9} {t:22} {p:9} {n:5} {len(fl):5} {avg:7.2f}{mark}")
    print(f"\n{bad} of {len(combos)} combinations failed; "
          f"{sum(len(v) for v in fails.values())} failing runs of {done}; "
          f"{(time.monotonic() - t_start) / 60:.1f} min")
    if bad:
        print(f"logs: {logdir}")
    return min(bad, 255)


if __name__ == "__main__":
    sys.exit(main())

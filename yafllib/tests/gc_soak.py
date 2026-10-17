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
    python3 tests/gc_soak.py --minutes 120          # whole rounds until the time is up (CI)

Builds go to yafllib/build/soak-<variant>/, failure logs to
yafllib/build/soak-logs/<timestamp>/. Exit status is the number of failing
(build, test, profile) combinations, capped at 255.
"""

import argparse
import concurrent.futures as cf
import datetime
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

YAFLLIB = Path(__file__).resolve().parent.parent

# Variant -> (C compiler, extra flags). Asserts stay on in every variant but
# the -ndebug ones: they are half the checking. The C tests compile the runtime sources
# into each test binary, so the flags apply to the runtime as well.
BUILDS = {
    "gcc-O0":   ("gcc",   "-O0 -g"),
    "gcc-O2":   ("gcc",   "-O2 -g"),
    "clang-O0": ("clang", "-O0 -g"),
    "clang-O2": ("clang", "-O2 -g"),
    # -O3 is what ships (yafl_static, and programs from the full protocol):
    # more inlining across the barrier helpers, vectorised bitmap loops,
    # values that live only in registers. With asserts, and without (NDEBUG,
    # exactly the shipped runtime's flags).
    "gcc-O3":          ("gcc",   "-O3 -g"),
    "clang-O3":        ("clang", "-O3 -g"),
    "gcc-O3-ndebug":   ("gcc",   "-O3 -g -DNDEBUG"),
    "clang-O3-ndebug": ("clang", "-O3 -g -DNDEBUG"),
}
# The default matrix; the -O3 variants are opt-in (--builds), as they double
# the run time.
DEFAULT_BUILDS = ["gcc-O0", "gcc-O2", "clang-O0", "clang-O2"]

# The tests that exercise the collector, with a per-run timeout (seconds) and
# any test-specific environment.
#
# ONLY_PROFILES: tests that step the collector to an exact state depend on its
# settings, and fail by design under other profiles. test_gc_gen and
# test_gc_late_pin_race need generations at their default floor (the nursery
# knobs change which cycle promotes); the other stepped tests are limited the
# same way. test_gc_pressure under `hot` does 16x the collector work and
# outlasts any sane timeout on a small machine.
ONLY_PROFILES = {
    "test_gc_gen":           {"default", "global"},
    "test_gc_late_pin_race": {"default", "global"},
    "test_gc_publish_step":  {"default", "global"},
    "test_gc_lazy_step":     {"default", "global"},
    "test_gc_old_late_write": {"default", "global"},
    "test_gc_late_requeue":  {"default", "global"},
    "test_gc_static_store":  {"default", "global"},
    "test_gc_builder_idle":  {"default"},
    "test_gc_once_escape":   {"default"},
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
    "test_gc_old_late_write": (60, {}),
    "test_gc_late_requeue":  (60,  {}),
    "test_gc_static_store":  (60,  {}),
    "test_gc_builder_idle":  (60,  {}),
    "test_gc_once_escape":   (60,  {}),
    "test_lazy_runner":      (60,  {}),
    # test_gc_mesh picks a 64 MB heap for itself (4 workers, collector always
    # busy). Under oversub (8 workers) and hot (every survivor page compacted)
    # that runs out, by design rather than by a collector bug, so the soak
    # gives it room: it hunts safety failures, not out-of-memory.
    "test_gc_mesh":          (300, {"MESH_STEPS": "100000", "YAFL_HEAP_SIZE": "256m"}),
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
    "hotglobal": {**P, "YAFL_GC_STEP_PAGES": "64", "YAFL_GC_PRUNE_PAGES": "1024",
                  "YAFL_GC_COMPACT_PERCENT": "100", "YAFL_GC_PROMOTE_FLOOR": "16",
                  "YAFL_LOCAL_GC": "0"},
    "globaleom": {**P, "YAFL_LOCAL_GC": "0", "YAFL_GC_DIAG_EOM": "1"},
    "compactglobal": {**P, "YAFL_GC_COMPACT_PERCENT": "100", "YAFL_LOCAL_GC": "0"},
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
    # Configured every time (cheap), so a test added since the last soak has
    # a target.
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


class Combo(NamedTuple):
    build: str
    test: str
    profile: str


@dataclass
class Tally:
    """What one combination's runs came to."""
    runs: int = 0
    seconds: float = 0.0
    failures: list[str] = field(default_factory=list)


def run_one(binary, env, timeout, args=()):
    t0 = time.monotonic()
    try:
        r = subprocess.run([str(binary), *args], env=env, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        rc, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        rc, out = "timeout", _text(e.stdout) + _text(e.stderr)
    return rc, out, time.monotonic() - t0


def _text(stream):
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return stream or ""


def describe(rc):
    if rc == "timeout":
        return "timeout"
    if isinstance(rc, int) and rc < 0:
        try:
            return signal.Signals(-rc).name
        except ValueError:
            return f"signal {-rc}"
    return f"rc={rc}"


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--runs", type=int, default=20, help="runs per (build, test, profile)")
    ap.add_argument("--minutes", type=float, default=None,
                    help="instead of -n: keep starting rounds (one run of every combination) "
                         "until this much time has passed since the builds finished")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4, help="runs at once")
    ap.add_argument("--builds", default=",".join(DEFAULT_BUILDS), help="comma-separated build variants")
    ap.add_argument("--tests", default=",".join(TESTS), help="comma-separated tests")
    ap.add_argument("--profiles", default=",".join(DEFAULT_PROFILES), help="comma-separated profiles")
    ap.add_argument("--stop-on-fail", action="store_true", help="stop a combination at its first failure")
    ap.add_argument("--summary", type=Path, default=None, metavar="FILE",
                    help="append a Markdown summary (the failing combinations) to FILE, "
                         "e.g. $GITHUB_STEP_SUMMARY")
    ap.add_argument("--list", action="store_true", help="list builds, tests and profiles, then exit")
    return ap.parse_args()


def pick(arg, table, what):
    names = [s for s in arg.split(",") if s]
    unknown = [s for s in names if s not in table]
    if unknown:
        sys.exit(f"gc_soak: unknown {what}: {', '.join(unknown)}")
    return names


def env_for(combo):
    """The environment one run gets: ours without any collector setting, then
    the test's own, then the profile's."""
    env = {k: v for k, v in os.environ.items() if not (k.startswith("YAFL_") or k == "MESH_STEPS")}
    env.update(TESTS[combo.test][1])
    env.update(PROFILES[combo.profile])
    return env


def schedule(combos, runs, deadline):
    """Round after round of every combination, interleaved so concurrent runs
    are of different tests. With a deadline, a new round starts only while
    there is time left, so every combination ends with the same run count give
    or take one."""
    run = 0
    while (run < runs) if deadline is None else (time.monotonic() < deadline):
        for combo in combos:
            yield combo, run
        run += 1


def soak(combos, binaries, args, logdir, total):
    """Run the schedule, `args.jobs` at a time; tally every combination."""
    tallies = {combo: Tally() for combo in combos}
    stopped = set()
    started = time.monotonic()
    deadline = None if args.minutes is None else started + args.minutes * 60
    work = schedule(combos, args.runs, deadline)
    done = 0

    def record_failure(combo, run, rc, out, seconds):
        tallies[combo].failures.append(describe(rc))
        logdir.mkdir(parents=True, exist_ok=True)
        settings = " ".join(f"{k}={v}" for k, v in {**TESTS[combo.test][1], **PROFILES[combo.profile]}.items())
        (logdir / f"{combo.build}.{combo.test}.{combo.profile}.run{run}.log").write_text(
            f"# {combo.build} {combo.test} {combo.profile} run {run}: {describe(rc)} after {seconds:.1f}s\n"
            f"# env: {settings}\n" + out[-20000:])
        last_line = (out.strip().splitlines() or [""])[-1][:160]
        print(f"FAIL {combo.build} {combo.test} {combo.profile} run {run}: {describe(rc)} "
              f"({seconds:.1f}s) {last_line}", flush=True)
        if args.stop_on_fail:
            stopped.add(combo)

    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        pending = {}

        def submit_next():
            for combo, run in work:
                if combo in stopped:
                    continue
                future = pool.submit(run_one, binaries[combo.build] / combo.test, env_for(combo),
                                     TESTS[combo.test][0], YAFL_TESTS.get(combo.test, (None, []))[1])
                pending[future] = (combo, run)
                return True
            return False

        for _ in range(args.jobs):
            if not submit_next():
                break
        while pending:
            finished, _ = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            for future in finished:
                combo, run = pending.pop(future)
                rc, out, seconds = future.result()
                tallies[combo].runs += 1
                tallies[combo].seconds += seconds
                done += 1
                if rc != 0:
                    record_failure(combo, run, rc, out, seconds)
                if done % 50 == 0:
                    failures = sum(len(t.failures) for t in tallies.values())
                    print(f"  {done}/{total or '?'} runs, {failures} failures, "
                          f"{(time.monotonic() - started) / 60:.1f} min", flush=True)
                submit_next()
    return tallies, done, time.monotonic() - started


def kinds(failures):
    return ", ".join(f"{n}x {kind}" for kind, n in Counter(failures).items())


def report(tallies, done, seconds, logdir):
    print()
    print(f"{'build':9} {'test':22} {'profile':9} {'runs':>5} {'fail':>5} {'avg s':>7}  failures")
    for combo, tally in tallies.items():
        average = tally.seconds / tally.runs if tally.runs else 0
        mark = f"  {kinds(tally.failures)}" if tally.failures else ""
        print(f"{combo.build:9} {combo.test:22} {combo.profile:9} {tally.runs:5} "
              f"{len(tally.failures):5} {average:7.2f}{mark}")
    failed = [combo for combo, tally in tallies.items() if tally.failures]
    print(f"\n{len(failed)} of {len(tallies)} combinations failed; "
          f"{sum(len(t.failures) for t in tallies.values())} failing runs of {done}; "
          f"{seconds / 60:.1f} min")
    if failed:
        print(f"logs: {logdir}")
    return failed


def write_summary(path, title, tallies, failed, done, seconds):
    lines = [f"### {title}", ""]
    if failed:
        lines += ["| build | test | profile | runs | failures |", "|---|---|---|---|---|"]
        lines += [f"| {c.build} | {c.test} | {c.profile} | {tallies[c].runs} | {kinds(tallies[c].failures)} |"
                  for c in failed]
    else:
        lines.append("No failures.")
    lines += ["", f"{len(failed)} of {len(tallies)} combinations failed; {done} runs; "
                  f"{seconds / 60:.1f} min", ""]
    with open(path, "a") as out:
        out.write("\n".join(lines))


def main():
    args = parse_args()
    if args.list:
        print("builds:  ", " ".join(BUILDS))
        print("tests:   ", " ".join(TESTS))
        for name, settings in PROFILES.items():
            print(f"profile {name:9} {' '.join(f'{k}={v}' for k, v in settings.items())}")
        return 0

    builds = pick(args.builds, BUILDS, "build")
    tests = pick(args.tests, TESTS, "test")
    profiles = pick(args.profiles, PROFILES, "profile")
    logdir = YAFLLIB / "build" / "soak-logs" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    binaries = {}
    for b in builds:
        print(f"building {b} ...", flush=True)
        binaries[b] = build(b, tests, args.jobs)

    combos = [Combo(b, t, p) for b in builds for t in tests for p in profiles
              if p in ONLY_PROFILES.get(t, PROFILES)]
    if args.minutes is None:
        total = len(combos) * args.runs
        print(f"{len(combos)} combinations x {args.runs} runs = {total} runs, {args.jobs} at a time; "
              f"failure logs -> {logdir}", flush=True)
    else:
        total = None
        print(f"{len(combos)} combinations, rounds for {args.minutes:g} min, {args.jobs} at a time; "
              f"failure logs -> {logdir}", flush=True)

    tallies, done, seconds = soak(combos, binaries, args, logdir, total)
    failed = report(tallies, done, seconds, logdir)
    if args.summary is not None:
        write_summary(args.summary, f"gc-soak ({', '.join(builds)})", tallies, failed, done, seconds)
    return min(len(failed), 255)


if __name__ == "__main__":
    sys.exit(main())

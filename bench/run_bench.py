#!/usr/bin/env python3
"""Interleaved A/B benchmark runner for memo_bench.

Runs every (binary, mode) pair round-robin — A/B/A/B rather than all of A then
all of B — so drift in machine load lands on both sides equally. The box is
shared and wall time varies about twofold across a day, so only the paired
comparison is meaningful; absolute numbers are recorded but not to be trusted
across sessions.

    ./run_bench.py --reps 3 base=./memo_bench_base pin=./memo_bench_pin

Reports the MEDIAN of the repetitions per (binary, mode), plus peak RSS, and
verifies that every binary produced the same checksum for a given mode — a
differing checksum means the two builds are not doing the same work and the
times are meaningless.
"""
from __future__ import annotations

import argparse
import re
import resource
import statistics
import subprocess
import sys
import time

MODES = ["hit", "insert", "churn", "par", "parins"]


def run_once(binary: str, mode: str) -> tuple[float, int, str]:
    """One run: returns (wall seconds, peak RSS KB, checksum line)."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    t0 = time.monotonic()
    r = subprocess.run([binary, mode], capture_output=True, text=True, timeout=600)
    wall = time.monotonic() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if r.returncode != 0:
        raise SystemExit(f"{binary} {mode} exited {r.returncode}: {r.stderr[:400]}")
    m = re.search(r"checksum (-?\d+)", r.stdout)
    if not m:
        raise SystemExit(f"{binary} {mode} printed no checksum: {r.stdout[:200]}")
    # ru_maxrss over children is a high-water mark, so it only rises; the
    # delta is zero unless this run set a new peak. Report the run's own peak
    # by reading it directly from a fresh child instead when it matters.
    return wall, max(after - before, 0), m.group(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--modes", default=",".join(MODES))
    ap.add_argument("pairs", nargs="+", help="label=path")
    args = ap.parse_args()

    binaries = []
    for pair in args.pairs:
        label, _, path = pair.partition("=")
        if not path:
            raise SystemExit(f"expected label=path, got {pair!r}")
        binaries.append((label, path))
    modes = [m for m in args.modes.split(",") if m]

    times: dict[tuple[str, str], list[float]] = {}
    sums: dict[tuple[str, str], str] = {}

    for rep in range(args.reps):
        for mode in modes:
            for label, path in binaries:
                wall, _rss, checksum = run_once(path, mode)
                times.setdefault((label, mode), []).append(wall)
                prev = sums.setdefault((label, mode), checksum)
                if prev != checksum:
                    raise SystemExit(
                        f"{label} {mode}: checksum changed between reps "
                        f"({prev} vs {checksum}) — workload is not deterministic")
                print(f"  rep{rep + 1} {mode:<7} {label:<6} {wall:7.2f}s",
                      file=sys.stderr, flush=True)

    # Checksums must agree ACROSS binaries: different answers, different work.
    for mode in modes:
        distinct = {sums[(label, mode)] for label, _ in binaries}
        if len(distinct) > 1:
            print(f"MISMATCH {mode}: " +
                  ", ".join(f"{label}={sums[(label, mode)]}" for label, _ in binaries))
            return 1

    base_label = binaries[0][0]
    head = f"{'mode':<8} " + " ".join(f"{label:>10}" for label, _ in binaries)
    if len(binaries) > 1:
        head += "   delta"
    print()
    print(head)
    print("-" * len(head))
    for mode in modes:
        row = f"{mode:<8} "
        medians = []
        for label, _ in binaries:
            med = statistics.median(times[(label, mode)])
            medians.append(med)
            row += f" {med:9.2f}s"
        if len(medians) > 1 and medians[0] > 0:
            delta = (medians[-1] - medians[0]) / medians[0] * 100.0
            row += f"   {delta:+6.1f}%"
        print(row)
    print()
    print(f"median of {args.reps} interleaved repetitions; "
          f"baseline = {base_label}; checksums agree across builds")
    return 0


if __name__ == "__main__":
    sys.exit(main())

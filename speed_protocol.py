#!/usr/bin/env python3
"""YAFL speed protocol: the SEPARATE, post-suite measurement step.

Correctness is full_protocol.py's job; this only times. Run it after a green
full protocol (it needs that run's build: the runtime archive and the staged
System library).

Runs, in order:
  1. o3_bootstrap — build the PORT through the -O3 pipeline (build/ybootstrap_O3)
  2. o3_timed     — best-of-three -O1 self-compile with /usr/bin/time: wall +
                    peak RSS per leg, two runs per leg, byte-identical across
                    all six runs

Stages are sequential BY DESIGN: two bootstrap builds at once OOM this VM, and
the timed legs want the machine to themselves.

    python3 speed_protocol.py
    python3 speed_protocol.py --only o3_timed      # re-time an existing build
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from full_protocol import (BUILD, COMPILER, Result, parse_rusage, run_stages,
                           run_stream, stage_env)


def parse_leg(log_path: Path) -> dict | None:
    """Per-leg self-compile numbers: run1/run2 seconds + C bytes emitted."""
    if not log_path.is_file():
        return None
    out: dict = {"runs": []}
    for line in log_path.read_text().splitlines():
        m = re.match(r"\s+run (\d): ([0-9,]+) bytes of C in (\d+)s", line)
        if m:
            out["runs"].append((int(m.group(1)),
                                int(m.group(2).replace(",", "")),
                                int(m.group(3))))
        if "identical output on all" in line:
            out["identical"] = True
    return out



def stage_o3_bootstrap(run_dir: Path) -> Result:
    cmd = [sys.executable, "build_bootstrap.py", "-O", "3",
           "-o", str(BUILD / "ybootstrap_O3")]
    env = stage_env(YAFL_LIBYAFL_A=str(BUILD / "yafllib" / "libyafl.a"),
                    PYTHONHASHSEED="0")
    rc = run_stream(cmd, COMPILER, run_dir / "o3_bootstrap.log", env=env)
    return Result("o3 bootstrap build", rc == 0,
                  "build/ybootstrap_O3" if rc == 0 else "see log")



# ── timed O3 self-compile ────────────────────────────────────────────────────

def stage_o3_timed(run_dir: Path) -> Result:
    if not shutil.which("/usr/bin/time"):
        return Result("o3 timed self-compile", False, "/usr/bin/time missing")
    binary = BUILD / "ybootstrap_O3"
    if not binary.is_file():
        return Result("o3 timed self-compile", False,
                      "build/ybootstrap_O3 missing — run the o3_bootstrap stage first")
    if not (BUILD / "stage" / "system.yl").is_file():
        return Result("o3 timed self-compile", False,
                      "build/stage/system.yl missing — run full_protocol.py first")

    legs: list[dict] = []
    for i in range(1, 4):
        rusage = run_dir / f"leg{i}.rusage"
        selflog = run_dir / f"leg{i}.log"
        print(f"      leg {i}")
        rc = run_stream(
            ["/usr/bin/time", "-v", "-o", str(rusage),
             sys.executable, "selfcompile.py", "--binary", str(binary),
             "-L", str(BUILD / "stage"), "--runs", "2"],
            COMPILER, selflog)
        if rc != 0:
            return Result("o3 timed self-compile", False, f"leg {i} exited {rc}")
        legs.append({"rusage": rusage, "log": selflog})

    c_bytes: list[int] = []
    rows = []
    for i, leg in enumerate(legs, 1):
        lg = parse_leg(leg["log"])
        rs = parse_rusage(leg["rusage"])
        runs = lg["runs"] if lg else []
        c_bytes += [b for _, b, _ in runs]
        rows.append({
            "leg": i,
            "wall_s": rs["wall_s"] if rs else None,
            "rss_kb": rs["rss_kb"] if rs else None,
            "user_s": rs["user_s"] if rs else None,
            "runs_s": [t for _, _, t in runs],
        })
        print(f"      leg {i}: "
              + (f"runs {rows[-1]['runs_s']}s  leg wall {rs['wall_s']:.1f}s  rss {rs['rss_kb']:,} KB"
                 if rs else "no /usr/bin/time output"))

    if not rows or any(r["wall_s"] is None for r in rows):
        return Result("o3 timed self-compile", False, "could not parse legs")
    if not c_bytes or len(set(c_bytes)) != 1:
        return Result("o3 timed self-compile", False,
                      "runs emitted differing C sizes — nondeterministic")
    best_run = min((t for r in rows for t in r["runs_s"]), default=0)
    best_wall = min(rows, key=lambda r: r["wall_s"])
    best_rss = min(rows, key=lambda r: r["rss_kb"])
    detail = (
        f"best single self-compile {best_run}s; "
        f"best leg wall {best_wall['wall_s']:.1f}s (leg {best_wall['leg']}, = 2 runs); "
        f"peak RSS {best_rss['rss_kb']:,} KB (leg {best_rss['leg']}); "
        f"6 runs byte-identical ({c_bytes[0]:,} B C)")
    result = Result("o3 timed self-compile", True, detail)

    report = (run_dir / "timed_report.txt").open("w")
    report.write("O3 self-compile best-of-three (build/ybootstrap_O3, -O1, 6G)\n")
    for r in rows:
        report.write(f"  leg {r['leg']}: runs {r['runs_s']}s  leg wall {r['wall_s']:.1f}s  "
                     f"rss {r['rss_kb']:,} KB  user {r['user_s']:.1f}s\n")
    report.write(f"  -> {detail}\n")
    report.close()
    return result


STAGES = {
    "o3_bootstrap": stage_o3_bootstrap,
    "o3_timed": stage_o3_timed,
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="",
                    help="comma-separated subset of stages to run: " + ",".join(STAGES))
    ap.add_argument("--keep-going", action="store_true",
                    help="run every stage even after a failure; exit reports them all")
    args = ap.parse_args(argv)
    return run_stages("speed protocol", STAGES, args.only, args.keep_going,
                      lambda stage, run_dir: stage(run_dir))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

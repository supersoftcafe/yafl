#!/usr/bin/env python3
"""YAFL full test protocol: one command, every stage, a per-stage report.

Runs, in order:
  1. build      — the whole toolchain (yafllib, PyInstaller `yafl`, system.yl)
  2. ctest      — the CTest gate: yafllib C tests, bootstrap fixture, the full
                  Python compiler suite (byte-parity -O0..-O3), stdlib YAFL
                  tests, and the c1 self-compile gate
  3. o3_bootstrap — build the PORT through the -O3 pipeline (build/ybootstrap_O3)
  4. examples   — compile every examples/*.yafl with the FRESH compiler at
                  -O2, then run each with its fixture input
  5. o3_timed   — best-of-three c1 self-compile with /usr/bin/time: wall +
                  peak RSS per leg, byte-identical across all six runs

Stops at the first failing stage unless --keep-going is given. Every stage's
output is streamed to the terminal AND tee'd to build/protocol-runs/<ts>/; a
one-line-per-stage report is printed at the end (and written to report.txt).

Stages are sequential BY DESIGN: two bootstrap builds at once OOM this VM, and
the timed legs want the machine to themselves.

    python3 full_protocol.py               # the whole thing (~2.5h)
    python3 full_protocol.py --keep-going  # run every stage, fail at the end
    python3 full_protocol.py --only examples,o3_timed
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPILER = HERE / "compiler"
EXAMPLES = HERE / "examples"
BUILD = HERE / "build"
RUNS_DIR = BUILD / "protocol-runs"


# ── helpers ──────────────────────────────────────────────────────────────────

def run_stream(cmd: list[str], cwd: Path, log_path: Path, env=None) -> int:
    """Run `cmd`, streaming output to the terminal and `log_path`. Returns rc."""
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, stdin=subprocess.DEVNULL)
    with log_path.open("w") as out:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            out.write(line)
    proc.wait()
    return proc.returncode


def parse_ctest_summary(log_path: Path) -> tuple[int, int] | None:
    """(failed, total) from a ctest run; None if the summary line never printed."""
    for line in log_path.read_text().splitlines():
        m = re.match(r"(\d+)% tests passed, (\d+) tests failed out of (\d+)", line)
        if m:
            return int(m.group(2)), int(m.group(3))
    return None


def _hms_to_seconds(text: str) -> float:
    parts = text.strip().split(":")
    return sum(float(x) * 60 ** i for i, x in enumerate(reversed(parts)))


def parse_rusage(path: Path) -> dict | None:
    """Peak RSS (KB), wall (s), user CPU (s) from a /usr/bin/time -v file."""
    if not path.is_file():
        return None
    out: dict = {}
    for line in path.read_text().splitlines():
        line = line.lstrip()
        m = re.match(r"Maximum resident set size \(kbytes\): (\d+)", line)
        if m:
            out["rss_kb"] = int(m.group(1))
        m = re.match(r"User time \(seconds\): ([0-9.]+)", line)
        if m:
            out["user_s"] = float(m.group(1))
        mm = re.match(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (.+)", line)
        if mm:
            out["wall_s"] = _hms_to_seconds(mm.group(1))
    return out if out else None


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
        if "identical output on both runs" in line:
            out["identical"] = True
        if "bytes of source" in line:
            m2 = re.search(r"([0-9,]+) bytes of source", line)
            if m2:
                out["source_bytes"] = int(m2.group(1).replace(",", ""))
    return out


def stage_env(**extra) -> dict:
    env = dict(os.environ)
    env.update(extra)
    return env


# ── stages ───────────────────────────────────────────────────────────────────

@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


def stage_build(run_dir: Path) -> Result:
    if not (BUILD / "CMakeCache.txt").is_file():
        rc = run_stream(["cmake", "-B", str(BUILD)], HERE, run_dir / "build.log")
        if rc != 0:
            return Result("build", False, "cmake configure failed")
    jobs = os.cpu_count() or 4
    rc = run_stream(["cmake", "--build", str(BUILD), f"-j{jobs}"],
                    HERE, run_dir / "build.log")
    return Result("build", rc == 0, "cmake --build")


def stage_ctest(run_dir: Path) -> Result:
    rc = run_stream(["ctest", "--test-dir", str(BUILD), "--output-on-failure"],
                    HERE, run_dir / "ctest.log")
    total = parse_ctest_summary(run_dir / "ctest.log")
    if total is None:
        return Result("ctest gate", False, "ctest printed no summary line")
    failed, n = total
    return Result("ctest gate", rc == 0 and failed == 0 and n > 0,
                  f"{n - failed}/{n} tests passed")


def stage_o3_bootstrap(run_dir: Path) -> Result:
    cmd = ["python3", "build_bootstrap.py", "-O", "3",
           "-o", str(BUILD / "ybootstrap_O3")]
    env = stage_env(YAFL_LIBYAFL_A=str(BUILD / "yafllib" / "libyafl.a"),
                    PYTHONHASHSEED="0")
    rc = run_stream(cmd, COMPILER, run_dir / "o3_bootstrap.log", env=env)
    return Result("o3 bootstrap build", rc == 0,
                  "build/ybootstrap_O3" if rc == 0 else "see log")


# ── examples ─────────────────────────────────────────────────────────────────

@dataclass
class Example:
    name: str
    stdin: str | None = None
    args: list[str] | None = None
    rc: int = 0


def _build_example_specs(run_dir: Path) -> list[Example]:
    ctx = run_dir / "fixtures"
    dict_path = ctx / "dict.txt"
    text_path = ctx / "text.txt"
    findroot = ctx / "tree"
    (findroot / "sub").mkdir(parents=True, exist_ok=True)
    dict_path.write_text("hello\nworld\nfoo\nbar\nspelling\n")
    text_path.write_text("hello world\nfoo bar\n")
    (findroot / "a.txt").write_text("hello from root\n")
    (findroot / "sub" / "b.txt").write_text("world\nhello nested\n")
    return [
        Example("helloWorld"),
        Example("closure_field_union"),
        Example("hashed_tree"),
        Example("seq_pin"),
        Example("json_pretty", stdin='{"name": "yafl", "v": [1, 2, 3]}'),
        Example("linenumbers", stdin="a\nb\nc\n"),
        Example("findstr", args=["hello", str(findroot)]),
        Example("raytracer", stdin=(EXAMPLES / "scenes" / "spheres.scene").read_text()),
        Example("yaflc", stdin="fun main() => 6 * 7"),
        Example("ylisp", stdin="(print (+ 2 3))"),
        Example("yspell", args=["-d", str(dict_path), str(text_path)]),
    ]


def stage_examples(run_dir: Path) -> Result:
    compiler = COMPILER / "dist" / "yafl"
    if not compiler.is_file():
        return Result("examples", False,
                      f"{compiler} missing — run the build stage first")
    outdir = run_dir / "examples-bin"
    outdir.mkdir(parents=True, exist_ok=True)
    env = stage_env(YAFL_PATH=str(BUILD / "stage"))

    specs = _build_example_specs(run_dir)
    failed: list[str] = []
    log = (run_dir / "examples.log").open("w")
    for i, ex in enumerate(specs, 1):
        src = EXAMPLES / f"{ex.name}.yafl"
        if not src.is_file():
            failed.append(f"{ex.name}: no source")
            continue
        line = f"===== [{i}/{len(specs)}] {ex.name} ====="
        print(line)
        log.write(line + "\n")
        r = subprocess.run([str(compiler), "-O2", "-o", str(outdir / ex.name),
                            str(src)],
                           capture_output=True, text=True, env=env,
                           timeout=1800, stdin=subprocess.DEVNULL)
        log.write(r.stdout)
        log.write(r.stderr)
        if r.returncode != 0:
            failed.append(f"{ex.name}: compile failed")
            continue
        cmd = [str(outdir / ex.name)] + (ex.args or [])
        run = subprocess.run(cmd, input=ex.stdin or "", capture_output=True,
                             text=True, timeout=600)
        log.write(run.stdout)
        log.write(run.stderr)
        ok = run.returncode == ex.rc
        print(f"       -> rc={run.returncode} {'PASS' if ok else 'FAIL'}")
        if not ok:
            failed.append(f"{ex.name}: run rc={run.returncode}, expected {ex.rc}")
    log.close()
    detail = f"{len(specs) - len(failed)}/{len(specs)} examples passed"
    if failed:
        detail += "; failed: " + ", ".join(failed)
    return Result("examples", not failed, detail)


# ── timed O3 self-compile ────────────────────────────────────────────────────

def stage_o3_timed(run_dir: Path) -> Result:
    if not shutil.which("/usr/bin/time"):
        return Result("o3 timed self-compile", False, "/usr/bin/time missing")
    binary = BUILD / "ybootstrap_O3"
    if not binary.is_file():
        return Result("o3 timed self-compile", False,
                      "build/ybootstrap_O3 missing — run the o3_bootstrap stage first")

    legs: list[dict] = []
    for i in range(1, 4):
        rusage = run_dir / f"leg{i}.rusage"
        selflog = run_dir / f"leg{i}.log"
        print(f"      leg {i}")
        rc = run_stream(
            ["/usr/bin/time", "-v", "-o", str(rusage),
             "python3", "selfcompile.py", "--binary", str(binary), "--mode", "c1"],
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
    report.write("O3 self-compile best-of-three (build/ybootstrap_O3, mode c1, 6G)\n")
    for r in rows:
        report.write(f"  leg {r['leg']}: runs {r['runs_s']}s  leg wall {r['wall_s']:.1f}s  "
                     f"rss {r['rss_kb']:,} KB  user {r['user_s']:.1f}s\n")
    report.write(f"  -> {detail}\n")
    report.close()
    return result


# ── driver ───────────────────────────────────────────────────────────────────

STAGES = {
    "build": stage_build,
    "ctest": stage_ctest,
    "o3_bootstrap": stage_o3_bootstrap,
    "examples": stage_examples,
    "o3_timed": stage_o3_timed,
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="",
                    help="comma-separated subset of stages to run: "
                         "build,ctest,o3_bootstrap,examples,o3_timed")
    ap.add_argument("--keep-going", action="store_true",
                    help="run every stage even after a failure; exit reports them all")
    args = ap.parse_args(argv)

    wanted = STAGES.keys() if not args.only else [s.strip() for s in args.only.split(",")]
    unknown = [s for s in wanted if s not in STAGES]
    if unknown:
        print(f"unknown stage(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"YAFL full protocol — {ts}")
    results: list[Result] = []
    wanted = list(wanted)
    for i, name in enumerate(wanted, 1):
        print(f"\n--- [{i}/{len(wanted)}] {name} ---")
        res = STAGES[name](run_dir)
        results.append(res)
        print(f"    {'DONE' if res.ok else 'FAILED'}: {res.detail}")
        if not res.ok and not args.keep_going:
            break

    print("\n" + "=" * 60)
    failures = [r for r in results if not r.ok]
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] {r.name:<22} {r.detail}")
    report = (run_dir / "report.txt").open("w")
    report.write(f"YAFL full protocol — {ts}\n")
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        report.write(f"  [{mark}] {r.name}: {r.detail}\n")
    report.write(f"logs: {run_dir}\n")
    report.close()

    if not failures:
        print("\nALL STAGES PASSED")
        print(f"logs: {run_dir}")
        return 0
    print(f"\n{len(failures)} STAGE(S) FAILED: " +
          ", ".join(r.name for r in failures))
    print(f"logs: {run_dir}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
#!/usr/bin/env python3
"""YAFL full test protocol: CORRECTNESS, one command, a per-stage report.

Runs, in order:
  1. build      — the whole toolchain (yafllib, PyInstaller `yafl`, system.yl,
                  System::Test staged beside it)
  2. ctest      — the CTest gate: yafllib C tests; the Python compiler builds
                  the port; the compiler suite; the YAFL `[test]` folders; and
                  LAST, one self-compile that must reproduce Python's C for the
                  port byte for byte
  3. examples   — compile every examples/*.yafl at -O2 with the compiler under
                  test, then run each with its fixture input

`--compiler port|python` picks the COMPILER UNDER TEST (default port): the two
have parity, so either is a drop-in replacement, and every behaviour test and
example runs against the one chosen.

Speed is not measured here: speed_protocol.py is the separate post-suite step.

Stops at the first failing stage unless --keep-going is given. Every stage's
output is streamed to the terminal AND tee'd to build/protocol-runs/<ts>/; a
one-line-per-stage report is printed at the end (and written to report.txt).

    python3 full_protocol.py                    # the whole thing
    python3 full_protocol.py --compiler python  # same, against the Python compiler
    python3 full_protocol.py --keep-going       # run every stage, fail at the end
    python3 full_protocol.py --only ctest,examples
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
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


def _configure(compiler: str, log: Path) -> int:
    """(Re)configure with the compiler under test — cheap when nothing changed."""
    return run_stream(["cmake", "-B", str(BUILD), f"-DYAFL_TEST_COMPILER={compiler}"],
                      HERE, log)


def stage_build(run_dir: Path, compiler: str) -> Result:
    if _configure(compiler, run_dir / "configure.log") != 0:
        return Result("build", False, "cmake configure failed")
    jobs = os.cpu_count() or 4
    rc = run_stream(["cmake", "--build", str(BUILD), f"-j{jobs}"],
                    HERE, run_dir / "build.log")
    return Result("build", rc == 0, "cmake --build")


def stage_ctest(run_dir: Path, compiler: str) -> Result:
    if _configure(compiler, run_dir / "configure.log") != 0:
        return Result("ctest gate", False, "cmake configure failed")
    rc = run_stream(["ctest", "--test-dir", str(BUILD), "--output-on-failure"],
                    HERE, run_dir / "ctest.log")
    total = parse_ctest_summary(run_dir / "ctest.log")
    if total is None:
        return Result("ctest gate", False, "ctest printed no summary line")
    failed, n = total
    return Result("ctest gate", rc == 0 and failed == 0 and n > 0,
                  f"{n - failed}/{n} tests passed ({compiler} compiler)")


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
        Example("hashed_tree"),
        Example("json_pretty", stdin='{"name": "yafl", "v": [1, 2, 3]}'),
        Example("linenumbers", stdin="a\nb\nc\n"),
        Example("findstr", args=["hello", str(findroot)]),
        Example("raytracer", stdin=(EXAMPLES / "scenes" / "spheres.scene").read_text()),
        Example("yaflc", stdin="fun main() => 6 * 7"),
        Example("ylisp", stdin="(print (+ 2 3))"),
        Example("yspell", args=["-d", str(dict_path), str(text_path)]),
    ]


def _example_compiler(compiler: str) -> Path:
    """The INSTALLABLE compiler of each kind: the port binary, or the
    PyInstaller `yafl` — each finds System on YAFL_PATH as an install would."""
    return BUILD / "ybootstrap" if compiler == "port" else COMPILER / "dist" / "yafl"


def stage_examples(run_dir: Path, compiler: str) -> Result:
    compiler_bin = _example_compiler(compiler)
    if not compiler_bin.is_file():
        return Result("examples", False,
                      f"{compiler_bin} missing — run the build and ctest stages first")
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
        r = subprocess.run([str(compiler_bin), "-O2", "-o", str(outdir / ex.name),
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
    detail = f"{len(specs) - len(failed)}/{len(specs)} examples passed ({compiler} compiler)"
    if failed:
        detail += "; failed: " + ", ".join(failed)
    return Result("examples", not failed, detail)


# ── driver ───────────────────────────────────────────────────────────────────

STAGES = {
    "build": stage_build,
    "ctest": stage_ctest,
    "examples": stage_examples,
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", default="port", choices=["port", "python"],
                    help="the compiler under test (default: port)")
    ap.add_argument("--only", default="",
                    help="comma-separated subset of stages to run: " + ",".join(STAGES))
    ap.add_argument("--keep-going", action="store_true",
                    help="run every stage even after a failure; exit reports them all")
    args = ap.parse_args(argv)
    return run_stages("full protocol", STAGES, args.only, args.keep_going,
                      lambda stage, run_dir: stage(run_dir, args.compiler))


def run_stages(title: str, stages: dict, only: str, keep_going: bool, call) -> int:
    """Run `stages` (or the `only` subset) in order with `call(stage, run_dir)`,
    stopping at the first failure unless `keep_going`; print and file a report."""
    wanted = stages.keys() if not only else [s.strip() for s in only.split(",")]
    unknown = [s for s in wanted if s not in stages]
    if unknown:
        print(f"unknown stage(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"YAFL {title} — {ts}")
    results: list[Result] = []
    wanted = list(wanted)
    for i, name in enumerate(wanted, 1):
        print(f"\n--- [{i}/{len(wanted)}] {name} ---")
        res = call(stages[name], run_dir)
        results.append(res)
        print(f"    {'DONE' if res.ok else 'FAILED'}: {res.detail}")
        if not res.ok and not keep_going:
            break

    print("\n" + "=" * 60)
    failures = [r for r in results if not r.ok]
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] {r.name:<22} {r.detail}")
    report = (run_dir / "report.txt").open("w")
    report.write(f"YAFL {title} — {ts}\n")
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
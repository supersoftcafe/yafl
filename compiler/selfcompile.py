"""Self-compile: the port compiles its own sources, through its command line.

This is the hardest input the compiler has — itself — and it exercises paths
nothing else reaches: codegen over the compiler's own sources, GC and runtime
behaviour under a compiler-sized workload, and any residual nondeterminism.

    ybootstrap -O1 -L <libs> -c <out.c> bootstrap/

exactly as a user compiles a project: `bootstrap/` is a project directory, its
units named by their paths relative to it (`driver/main.yafl`) — the names
build_bootstrap.py gives them — and the stdlib comes from the System library
on the search path.

    python selfcompile.py -L build/stage --expect build/ybootstrap.c   # the gate
    python selfcompile.py -L build/stage --runs 2                       # timing

`--expect` is the correctness gate run LAST by ctest: the port must emit, byte
for byte, the C the Python compiler emitted when it built the port. `--runs N`
repeats the compile and requires every run to agree — the check for
nondeterminism the speed protocol times.

Exits non-zero if the port fails, emits nothing, disagrees with itself, or
disagrees with `--expect`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
_BOOT_DIR = _REPO / "bootstrap"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path,
                    default=Path(os.environ.get("YAFL_BOOTSTRAP_BIN",
                                                _REPO / "build" / "ybootstrap")))
    ap.add_argument("-L", "--lib-path", dest="lib_path", required=True, metavar="DIR",
                    help="library search path holding the System library")
    ap.add_argument("-O", dest="level", default="1", choices=["0", "1", "2", "3"],
                    help="optimisation level (default 1, as build_bootstrap.py)")
    ap.add_argument("--runs", type=int, default=1,
                    help="compile this many times; every run must agree")
    ap.add_argument("--expect", type=Path,
                    help="C the output must equal byte for byte")
    ap.add_argument("--heap", default="6G", help="YAFL_HEAP_SIZE (default 6G)")
    args = ap.parse_args(argv)

    if not args.binary.is_file():
        print(f"self-compile: no binary at {args.binary} — build it first "
              f"(python build_bootstrap.py)", file=sys.stderr)
        return 2
    expected = args.expect.read_text() if args.expect else None

    env = dict(os.environ, YAFL_HEAP_SIZE=args.heap)
    env.pop("YAFL_PATH", None)
    print(f"self-compile: {args.binary} -O{args.level}, heap {args.heap}, "
          f"{args.runs} run(s)")

    def run_once(label: str, out: Path) -> str:
        t = time.time()
        r = subprocess.run([str(args.binary), f"-O{args.level}", "-L", args.lib_path,
                            "-c", str(out), str(_BOOT_DIR)],
                           text=True, capture_output=True, env=env, timeout=4 * 3600)
        el = time.time() - t
        if r.returncode != 0:
            print(f"self-compile: port exited {r.returncode} after {el:.0f}s\n"
                  f"{r.stdout[-4000:]}{r.stderr[-4000:]}", file=sys.stderr)
            raise SystemExit(1)
        c_text = out.read_text() if out.is_file() else ""
        if not c_text:
            print(f"self-compile: port produced no output after {el:.0f}s",
                  file=sys.stderr)
            raise SystemExit(1)
        print(f"  {label}: {len(c_text):,} bytes of C in {el:.0f}s")
        return c_text

    with tempfile.TemporaryDirectory() as td:
        first = run_once("run 1", Path(td) / "run1.c")
        for i in range(2, args.runs + 1):
            if run_once(f"run {i}", Path(td) / f"run{i}.c") != first:
                print(f"self-compile: RUN {i} DISAGREES WITH RUN 1 — the compiler "
                      f"is nondeterministic on its own sources", file=sys.stderr)
                return 1
        if args.runs > 1:
            print(f"  identical output on all {args.runs} runs")

    if expected is not None:
        if first != expected:
            line = next((i for i, (a, b) in enumerate(zip(first.splitlines(),
                                                          expected.splitlines()), 1)
                         if a != b), None)
            print(f"self-compile: the port's C DIFFERS from {args.expect} "
                  f"({len(first):,} vs {len(expected):,} bytes; first difference at "
                  f"line {line})", file=sys.stderr)
            return 1
        print(f"  byte-identical to {args.expect}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

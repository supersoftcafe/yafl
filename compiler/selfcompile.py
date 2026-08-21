"""Self-compile gate: the port compiles the whole program (stdlib + bootstrap).

This is the hardest input the compiler has — itself — and it exercises paths
nothing else reaches: codegen over the compiler's own sources, GC and runtime
behaviour under a compiler-sized workload, and any residual nondeterminism.

Run AFTER the test suite: the suite says the compiler is correct on small
programs, this says it survives the real one. A failure here with a green suite
means the problem only shows up at scale.

    python selfcompile.py                      # uses build/ybootstrap
    python selfcompile.py --binary /tmp/other
    python selfcompile.py --mode c3            # -O3 pipeline

Exits non-zero if the port fails, emits nothing, or emits a different result on
a second run (that last check is cheap relative to the compile and is the only
thing that catches nondeterminism).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent


def _stream() -> str:
    """The #FILE#-marked whole-program stream: stdlib, then the bootstrap.

    Each part must END WITH A NEWLINE or the next `#FILE#` marker glues onto
    the previous file's last line and the port misattributes it.
    """
    def part(p: Path) -> str:
        t = p.read_text()
        return f"#FILE# {p.name}\n{t if t.endswith(chr(10)) else t + chr(10)}"
    parts = [part(p) for p in sorted((_HERE / "stdlib").glob("*.yafl"))]
    parts += [part(p) for p in sorted((_REPO / "bootstrap").rglob("*.yafl"))]
    return "".join(parts)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path,
                    default=Path(os.environ.get("YAFL_BOOTSTRAP_BIN",
                                                _REPO / "build" / "ybootstrap")))
    ap.add_argument("--mode", default="c1",
                    help="port mode: c, c1, c2, c3 (default c1)")
    ap.add_argument("--heap", default="6G", help="YAFL_HEAP_SIZE (default 6G)")
    ap.add_argument("--skip-determinism", action="store_true",
                    help="skip the second run (halves the time, loses the "
                         "only check for nondeterminism)")
    args = ap.parse_args(argv)

    if not args.binary.is_file():
        print(f"self-compile: no binary at {args.binary} — build it first "
              f"(python build_bootstrap.py)", file=sys.stderr)
        return 2

    text = _stream()
    print(f"self-compile: {len(text):,} bytes of source, mode {args.mode}, "
          f"heap {args.heap}")
    env = dict(os.environ, YAFL_HEAP_SIZE=args.heap)

    def run_once(label: str) -> str:
        t = time.time()
        r = subprocess.run([str(args.binary), args.mode], input=text, text=True,
                           capture_output=True, env=env, timeout=4 * 3600)
        el = time.time() - t
        if r.returncode != 0:
            print(f"self-compile: port exited {r.returncode} after {el:.0f}s\n"
                  f"{r.stderr[-4000:]}", file=sys.stderr)
            raise SystemExit(1)
        if not r.stdout:
            print(f"self-compile: port produced no output after {el:.0f}s",
                  file=sys.stderr)
            raise SystemExit(1)
        print(f"  {label}: {len(r.stdout):,} bytes of C in {el:.0f}s")
        return r.stdout

    first = run_once("run 1")
    if not args.skip_determinism:
        if run_once("run 2") != first:
            print("self-compile: THE TWO RUNS DISAGREE — the compiler is "
                  "nondeterministic on its own sources", file=sys.stderr)
            return 1
        print("  identical output on both runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Build the bootstrap (port) compiler binary.

`bootstrap/**/*.yafl` is the YAFL compiler written in YAFL. Running it means
turning it into an executable: the PYTHON compiler emits ~96 MB of C from those
sources, and clang links that into one binary. That takes about ten minutes.

This is a BUILD step, deliberately separate from the tests. It used to happen
lazily inside `shared_bootstrap_binary()`, the first test to ask for it paying
the cost while every other bootstrap test blocked on an exclusive flock — with
~25 modules wanting it, that serialised the parallel suite behind one build.
Tests consume a built artefact; deciding when to rebuild it is the operator's
call, exactly as it is for the runtime archive.

    python build_bootstrap.py                 # -> build/ybootstrap
    python build_bootstrap.py -o /tmp/mine    # somewhere else

Point the suite at a binary with YAFL_BOOTSTRAP_BIN, which is how you test a
release build or a worktree build without touching test code.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # .../compiler
_REPO = _HERE.parent
_BOOT_DIR = _REPO / "bootstrap"

DEFAULT_BINARY = _REPO / "build" / "ybootstrap"


def build(out: Path, optimization_level: int = 1) -> Path:
    """Compile the port to `out`. Returns the path written."""
    sys.setrecursionlimit(5000)      # see compiler.py — the parser needs ~1.5k
    sys.path.insert(0, str(_HERE))
    import compiler as c
    from tests.testutil import _CLANG_BUILD_FLAGS, static_link_for

    sources = sorted(_BOOT_DIR.rglob("*.yafl"))
    if not sources:
        raise SystemExit(f"no bootstrap sources under {_BOOT_DIR}")
    print(f"compiling {len(sources)} port sources at -O{optimization_level} ...")
    c_code = c.compile([c.Input(p.read_text(), p.name) for p in sources],
                       use_stdlib=True, just_testing=False,
                       optimization_level=optimization_level)
    if not c_code:
        raise SystemExit("bootstrap compilation produced no output (type errors?)")
    print(f"  {len(c_code):,} bytes of C; linking ...")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    # clang -O2, not -O0: this binary is EXECUTED by ~25 test modules, once
    # per corpus file per mode. The emitted C is identical either way — only
    # the binary's own speed differs, and measured on the self-compile that is
    # 1.9x (2031s at -O0 vs 1062s at -O2). Paying it once here is free
    # everywhere else. The runtime archive is already the release one.
    r = subprocess.run(["clang", "-g", "-x", "c", "-", "-O2",
                        *_CLANG_BUILD_FLAGS, *static_link_for(1), "-o", str(tmp)],
                       input=c_code, text=True, capture_output=True, timeout=600)
    if r.returncode != 0:
        raise SystemExit(f"clang failed:\n{r.stderr[:4000]}")
    tmp.replace(out)                 # atomic: readers see whole file or none
    print(f"  wrote {out}")
    return out


def refresh_references() -> int:
    """Drop cached Python reference outputs so the next run regenerates them.

    The reference cache is keyed on its INPUT, not on a hash of the compiler,
    so changing the compiler does not invalidate it — that is deliberate (a
    source hash meant the cache never hit during a fix/test loop). Discarding
    them is therefore an explicit act, like rebuilding the binary.
    """
    import getpass, tempfile
    cache = Path(tempfile.gettempdir()) / f"yafl-bootstrap-cache-{__import__('os').getuid()}"
    n = 0
    for stale in cache.glob("ref-*"):
        stale.unlink(missing_ok=True)
        n += 1
    print(f"cleared {n} cached reference outputs from {cache}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_BINARY,
                    help=f"where to write the binary (default: {DEFAULT_BINARY})")
    ap.add_argument("-O", "--optimization-level", type=int, default=1,
                    help="YAFL optimisation level for the port build (default: 1). "
                         "This selects WHICH COMPILER PIPELINE the port went "
                         "through, so it changes what is under test — unlike "
                         "the clang level it is not a free speed dial.")
    ap.add_argument("--refresh-references", action="store_true",
                    help="clear cached Python reference outputs and exit; the "
                         "reference cache is keyed on its input, not on a hash "
                         "of the compiler, so dropping it is an explicit act")
    args = ap.parse_args(argv)
    if args.refresh_references:
        return refresh_references()
    build(args.output, args.optimization_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

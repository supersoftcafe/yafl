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

    python build_bootstrap.py --reuse -L build/stage     # the fast test path

Every build by the Python compiler is cached beside the output
(`bootstrap-cache/`): the binary and the C it was linked from, keyed on the
Python compiler's sources. `--reuse` skips the Python build while that key
still matches. If the port's sources (or the stdlib) changed since, the cached
compiler compiles them instead, and that C is what the self-compile must
reproduce: the new port has to emit what the Python-built one did. A change
to the Python compiler always means a Python build; the full test path never
reuses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # .../compiler
_REPO = _HERE.parent
_BOOT_DIR = _REPO / "bootstrap"

DEFAULT_BINARY = _REPO / "build" / "ybootstrap"


def build(out: Path, optimization_level: int = 1, c_output: Path | None = None,
          reuse_lib_path: str | None = None) -> Path:
    """Compile the port to `out`. Returns the path written. With `c_output`,
    the emitted C is kept there too — the reference the self-compile at the
    end of ctest must reproduce byte for byte. With `reuse_lib_path` (the
    System library's directory), the cached Python build stands in for a new
    one when the Python compiler has not changed — see the module docstring."""
    sys.path.insert(0, str(_HERE))
    cache = _Cache(out.parent / "bootstrap-cache")
    keys = {"python": _python_key(optimization_level), "sources": _sources_key(),
            "link": _link_key()}
    held = cache.keys()
    if reuse_lib_path is None or held.get("python") != keys["python"]:
        if reuse_lib_path is not None:
            print("the Python compiler changed since the cached build: building with it")
        c_code = _python_emit(optimization_level)
        _link(c_code, out)
        cache.store(keys, out, c_code)
    elif held.get("sources") == keys["sources"]:
        print("reusing the cached Python build: nothing it was built from has changed")
        c_code = cache.c_path.read_text()
        if held.get("link") == keys["link"]:
            _copy(cache.binary_path, out)
        else:
            print("  the runtime changed: relinking its C")
            _link(c_code, out)
            cache.store(keys, out, c_code)
    else:
        print("the port's sources changed since the cached Python build: "
              "the cached compiler compiles them")
        c_code = _port_emit(cache.binary_path, optimization_level, reuse_lib_path)
        _link(c_code, out)
    if c_output is not None:
        c_output.parent.mkdir(parents=True, exist_ok=True)
        c_output.write_text(c_code)
    print(f"  wrote {out}")
    return out


def _port_sources() -> list[Path]:
    """Named by path relative to bootstrap/ — `driver/main.yafl` — the names a
    compiler gives a project directory's units, so `ybootstrap bootstrap/`
    (selfcompile.py) compiles exactly these units under exactly these names."""
    from libraries import unit_name
    sources = sorted(_BOOT_DIR.rglob("*.yafl"), key=lambda p: unit_name(p, _BOOT_DIR))
    if not sources:
        raise SystemExit(f"no bootstrap sources under {_BOOT_DIR}")
    return sources


def _python_emit(optimization_level: int) -> str:
    """The port's C, from the Python compiler."""
    sys.setrecursionlimit(5000)      # see compiler.py — the parser needs ~1.5k
    import compiler as c
    from libraries import unit_name
    sources = _port_sources()
    print(f"compiling {len(sources)} port sources at -O{optimization_level} ...")
    c_code = c.compile([c.Input(p.read_text(), unit_name(p, _BOOT_DIR))
                        for p in sources],
                       use_stdlib=True, just_testing=False,
                       optimization_level=optimization_level)
    if not c_code:
        raise SystemExit("bootstrap compilation produced no output (type errors?)")
    print(f"  {len(c_code):,} bytes of C")
    return c_code


def _port_emit(binary: Path, optimization_level: int, lib_path: str) -> str:
    """The port's C, from an earlier build of the port."""
    from selfcompile import compile_port
    print(f"compiling the port's sources with {binary} at -O{optimization_level} ...")
    with tempfile.TemporaryDirectory() as td:
        c_file = Path(td) / "port.c"
        r = compile_port(binary, str(optimization_level), lib_path, c_file)
        if r.returncode != 0 or not c_file.is_file():
            raise SystemExit(f"the cached compiler failed ({r.returncode}):\n"
                             f"{r.stdout[-4000:]}{r.stderr[-4000:]}")
        c_code = c_file.read_text()
    print(f"  {len(c_code):,} bytes of C")
    return c_code


def _link_argv() -> list[str]:
    """clang -O2, not -O0: this binary is EXECUTED by ~25 test modules, once
    per corpus file per mode. The emitted C is identical either way — only
    the binary's own speed differs, and measured on the self-compile that is
    1.9x (2031s at -O0 vs 1062s at -O2). Paying it once here is free
    everywhere else. The runtime archive is already the release one."""
    from tests.testutil import _CLANG_BUILD_FLAGS, static_link_for
    return ["clang", "-g", "-x", "c", "-", "-O2", "-DNDEBUG",
            *_CLANG_BUILD_FLAGS, *static_link_for(1)]


def _link(c_code: str, out: Path) -> None:
    print("  linking ...")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    r = subprocess.run([*_link_argv(), "-o", str(tmp)],
                       input=c_code, text=True, capture_output=True, timeout=1800)
    if r.returncode != 0:
        raise SystemExit(f"clang failed:\n{r.stderr[:4000]}")
    tmp.replace(out)                 # atomic: readers see whole file or none


def _copy(src: Path, out: Path) -> None:
    tmp = out.with_suffix(".tmp")
    shutil.copy2(src, tmp)
    tmp.replace(out)


# ── the cache of the Python build ────────────────────────────────────────────
# Three keys, one per thing that can go stale: the Python compiler (decides
# whether the cached build may stand in at all), the port's sources and the
# stdlib (decide whether its C is still the C), and the runtime and link
# command (decide whether its binary is still the binary).

def _digest(paths: list[Path], *extra: str) -> str:
    h = hashlib.sha256()
    for text in extra:
        h.update(text.encode() + b"\0")
    for p in sorted(paths):
        h.update(str(p.relative_to(_REPO) if p.is_relative_to(_REPO) else p).encode() + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


def _python_key(optimization_level: int) -> str:
    """Every Python source of the compiler, tracked or new, but not its tests."""
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard",
                             "--", "*.py", ":!tests/"],
                            cwd=_HERE, capture_output=True, text=True, check=True).stdout
    paths = [_HERE / line for line in listed.splitlines() if (_HERE / line).is_file()]
    return _digest(paths, f"-O{optimization_level}")


def _sources_key() -> str:
    stdlib = [p for p in (_HERE / "stdlib").rglob("*") if p.is_file()]
    return _digest([*_BOOT_DIR.rglob("*.yafl"), *stdlib])


def _link_key() -> str:
    from tests.testutil import libyafl_for
    headers = list((_REPO / "yafllib").rglob("*.h"))
    return _digest([*headers, Path(libyafl_for(1)).resolve()], *_link_argv())


class _Cache:
    def __init__(self, root: Path):
        self.root = root
        self.binary_path = root / "ybootstrap"
        self.c_path = root / "ybootstrap.c"
        self.keys_path = root / "keys.json"

    def keys(self) -> dict:
        try:
            return json.loads(self.keys_path.read_text())
        except (OSError, ValueError):
            return {}

    def store(self, keys: dict, binary: Path, c_code: str) -> None:
        """The keys go last, so a half-written entry is never trusted."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.keys_path.unlink(missing_ok=True)
        _copy(binary, self.binary_path)
        self.c_path.write_text(c_code)
        self.keys_path.write_text(json.dumps(keys))


def refresh_references() -> int:
    """Drop cached Python reference outputs so the next run regenerates them.

    The reference cache is keyed on its INPUT, not on a hash of the compiler,
    so changing the compiler does not invalidate it — that is deliberate (a
    source hash meant the cache never hit during a fix/test loop). Discarding
    them is therefore an explicit act, like rebuilding the binary.
    """
    import getpass
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
    ap.add_argument("--c-output", type=Path,
                    help="also write the emitted C here")
    ap.add_argument("--refresh-references", action="store_true",
                    help="clear cached Python reference outputs and exit; the "
                         "reference cache is keyed on its input, not on a hash "
                         "of the compiler, so dropping it is an explicit act")
    ap.add_argument("--reuse", action="store_true",
                    help="stand the cached Python build in for a new one while "
                         "the Python compiler is unchanged (needs -L)")
    ap.add_argument("-L", "--lib-path", dest="lib_path", metavar="DIR",
                    help="the System library's directory, for --reuse")
    args = ap.parse_args(argv)
    if args.refresh_references:
        return refresh_references()
    if args.reuse and not args.lib_path:
        ap.error("--reuse needs -L, the System library's directory")
    build(args.output, args.optimization_level, args.c_output,
          args.lib_path if args.reuse else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

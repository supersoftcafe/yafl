
import compiler as c
from pathlib import Path
import sys
import subprocess
import argparse
import re

import libraries
import warning_flags


def main():
    parser = argparse.ArgumentParser(description="My compiler-like tool")

    # Mutually exclusive optimisation levels
    parser.add_argument(
        "-O", choices=["0", "1", "2", "3"],
        help="Optimisation level", metavar="LEVEL",
        default="0",
    )

    # Optional -a flag
    parser.add_argument(
        "-a", metavar="OUTFILE",
        help="Assembly output"
    )

    # Optional -c flag
    parser.add_argument(
        "-c", metavar="OUTFILE",
        help="C output"
    )

    # Output file
    parser.add_argument(
        "-o", metavar="OUTFILE",
        help="Output file name"
    )

    # Extra library search paths (highest precedence), repeatable.
    parser.add_argument(
        "-L", "--lib-path", dest="lib_path", action="append", metavar="DIR",
        help="Additional library search path (repeatable)"
    )

    # Whole-program profiling: instrument every function with exact call
    # counters + a shadow stack, and sample CPU time at runtime. Composes with
    # any -O level (the IR inliners are disabled so profiled functions exist).
    parser.add_argument(
        "--profile", action="store_true",
        help="Instrument for profiling; the binary writes callgrind.out.<pid> at exit"
    )

    # Warning categories: -Wname enables, -Wno-name disables, -Wall enables
    # every optional one. Repeatable; applied left to right over the default
    # set (see warning_flags.py for the registry and semantics).
    parser.add_argument(
        "-W", action="append", dest="W", default=[], metavar="WARNING",
        help="Enable/disable a warning: -Wname, -Wall, -Wno-name"
    )

    # Build a TEST binary instead of the program: every [test] function is
    # collected into a registry and a main is synthesised to drive it. The
    # program's own main, if it has one, is ignored rather than an error.
    parser.add_argument(
        "--test", action="store_true",
        help="Build a unit-test binary from the [test] functions"
    )

    # Input: one or more .yafl files, or a project directory (compiled whole).
    parser.add_argument(
        "files", nargs="+",
        help="Input .yafl file(s), or a project directory"
    )

    args = parser.parse_args()

    try:
        enabled_warnings = warning_flags.resolve_enabled_warnings(args.W)
    except ValueError as e:
        parser.error(str(e))

    try:
        files = _gather_inputs(args.files)
    except _Unreadable as e:
        print(f"error: {e}: cannot be read", file=sys.stderr)
        sys.exit(1)
    try:
        c_code, link_spec, warnings = c.compile_project(
            files, use_stdlib=True, just_testing=False,
            optimization_level=int(args.O),
            lib_paths=args.lib_path,
            profile=args.profile,
            test_mode=args.test,
            enabled_warnings=enabled_warnings)
    except libraries.LibraryError as e:
        # Printed where compile_project prints its diagnostics, as the port does.
        print(f"error:{e}")
        sys.exit(1)
    for w in sorted(set(warnings)):
        print(w, file=sys.stderr)

    if not c_code:
        # compile_project printed diagnostics; exit non-zero so build systems see
        # the failure rather than silently using a stale output file.
        sys.exit(1)

    if args.c:
        try:
            with open(args.c, "w", encoding="utf-8") as f:
                f.write(c_code)
        except OSError:
            print(f"error: {args.c}: cannot be written", file=sys.stderr)
            sys.exit(1)

    include_args, link_inputs = _include_args(link_spec), _link_inputs(link_spec)

    # -O0 (the default) is a debug build: full debug info, nothing stripped.
    # Any optimisation level is a release build: no debug info, dead runtime code
    # dropped (--gc-sections, enabled by the runtime's per-function sections) and
    # the binary stripped. function/data-sections on the compile let the user
    # program's own unused code be collected too.
    debug = int(args.O) == 0
    common = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections"]
    common += ["-g"] if debug else []
    common += ["-DNDEBUG"] if int(args.O) >= 2 else []   # -O2+: the asserts go
    release_link = [] if debug else ["-Wl,--gc-sections", "-Wl,-s"]

    if args.a:
        _run_clang(["clang", *common, "-x", "c", "-", f"-O{args.O}", *include_args, "-S", "-o", args.a], c_code)

    if args.o:
        _run_clang(["clang", *common, "-x", "c", "-", f"-O{args.O}", *include_args, *link_inputs,
                    *release_link, "-o", args.o], c_code)


class _Unreadable(Exception):
    """An input that could not be read; the message is its path."""


def _gather_inputs(paths: list[str]) -> list:
    """Read the inputs. A single directory argument is treated as a project: every
    `.yafl` file under it (recursively) is compiled together."""
    if len(paths) == 1 and Path(paths[0]).is_dir():
        root = Path(paths[0])
        return sorted((_read(p, root) for p in root.rglob("*.yafl")),
                      key=lambda i: i.filename)
    # Named files are their own roots: a unit's name is the path as given.
    return [_read(Path(p), Path(p).parent) for p in paths]


def _read(path: Path, root: Path):
    try:
        return c._read_source(path, root)
    except (OSError, UnicodeDecodeError) as e:
        raise _Unreadable(str(path)) from e


def _include_args(link_spec) -> list[str]:
    """clang flags to COMPILE against the loaded libraries: each include dir."""
    return [f"-I{d}" for d in link_spec.include_dirs] if link_spec is not None else []


def _link_inputs(link_spec) -> list[str]:
    """What to LINK: the libraries' static archives and the system libraries the
    runtime needs. Static linking only (per the build design). Never passed with
    -S: under -Werror every unused linker input is an error, which is how `-a`
    failed on every program."""
    args: list[str] = []
    if link_spec is not None and link_spec.static_libs:
        # `-x c -` set the language to C for stdin; reset to "none" so the
        # static archives are treated as libraries, not C source files.
        args += ["-x", "none", *[str(p) for p in link_spec.static_libs]]
    # System libraries the static runtime depends on (threads, math, dl).
    args += ["-lpthread", "-lm", "-ldl"]
    return args


def _run_clang(argv: list[str], c_code: str) -> None:
    result = subprocess.run(argv, input=c_code, text=True, capture_output=True)
    if result.returncode != 0:
        print("Compilation failed:")
        print(result.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


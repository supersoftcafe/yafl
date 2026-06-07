
import compiler as c
from pathlib import Path
import sys
import subprocess
import argparse
import re


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

    # Disable the auto-parallelise tuple lowering (only takes effect at -O>=2)
    parser.add_argument(
        "--no-auto-parallel",
        dest="disable_auto_parallel",
        action="store_true",
        help="Disable auto-parallelisation of tuple constructions"
    )

    # Extra library search paths (highest precedence), repeatable.
    parser.add_argument(
        "-L", "--lib-path", dest="lib_path", action="append", metavar="DIR",
        help="Additional library search path (repeatable)"
    )

    # Input: one or more .yafl files, or a project directory (compiled whole).
    parser.add_argument(
        "files", nargs="+",
        help="Input .yafl file(s), or a project directory"
    )

    args = parser.parse_args()

    files = _gather_inputs(args.files)
    c_code, link_spec = c.compile_project(
        files, use_stdlib=True, just_testing=False,
        optimization_level=int(args.O), disable_auto_parallel=args.disable_auto_parallel,
        lib_paths=args.lib_path)

    if not c_code:
        # compile_project printed diagnostics; exit non-zero so build systems see
        # the failure rather than silently using a stale output file.
        sys.exit(1)

    if args.c:
        with open(args.c, "w", encoding="utf-8") as f:
            f.write(c_code)

    link_args = _link_args(link_spec)

    # -O0 (the default) is a debug build: full debug info, nothing stripped.
    # Any optimisation level is a release build: no debug info, dead runtime code
    # dropped (--gc-sections, enabled by the runtime's per-function sections) and
    # the binary stripped. function/data-sections on the compile let the user
    # program's own unused code be collected too.
    debug = int(args.O) == 0
    common = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections"]
    common += ["-g"] if debug else []
    release_link = [] if debug else ["-Wl,--gc-sections", "-Wl,-s"]

    if args.a:
        _run_clang(["clang", *common, "-x", "c", "-", f"-O{args.O}", *link_args, "-S", "-o", args.a], c_code)

    if args.o:
        _run_clang(["clang", *common, "-x", "c", "-", f"-O{args.O}", *link_args, *release_link, "-o", args.o], c_code)


def _gather_inputs(paths: list[str]) -> list:
    """Read the inputs. A single directory argument is treated as a project: every
    `.yafl` file under it (recursively) is compiled together."""
    if len(paths) == 1 and Path(paths[0]).is_dir():
        root = Path(paths[0])
        return [c._read_source(p) for p in sorted(root.rglob("*.yafl"))]
    return [c._read_source(Path(p)) for p in paths]


def _link_args(link_spec) -> list[str]:
    """clang flags to build against the loaded libraries: each library's include
    dir, its static archives, and the system libraries the runtime needs. Static
    linking only (per the build design)."""
    args: list[str] = []
    if link_spec is not None:
        for d in link_spec.include_dirs:
            args.append(f"-I{d}")
        if link_spec.static_libs:
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


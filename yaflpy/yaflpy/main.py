
import compiler as c
from pathlib import Path
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

    # Input files (positional, 1 or more)
    parser.add_argument(
        "files", nargs="+",
        help="Input file(s)"
    )

    args = parser.parse_args()

    # Example use
    # print(f"Optimisation: -O{args.O}")
    # print(f"C output: {args.c}")
    # print(f"Assembly output: {args.a}")
    # print(f"Output file: {args.o}")
    # print(f"Input files: {args.files}")

    files = [c._read_source(Path(x)) for x in args.files]
    c_code = c.compile(files, use_stdlib=True, just_testing=False)

    if c_code:
        if args.c:
            last_segment = re.split(r'(?m)^#line.*\n', c_code)[-1]
            with open(args.c, "w", encoding="utf-8") as f:
                f.write(f"#include \"yafl.h\"\n\n{last_segment}\n")

        if args.a:
            asm_result = subprocess.run(
                ["clang", "-x", "c", "-", f"-O{args.O}", "-S", "-o", args.a],
                input=c_code, text=True,
                capture_output=True
            )
            if asm_result.returncode != 0:
                print("Compilation failed:")
                print(asm_result.stderr)
                exit(1)

        if args.o:
            bin_result = subprocess.run(
                ["clang", "-x", "c", "-", "-s", f"-O{args.O}", "-o", args.o],
                input=c_code, text=True,
                capture_output=True
            )
            if bin_result.returncode != 0:
                print("Compilation failed:")
                print(bin_result.stderr)
                exit(1)


if __name__ == "__main__":
    main()


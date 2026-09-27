#!/bin/bash
# Build a tree's -O3 bootstrap in three separable steps, so a RUNTIME-only
# change needs only the (seconds-long) relink, not ~20 minutes of codegen:
#   1. generate the port's C          -> build/boot.c   (skipped if present, unless REGEN=1)
#   2. compile it once                -> build/boot.o   (skipped if newer than boot.c)
#   3. link against the tree's runtime -> build/ybootstrap_O3
# Same flags as compiler/build_bootstrap.py (clang -g -O2, strict C11).
set -eu
T=${1:?usage: build_boot_split.sh TREE}
B="$T/build"
LIBA="$B/yafllib/libyafl.a"
mkdir -p "$B"

cmake -S "$T/yafllib" -B "$B/yafllib" > /dev/null
cmake --build "$B/yafllib" -j"$(nproc)" --target yafl_static > /dev/null

if [ ! -s "$B/boot.c" ] || [ "${REGEN:-0}" = 1 ]; then
    echo "$(date +%T) generating C"
    (cd "$T/compiler" && PYTHONHASHSEED=0 YAFL_LIBYAFL_A="$LIBA" python3 - "$B/boot.c" <<'PY'
import sys
from pathlib import Path
sys.setrecursionlimit(5000)
sys.path.insert(0, ".")
import compiler as c
from libraries import unit_name
boot = Path("..").resolve() / "bootstrap"
sources = sorted(boot.rglob("*.yafl"), key=lambda p: unit_name(p, boot))
code = c.compile([c.Input(p.read_text(), unit_name(p, boot)) for p in sources],
                 use_stdlib=True, just_testing=False, optimization_level=3)
if not code:
    raise SystemExit("bootstrap compilation produced no output")
Path(sys.argv[1]).write_text(code)
print(f"  {len(code):,} bytes of C")
PY
    ) 2>&1 | grep -v "warning:"
fi

if [ ! -s "$B/boot.o" ] || [ "$B/boot.c" -nt "$B/boot.o" ]; then
    echo "$(date +%T) compiling C"
    clang -g -x c -O2 -std=c11 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
        -I "$T/yafllib" -c "$B/boot.c" -o "$B/boot.o"
fi

echo "$(date +%T) linking"
clang "$B/boot.o" "$LIBA" -lpthread -lm -ldl -Wl,--gc-sections -o "$B/ybootstrap_O3.tmp"
mv "$B/ybootstrap_O3.tmp" "$B/ybootstrap_O3"
echo "$(date +%T) built $B/ybootstrap_O3"

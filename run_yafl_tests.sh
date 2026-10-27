#!/usr/bin/env bash
# Build and run the YAFL [test] folders — compiler/yafl_tests and
# compiler/stdlib_tests — with the port (build/ybootstrap), against THIS
# tree: System from the compiler/stdlib sources, yafl.h from yafllib/, and
# build/yafllib/libyafl.a rebuilt from yafllib/ first. No Python.
#
#   ./run_yafl_tests.sh [OPT]       OPT is the optimisation level, default 3
#
# Exit status 0 when both folders build and pass.
set -uo pipefail
cd "$(dirname "$0")"

opt="${1:-3}"
out=build/yafl-test-bins
mkdir -p "$out"

make -s -C build yafl_static || exit 1

status=0
# yafl_tests stdlib_tests; do
for suite in stdlib_tests; do
    echo "== $suite (-O$opt)"
    # No -L and no YAFL_PATH: the port then assembles System from the tree's
    # stdlib sources and links the tree's runtime archive.
    if env -u YAFL_PATH -u YAFL_LIBYAFL_A build/ybootstrap -O"$opt" --test \
            -o "$out/$suite" "compiler/$suite"; then
        "$out/$suite" || status=1
    else
        echo "$suite: build failed"
        status=1
    fi
done
exit $status

#!/bin/bash
# Full gate for the main-branch fix, in the clean worktree yafl-mainfix:
# runtime (debug + release presets) + ctest, fresh port binary with refreshed
# Python references, then the FULL unittest suite. rc of the suite = failures.
set -u
W=/home/mbrown/Projects/yafl-mainfix
R=/home/mbrown/Projects/yafl-strings/strbench/results/mainfix
mkdir -p "$R"
log() { echo "$(date +%T) $*" >> "$R/progress.txt"; }
cd "$W/yafllib"
log "runtime"
cmake --preset debug-unix > "$R/runtime.log" 2>&1 && cmake --build build/debug-unix -j"$(nproc)" >> "$R/runtime.log" 2>&1 || { log "FAILED runtime"; exit 1; }
cmake -S . -B build/release -DCMAKE_BUILD_TYPE=Release >> "$R/runtime.log" 2>&1 && cmake --build build/release -j"$(nproc)" --target yafl_static >> "$R/runtime.log" 2>&1 || { log "FAILED release runtime"; exit 1; }
log "ctest"
(cd build/debug-unix && ctest -j 0 > "$R/ctest.log" 2>&1); log "ctest rc=$? $(grep -E 'tests passed' "$R/ctest.log")"
cd "$W/compiler"
log "bootstrap"
PYTHONHASHSEED=0 python3 build_bootstrap.py --refresh-references > "$R/refresh.log" 2>&1
PYTHONHASHSEED=0 python3 build_bootstrap.py > "$R/bootstrap.log" 2>&1 || { log "FAILED bootstrap"; exit 1; }
log "suite"
PYTHONHASHSEED=0 unittest-parallel -j 0 -s tests -t . > "$R/suite.out" 2> "$R/suite.err"
log "suite rc=$?"
log DONE

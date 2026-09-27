#!/bin/bash
# Fat-string bootstrap vs baseline bootstrap, on the SAME input.
#
# Both trees' ports are the same YAFL source; they differ only in how the
# Python compiler + runtime represent String. So on the same self-compile
# stream (the BASELINE tree's stdlib + bootstrap) their C output must be
# byte-identical, and their CPU/RSS are directly comparable.
#
# Builds run strictly one at a time (concurrent bootstrap builds OOM).
set -u
R=/home/mbrown/Projects/yafl-strings/strbench/results/boot
BASE=/home/mbrown/Projects/yafl-base
FAT=/home/mbrown/Projects/yafl-strings
mkdir -p "$R"
log() { echo "$(date +%T) $*" >> "$R/progress.txt"; }

for T in "$BASE" "$FAT"; do
    name=$(basename "$T")
    if [ -x "$T/build/ybootstrap_O3" ]; then log "reuse bootstrap $name"; continue; fi
    log "runtime $name"
    cmake -S "$T/yafllib" -B "$T/build/yafllib" > "$R/runtime-$name.log" 2>&1 \
        && cmake --build "$T/build/yafllib" -j"$(nproc)" --target yafl_static >> "$R/runtime-$name.log" 2>&1 \
        || { log "FAILED runtime $name"; exit 1; }
    log "bootstrap O3 $name"
    (cd "$T/compiler" && PYTHONHASHSEED=0 YAFL_LIBYAFL_A="$T/build/yafllib/libyafl.a" \
        /usr/bin/time -v -o "$R/build-$name.rusage" \
        python3 build_bootstrap.py -O 3 -o "$T/build/ybootstrap_O3" > "$R/build-$name.log" 2>&1) \
        || { log "FAILED bootstrap $name"; exit 1; }
done

log "stream"
(cd "$BASE/compiler" && python3 -c "import selfcompile, sys; sys.stdout.write(selfcompile._stream())") > "$R/stream.txt"

for i in 1 2 3; do
    for T in "$BASE" "$FAT"; do
        name=$(basename "$T")
        log "run $i $name"
        if [ "$i" = 1 ]; then out="$R/out1-$name.c"; else out=/dev/stdout; fi
        YAFL_HEAP_SIZE=6G /usr/bin/time -v -o "$R/run$i-$name.rusage" \
            "$T/build/ybootstrap_O3" c1 < "$R/stream.txt" 2> "$R/run$i-$name.err" \
            | tee "$out" | sha256sum > "$R/run$i-$name.sha"
        rc=${PIPESTATUS[0]}
        [ "$rc" = 0 ] || log "FAILED run $i $name rc=$rc"
    done
done

for i in 1 2 3; do
    if cmp -s "$R/run$i-yafl-base.sha" "$R/run$i-yafl-strings.sha"; then
        log "run $i: C identical"
    else
        log "run $i: C DIFFERS"
    fi
done
log DONE

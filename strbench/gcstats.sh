#!/bin/bash
# GC statistics (counts only — stats distort timing) for both binaries, in turn.
R=/home/mbrown/Projects/yafl-strings/strbench/results/boot
for v in "/home/mbrown/Projects/yafl-base/build/ybootstrap_O3 base" "/home/mbrown/Projects/yafl-strings/build/ybootstrap_inlinehash fat"; do
    set -- $v
    YAFL_GC_STATS=1 YAFL_HEAP_SIZE=6G "$1" c1 < "$R/stream.txt" > /dev/null 2> "$R/gcstats-$2.err"
done
echo DONE > "$R/gcstats.done"

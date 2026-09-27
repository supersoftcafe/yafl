#!/bin/bash
# Programs benchmark, then self-compile best-of-3 alternating with the baseline.
# usage: measure_all.sh LABEL
cd /home/mbrown/Projects/yafl-strings
L=${1:?label}
PROGS_OUT=progs-$L strbench/progs_bench.sh
cmake --build build/yafllib -j"$(nproc)" --target yafl_static > /dev/null
clang build/boot.o build/yafllib/libyafl.a -lpthread -lm -ldl -Wl,--gc-sections -o build/ybootstrap_$L
for i in 1 2 3; do
    strbench/timed_run.sh /home/mbrown/Projects/yafl-base/build/ybootstrap_O3 $L-base-$i
    strbench/timed_run.sh build/ybootstrap_$L $L-fat-$i
done
echo "$L-DONE" >> strbench/results/boot/timed.txt

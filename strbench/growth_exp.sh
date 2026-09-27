#!/bin/bash
# Growth-policy experiment on the self-compile: recompile boot.o once (yafl.h
# changed), link g20 / g15 / glarge, time each on the baseline stream.
set -e
cd /home/mbrown/Projects/yafl-strings
touch build/boot.c
strbench/build_boot_split.sh /home/mbrown/Projects/yafl-strings
for n in g15 glarge; do
    clang build/boot.o build/yafllib-$n/libyafl.a -lpthread -lm -ldl -Wl,--gc-sections -o build/ybootstrap_$n
done
cp build/ybootstrap_O3 build/ybootstrap_g20
for n in g20 g15 glarge; do
    strbench/timed_run.sh build/ybootstrap_$n growth-$n
done
echo DONE >> strbench/results/boot/timed.txt

#!/bin/bash
# Best-of-3, alternating: baseline vs current fat bootstrap on the same stream.
cd /home/mbrown/Projects/yafl-strings
for i in 1 2 3; do
    strbench/timed_run.sh /home/mbrown/Projects/yafl-base/build/ybootstrap_O3 parity-base-$i
    strbench/timed_run.sh build/ybootstrap_g20 parity-fat-$i
done
echo PARITY-DONE >> strbench/results/boot/timed.txt

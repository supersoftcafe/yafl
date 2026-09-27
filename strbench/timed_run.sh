#!/bin/bash
# One timed self-compile of a bootstrap binary on the baseline stream; its C
# must equal the baseline binary's run-1 output byte for byte.
# usage: timed_run.sh BINARY LABEL
R=/home/mbrown/Projects/yafl-strings/strbench/results/boot
YAFL_HEAP_SIZE=6G /usr/bin/time -v -o "$R/$2.rusage" "$1" c1 < "$R/stream.txt" > "$R/$2.c" 2> "$R/$2.err"
rc=$?
if cmp -s "$R/$2.c" "$R/out1-yafl-base.c"; then same="C identical to baseline"; else same="C DIFFERS from baseline"; fi
awk -F': ' -v rc=$rc -v same="$same" -v l="$2" '/User time/{u=$2} /Maximum resident/{m=$2} END{printf "%s rc=%s user=%.1fs rss=%.2fGB  %s\n", l, rc, u, m/1048576, same}' "$R/$2.rusage" >> "$R/timed.txt"

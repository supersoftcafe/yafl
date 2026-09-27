#!/bin/bash
# Flat CPU profile of each bootstrap binary self-compiling the same stream.
R=/home/mbrown/Projects/yafl-strings/strbench/results/boot
for T in /home/mbrown/Projects/yafl-base /home/mbrown/Projects/yafl-strings; do
    name=$(basename "$T")
    echo "$(date +%T) perf $name" >> "$R/progress.txt"
    YAFL_HEAP_SIZE=6G perf record -q -F 199 -o "$R/perf-$name.data" \
        "$T/build/ybootstrap_O3" c1 < "$R/stream.txt" > /dev/null 2> "$R/perf-$name.err"
    perf report -i "$R/perf-$name.data" --no-children --stdio --sort symbol 2>/dev/null \
        | grep -E "^ +[0-9.]+%" | head -60 > "$R/perf-$name.txt"
done
echo "$(date +%T) perf DONE" >> "$R/progress.txt"

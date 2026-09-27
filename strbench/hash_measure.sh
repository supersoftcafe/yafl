#!/bin/bash
cd "$(dirname "$0")"
R=results/boot
./timed_run.sh /home/mbrown/Projects/yafl-strings/build/ybootstrap_O3 fat-shorterwins
YAFL_HEAP_SIZE=6G /home/mbrown/Projects/yafl-strings/build/ybootstrap_stats c1 < $R/stream.txt > /dev/null 2> $R/shorterwins-stats.err
grep "^str_hash" $R/shorterwins-stats.err > $R/shorterwins-stats.txt
echo DONE >> $R/shorterwins-stats.txt

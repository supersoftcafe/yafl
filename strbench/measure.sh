#!/bin/bash
# Full comparison: today's code vs fat32 vs fat16.
#   results/instr.txt  callgrind instruction counts (deterministic)
#   results/time.txt   best-of-5 CPU seconds + peak RSS
#   results/heap.txt   retained-population heap footprint per GC phase
cd "$(dirname "$0")"
R=results

instr() {  # bin workload impl scale label
    n=$(valgrind --tool=callgrind --callgrind-out-file=/dev/null ./$1 $2 $3 $4 2>&1 \
        | sed -n 's/.*Collected : *\([0-9]*\).*/\1/p')
    printf "%-12s %-11s scale=%-9s instr=%8.1fM per-op=%7.1f\n" $2 $5 $4 $(echo "$n/1000000" | bc -l) $(echo "$n/$4" | bc -l)
}
timed() {  # bin workload impl scale label
    best=""; brss=""; h=""
    for r in 1 2 3 4 5; do
        out=$( { /usr/bin/time -f "RSS %M" ./$1 $2 $3 $4; } 2>&1 ) || { echo "$2 $5 FAILED"; return; }
        cpu=$(sed -n 's/.*cpu= *\([0-9.]*\)s.*/\1/p' <<<"$out"); m=$(sed -n 's/RSS //p' <<<"$out")
        h=$(sed -n 's/.*hash=\([0-9a-f]*\).*/\1/p' <<<"$out")
        if [ -z "$best" ] || awk "BEGIN{exit !($cpu < $best)}"; then best=$cpu; brss=$m; fi
    done
    printf "%-12s %-11s scale=%-9s cpu=%7.3fs rss=%7sKB hash=%s\n" $2 $5 $4 $best $brss $h
}

{
for w in "append1 4000000" "appendmix 4000000" "small 1000000" "fork 200000" "chars 4000000"; do set -- $w
    for v in "b32 builder today-builder" "b32 builderobj today-sbobj" "b32 flat today-flat"; do
        set -- $w $v
        case "$1:$4" in append*:flat) continue;; small:builder*|fork:builder*|chars:builder*) continue;; esac
        instr $3 $1 $4 $2 $5
    done
    set -- $w; instr b32 $1 fat $2 fat32; instr b16 $1 fat $2 fat16
done
instr b32 readevery builder 400000 today-builder
instr b32 readevery fat 400000 fat32; instr b16 readevery fat 400000 fat16
instr b32 tree flat 500000 today-flat
instr b32 tree fat 500000 fat32; instr b16 tree fat 500000 fat16
instr b32 tree fatinto 500000 fat32-into; instr b16 tree fatinto 500000 fat16-into
echo DONE
} > $R/instr.txt 2>&1

{
for w in "append1 32000000" "appendmix 32000000" "small 4000000" "fork 2000000" "chars 32000000"; do set -- $w
    for v in "b32 builder today-builder" "b32 builderobj today-sbobj" "b32 flat today-flat"; do
        set -- $w $v
        case "$1:$4" in append*:flat) continue;; small:builder*|fork:builder*|chars:builder*) continue;; esac
        timed $3 $1 $4 $2 $5
    done
    set -- $w; timed b32 $1 fat $2 fat32; timed b16 $1 fat $2 fat16
done
timed b32 readevery builder 400000 today-builder
timed b32 readevery fat 32000000 fat32; timed b16 readevery fat 32000000 fat16
timed b32 tree flat 4000000 today-flat
timed b32 tree fat 4000000 fat32; timed b16 tree fat 4000000 fat16
timed b32 tree fatinto 4000000 fat32-into; timed b16 tree fatinto 4000000 fat16-into
echo DONE
} > $R/time.txt 2>&1

{
for w in retain retainsparse; do
    for v in "b32 flat today" "b32 fat fat32" "b16 fat fat16"; do set -- $v
        echo "$w $3"; /usr/bin/time -f "  rss=%MKB" ./$1 $w $2 100000 2>&1
    done
done
echo DONE
} > $R/heap.txt 2>&1

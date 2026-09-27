#!/bin/bash
# usage: run_ut.sh OUTDIR module...   — runs each unittest module (4 at a time),
# one log per module, then a summary line per module.
cd "$(dirname "$0")/../compiler"
out=$1; shift
printf "%s\n" "$@" | xargs -P 4 -I{} sh -c 'python3 -m unittest tests.{} > '"$out"'/{}.log 2>&1; echo "{} rc=$?" >> '"$out"'/summary.txt'
echo DONE >> $out/summary.txt

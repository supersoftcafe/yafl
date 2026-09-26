#!/bin/bash
# Build the benchmark binaries against the worktree runtime.
#   b32 / b16      release runtime, -O2        (timings)
#   b32d / b16d    debug runtime, -O0 -g       (correctness: poison + compaction)
set -e
cd "$(dirname "$0")"
L=../yafllib
for v in "b32:" "b16:-DFAT16"; do
    name=${v%%:*}; flag=${v#*:}
    gcc -O2 -g -DNDEBUG $flag -Wall -Wextra -I$L bench2.c $L/build/rel/libyafl.a -lpthread -lm -ldl -o $name
    gcc -O0 -g $flag -I$L bench2.c $L/build/dbg/libyafl.a -lpthread -lm -ldl -o ${name}d
done
echo built

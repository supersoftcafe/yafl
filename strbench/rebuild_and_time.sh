#!/bin/bash
# Recompile+relink the fat bootstrap (C unchanged), then one timed self-compile.
set -e
cd "$(dirname "$0")"
./build_boot_split.sh /home/mbrown/Projects/yafl-strings
./timed_run.sh /home/mbrown/Projects/yafl-strings/build/ybootstrap_O3 "${1:?label}"

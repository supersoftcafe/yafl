#!/bin/bash
# String-heavy YAFL programs: baseline compiler vs fat-string compiler.
# Each program is built by both (-O2, each tree's own RELEASE runtime), run
# best-of-3 alternating, and the two builds' stdout must be identical.
set -u
S=/home/mbrown/Projects/yafl-strings/strbench
R=$S/results/${PROGS_OUT:-progs}
B=$R/bin
mkdir -p "$R" "$B" "$R/in"
BASE=/home/mbrown/Projects/yafl-base
FAT=/home/mbrown/Projects/yafl-strings
log() { echo "$(date +%T) $*" >> "$R/progress.txt"; }

# ── inputs ──────────────────────────────────────────────────────────────────
cat "$BASE"/docs/*.md > "$R/in/english.txt"
python3 - "$R/in/big.json" <<'PY'
import json, random, sys
random.seed(7)
doc = [{"id": i, "name": f"item-{i}", "tags": [f"t{j}" for j in range(i % 7)],
        "price": round(random.random() * 1000, 2), "active": i % 3 == 0,
        "note": "lorem ipsum dolor sit amet " * (i % 4)} for i in range(120000)]
json.dump(doc, open(sys.argv[1], "w"))
PY
for i in 1 2 3 4; do cat "$S/results/boot/stream.txt"; done > "$R/in/lines.txt"

# ── programs: name | source | args | stdin ──────────────────────────────────
PROGS=(
  "accum|$S/progs/accum.yafl||"
  "splitjoin|$S/progs/splitjoin.yafl||"
  "wordfreq|$S/progs/wordfreq.yafl||"
  "tokens|$S/progs/tokens.yafl||"
  "yspell|@/examples/yspell.yafl|-d /usr/share/dict/words $R/in/english.txt|"
  "findstr|@/examples/findstr.yafl|String $BASE/bootstrap|"
  "json_pretty|@/examples/json_pretty.yafl||$R/in/big.json"
  "linenumbers|@/examples/linenumbers.yafl||$R/in/lines.txt"
  "raytracer|@/examples/raytracer.yafl||$FAT/examples/scenes/spheres.scene"
)

for entry in "${PROGS[@]}"; do
    IFS='|' read -r name src args input <<< "$entry"
    for T in "$BASE" "$FAT"; do
        tag=$(basename "$T")
        s=${src/@/$T}
        log "compile $name $tag"
        (cd "$T/compiler" && YAFL_LIBYAFL_A="$T/yafllib/build/rel/libyafl.a" \
            python3 main.py -O 2 -o "$B/$name-$tag" "$s" > "$R/compile-$name-$tag.log" 2>&1) \
            || log "FAILED compile $name $tag"
    done
done

for entry in "${PROGS[@]}"; do
    IFS='|' read -r name src args input <<< "$entry"
    for round in 1 2 3; do
        for tag in yafl-base yafl-strings; do
            bin="$B/$name-$tag"
            [ -x "$bin" ] || continue
            in=${input:-/dev/null}
            /usr/bin/time -f "%U %M" -o "$R/t.tmp" "$bin" $args < "$in" 2> /dev/null | sha256sum | cut -c1-16 > "$R/out-$name-$tag.sha"
            read -r user rss < <(tail -1 "$R/t.tmp")   # a non-zero exit adds a line first
            echo "$name $tag $round $user $rss $(cat "$R/out-$name-$tag.sha")" >> "$R/runs.txt"
        done
    done
    log "ran $name"
done
log DONE

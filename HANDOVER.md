# Handover — compiler-port branch (2026-08-06)

State as of `a43950d`, tree clean, 960 tests green, gate byte-identical at
-O0..-O3. Read `~/.claude/projects/-home-mbrown-Projects-yafl/memory/MEMORY.md`
first; this is the working state.

## This week, newest first

- `a43950d` — generic type args INVARIANT (mutual-assignability, both
  compilers); closes the ctor-arg gap.
- `036beee` — derived enum equality: every qualifying enum is a record
  (auto `instance BasicEquality`, coinductive member check, user instance
  suppresses).
- `0954199` — every boxed enum carries the `$hash` slot; the three internals
  (`yafl_hash_peek/store`, `yafl_ref_eq`) are representation-aware builtins.
- `adfd6e3`/`5b3409d`/`6c9b807` — `[refeq]`, `[hashed]` (function-level),
  enum attribute grammar.
- `a6d9edb` — Python reference-output cache (suite reruns ≈ port-side cost).
- `d61ffd5` — CeKey precise memo keys both compilers; snapping invariant
  VERDICT: held.

## In flight — NEXT: the `with` expression

`docs/preserving-rewrites-design.md` — fully ruled by the user:
`with subject(name = value, …)`; zero-replacement is a CHECK error; subjects
class- and enum-typed (root included, dynamic leaf preserved, covering-field
names only); identity-preserving lowering via `SAME` (bit-identical repr —
one memcmp-style macro covers pointer/scalar/struct); copy's `$hash` zeroed.
Both compilers implement FULLY before any bootstrap source adopts it; then
port rewrite walks migrate file-by-file measured against 689.9s/2.8GB;
then eqStmt/eqSpec SAME heads, measured separately.

Queued after: async inlining policy (docs/inlining-async-policy.md — frame
budgets); the remaining expectedFailure (union variant arms) is a feature
record, kept deliberately.

## Traps (hard-won this week)

- O1+ tests link `yafllib/build/release/libyafl.a` (libyafl_for), and the
  debug-unix preset does NOT rebuild it — after ANY yafllib edit run
  `cmake --build yafllib/build/release --target yafl_static` too, or every
  optimised test runs new compiler output against an old runtime.
  (2026-08-13: an Aug-6 archive under the [pinnable] compiler = memoize UAF
  only YAFL_GC_POISON could see; the whole suite passed silently on the
  skew.) The bootstrap-binary cache now hashes the archive BYTES, so at
  least shared_bootstrap_binary can't reuse a binary across that skew.
- FULL suite before commit; `unittest-parallel` rc = failure count; suites
  ~85 min warm, ~135 min cold (assignability/test edits go cold).
- Never edit sources under a running suite. Kill workers by PROCESS TREE
  (`spawn_main` cmdlines dodge pkill -f; orphans burned a day).
- A new pipeline pass goes into compiler.py, port postmonoRes3 AND
  genericsDump, and ALL TEN hand-rolled harnesses (the tenth is
  _python_c_text inside test_bootstrap_c.py).
- Positional AST-node construction: enumerate sites TREE-WIDE first
  (PsEnum had 17); new fields go at the END with defaults.
- Port YAFL pitfalls: variant arms can't sit under `X|None` (two-level
  match); variant binders into append/list1 need explicit type params;
  `list1` lives in StdlibCandidates; [tail] means DIRECT self-recursion.
- Exit codes are 8-bit; println totals over 255.

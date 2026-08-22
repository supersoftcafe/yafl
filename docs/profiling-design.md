# Profiling (`--profile`)

Status: M1 (flat profile) and M2 (call graph) implemented. M2 is runtime-only
— the compiler emits the same instrumentation for both. This document is the
design record and the user guide.

## What it is

`--profile` instruments the WHOLE program — every function, no per-function
opt-in — with two complementary mechanisms:

1. **Exact call counters.** Every generated C function begins with
   `yafl_prof_enter(id)` (one counter bump + one shadow-stack push) and pops
   before every exit. Counts are exact to the call, deterministically.
2. **Sampled CPU time.** Each worker thread owns a
   `timer_create(CLOCK_THREAD_CPUTIME_ID, SIGEV_THREAD_ID)` timer firing
   SIGPROF at `YAFL_PROF_HZ` (default 997). The handler hash-conses the
   current shadow stack into a preallocated per-thread table; everything else
   is derived at exit. Sampling needs no safe points — a pure non-allocating
   loop is sampled like anything else — and the CPU-time clock makes sample
   floors load-independent (a loaded machine slows the wall, not the count).

At exit the runtime writes two files and announces them once on stderr:

- **`callgrind.out.<pid>`** (CWD; `YAFL_PROF_FILE` overrides) — callgrind
  format, two event columns: `Ns` (sampled CPU nanoseconds, all threads
  summed) and `Calls` (exact counts). Read it with KCachegrind/QCachegrind,
  gprof2dot, or speedscope.
- **`<path>.folded`** — folded stacks (`a;b;c weight` per unique sampled
  stack, weights in samples). Direct input to flamegraph.pl and speedscope;
  this is the hierarchy/inclusive view until M2 adds callgrind edges.

```
$ python main.py --profile -O2 -o prog prog.yafl
$ ./prog
[yafl] profile written to callgrind.out.41837 (+ callgrind.out.41837.folded)
$ kcachegrind callgrind.out.41837
```

Environment: `YAFL_PROF_HZ` (0 = counters only, no timers; clamped to
10000), `YAFL_PROF_FILE` (exact output path).

## Division of labour

- **Compiler** (`--profile`, both compilers — port modes `cp`/`c1p`/`c2p`/`c3p`):
  numbers the non-foreign functions 0..N-1 in emission order (ASCII-sorted,
  deterministic), injects `ProfEnter`/`ProfLeave` ops AFTER the emission
  cleanup chain (`Application.__gen_function` / `genFunction`) — so no
  optimisation pass ever sees them and CSE cannot coalesce a duplicated
  leave — emits the `yafl_prof_fns[]` descriptor table (name, file, line)
  after the emission loops (the lazy `struct_anon` numbering is settled;
  named C types only), and plants `yafl_prof_init(...)` in `main()` before
  `thread_start`, so the profiler precedes every worker registration.
- **Runtime** (`yafllib/prof.c` + fast paths in `yafl.h`, always in
  `libyafl.a`): per-thread state is wired in `gc_declare_thread`; the enter/
  leave fast paths are INLINE in yafl.h (the `object_alloc_fast_raw`
  pattern); the dump runs via `atexit` (the `gc_stats_report` pattern). An
  unprofiled program calls none of it.

Profile-off output is byte-identical to before the feature existed — the
flag adds emission, never changes it — so the parity gates hold unchanged,
and profile mode has its own byte gates (`test_bootstrap_c_o0p`/`_o2p`).

## Inlining policy

Under `--profile` the two IR inliner blocks (-O2 small-function, -O3
single-caller) are DISABLED: they are the only passes that erase whole
functions, and a profile must attribute counts and time to the functions the
source declares. Every other pass runs, at every -O level.

The AST inliner still runs. Its size-heuristic inlining of sub-threshold
functions and bare-`[inline]` operators is structurally load-bearing at all
levels (gating it regresses -O0 — see ast_inline.py:229-234), and those
functions exist in NO binary at any -O level today: the profiler honestly
reports the binary. Consequence: a tiny helper below the inline threshold
will not appear as a row; its cost lands in its callers. Everything of
measurable weight — above-threshold functions, `[inline(always)]` chains
(which only fuse at -O3, now gated off), O3 single-caller folds — is visible
under `--profile`.

## Attribution semantics

- **`[tail]` functions** count ONCE per logical call — the back edge is a
  `goto`, not a call. Iterations are not calls.
- **Async**: the hot path keeps the function's name and is entered exactly
  once per logical call, so its `Calls` are logical call counts. The
  `foo$async` state machine is a separate row; its count is the number of
  resumptions (scheduling-dependent). Time is attributed per C symbol —
  a resumed slice's samples land on `foo$async`, not on the logical awaiter.
- **musttail**: leave-then-tail-call. The frame is genuinely replaced, so
  tail-called callers vanish from sampled stacks, as in any tail-calling
  runtime.
- **Synthesised functions** (`$async`, lazy thunks, `$par$` callbacks,
  `__entrypoint__`) carry no source location (`fl=??`, line 0); their names
  self-describe.
- **Pseudo-frames**: reserved ids after the N program ids make runtime work
  visible — `(GC)` brackets ALL collector work (the `gc_fsa` shim),
  `(scavenger)` the madvise scavenger inside it, `(truncated)` marks samples
  whose stack exceeded the 4096-entry shadow cap, `(runtime)` samples taken
  with an empty shadow stack (dispatch loop between tasks).
- **Time basis is per-thread CPU time**: parked tasks and idle workers
  accumulate nothing. That is correct for this runtime — waiting tasks park
  rather than block threads. IO threads run no YAFL code and are never
  sampled.

## Tolerances (documented, deliberate)

- Counters are plain per-thread u64 with a single writer; the exit dump
  reads them while workers may still run. A boundary increment can be
  missed. The alternative is an atomic RMW on every call.
- A `Return` whose value expression performs work evaluates it after the
  leave; that skew attributes to the caller.
- Shadow-stack overflow saturates: `sp` keeps counting (balance and counters
  stay exact), stores stop, and affected samples gain a `(truncated)` leaf.
- Sample-table/pool overflow degrades rather than drops: the sample falls
  back to a per-thread per-leaf accumulator (constant time, cannot fill), so
  its SELF attribution — the flat profile, M1's primary product — survives
  exactly and unbiased; only its ancestry is lost, shown in the folded view
  as `(truncated);leaf` rows. The dump reports how many samples were kept
  self-only (observed: a c1 self-compile overflows the full-stack tables —
  deep, highly distinct stacks — while smaller programs fit entirely). No
  sample is ever dropped.

## File formats

Callgrind, with the call graph:

```
# callgrind format
version: 1
creator: yafl --profile
pid: 41837

desc: Ns: sampled CPU nanoseconds (997 Hz per-thread CPU-time timers, all threads summed)
desc: Calls: exact call count (compiler-emitted counters)

positions: line
events: Ns Calls

fl=fib.yafl
fn=Main::main@d4e5f6
1 3000000 1
cfl=fib.yafl
cfn=Main::fib@a1b2c3
calls=1 3
1 401000000 0

fl=fib.yafl
fn=Main::fib@a1b2c3
3 401000000 832040
cfl=fib.yafl
cfn=Main::fib@a1b2c3
calls=832039 3
3 399000000 0

summary: 456000000 832164
```

`calls=` counts are EXACT (one bounded hash probe per call in
`yafl_prof_enter`, one uniform mechanism for direct, indirect and musttail
calls); the cost line under each call record carries the edge's SAMPLED
inclusive nanoseconds, derived at dump time from the unique-stack table's
adjacent pairs (deduplicated per stack, so recursion is charged once). This
is what lights up KCachegrind's inclusive costs and caller/callee views.

Folded stacks: `__entrypoint__;Main::main@d4e5f6;Main::fib@a1b2c3 400`.

## Call-graph edge semantics (M2)

- Per-thread open-addressing edge table keyed (shadow-stack top, callee).
  On table overflow the count degrades to a per-callee accumulator —
  SEPARATE storage, so the fallback cannot starve — reported under the
  `(truncated)` caller.
- Calls made while the shadow stack is beyond its 4096-frame cap have no
  stored caller; they are charged to `(truncated)` as well (exact in total,
  ancestry unknown). The KCachegrind invariant — a function's incoming
  `calls=` sum equals its `Calls` counter — holds, roots aside.

## Deliberately out of scope

- Logical async-chain stitching (attributing a resumed slice to its awaiter)
  needs a `task_t` field, which is compiler-mirrored (`_TASK_FIELDS`) — a
  cross-cutting change deferred until wanted.
- pprof protobuf output — additive runtime-only work if the ecosystem pull
  justifies it.
- Per-line costs within a function (descriptors carry the definition line
  only).

# OPEN BUGS — take these first, fresh session

(FIXED 2026-08-12, same session it was found: whole-compiler c1 byte parity
RESTORED — FINAL PARITY: BYTE-IDENTICAL, 93,686,568 bytes, port c1 vs the
_python_c_text mirror framing. Root cause was the port's fold walkers
(rewrite.yafl foldExpr/foldStmt family) never descending SPEC positions, so
aiNodeCount missed the default-value EXPRESSIONS riding inside a Convert
TARGET's tuple entries — Python's search_and_replace counts those — and
`deRef`'s body counted 8 in the port vs 10 in Python once its inner
`List<Spec>()` call inlined: under the <10 threshold the port catalogued
and inlined it at all 14 sites, Python never did. Fold family now mirrors
the rw walker's spec reach exactly (comment at the foldSpec block records
the incident). Also: driver dump modes now parse `#FILE#` streams per-file
via parseMulti (postmonoRes), so every telescoping stage contract can run
under the C contract's framing. GATE LESSON, do not repeat: the
whole-stream comparison MUST use the _python_c_text MIRROR framing
(sorted per-file parse + just_testing=True + yafl.h) — comparing against
`c.compile(use_stdlib=True)` fabricates counter-skew diffs. The defect
predated the 08-12 bug fixes (deRef structurally absent from cba122e's
port output). Worth adding: a whole-stream parity test in the suite,
gated like selfhost.)

## 0. Self-compile peak RSS +60% from the 08-12 fixes — needs a remedy

MEASURED (same-day A/B, same protocol: port built Python -O3 emit +
clang -O2, then `YAFL_HEAP_SIZE=6G <binary> c1 < stdlib+bootstrap stream`,
peak RSS via /usr/bin/time %M):

  * cba122e (before the fixes):  883.7 s wall / 1.22 GB peak RSS
  * 9538ec0/20045cb (after):     829-851 s wall / 1.94-2.05 GB peak RSS

Wall is FINE (slightly better). Peak RSS is +0.7-0.8 GB (+60%) and that is
a REAL regression from the fixes, not noise (two independent runs, and the
1.22 GB side matches the ledgered 1.32 GB best-tree figure).

Prime suspect — the bug-2 gate: `needs_conversion`'s union→union arm
(compiler/pyast/expression/conversion.py, and the port's `intoUnion` in
bootstrap/types/conversions.yafl) used to `return True` for any two
distinct union ids; it now runs FULL member-wise assignability
(trivially_assignable_equals / assignableEq) un-memoised on the compile
fixpoint's hot path. The port's assignability walk allocates chains/lists
per query, and under the structural-pacing GC that garbage IS the peak.
Secondary suspect (likely smaller): the bug-1 arm stamping puts type args
on every bare variant arm in generic bodies — more distinct EnumSpec
instances and deeper spec equality in converge/mono.

Remedies to design (BOTH compilers, in preference order):
  1. uid-subset prefilter: if every SOURCE member uid is present in the
     TARGET's member uid set, it is a genuine widening — answer True from
     string compares alone, no assignability walk. Covers the overwhelming
     common case; fall through to the full check only on a miss.
  2. Memoise the verdict per (source uid, target uid) pair — but mind the
     ledgered memo traps (d61ffd5: value-keyed memos that pay a deep walk
     per hit made things WORSE; key by the uid STRINGS, not specs).

Gate for any change here: whole-stream c1 byte parity MUST stay green
(port c1 vs the _python_c_text MIRROR framing — sorted per-file parse,
just_testing=True, yafl.h; NEVER compare against c.compile output), plus
the full suite, plus a re-measured A/B pair. Success = peak RSS back
toward ~1.2-1.4 GB with wall no worse.

(Fixed 2026-08-12, for context: the two-generic-match silent abort — a bare
variant arm in a generic host latched the wrong enum instantiation at mono —
propagation of resolvable subject type args onto bare arms fixed it, both
compilers, witness `compiler/tests/test_two_generic_match.py`; and the
wrong-return-shape-through-a-union silent acceptance — `needs_conversion`
treated ANY two distinct union ids as a widening, now gated on genuine
member-wise assignability, both compilers, test
`compiler/tests/test_union_return_shape.py`. The LOUD cross-function
inference gap in multi-param generic hosts — "cannot infer the type
arguments" — remains open, ledgered as shapes 1–2 in
`project_nested_fn_generic_inference.md`; explicit `<T>`/`<U>` args stay the
sanctioned form, e.g. `bootstrap/ast/classtools.yafl` co-walks.)

## 1. Port silently compiles an UNDEFINED name

Python rejects the program; the port emits broken C (ledgered 08-01,
`project_port_accepts_unresolved_name.md`). The golden rule (byte-identical
C) is only meaningful if both compilers also REJECT identically — there is
no gate feeding invalid programs to both compilers today. Fix the port's
resolution hole, then add a small invalid-program parity harness.

## 1b. Corpus files that test nothing and still pass (QUEUED after the
##     multi-subject `match` and `??` milestones)

A `corpus_converge/*.yafl` file with no `namespace` + `import System` (and no
self-contained prelude of its own) resolves NOTHING — `Int`, `String`, `+` all
fail — so the port emits a few hundred bytes of error text where it should emit
tens of thousands of bytes of C. The parity test still passes, because
`_python_c_text` produces the SAME error text: a dud test is indistinguishable
from a green one.

Known duds, each carrying a comment claiming to pin a specific codegen
behaviour it cannot be reaching:

  * `pipe_chain.yafl`         — 270 bytes; claims to pin destructure-type
                                inference surviving beta-reduction
  * `union_boxing.yafl`
  * `default_fill_const.yafl`

Fix = give each a prelude (`namespace Corpus` + `import System`, or an own
`namespace System` prelude like drop_balancing.yafl), then re-check parity.
EXPECT FALLOUT: these have been mutually-failing for an unknown time, so real
port-vs-Python differences may be hiding behind them.

Verify any corpus file is real before believing it:

    from tests import bootstrap_c_base as b
    from tests.testutil import shared_bootstrap_binary
    t = next(p for p in b._CORPUS if p.name == NAME)
    print(len(b._run_port_c(shared_bootstrap_binary(), b._port_stream(t), 'c1')))
    # hundreds = dud; tens of thousands = real

(Found 2026-08-29 when `bind_parse_state.yafl` shipped in f32c8c1 as a dud and
was fixed the same session.)

## 1d. Multi-subject match: position-support refusal is UNVERIFIED in the port

Python's `MatchExpression.check` refuses a pattern whose repr cannot serve a
position ("this pattern cannot serve a position of a multi-subject match") —
e.g. a MULTI-MEMBER pattern at a position of a tagged-combination subject,
which needs a Phi over entry edges rather than one tag test.

The port checks the same thing, but NOT in its check phase: `classifyRepr`
lives in Bootstrap::Codegen, which imports Bootstrap::Frontend, so asking from
the check phase would be a cycle. It runs instead as a codegen validation
(`multiSubjectPositionErrs`, create_c_code.yafl, at the ssaValidate seam).
Consequence: both compilers refuse, but in different PHASES, so the message
FORMAT differs — a check diagnostic carries `file[line:col]`, a codegen error
does not.

WHAT IS VERIFIED:
  * ARITY parity is exact — both emit
    `match arm has 2 patterns but the match has 1 subject`, byte-identical.
  * `soleMemberOf` returned the whole union for a multi-member pattern where
    Python returns None, so the port handed back ONE tag for a pattern
    matching SEVERAL — a silent wrong-variant match. FIXED.

WHAT IS NOT VERIFIED: that the port's codegen-side check actually FIRES.
Two probe attempts failed to reach it — one was inlined away before codegen,
the other was rejected earlier for an unrelated reason (`Int32(n)` is not a
valid conversion). Do not assume it works; write a probe that survives
inlining and type-checks, and confirm the port refuses.

## 2. Undischarged `where` crashes codegen

Ledgered in `project_undischarged_where_crash.md`: a `where` constraint
that survives monomorphisation undischarged reaches codegen and crashes it.
Needs a post-mono discharge check with a proper diagnostic (both compilers).

(Fixed-and-guarded, for context, not work: the arm-binder-into-pipe-stage
bug has a regression test at `compiler/tests/test_arm_binder_in_pipe.py`.)


# TODO: functions can derive their "async" nature from parameters

In YAFL all functions are async, but if the call knows that the function
will never yield it can optimise the call and treat it as a sync call. Sometimes
this can depend on parameters, so for example 'fold' which takes a function
as a parameter must be async because function pointers are async, but if
the caller knows that the function it is passing in is sync, we can derive
that 'fold' is itself going to be sync. This might help to reduce the amount
of inlining we do when trying to reduce the amount of async work, allowing
us to lower the inline thresholds.

# TODO: a cached (memoised) function in YAFL

Long term we want a language/stdlib facility for a **cached function**: same
arguments ⇒ same answer, returned from a cache rather than recomputed, for
functions that are expensive to evaluate. Conceptually "a lazy `Dict`" — the
memo table is keyed by the argument tuple, and an entry is computed on first
demand and then reused, in the same spirit as the existing `[lazy]` let (which
already gives us demand-driven evaluation and memoisation of a *nullary* value).

Why it matters (evidence, not speculation): the Python compiler has now been
bitten TWICE by exactly the missing-memo shape — a pure recursive rewrite over
a shared graph re-deriving the same answer once per path that reaches it, which
is exponential in the graph's size. `lowering/complex_enums.py` cost 9GB / 418s
compiling the bootstrap until a hand-rolled memo took it to ~1GB / 1s, and
`EnumSpec.replace_in_all_fields` (used by `lowering/simple_classes.py`) has the
same shape. Every one of these is a hand-written dict that must be threaded by
hand and kept out of global state. A first-class cached function would make the
correct thing the easy thing — and the self-hosted compiler will want it for
the very same passes.

Design notes / open questions:
  * keying needs structural equality + hashing on the argument tuple — YAFL
    derives nothing, so this leans on the hand-written equality/hash story.
  * scope of the cache: per-call-site? per-invocation of an enclosing pass?
    It must NOT become process-global mutable state (see the
    `lazy_thunks._STRUCT_REGISTRY` bug) — a cache that outlives its compilation
    hands back stale answers.
  * interaction with `[linear]` values (a cached result cannot be consumed
    twice) and with purity: only sound for pure functions.

# TODO: annotated tests + a test-runner build mode

Tests should be a FIRST-CLASS thing the compiler knows about, not a separate
harness bolted on:

  * **Annotated tests** — a test is an annotated declaration in ordinary YAFL
    source (spelling to be designed; the obvious shape is an attribute, e.g.
    `fun [test] roundTrips(): ...`, sitting beside the code it tests).
  * **A compiler option to build the tests.** When it is given, the emitted
    binary is NOT the application — it is a **test runner** that discovers the
    annotated tests, runs them, and reports. Same source tree, same compiler,
    a different output artefact. Without the flag the test declarations are
    simply not part of the build (dead-code eliminated, or never emitted).

Design questions to settle first:
  * the annotation's spelling, and what a test's SIGNATURE must be (nullary?
    what does it return — a Bool, a Result, or does it signal failure by some
    other means? how are assertions expressed and reported?);
  * discovery: the runner needs the set of annotated functions, which the
    compiler already knows — so this is a codegen/entry-point question, not a
    reflection one (YAFL has no reflection and stays that way);
  * naming/reporting: a failure must name the test and its source position;
  * how it composes with the build system (`docs/build-and-packaging.md`) —
    per-project and per-library test targets;
  * whether tests may be [linear]/IO, and what the runner's `main` looks like.

# TODO: specialise a `let` bound to a function-RETURNING call into a function

A `let` whose initialiser is a CALL that returns a function is, once its
arguments are known, a function with a fixed shape — so derive that shape at
compile time and rewrite the LetStatement into a **FunctionStatement**.

    let number = many1(digit)          # many1 returns a parser (a function)
    let expr   = seq(term, plus, term)

Today each of these stays a `fun_t` value: a closure built at run time, called
indirectly, allocating its captures, and opaque to inlining. If the call can be
evaluated at compile time (the callee is known, its arguments are known, and it
is pure), the result is a KNOWN function body and can be emitted as an ordinary
top-level function — direct calls, no closure allocation, and open to the
inliner like any other function.

This is exactly the shape a COMBINATOR PARSER is built from, so it is the
optimisation that would make one fast — and the compiler's own parser (both the
Python `parselib` and the ported one) is precisely such a program. It is
plausibly the single biggest win available for the self-hosted compiler's own
runtime.

Precedent already in the tree: `lowering/lambda_globals.py` rewrites a global
`let` holding a LAMBDA into a function ("a global let holding a lambda is a
function by another name"). This is the same idea one step further out: the let
holds a lambda *produced by a call*, so the call must be evaluated first.

Design questions to settle:
  * **When can the call be evaluated at compile time?** Needs a known callee, a
    pure body, and arguments that are themselves compile-time known (literals,
    [const]s, or other specialised lets). This is partial evaluation — bound it
    deliberately, or it becomes an arbitrary interpreter at compile time.
  * **Termination / blow-up.** Recursive combinators (`expr := term ('+' expr)`)
    must not be unfolded forever; a self-referential parser needs a fixed point,
    not inlining. Some cutoff or cycle detection is required — and note this
    codebase has ALREADY been bitten twice by unbounded graph expansion
    (see the enum-graph exponential).
  * **Captures.** A specialised function's captured values become... what?
    Constants folded into the body, or an emitted [const] global?
  * Interaction with generics/monomorphisation (the specialisation is a close
    cousin of it), with [linear] captures (cannot be duplicated), and with the
    existing lambda/closure-conversion order in the lowering pipeline.
  * Where it sits: after convergence (types known) and before `lambdas.py`, in
    the spirit of `lambda_globals`.

# YAFL bootstrap compiler — remaining blockers

Ranked by how blocking they are to writing the compiler in YAFL itself.

## FIXED 2026-07-04: function-typed global `let` segfault (root-caused)

Root cause: `lower_lazy_lets` SPECIAL-CASED a lambda RHS — it skipped wrapping
the value in the nullary `() => expr` init thunk whenever the value was a
lambda, so a parameterised value-lambda was used directly as the init closure
and called with NO arguments → garbage `fun_t` → the caller's segfault (and a
nullary value-lambda would have been CALLED and its result memoised instead of
the function). Fix: remove the special-case entirely — every deferred-init RHS
is wrapped uniformly; construct-lazy does not care what it memoises. Plus the
lazy machinery now supports a FuncPointer value type (`_ir_mangle` "fun" case;
`StructField` reads a `fun_t`'s `.o`, which the task ABI tags). All shapes
work at -O0/-O3: alias, ternary-of-funs, ternary-of-lambdas, nullary function
value. tests/test_function_typed_globals.py.

### also FIXED 2026-07-04: dead arm not stripped after a folded const branch
`let h = true ? l1 : l2` at -O3: `known_tags` folds the constant `JumpIf` to
an unconditional `Jump`, but LEFT the now-unreachable arm's ops in place —
their `Move result = l2` still referenced `l2`, so the reachability prune kept
`l2` while C emission (which skips unreachable ops) dropped it → clang
`-Wunused-function`. Fix: `known_tags` calls `strip_unused_operations()` after
folding, removing the unreachable arm so the prune sees `l2` truly dead. The
prune was right all along; the fold just needed to drop its own dead code.

## OPEN (optimisation): static-const global lets

Separately from the bug above: **any global `let` whose initialiser is a
compile-time constant with no captures, calls, or allocations should be a
static const**, not a lazy memoised thunk. Today every non-trivial global
goes through the `[lazy]` stub (files have no order → no ordered init); a
constant initialiser needs no thunk. This would also make some function-typed
globals avoid the lazy path, but it does NOT fix the bug above for the
run-code cases.

## MEASUREMENT RULE: peak RSS is only valid when the heap cap BINDS (08-14)

Learned the hard way while A/B-ing the vtable tag bit (3eb36ae). At the
reference `YAFL_HEAP_SIZE=6G` the pair read 1.464GB vs 2.520GB — a +73%
"regression" that does not exist. Re-run at caps that bind:

    heap 3G   A 1.590GB   B 1.617GB   (+1.7%)
    heap 2G   A 1.975GB   B 1.987GB   (+0.6%)

With a 6G cap and a ~1.4GB live set the reserve gate never engages, so peak
RSS measures how far the allocation frontier outran the collector — a RATE
difference, not liveness. Proof it is not a property of the code under test:
adding only relaxed atomic counters to `gc_compact_page` moved an otherwise
identical build from 1.449GB to 2.280GB. Same semantics, same emitted C,
+57% RSS.

**So: quote peak RSS only from a run whose heap cap binds, or quote the
frontier (`max in_use` pages) instead.** Structural metrics stayed honest
throughout the same investigation — bytes evacuated, objects marked, symbol
reference counts, text size — and they, not RSS, are what caught the real
effects. Three plausible mechanisms (misclassification, compaction
starvation, promote-volume runaway) were each refuted by direct counters
after being argued convincingly from the code; instrument before believing.

Related and still open: **release pages more deterministically** (user, 08-14
— direction chosen: WARM-FIRST REUSE ORDERING). Every term in the current
policy is clocked on cycles or on a floating quantity, never on the
allocation clock the rest of the GC uses: `SCAVENGE_FREE_AGE` counts scavenge
epochs (i.e. GC cycles), `memory_scavenge` is per-call budget-limited, and
retention is `slack = young * 3`. Meanwhile 62-69% of returned pages are
re-claimed (returned 613k-684k vs reclaimed 379k-470k on one self-compile) —
we madvise pages and take them straight back. First step agreed: never claim
a virgin page while a warm free page exists, so the frontier stops growing
and RSS self-limits without any madvise policy change.

## OPEN (optimisation): CSE the `object_resolve` read barrier

**HAZARD, noted 08-14 (Fable):** every resolve hoisted out of a loop is a
heap pointer with a LONGER LIVE RANGE, and the root scan is CONSERVATIVE —
a pointer parked in a callee-saved register pins its page
(`scanner.pinned`), and pinned pages are exactly the ones `gc_compact_page`
refuses. So the TODO's "per basic block, invalidate at anything that could
relocate" is a HARD CONSTRAINT, not an implementation detail: do not
loop-hoist resolves without a story for pinned-page pressure. (Measured on
the tag-bit branch, this effect did NOT appear — `cons_seeds` 24.6M -> 23.8M
and `cs_skip_pinned` 7.66M -> 7.59M, both DOWN — but that was clang's CSE,
not ours, and a deliberate IR-level pass hoists further.)

`lowering/pinnable_reads.py` (port: `lower/ir/pinnable_reads.yafl`) wraps
every read of a `[pinnable]` object's fields in `object_resolve`, because a
late pinned write lands on the live copy only and a stale pointer would read
the pre-write bytes. Correct, and currently **resolving the same pointer 3–6
times inside one function**. From the emitted C of `bench/memo_bench.yafl`:

    6 object_resolve(loopvar_n_zE8BDY)
    4 object_resolve(r_yNrf64)
    4 object_resolve(n_mnu3WB)

`_walkNode` reads `mnHash`, then `mnKey`, then a child — three resolves of
one pointer with nothing between them that could move the object. Clang
cannot fold them: `object_resolve` loads through a pointer that may alias the
loads in between, so it must redo the work each time (and each resolve also
reloads the two `_memory_heap_base`/`_memory_heap_bytes` globals).

**The fix:** resolve once per pointer per basic block and reuse the register —
a local CSE in our own IR, in the same pass, BOTH compilers. Invalidate at
anything that could relocate (a call, a safe point); within straight-line
field reads the resolved value is stable.

**Measured cost of not doing it** (-O3, median of 5 interleaved A/B, vs the
same build without the barrier): `hit` +81%, `par` +77%, `insert` +39%,
`parins` +35%. `churn` is still −30% overall because promotion outweighs it.
`hit` is pure probing, i.e. exactly what a cache is for, so this is the
number that matters.

**Second, independent lever — needs a user ruling, do not just do it.** The
barrier is applied per TYPE, but only LATE-WRITTEN fields can differ between
copies. `mnHash`/`mnKey`/`mnValue` are set at construction and identical in
every copy, so reading them through a stale pointer is already correct; only
the write-once child slots `mnC0..3` need resolving — and the probe path is
dominated by the fields that don't. Narrowing the barrier to late-written
fields is exactly `[once]` from `docs/memoize-proposal.md` §4b, which was
already scoped there for enforcing zero-to-value and emitting the right
ordering. Sound on the same argument that motivated the barrier: a field
never late-written keeps the "every copy is authoritative" property, so an
intra-thread re-read cannot disagree.

Both deferred 2026-08-13 by explicit user instruction: correctness first,
optimise later. See memory `project_late_pinning.md`.

## OPEN (idea): lazy-backed eager parallelism

Use the existing lazy/task machinery to speculatively parallelise: a function
doing a heavy operation could **eagerly kick off the work as a lazy/async
evaluation and return the lazy object immediately**, so the caller proceeds
and the heavy work overlaps on a worker thread; forcing the lazy value later
blocks only if the work hasn't finished. This turns `[lazy]` from
compute-on-first-force into compute-eagerly-in-background — a form of
automatic futures. Investigate: which heavy ops to auto-wrap (cost model?),
interaction with `__parallel__` and the task backpressure machinery, and
whether it's opt-in (an attribute) or inferred.

## "findstr integer overflow" — ROOT-CAUSED & FIXED 2026-06-13 (two bugs, both fixed)

The long-standing findstr `Aborting due to integer overflow` was **two unrelated
bugs**, both now fixed: a deterministic CSE value-routing bug (PRIMARY) and a
multi-thread-only GC fixup-vs-mutator race on mutable objects (SECONDARY).

### PRIMARY (FIXED): CSE did not invalidate heap reads on a heap write
`codegen/things.py eliminate_common_subexpressions` invalidated cached
`StructField` reads on a Call / NewObject / `ObjectField`-write, but NOT cached
`ObjectField` / `ArrayElement` (heap dereference) reads. An async state object's
coalesced array slot is read, overwritten with a *different* logical variable,
then read again; CSE reused the first read for the second, substituting the
slot's previous occupant. In `searchFiles`, `array[3]` holds `path` then `lineNo`
(coalesced, disjoint live ranges); CSE made `String(lineNo)` append `path`
instead, so the integer-append helper read a string's length as a bignum limb
count and overflowed. Fix: invalidate `StructField`, `ObjectField` AND
`ArrayElement` on any heap-mutating op (one-liner at things.py:~412).
- DETERMINISTIC + SERIAL (the GC was a red herring): `YAFL_THREADS=1
  YAFL_HEAP_SIZE=256m ./findstr fn <aho-corasick>/src/packed` aborted 100% before,
  0/50 after. Hot path was immune (there `path`/`lineNo` are plain StackVars; CSE
  doesn't cache StackVar sources) — only the SM, where they become `array[]`
  ObjectFields, hit it. This is why it masqueraded as an async/SM/coalescing/GC bug.
- Regression test: `tests/test_things.py::TestCseHeapInvalidation` (fails without
  the fix, and a second case asserts genuine duplicate reads are still coalesced).
- Earlier mis-diagnoses (all WRONG, recorded so we don't repeat): "GC-root slot
  coalescing", "moving-GC compaction race / TSAN gc_compact_page" (real race but
  NOT this abort), "interference/liveness", "phi-copy ordering". The repro needs a
  needle with MANY matches (`fn`, not `needle`) so `emit`/`String(lineNo)` runs.

### SECONDARY (FIXED 2026-06-13): GC rewrote pointers inside MUTABLE objects
After the CSE fix a rarer multi-thread-only abort remained (~1/60; THREADS=1
0/120). Cause: `gc_fsa_mark_sweep$scan_elements` snapped a relocated child's
field to its forwarding target (`*ptr_ptr = fwd`) even when the CONTAINING object
is mutable. An async state object rewrites its own coalesced `array[]` slots as
it runs; the GC's fixup write races the mutator's store and clobbers it with the
slot's previous occupant → `lineNo` reads a stale string → overflow. Fix (user's
hypothesis): the GC must not rewrite pointers in a mutable object — `scan_object`
computes `fixup = !page->head.mutable` and `scan_elements` takes a `fixup` flag;
for mutable containers it still marks through the whole forward chain (so the
original stays live and the mutator follows forwarding lazily on read) but never
stores back. Mutable pages are never compacted, so the object is never a
forwarder itself and its page flag is authoritative.
- Verified: release -O2 multi 0/150; debug+poison multi 0/250; THREADS=1 0/120;
  output identical single vs multi; ctest 17/17; yspell (500k-word immutable BST
  + compaction) correct + stable.
- Remaining TSAN reports are the GC's by-design lock-free SATB marking READ races
  (bitmap_test/fetch_set, scan_elements reads, object_get_vtable, gc_compact_page
  forwarding-install-vs-reader). No abort in 250+ runs — these are the accepted
  benign class ("spurious mark harmless"; reader follows forwarding, original data
  intact). NOT a bug — rewriting a pointer to its forward while in use is part of
  the design: compaction COPIES, the original object stays live and valid for
  in-flight readers, and a later GC cycle reclaims it only once provably
  unreferenced. Do NOT chase `gc_compact_page` under TSAN.
- **Re-verified 2026-06-14 (both bugs stay closed):** 650 abort-free findstr runs
  on the aho-corasick `packed` dir — 80× (-O2, 8m heap), 200× (-O2, 4m heap / 4
  threads), 120× (-O0 + `YAFL_GC_POISON`, 4m heap / 4 threads). A TSAN rebuild
  still reports only the by-design races above (incl. `gc_compact_page`).

### Codegen non-determinism — FIXED (4 hash-ordered sources), committed:
- `lowering/async_lower.py __frame_field_types` + 2 save sites: iterate `bb.live`
  (a frozenset) as `sorted(..., key=lambda v: v.name)`.
- `lowering/task_abi.py task_subtype_name`: `blake2b(repr(result_type))` not `hash()`.
- `lowering/strings.py`: `enumerate(sorted(all_string_literals))`.
- `pyast/match.py`: iterate `valid_leaf_names` as `sorted(..., key=leaf_id)`.
Byte-identical across runs with random seed. Orthogonal to the bugs above.
Committed and re-confirmed 2026-06-14 (findstr/json_pretty/yspell byte-identical
across random `PYTHONHASHSEED`).

## FIXED 2026-06-14: match arms on a concrete generic enum mistyped the binder

Matching a CONCRETE instantiation's variants from non-generic code left the
binder's fields typed as the enum's placeholders — `match(c: Chain<String>)
(link: ChainLink) => link.value` had `link.value: T` not `String`.

Two-part fix (committed f823aeb):
- `pyast/expression/access.py` `_substitute_enum_type_params`: reading a field
  off a concrete generic-enum instantiation maps the enum's declared
  placeholders to the receiver's type arguments (the enum analogue of the
  existing `_substitute_class_type_params`). Fixes the *explicit*
  `ChainLink<String>` case. Only `get_type` (the type-check path) needed it;
  the compile/check/generate enum cases are name-only or post-monomorphisation.
- `pyast/match.py` `MatchExpression.compile`: propagate the subject's
  *resolved concrete* type arguments onto variant arms that didn't spell them
  out. Guard: skip when any arg is a placeholder (GenericPlaceholderSpec) or
  unresolved (NamedSpec) — otherwise generic-context matches (the stdlib's own
  `Dict<K,V>` etc.) get placeholder type_params pushed onto their arms and fail
  to resolve. The iterate-to-fixpoint loop fires this once args resolve.

Tests: `compiler/tests/test_generic_match_binder.py` (was failing, now passes).
Full suite 620 OK. The `chainNext` workaround in `examples/yspell.yafl`
(`buildAt`) is REMOVED — it now matches `Chain<String>` directly (the formerly-
broken pattern); yspell test 11 OK, output unchanged.

## Postfix method chaining — DONE

Postfix `.field` / `(...)` / `[...]` form one left-associative chain
(`parsing/parser.py`, `__parse_invoke` / `__to_invokes` / `__parse_postfix_dot`),
so `f().g()`, `a().b`, `m()[0].x`, and full method chains all parse and run.
Tests: `tests/test_postfix_chaining.py`.

The deep case (`Box(0).inc().get()` — a method call on a method-call result) is
**fixed** (2026-06-08). Root cause was `simple_classes.lower_simple_classes`, NOT
the async/Task lowering: it lifts a small class's methods to free functions
(`Cls__m`) but the method-call rewrite resolved receiver types against a resolver
that didn't include those lifted functions — so for a chained receiver that had
just been rewritten to `Cls__m(...)`, the outer call's receiver type came back
`None` and the outer `.m` was left as an unrewritten `DotExpression` that crashed
at generate. Fix: the rewrite now uses `ResolverRoot(statements + lifted_pre)`, so
a lifted-method-call receiver resolves and the next call in the chain is rewritten.
(Two earlier wrong guesses were retracted along the way: "NamedSpec base" and
"the Task/CPS lowering rewrites returns to unit" — `async_lower` runs *after* the
crash point and was never involved.)

NOTE for future readers: the async/Task lowering is **already an IR pass**
(`async_lower.lower_async` operates on `Application`, runs at `compiler.py:211`
after AST→IR codegen; no async transformation exists in `pyast/`). The
once-mooted "move async AST→IR" is a non-task — it's done.

## Language & parser features

From a parser review (2026-06). Bit shifts (`<<`/`>>`, all integer types), a
`splitLines` helper, arrays (`Array<T>` + the `[]` index operator, built on
the array-as-final-class mechanism — `stdlib/array.yafl`), short-circuit
`&&` / `||`, and `if` / `else if` / `else` are now done; remaining:

- **`\u` / `\x` string escapes.** Strings are UTF-8 codepoints, but only
  `\n \r \t \0 \\ \" \'` decode — there is no way to write a non-ASCII codepoint
  as an escape. Add `\xNN` and `\u{…}` / `\uXXXX`.
- **`map` combinator (parser simplification).** ~30 of the parser's `__to_*`
  callbacks only transform `result.value` yet hand-thread
  `tokens`/`line_ref`/`errors`. A `Parser.map(f)` combinator would collapse
  them, leaving `>>` only for the few that add errors or inspect tokens.

Explicitly not planned: block comments (only `#` line comments) and multi-line
string literals.

## Lift the 16 KB per-object size cap — done

`_object_alloc` (`yafllib/object.c:350`) now allocates a dedicated multi-page run
for objects larger than one page (the `actual_size > MAX_OBJECT_SIZE` branch)
instead of calling `abort_on_too_large_object`, so strings/arrays grow past
16 KB. The scaffolding described below (page-count tracking, multi-page free,
compaction skip) is all wired in now.

**What's already there.** The scaffolding for multi-page allocations exists
but is partly disabled. `page_head_t.pages` (line 84) explicitly counts
"pages, including this one, in the complete allocation". `gc_page_alloc(page_count)`
(line 272) already takes a count, calls `memory_pages_alloc(page_count)`,
zeros all pages, stores the count. `gc_page_free` (line 312) routes
multi-page allocations straight to `memory_pages_free`, bypassing the
single-page quarantine. `gc_compact_page` (line 508) early-returns on
`pages > 1` — multi-page is never moved, so `[is_mutable]` invariants
come for free. The stubbed allocation path at lines 348–354 sketches the
alloc branch but is replaced with `abort_on_too_large_object`.

**The threat model the simple fix gets wrong.** Multi-page allocations have
only one valid object pointer — slot 0 of the head page. There are no real
interior pointers in YAFL data. The hazard is **spurious** interior pointers:
a stack word during conservative scanning that happens numerically to land
in a tail page. Today's checks fail unsafely: `memory_pages_is_heap` returns
true (the page is part of our address space); masking gives the tail page;
`bitmap_test(&page->head.objects, slot)` reads the first ~64 bytes of the
tail page **as a `bitmap_t`** — but those bytes are payload (string data).
For a long string the bit at `slot` will eventually be set by chance, and the
GC will treat the spurious address as a live object: read `object->vtable`,
dispatch, corrupt. In-band page validation cannot work for tail pages
because their first bytes are user payload.

**Side table for page state.** A **byte-per-page side table** maps every
page in the reserved heap region to one of `FREE`, `HEAD`, `TAIL`.
Validation in `gc_object_is_on_heap_slow` becomes a single lookup; the
magic-number tag goes away. `gc_page_alloc(N)` claims a run of N `FREE`
entries and marks `HEAD + (N-1) × TAIL`. N=1 is the normal path.
`gc_page_free` walks N entries back to `FREE`; single-page goes through
quarantine as today; multi-page decommits the pages and returns immediately.
`head.tag` is removed (the side table is now the authority).
`head.pages` stays — O(1) freeing without walking the table.
The existing bitmap-of-mapped-pages in `memory.c` collapses into the side
table.

**Pre-allocated virtual heap region**, JVM/Node-style: at startup,
`mmap(NULL, HEAP_VIRTUAL_MAX, PROT_NONE, MAP_NORESERVE | MAP_ANON | MAP_PRIVATE, -1, 0)`
a fixed range. All YAFL heap pages live inside it. Real memory only gets
billed on commit (`mprotect READ|WRITE` or `mmap(MAP_FIXED)` over the
reserved range). On `gc_page_free` for multi-page allocations,
`madvise(MADV_DONTNEED)` returns real RAM to the OS while keeping the
virtual range reserved — committed footprint tracks live large objects,
not peak. `HEAP_VIRTUAL_MAX` can be aggressive (16–64 GB on 64-bit Linux);
reserved-but-uncommitted pages cost effectively nothing. The side table
is then a flat `uint8_t[HEAP_VIRTUAL_MAX / GC_PAGE_SIZE]` (≤ 4 MB per GB
of virtual heap).

**Work to do.** Reserve the heap region at startup and rework `memory.c`
so all allocations commit within it. Introduce the side table; expose
`page_state_get(addr)` and a run-set operation. Replace
`gc_object_is_on_heap_slow`'s magic-tag check with the side-table lookup.
Enable the multi-page branch of `_object_alloc` — set `head.mutable`,
mark slot 0 in `head.objects`, link the head page into `new_pages`,
return `&page->slots[0]`. Drop `head.tag` and the existing
bitmap-of-mapped-pages. Tests: a 1 MB / 4 MB string survives a GC cycle
through a stack reference; a stack word whose value falls inside a tail
page does not register as a live object; RSS returns to baseline after
multi-page allocations are dropped; stress test interleaving single-page
and multi-page allocations during a GC cycle.

**Knock-on once this lands.** `abort_on_too_large_object` becomes
unreachable — remove it. The "Large strings" entry further down this file
is subsumed: `String` just works at any size, no rope wrapper needed.
`StringBuilder` is no longer load-bearing for safety; still a perf win
for many-concat workloads but no longer the only way to produce a large
string.


## Follow-up — optimal binding-order analysis (was: nested-fn codegen hazards)

The original "nested function calling its enclosing function" bug split
into two parts: (a) the hoist mis-classification that left dangling
references when a non-capturing sibling called a capturing one; (b) the
runtime crash when two capturing nested fns mutually called each other
through independent closures. The current fix (in `lowering/ast_inline.py`)
handles both — by running an SCC analysis over the sibling-call graph,
forcing non-capturing callers of capturing closures into closure form,
and coalescing mutually-recursive capturing SCCs into a single class
with one method per member so cross-calls route through `this`.

What remains is broader than nested fns or lambdas. It's an
**optimal-ordering / lazy-init problem** for any binding block.

A YAFL block is a series of uninterrupted `LetStatement` /
`FunctionStatement` declarations — anything with side effects is an
`ActionStatement` which by definition splits blocks. Within one block,
**any binding can reference any other**; that's the language's contract,
not a property tied to nested fns.

The hoist transform needs to honour that contract by *choosing* an
evaluation order:

1. **Reorder Let/Function statements so no recursive issue remains** —
   then ordinary sequential evaluation suffices. Topological sort over
   the dependency graph; works when the graph is a DAG.
2. **Reorder so only functions form recursive cycles** — then the
   mutual-class solution (current fix) handles those cycles; Lets stay
   plain sequential. Works when the cycles are confined to function
   bindings.
3. **No reorder eliminates the cycle (recursive Let↔Let or Let↔Fn
   cycles)** — fall back to lazy initialisation:
   - Push all the at-risk Lets/Fns into one mutual class.
   - Convert each at-risk Let into a member function (zero-arg
     thunk) that performs the lazy init and returns the value.
   - Member-function dispatch through `this` then resolves the cycle
     uniformly.

Edge cases that need (3) should be rare. The compiler should try (1)
first, fall back to (2), and only reach (3) as a last resort —
preferably with a diagnostic so the programmer knows they tripped it.

Witness for why (1)/(2) alone are insufficient:

```yafl
fun outer(f: String): String
  fun inner1(g: Int): String
    ret g < 1 ? f : inner2(g - 1)
  let x = "_x_"
  fun inner2(g: Int): String
    ret g < 1 ? x : inner1(g - 1)
  ret inner1(3)
```

`inner1` and `inner2` are mutually recursive and both visible to each
other and to the `let x`. `inner2` captures `x`. The current fix emits
the synthesised `let shared = MutualClass(f, x)` at the position of
the first SCC member (i.e. before `x`), so `x` is read-before-write at
the construction site. Reordering `x` before `inner1` resolves it here
(`x` doesn't depend on either fn), but the general case can construct
mutually-dependent Let/Let or Let/Fn cycles where no order works — that's
where lazy thunks land.

## Hard blockers (compiler cannot function without these)

- **subprocess spawn — done.** `System::IO::run(program: String, args: List<String>):
  ProcessResult|IOError` (`stdlib/process.yafl`) spawns a PATH-resolved program
  through the IO threadpool (`posix_spawnp`, stdin = /dev/null), capturing stdout,
  stderr, and the exit code. A non-zero child exit is a successful `ProcessResult`,
  not an error; only a failure to start the program is `IOError`. argv crosses the
  foreign boundary as a single NUL-separated String (the separators double as the
  C-string terminators), split back out in `process_run` (`io.c` / `io_thread.c`,
  `IO_OP_SPAWN`); stdout/stderr captured into growable non-GC buffers via `poll()`
  (deadlock-free). Tests: `tests/test_process.py`. A YAFL-written compiler can now
  invoke clang directly.

## Performance / scaling

- **Compiler self-throughput** — the Python compiler runs the suite in ~33 min
  today. A YAFL compiler will be slower (per-call dispatch through generics,
  allocation per AST node). It needs to compile itself in a tolerable time,
  gated on: generic monomorphisation cost, GC throughput under high
  allocation, and whether `[tail]` covers enough of the deep traversal paths.
- **Compile times scale with stdlib size** — every example pulls in the whole
  stdlib. As the stdlib grows to support bootstrap, compile times balloon.

# String ops efficiency

String::startsWith and String::endsWith needlessly do heap allocations

# Tail-call optimisation — done

Both sync and async functions now get tail-call optimisation. The state
machine path re-expands `Call(musttail=True)` back into `Call + Return` via
`__unroll_musttail_for_state_machine` so the terminal-block writer's
`task_complete` sequence still fires; the hot path keeps the `musttail`
so clang emits `return foo(...)` and TCOs it. `strip_unused_operations`
treats `Call(musttail)` as a terminator and guards its worklist against
re-queuing seen indices, so cyclic CFGs converge.

Landed in `3c5f5c4`. The `stdlib/json.yafl` lookahead workaround
(`_strBody` bulk-consume of ~1 KiB per recursion) predates the fix and is
no longer needed for correctness — keep it as a perf win or simplify if a
profile says it doesn't matter.


# Generic class field reads — done

`DotExpression.get_type` and `DotExpression.check` now substitute the
receiver's `ClassSpec.type_params` into the field's declared type via
`_substitute_class_type_params` (`pyast/expression.py`). The substitution
flows recursively through nested `ClassSpec`s so `b: Box<Int>; b.inner`
yields `List<Int>` rather than the bare `T` placeholder.

`LetStatement.check` and `ReturnStatement.check` use `is False` to compare
trivially-assignable results, matching `BlockExpression.check`'s treatment
of `None` (undecided) as acceptable. Landed in `63f7de5`.

Follow-up `Set<T>` rewrite from enum-wrapper to `class Set<T>(_d: Dict<T,()>)`
also landed in `63f7de5`; field accesses (`s._d`) now type-check directly
and all four public functions dropped their `match` boilerplate.


# argv / process args — done

`stdlib/args.yafl` exposes `args(): List<String>` built on the foreign
helpers `sys_argc` / `sys_argv_at`. Callers get the user-supplied
positional args without the program path. Landed in `f9ad565`.


# StringBuilder — done

`stdlib/string.yafl` provides a `StringBuilder` for amortised-linear
string concatenation; `format` is the primary user. Eliminates the
O(n²) `+`-concat hazard for code that produces tens of KB of output
(notably codegen). Landed in `f9ad565`.


# format / printf — done

`stdlib/format.yafl` provides `format(template, args...)` with
per-arity overloads up to four arguments; each argument's value is
rendered via its `Show<T>` instance. Diagnostics and assertion
messages no longer need `+`-concat. Landed in `f9ad565`.


# Stdlib list ops & filesystem — done

`stdlib/list.yafl` now provides `findIndex<T>`, `partition<T>`, and
`groupBy<T,K>` alongside the existing `fold`/`map`/`filter`/etc.
`groupBy` returns `Dict<K, List<T>>` with `where BasicEquality<K>`.
All three are implemented in terms of `fold`.  An earlier draft used
direct cons-list recursion as a workaround for a lambda-lift bug; that
bug (collision on `lambda@<line_ref.hash6()>` across monomorphisations
of the same template) was fixed by switching the lambda-class naming
to a path-based scheme — `lowering/lambdas.py:__collect_lambda_paths`
records the enclosing-statement path for every `LambdaExpression` and
`__create_unique_name` mixes the path into the class name so two
monomorphisations of `fold<T,U>` produce two distinct classes.

`stdlib/fs.yafl` is new: `exists(path): Bool` (errors map to false),
`stat(path): FileInfo|IOError` with a public `class FileInfo(size,
mtime, isDir, isRegular, mode)`, plus a `[linear,final] Dir` cursor
(`openDir` / `next` / `[terminal] close`) and a `listDir(path):
List<String>|IOError` convenience that opens, drains, and closes the
handle.  All ops dispatch through the existing IO threadpool —
`io_thread.c`'s switch grew five new cases (`IO_OP_FS_EXISTS`,
`IO_OP_FS_STAT`, `IO_OP_DIR_OPEN`, `IO_OP_DIR_NEXT`, `IO_OP_DIR_CLOSE`)
and `io_job_t` carries a small `fs_aux: fs_file_info_t*` and `dir:
dir_t*` for those ops.  The `FileInfo` is pre-allocated on the worker
before STAT dispatch so the IO thread only writes scalar fields — the
allocation boundary rule from `[[feedback_io_design]]` is preserved.

Test coverage: `tests/test_runtime.py::TestListOps` (9 cases),
`tests/test_fs.py` (9 cases). The compiler suite is now 591 tests at
~18 min.


# Another specific heap layout optimisation

```
enum List<T>
  enum ListEmpty()
  enum ListFull(front: Chain<T>, rear: Chain<T>)
```

(`_ListNode`/`_Nil`/`_Cons` were renamed to the public `Chain`/`ChainEnd`/
`ChainLink` on 2026-06-12 — List is the build structure, Chain the zero-
allocation consumption view; see `chain`/`chainNext`/`chainLength` in
`stdlib/list.yafl`.)

Check if the ListEmpty() case uses runtime NULL in one of the fields as the signal, or if it
uses an extra field to distinguish. There is an optimisation opportuntiy here.

# JsonValue is complex — resolved (note was stale)

DO NOT re-investigate. Reviewed 2026-06-07: the JsonValue encoding is fine and
not an issue. (For the record: it's the recursive `_ListNode` cons cell that gets
heap-promoted as the cycle-breaker, not JsonValue itself — JsonValue stays a flat
by-value tagged-union struct. The generated C looks verbose because of the
type-segregated shared-slot packing, but it's correct and works.)

There is a SEPARATE, genuine question about more efficient enum *packing* (the
flat-tagged-union slot layout vs a sum-of-products / boxed-per-variant encoding) —
deliberately deferred, not a bug. Don't conflate it with this stale note.

# Parallel grep — done (as `examples/findstr`)

`examples/findstr.yafl`: substring search (no regex yet) over a folder hierarchy,
giving `__parallel__` a real workout — the file list is searched divide-and-conquer,
each half on a separate worker. Walks the tree with `fs.stat`/`listDir`, reads each
file, and prints `file:lineNo:line` for matching lines. Built by `examples/CMakeLists.txt`;
guarded by `tests/test_findstr.py`. Future: regex instead of substring, and once auto
parallelisation lands, drop the explicit `__parallel__`.

# Build system, libraries & examples — done

Project-folder compilation, manifest-based libraries (`.yl` packages), the
installed `yafl` toolchain (static-only runtime), and the standalone `examples/`
project are implemented. See docs/build-and-packaging.md.

# Parallel tuple construction

This is a core feature for supporting implicit parallelism. Any tuple construction would be
analysed for complexity, and if high each part could be pushed to a different worker. Additionally
sequences of non-dependent let statements could be grouped into tuple constructions so that
there are more parallel computation opportunities.

# Optimiser to reduce local variables

If different parts of a function use a variable declared as object_t*, but they don't overlap, 
they can share the same slot. This goes for heap frames for async functions as well, and of
course other types. This step would reduce heap usage. Doesn't really reduce stack usage as
the C compiler will do that anyway.

# Large strings — done

Resolved by multi-page object allocation (see "Lift the 16 KB per-object size
cap"): a large string is a single object spanning multiple pages — no
compound-object scheme needed.

# IO readline — done

`IO.readLine(): (io: IO, v: String|IOError)` is implemented in `stdlib/io.yafl`:
reads one byte at a time, stops at `\n`, skips `\r`, and returns a partial line
on EOF-with-bytes (EOFError only when no bytes were read). Note this is distinct
from the buffering issue below — readLine still goes through the buffer-filling
`read`, so on a TTY it shares the "IO TTY input" latency problem until that lands.

# IO TTY input — done

Fixed in `yafllib/io_thread.c` (IO_OP_REFILL): the read path used
`fread(io->buf, 1, IO_BUFFER_SIZE, …)`, which loops until the 8 KB buffer is full,
so interactive (TTY/pipe) reads blocked until 8 KB was typed or Ctrl-D. It now
uses a single `read()` syscall, which returns as soon as any input is available —
fixing the interactive block while preserving file read-ahead (so byte-at-a-time
`readLine` is still served from the buffer, not one syscall per byte). Test:
`tests/test_io_tty.py` (drives the process with a held-open stdin pipe).

# Tuple let grouping

A lowering pass groups all sequences of independent `let` bindings — those with
no data dependency between them — into a single tuple construct/destruct
statement. This is unconditional: every eligible sequence is grouped regardless
of cost. A later, separate pass will decide which grouped tuples to evaluate in
parallel based on a weighing function. The consequence is that independent `let`
bindings must not be assumed to have a defined evaluation order.

# Conditions (if / else if / else) — done

Implemented as `IfStatement` (`pyast/statement.py`). It is a **statement**, not
an expression — pure control flow yielding no value (the value-producing
conditional remains the ternary `?:`). `else` is optional; `else if` chains via
`ElseIfStatement` + `collapse_else_if`. Branches are pure scopes (a `let` inside
a branch is branch-local and does not escape); a branch ending in `ret` exits the
function, otherwise control falls through. Lowers to `JumpIf`/`Label`/`Jump` (no
Phi merge, distinct from the ternary). The condition must be `Bool`. Tests:
`tests/test_conditionals.py`, `tests/test_conditionals_runtime.py`.

DO NOT re-design or re-implement this — the design was re-derived from scratch in
discussion on 2026-06-07 only to find it already existed and matched. The original
"each block defines the same named values" sketch was NOT adopted: branch-local
`let`s do not escape, so an `else` is not required to "set" a downstream value.

# Loops — design under discussion, DO NOT implement

`[tail]` recursion (`lowering/tail_loop.py`) already covers the capability. Whether
to add surface loop syntax — and what it looks like — is an OPEN design question the
user is actively developing; we have not reached agreement. Do not implement or
re-propose a design until the user drives it. The sketch below is an early,
non-final note, not an agreed spec.

```
fun loops(x:int): int
  # Required default value if the loop is empty.
  let a = 1
  for i in 0 to 3
    let a = a+x
  ret a
```
is functionally equivalent to
```
fun loops(x:int): int
  let a = 1
  let a0 = a+x
  let a1 = a0+x
  let a2 = a1+x
  ret a2
```
which suggests that loops are compatible wiaddth the functional paradigm if
the inner loop type of 'a' is identical to the outer loop type, where the
value is referenced downstream.
```
fun loops(x:int): int
  let a = 1
  for i in 0 to 3
    let a = a+x
    break if a > 20
  ret a
```
A break statement should be safe as well, and in terms of recursion is
the procedural equivalent of a return statement. It still obeys the
functional paradigm, but having it inside conditions might imply that
else blocks are not required. I think that making the break statement
itself a condition helps to avoid this anti-pattern.

## `[tail]` on nested functions — done

Nested `[tail]` functions (and methods) are now lowered too (`lowering/tail_loop.py`),
so a `[tail]` loop can be written nested — capturing outer variables — instead of
a top-level helper that threads state through parameters.






## Fusible stream transformers via generic trait instances

STATUS 2026-06-25: DELIVERED end to end. Generic trait instances + `Stream<S,T,E>`
= `Result<T|None,E>` + StreamIO folded onto the trait + generic Lines/Numbered +
nested-generic-call inference + `[inline(always)]` fusion. examples/linenumbers
runs `stream |> toLines |> prependLineNumbers` over fully-generic instances, and
at -O3 the ENTIRE transform pipeline fuses into ONE async state machine (the
drain absorbs every `next` stage AND the recursive line-assembly loop — `[tail]`
lowers to a loop in the AST before the codegen inliner, so recursive loops inline
as loops, no unrolling), collapsing per-element continuation allocations. The
notes below are the ORIGINAL design write-up, kept for context.

OPEN (smaller): residual field-access-source inference (typed-let workaround);
promote Result/Never to a base module; `impl Trait` sugar for witness boilerplate;
automatic fusion (inliner ordering/budget) as the general alternative to the
opt-in `[inline(always)]`.

StreamIO (stdlib/io.yafl) is a working but interim design: a single concrete
`StreamIO(_thunk: (): _Step)` closure type, with the transformers (`toLines`,
`prependLineNumbers`) building more such closures. Every node memoises, which is
only actually needed at the IO *leaf* (re-reading IO is not repeatable); the pure
transformers memoise needlessly and, being runtime closures, defeat fusion.

The intended design is type-level: a carrier trait

```
interface Stream<S, U>
  fun next(stream: S): (stream: S, value: U|None)
```

with each transformer a dedicated generic type that wraps its source and is
itself a Stream:

```
fun toLines<T>(in: T): StreamLines<T> where Stream<T, String>
# StreamLines<T>(source: T, pending: String) : Stream<StreamLines<T>, String>
```

No memoisation in transformers (state lives in fields); composition is the
static type `StreamNumbered<StreamLines<StreamIO>>`, whose monomorphic `next`
chain the inliner can later fuse into one allocation-free loop.

WHAT WORKS TODAY (probed 2026-06-23): the carrier trait `Stream<S,U>` with a
concrete leaf, a generic consumer (`drain<S> ... where Stream<S, Int>`), and a
union-returning `next` compiles and runs.

THE BLOCKER (was): a generic trait *instance*. A wrapping transformer needs
`StreamLines<T>` to witness `Stream<StreamLines<T>, String>` for *every* `T`,
but there was no syntax for a generic `[trait]` instance.

SHIPPED TO STDLIB 2026-06-24 (stdlib/stream.yafl, tests in
test_generic_trait_instance.py). The REAL design compiles and runs as library
code: a `System::Stream<S,T>` carrier trait with `Map<S,A,B>` and `Filter<S,T>`
as generic instances, composed into the static type `Map<Filter<Count>>` —
`Count 1..5 |> filter odd |> map *10 |> sum` = 90. Plus a `Box`/`Wrap` test
case incl. recursively-nested wrappers. What landed:
  * Parse: `let [trait] _x<S,T>: … = … where C` and `typealias [where] _W<S,T>
    : P where C` (parser.py: __parse_let_generic, extended typealias rule).
    AST already carried type_params/trait_params on Let/TypeAliasStatement.
  * Scope: those declarations enter their generic scope on check/compile
    (statement.py — Let via the existing _initialiser_resolver, TypeAlias gets
    its own ResolverType wrap).
  * Monomorphise by constraint discharge (generics.py): a generic `[trait]` let
    is never referenced with explicit type args, so __generic_instance_refs
    unifies its implemented pattern `Box<Wrap<S,T>,T>` against each concrete
    `where` constraint to recover S/T and seed the witness instantiation. The
    constraint's inner types are already name-mangled by the concreteness gate,
    so __reinflate rebuilds structure from the recorded (name,type_args) and
    __remangle puts the recovered args back into bare monomorphic form. The
    witness's own `where` then becomes a fresh constraint — nested wrappers
    recurse.

STILL OPEN before this is stdlib-grade ergonomics (both pre-existing, separately
tracked — NOT specific to generic instances):
  * Member shadowing: a same-named trait call inside the witness method binds to
    the enclosing method; the prototype routes the recursive call through a free
    helper. Fixing resolution to prefer the `where`-constraint method by argument
    type is the clean fix.
  * Phantom type-param inference: a `T` appearing only in the return/`where` (not
    in any argument) can't be inferred, so calls need explicit `<S,T>`. Needs
    inference from the expected return type to thread through.
  * Witness boilerplate: the carrier-trait witness class + paired `typealias
    [where]` is verbose; a sugar that derives both from the instance `where`
    clause would make this usable in stdlib.
  * No `map`/`filter` constructor functions in stdlib/stream.yafl: they'd need
    explicit `<S,A,B>` anyway (phantom B), AND a free `map(source: S, …)` with an
    unconstrained `S` overload-clashes with `System::map` over List (the `where`
    constraint doesn't filter during overload resolution). Users construct
    `System::Map<…>` / `System::Filter<…>` directly for now. The clean endgame is
    List (and StreamIO) BECOMING `Stream` instances so there is one `map`/`filter`
    over the trait — fold the existing concrete StreamIO (io.yafl) onto this once
    the ergonomics land.

GENERIC ERROR CHANNEL 2026-06-24: `Stream<S,T,E>` — element
`Result<T | None, E>`: `Ok(value)` | `Ok(None)` (clean end) | `Error(e)`
(failure, terminal). Error and "done" are orthogonal: Error is forwarded
uninterpreted by transformers and terminates; the inner `T|None` is the shared
protocol every stage knows and can originate (a sentinel filter emits `Ok(None)`
to stop early). New stdlib types in stream.yafl: `enum Result<T,E> = Ok(value:T)
| Error(error:E)` and uninhabited `enum Never` (so `Stream<S,T,Never>` cannot
fail). Map/Filter forward Ok(None)/Error. This needed the generic-enum
variant-match bug fixed first (done — see below).

DONE — StreamIO folded onto the generic trait (io.yafl): the IO byte stream is
now `System::Stream<StreamIO, String, IOError>`, element `Result<String|None,
IOError>`. The `StreamIO.next()` method is gone — step via
`System::streamNext<StreamIO, String, IOError>(s)`. Proven: the generic
`System::Map` composes over a real file's line stream
(test_io_stream.test_generic_map_over_io_lines).

DONE — generic stateful transducers `System::Lines<S>` (line splitter, stateful
many-to-many) and `System::Numbered<S>` (1-based line numbering) over ANY
`Stream<S, String, E>` (stream.yafl). Lines<S> tested over a pure source
(test_generic_trait_instance.test_generic_lines_splitter). Constructed directly
(`Lines<S>(src, "")`), like Map/Filter. io.yafl keeps its CONCRETE
toLines/prependLineNumbers (StreamIO→StreamIO) so the example pipeline stays one
type and infers cleanly; the generic versions are the general primitives.

FIXED 2026-06-25 — generic inference through NESTED generic calls. The root
cause was ordering in CallExpression.compile: it compiled the FUNCTION (and
inferred its generic params) before the ARGUMENT, so for `c(wrap(x))` the
argument's type was still `Wrap<S>` (placeholder) when c's S was inferred — c's S
came out non-concrete and never monomorphised. Fix: compile the argument first,
then infer the function's params from its now-resolved type (one reorder in
pyast/expression/call.py). Proven: generic transformer FUNCTIONS now chain via
`|>` with full inference (`Feed |> mapped` → 60). Tests:
test_nested_generic_inference.py. Full suite 673 green.

DONE — toLines/prependLineNumbers are now GENERIC (`System::toLines<S>`/
`prependLineNumbers<S>` returning Lines<S>/Numbered<S>); io.yafl's concrete
versions removed. examples/linenumbers.yafl runs the fully-generic pipeline:
`stream |> toLines |> prependLineNumbers` drained by generic `writeToFile`.

RESIDUAL inference edge (minor): a FIELD-ACCESS source into a generic `|>` chain
(`a.stream |> toLines |> …`, or an untyped `let s = a.stream`) doesn't infer —
pin it with a type (`let stream: StreamIO = a.stream`) and the whole chain
infers. The nested-call fix covers constructor/call sources; only a
DotExpression / untyped-let source still needs the hint. Same family as the
nested-call fix — worth chasing the field-access/untyped-let case down to make
even that explicit-type hint unnecessary.

NEXT: that residual field-access-source inference case; promote Result/Never out
of stream.yafl to a base module.

FIXED 2026-06-24 — generic-enum VARIANT match at a concrete instantiation
(`fun f(x: End<Int>) ret match(x) (d: Done)/(f: Failed)`) crashed codegen: the
subject's all_leaf_names were un-mangled while the arm's were `$generic$`-mangled
(two monomorphisation passes disagreed). union_repr.leaf_id now matches leaves by
BASE identity (strip `$generic$…`), correct-by-construction on tag indices.
Test: test_generic_enum_concrete_match.py. (Whole-enum match and generic-position
variant match — Chain/List/Dict — were always fine.)

stream.yafl uses NO `typealias [where]` (user decision 2026-06-24): the `[trait]`
let alone registers an instance for monomorphisation discharge; the alias's only
extra effect is making a CONCRETE instance an AMBIENT implicit where-spec
(get_implicit_where_specs), so callers could use the trait without declaring
`where Stream<S,T>`. Streams want that obligation explicit, so the aliases are
gone (and a GENERIC alias was always a no-op — never concrete, never registered).
The operator instances in integer.yafl KEEP their aliases — that ambient path is
exactly what makes `1+2`/`show(x)` work without an explicit where.

FIXED 2026-06-24 — nested generic type args ending in `>>`/`>>>`
(`sumStream<Map<Count,Int,Int>>`) now parse. The tokeniser fuses a `>` run into
one token; parselib.close_angle() peels a single `>` off the front (pushing the
remainder back) and replaces discard_sym(">") in the two type-arg-list rules.
Shift/comparison operators are untouched (close_angle only fires after a matched
`<` opening a type-arg list). Tests in test_parser.py.

OPEN 2026-07-17 — GC use-after-free, pre-existing on compiler-port (found
while validating the prune-pacing decoupling; unrelated to it — proven by
stash baseline). Two surfaces of what is likely one bug:
  * test_gc_pressure: FLAKY poison DANGLE abort — a live object's field
    points at a reclaimed one ("live 0x... (vt=node) field#1 -> reclaimed
    0x...", cycle ~23). Intermittent ⇒ a race, not a deterministic
    lifetime error.
  * test_large_objects: deterministic SEGFAULT in
    mixed_sizes_survive_gc_churn.
Repro: yafllib/build/release && ctest -R "test_gc_pressure|test_large_objects"
--output-on-failure (poison is on for all C tests via CMake ENVIRONMENT).

DONE 2026-07-17 — GC prune pacing decoupled from the scan ratio (user
ruling: deriving prune from scan is backwards — a lower scan ratio stretches
sweep completion and grows the garbage backlog per completed sweep, exactly
when prune must not slow down). GC_PACE_PRUNE_PAGES (default 64, the old
effective 16x4) with its own YAFL_GC_PRUNE_PAGES env var; YAFL_GC_STEP_PAGES
now tunes scan only.

MOSTLY FIXED 2026-07-27 (was OPEN 2026-07-17) — Bool-through-union-slot
precision inconsistency: the twin-minting site was phi_removal's copy
coalescing, which renamed the source's defining op by NAME only, keeping
the source's type — an i16 union-slot shard coalesced into an i8 Bool
ctor param left one variable spelled at two precisions. Beyond
uninit_check (name-keyed since), the twins broke async_lower's
(type,name)-keyed liveness kill and inflated frame layouts — the last
223 lines of whole-compiler Python-vs-port parity. Fixed in both
compilers: the coalescer substitutes the copy target's own StackVar
spelling (name AND type) via replace_params. The ops.yafl let-bind
workaround (opWsvMove/JumpIf/Call) can likely be retired now; the
underlying slot-read/boxing precision design note stands.

OPEN 2026-07-17 — union-member field read miscompiled on REPEATED access.
Reading a narrowed union member's field more than once (e.g. fl.flParamSpecs
where fl: FrLoop came from GenFrame = FrLoop|FrBlock, re-read per loop
iteration) returns a SHORT/garbage value on later reads though the first read
is correct — a live abort (forceNth on an apparently-4-elem list hit empty at
index 2) that a length guard reading the same field passed moments earlier.
Worked around in generate_expr.yafl genRecurOn (read the frame's lists ONCE,
thread the plain Lists down). Likely same root as the bool-slot precision bug
(both union-slot read/repr). Repro: the pre-fix genRecurArgsStep re-reading
fl.flParamSpecs; the io-copy [tail] loop in examples/helloWorld.yafl triggers
it. Real fix in union_repr read-field / slot codegen — task #15.

CLOSED 2026-07-21 (551edb0) — PORT 8: json_pretty.yafl C now byte-identical
(18/18). The void slot was an UNBOUND generic placeholder surviving to
codegen, from two port bugs in one family — specs compared by uid string
where Python compares structurally (uid "" on placeholder-bearing/unresolved
specs made compares silently defer or conflict): (1) unify's union
set-fallback matched ground members by uid, so a raw NamedSpec ground member
deferred forever and collect's E never bound; (2) meetSpecs had no UNION arm
at all (and no CALLABLE arm), so a $pipe let that latched a generic call's
raw declared-result view could never refine to the ground view — meet on the
holey union conflicted every pass, freezing writeStream's E. Pinned by
corpus_converge/pipe_generic_result.yafl and the stdlib+json_pretty
whole-program converge entry.

# Copy elimination for object copy-and-modify (`with`) — in-place update lowering

A plan for a late IR lowering stage that removes the heap copy behind
copy-and-modify (`with x(f = v, …)`, and the broader *functional update*
shape) by rewriting the modification **in place into the original object**,
when three facts are provable:

1. we hold the **only reference** to the object;
2. **no GC safe point** can occur between the establishment of that reference
   and the in-place modify code;
3. after the modification, the **original reference is never used again**.

Once the three preconditions are proven, the field writes are **in-effect
initialisation writes** — even when they overwrite a field that already holds
a value — so **no write barrier or old-value shading is needed** (§6), and
the rewrite emits plain stores into the original object.

This is a design/plan document. Nothing here is implemented.

---

## 1. Why this is worth doing

`with` today expands (in `pyast/expression/with_expr.py`) into

```
let $ws = subject
let $w0 = v0        …           # typed as the FIELD, per replacement
cond = yafl_same($w0,$ws.f0) && yafl_same($w1,$ws.f1) && …
Ternary(cond,
        $ws,                      # bit-identical: return the ORIGINAL
        <copy of $ws mixing carried fields and replacements>)
```

The copy is a constructor call (`Class(…)` / `Leaf(…)`) that **allocates a
fresh heap object** and **reads every field of the subject** to fill it.
Costs, per `with`:

- one `NewObject` heap allocation (+ zero-fill, vtable tag, allocation fast
  path, possibly a slowdown on the GC pacing clock);
- a full field-read+write pass over the object — including the carried fields
  that *do not change at all*;
- after the allocation the old object and the new object exist side by side
  until the old one dies.

When the subject is dead after the `with` (the overwhelmingly common case
for a purely-functional update), the whole copy is wasted work: the object
will never be observed in its pre-update state by anyone, so mutating it in
place is unobservable. The `with` design already guarantees this is sound at
the language level — the two ternary arms are structurally identical and
identity never surfaces to user code (`with_expr.py` module docstring,
`docs/preserving-rewrites-design.md`).

The payoff is largest after inlining (-O2/-O3): a fused pipeline stage
boundary becomes `NewObject` + straight-line field writes in the caller, the
exact shape a def-chain pass can see and rewrite. It is exactly the same
economics the existing in-place passes exploit (`docs/compiler-internals.md`
§6: `string_accumulation` deforests `acc + x` into in-place builder writes;
`array-builder-design.md` shows the "construction window" discipline).

---

## 2. A companion correctness bug: `with` on a class subject loses the dynamic class

Fix this before the pass matters: for a class-typed subject, `with` builds a
copy of the **static** class, not the dynamic one.

**Reported behaviour.** A `Shape`-typed reference may hold a `Circle` (classes
extend via `:` — `class Circle : Shape`; the `[final]` attribute forbids
extending, `docs/guide.md`). `with` on that reference constructs a `Shape`,
not a `Circle`. Confirmed against the code:

- `with_expr.py:153-158` — the `ClassSpec` branch of `__expand` calls
  `construct(cls.name, cls.parameters.flatten(), …)` where `cls` is the
  statement of the **static** type (`resolver.find_type(stype.name)`), and
  carried fields are read with `DotExpression(ref("$ws"), bare)` — `$ws` is
  typed as the static class. There is no dispatch on the runtime class.
  The result is a `Shape`: Circle's own fields are dropped, and its vtable is
  replaced by Shape's. The type system cannot see the loss while the value is
  used through `Shape`, but `hashOf`/`refeq`/member dispatch would.
- The **enum** path (`with_expr.py:159-182`) does the opposite: it builds a
  `MatchExpression` over the valid leaves, each arm constructing the **leaf**
  with the *leaf's* fields carried through the arm binder `$wx`
  (`_leaves`/`_arm`, `with_expr.py:228-242`). The module docstring
  (lines 15-16) credits exactly this: "the match's leaf dispatch … preserves
  the DYNAMIC leaf under a root-typed subject", and
  `test_root_typed_subject_preserves_dynamic_leaf` enforces the ruling for
  enums.
- No equivalent exists for classes, and it has gone unnoticed because the
  only class `with` tests use `class [final] P2(…)` — a final class, where
  the static type *is* the dynamic type.

**Fix (mirrors the enum path exactly).** For a `ClassSpec` subject whose static
class is not `[final]` and may be extended:

1. Enumerate the possible **dynamic leaves**: the static class itself (it can
   be constructed directly — a parent class with a param list is still a
   value) plus every transitively-derived descendant. Classes record only
   their parents (`ClassStatement._all_parents`, `classdef.py:362`), so add a
   **reverse subclass index** — a derived registry in the same style as
   `ResolverRoot.is_complex_root`/`is_boxed_leaf` (`resolver.py:166-172`) —
   or compute the closure once from the compiled statement set.
2. Expand to `MatchExpression($ws, arms=…)`, one arm per leaf:
   `(bx: Circle) => Circle(<carried fields read through $bx>, <replaced
   static-visible fields>)`. Reading carried fields through the **binder**
   (not `$ws`) is what lets Circle's own fields survive — `.color` is not
   visible on a `Shape`-typed `$ws`, but is on a `Circle`-typed binder.
   Replacement names stay restricted to static-visible fields (already
   enforced by `check`, `with_expr.py:205-211`).
3. Class-subject dispatch needs machinery that does not yet exist: `match`
   handles only enum/union subjects (`match.py:1099` asserts
   `EnumSpec`/`CombinationSpec`). The runtime already has the right test:
   `object_is_instance` via `ObjVtableEq` (`param.py:367-410`) is the
   *transitive* "is-a" check over the vtable's `implements_array`. Add a
   class-subject branch to `union_repr.classify`/`match.generate`: guard each
   arm with `ObjVtableEq(subject, obj_<leaf>)`, most-derived first, the static
   class last as fallback. A `[final]`/single-leaf class keeps today's direct
   construction (no dispatch) — existing codegen is unchanged.
4. Widening each arm to the subject's static class is a **passthrough**:
   subclass→base is pointer identity (`needs_conversion` returns False for
   the class→wider-class case, `conversion.py:159-218`).

Test this independent of the pass — parity with
`test_root_typed_subject_preserves_dynamic_leaf`:
`class Shape(radius)`, `class Circle : Shape(color)`; `dim(s: Shape)` must return
the dynamic `Circle` with its own fields carried and the flat field adjusted;
a `[final]` class must behave as today.

**Interaction with this pass.** After the fix, class `with` fragments are the
same inlined match-arm shape as enums once IR inlining runs (§3.1): the binder
is a `Move`-defined variable, so Proof 1's alias set covers it. Single-leaf and
`[final]` classes keep the direct shape. The bug fix is a prerequisite for
`with`'s own semantics at **every** -O level; the elimination pass just
benefits from the shape unification.

---

## 3. The IR shapes to recognise

The pass looks for a **copy fragment**: a straight-line run of ops inside one
function that together form "build a fresh copy of `x` with some fields
replaced". Two shapes reach the IR:

### 3.1 Inlined shape (post -O2/-O3 IR inlining) — the shape the pass needs

```
…                                   # prelude (guard computation, subject load)
x   = <def>                         # param / let / Phi / call result / NewObject
t0  = ObjectField(x, f0)            # carried field loads
t1  = ObjectField(x, f1)
n   = NewObject Foo                 # ← the allocation to eliminate
n.f0 = t0              (fresh-like)  # carried stores
n.f1 = t1              (fresh-like)
n.f2 = w0              (fresh-like)  # replacement store (w0 = the $w0 let)
r   = n / Phi[(…, x), (…, n)]        # result; in the `with` shape this is a
                                     # ternary Phi merging (then: x, else: n)
```

Exactly the shape `NewExpression.generate` emits (`new.py:95-99`: `NewObject`
then `Move(ObjectField(…, fresh=True), StructField(params, _i))`), after
`branch_threading`/`copy_propagation`/`struct_folding` have collapsed the
constructor-call preamble so the writes read the subject's fields directly
(via `ssa_defs.resolve_value` on the `NewStruct`-packed arg slot).

The pass runs only at -O2 and above (§7), where IR inlining has already
lowered **every** copy — class ctors (`classdef.py` codegen) and complex-enum /
boxed-leaf construction (`union_repr.py:571`) — to this fragment. The new §2
match arms collapse onto the same shape once the match's per-arm constructor
is inlined. After §2's fix there is no separate -O1 "callee shape" to cover.

### 3.2 Callee shape (below -O2; and at -O2 when the inliner declines)

Before IR inlining a copy is a `Call(Foo$ctor, …)` whose arguments read `x`'s
fields. The pass does **not** fire on it in v1 — see §9. Since the pass is
gated to -O2+, this only affects sites the inliner refuses, not a whole
optimisation level.

---

## 4. The three proofs — the core of the pass

The pass is sound when (1), (2), (3) below all hold. Any op-level ambiguity
fails closed (no rewrite).

### Proof 1 — we hold the only reference

Build the **alias set** `S` of stack vars whose value is provably the *same
object* as the subject `x`, transitively:

- start `S = {x}`;
- add any `StackVar` defined by `Move(sv, s)` where `s ∈ S` (including via
  a `Phi` whose sources are all in `S`, i.e. a loop-carried/two-arm merge that
  provably flows the one object);
- using `lowering/ssa_defs.py` (`single_defs`, SSA single-definition is
  enforced by `ssa_validate`) chase copies to their sources.

Then prove, across the **whole function** (publication before the fragment
creates outside references as surely as during it):

- no `sv ∈ S` appears in the parameters of **any** `Call` op (a callee could
  retain it);
- no `sv ∈ S` is **written to the heap or a global**: never the *source* of a
  `Move` whose target is an `ObjectField`/`ArrayElement`/`GlobalVar`, never a
  slot value in a `NewStruct`/`NewStructTyped` that feeds such a store, never
  shaped into a closure environment;
- no `PointerTo(sv)` (address taken) anywhere;
- no `sv ∈ S` is marked `saved_vars` on any `Call` **before** the fragment
  (async-lowering would later promote it into the task-heap state object —
  itself a publication; in practice §4.2 already refuses any suspend in the
  window, but the publication must be refused regardless of where it sits).

Any match → uniqueness is unproven → no rewrite. Note this is a **static**
argument: it does not use runtime reachability, it proves `x` cannot have a
second owner. (Cross-thread reachability is covered by the same rules: a
second thread could only reach `x` through a reference the program created,
and every reference creation is a use we see in SSA.)

### Proof 2 — no GC safe point between the anchor and the modify code

Define the **window**: the contiguous op sequence from the subject's *anchor*
through the op *after* the last redirected store, inclusive.

- anchor of `x`:
  - *parameter* → function entry (the value's "birth" is the caller's call
    edge, a safe point that fixes nothing for us; everything after entry must
    be clean);
  - *defined by `Move`/`let`* → that defining op (birth of the handle);
  - *defined by `Phi`* → the phi's merge point (birth of the handle);
  - *defined by `NewObject`* → the op *after* the allocation (the object's
    birth; relocation can only occur at *subsequent* safe points, so the
    allocating op itself is allowed);
  - *defined by `Call`* → the op after the call, for the same reason.

Forbid **any safe-point-bearing op in the window**:

| op | why it is a safe point |
|---|---|
| `NewObject` | allocation polls `gc_alloc_tl.safe_point_request` (`yafl.h:596`); the slow path runs cycles. |
| `Call` with `may_suspend` | the task parks; the scheduler can run cycles / a root scan at any time. |
| any other `Call` (even `is_sync`) | a sync callee may **internally allocate**, and an allocation inside the callee polls and can run a cycle with our frame live beneath it. Our pointer may sit in a callee-saved register the conservative scan cannot fix up; after compaction it would be stale and the redirected stores would land in a forwarding stub. |

Conservatively v1: **no `Call`, no `NewObject`, no address-taken `RuntimeInvoke`
of unknown allocation behaviour** inside the window. This is deliberately the
same discipline `array-builder-design.md` describes as "no GC boundary falls
inside" a construction window — here proved, not by inspection.

Explicitly **not** safe points, and permitted in the window:

- the redirected field stores themselves: plain memory writes with the barrier
  elided (§6) — no allocation, no poll, no shade;
- the announce call (§6) — pure atomic flag stores, no allocation, no
  suspension;
- `GC_SAFE_POINT` polls we don't emit for these ops (generated straight-line
  field code contains none).

Refinement (future): add a whole-program **`does_not_allocate(fn)`** effect —
`sync` *and* body contains no `NewObject` and no `may_suspend` call and only
`does_not_allocate` callees — computed like `sync_inference.compute_sync_names`
(`sync_inference.py:334`), and permit `does_not_allocate` calls in the window.
This widens the fragment across small pure helpers (the `yafl_same` guard is
already an inline C macro, so the copy shape barely needs it).

### Proof 3 — the original is never used again after the modify

After the *last* redirected store, no variant of the subject may be **read**,
on any path that reaches the stores. Because SSA reads are plain `RParam`
occurrences, this is a scan: every op (including `Phi` sources, `JumpIf`
conditions, `Return` values, `Call` parameter packs) after the last store must
mention no `sv ∈ S`, except the two legitimate classes:

1. reads that **dominate** the stores — program-order-before on every path,
   i.e. the subject's value is consumed before it is mutated;
2. reads on paths that **never reach** the fragment's stores — the
   un-changed arm. This is exactly the `with` ternary's `then` arm:
   `Ternary(guard, $ws, <copy>)` reads `$ws` as a Phi source, but that read is
   guarded by the ternary condition and simply does not execute when the
   modifying `else` arm does. In the rewritten IR both arms collapse onto the
   same object (§5), which makes the identity of the two arms *even more*
   obviously unobservable.

A `Return` of an `sv ∈ S` on a path that reaches the fragment is refused
(conservative): the caller then holds a reference to an object the fragment
would mutate in place.

The `with` guard itself (`yafl_same($w0, $ws.f0) && …`) reads `$ws` **before**
the fragment; class (1) — fine.

### Why these three together are sufficient

- (1) no other reader/owner exists, so no *observer* can see the torn
  intermediate state between two redirected stores, and no other thread's
  conservative roots contain the address;
- (2) no compacting root scan runs inside the window, so the object cannot be
  relocated while our (possibly register-held) pointer is live; the writes
  land in the live copy;
- (3) after the window the object is frozen again at its new contents, so the
  runtime's immutability invariant ("every copy of one holds the same bytes
  forever", `yafl.h:285-287`) holds from the moment anyone else can look.

---

## 5. The rewrite

Given a proven fragment (object type `Foo`, subject `x`, fresh copy register
`n`):

1. **Delete** the `NewObject Foo → n` op (the allocation) — later
   deadstores/trim cleans anything it was the only reason for; better, delete
   it explicitly.
2. **Reroute every replacement store** `Move ObjectField(n, f, fresh=True), src`
   → `Move ObjectField(x, f, no_barrier=True), src`. This is **not**
   `fresh=False`: `fresh=False` would emit `GC_WRITE_BARRIER` for the prior
   occupant's shading, which is exactly what §6 shows is unnecessary — the
   prior occupant is provably dead. Add a new `ObjectField` flag
   `no_barrier: bool = False` (comparison-excluded, like `fresh`), honoured by
   `ObjectField.to_c_store` (`param.py:779-788`) as "skip `GC_WRITE_BARRIER`".
   Do **not** reuse `fresh` for this: `fresh`'s contract is "the field's prior
   value is NULL (allocator zero-fill)"; here the prior value is a *provably
   dead object* — a different invariant other passes rely on `fresh` to mean.
3. **Drop every carried store**: a store whose source provably *is* the
   field's current value (`resolve_value` of `src` == `ObjectField(x, f)`,
   after copy-prop) is a self-store; it changes nothing, and emitting it would
   only pay the pointless shade. Only replacement stores survive.
4. **Insert the announce** (§6) before the first surviving store, **only when
   at least one surviving store writes a pointer-typed field** (a scalar-only
   replacement installs no young edge, so there is nothing to protect).
5. **Substitute**: every reference to `n` after the fragment (the result
   consumer — `Move`, `Phi` source, `Return`, match-arm slot pack) becomes
   `x`. The `with` shape's joining `Phi` then reads `(then: x, else: x)` —
   a single-value merge the later `phi_removal`/copy-propagation collapses,
   leaving the ternary to return the object outright.
6. **Delete now-dead carried loads** (`t = ObjectField(x, f)` whose sole
   reader was the dropped carried store). Prefer letting
   `deadstores.eliminate_dead_stores` do this uniformly rather than hand-rolling
   the liveness.

No `is_mutable` vtable flag is set, and none is needed: we never extend a
write window across a safe point, so the collector's mutable-page/compaction
exemption machinery is irrelevant. Setting it would be a global, per-*type*
pessimisation (every future instance of `Foo` would lose compaction) — this
pass must not do that.

---

## 6. Runtime interaction — no shading, and the announce

Two GC properties matter past the rewrite. One of them (old-value shading) is
**entirely unnecessary** here; the other (protecting a new young edge) needs a
single pre-existing primitive.

### Part A — no SATB shading is needed

`GC_WRITE_BARRIER` (`yafl.h:693`) / `_gc_write_barrier2`
(`object.c:2989`) exists to preserve the *snapshot-reachable* set
(`atomic_gc_object_seen_by_field`, `object.c:1353`): an object reachable at a
cycle's open, whose only path is a field the mutator overwrites before the
tracer reaches it, must be shaded or it dies despite being in the snapshot.
The barrier only ever matters for occupants whose **only** path is the field
being overwritten — any other surviving path re-marks them each cycle anyway.

In this pass that prior occupant is exactly the case the proofs rule out:

- its only path is `x.f` — any other path to it passes through a reference the
  program created, all of which Proof 1 accounts for (overwriting `x.f` after
  copying its value elsewhere is safe too: the copied reference re-marks the
  object from that path at every subsequent cycle open);
- nothing reads `x`'s old contents after the window (Proof 3), so no scan
  *after* the store can need the old value; a scan *before* the store sees a
  value that is, by (3), as good as garbage already — retaining or freeing it
  is unobservable.

So the overwritten value is **dead the instant the store lands**, on every
execution. The store is semantically the field's *first and only-establishing*
write from the program's point of view — the same status a fresh object's
NULL-predecessor store has, with the "prior value is NULL" claim replaced by
"prior value is proven dead". Shading would only keep dead memory alive for a
cycle. `no_barrier=True` (§5.2) is exactly right, and no page-dirtying or
rotation bookkeeping duty rides on the elided barrier.

### Part B — the single remaining runtime duty: the announce

The rewritten store may install a reference to a **young** object (a
replacement `$w0`, allocated in the prelude) into a field of `x`, whose page
may have aged into the old generation. Minor cycles skip old pages unless the
page is `dirty_old` (`yafl.h:461-468`), and the barrier-free store gives the
collector no other signal — the young referent could be pruned from under the
field, dangling it. This protects the **new** occupant, so it is orthogonal to
the shading removed in Part A (nothing to do with the prior value's
snapshot-retention).

The runtime already has the right primitive: `gc_note_late_write`
(`object.c:1034`) unconditionally sets the page's `redirty` flag (and the
process-wide `gc_redirty_requested`), demoting the page back into the
collection rotation at the next cycle open — the Dekker-handshake protection
for the promotion race. The annotation is general and costs two atomic stores.
Copy-on-write never needs it (the fresh object and its referents share one
young birth window); in-place writes inherit the subject's age.

**Plan:** before the first surviving pointer store (only then, §5.4), emit a
discard-anchored `RuntimeInvoke("gc_note_late_write", x)` as a
`Move(…, keep=True)` — the same anchor pattern `ops.py` documents for
`task_on_complete` (`Move.keep`, `ops.py:45-55`). It is not a safe point (no
allocation, no suspension), so it does not disturb Proof 2.

This announce is **required** for correctness in the general case — the 3
preconditions do not remove it, because it protects the replacement value
*after* the window ends. Two ways to avoid it entirely:

- a subject provably still on a young/unrotated page at modify time (defined
  by a `NewObject` in this function with no intervening safe point) needs no
  announce — the young page is scanned in the next minor cycle regardless;
- this is not worth a separate proving rule in v1, but it is the natural
  zero-overhead refinement.

---

## 7. Pass placement in the pipeline

New module `compiler/lowering/copy_elimination.py`, application pass like
`struct_folding.py:22` (`def eliminate_redundant_copies(app) -> Application`,
per-function, functional style, frozen dataclasses).

Insert **after the -O2 inlining stage and before `phi_removal`/`sroa`** in
`__create_c_code` (`compiler.py`), gated on **`optimization_level >= 2`**:

- at -O2/-O3 IR inlining has already lowered every copy (class ctors, enum
  leaves, and §2's match arms) to the §3.1 fragment — the pass sees **one
  uniform shape**, which is the point of the -O2 gate;
- it must be **before `phi_removal`** (`compiler.py:337`): the uniqueness
  proof leans on SSA single-definition (`ssa_validate`, `compiler.py:203`);
- it must be before `sroa`/`stack_promotion`/`async_lower` so the savings
  ride (the mutated object is, after all, live across any later suspension
  that the *result* participates in — that is fine; we only mutate inside a
  safe-point-free window, the window's end is where the object becomes
  ordinary again);
- each function runs the small copy-prop/`ssa_defs.resolve_value` chase that
  exposes the shape and the `Phi`-collapse that follows; run the pass once
  (not inside a fixpoint) for cost; iterate if measurements later justify it.

Suggested wiring (exact edit site is `compiler.py`, inside the
`if optimization_level >= 1:` block, after the inlining/fixpoint stages):

```python
    a = lowering.copy_elimination.eliminate_redundant_copies(a)
    a = lowering.trim.removed_unused_stuff(
        lowering.deadstores.eliminate_dead_stores(a))
```

---

## 8. Restrictions for v1 (and why)

| restriction | reason |
|---|---|
| run only at `optimization_level >= 2` | below that, copies are still constructor `Call`s (`§3.2`); nothing to rewrite, and -O0/-O1 keep their exact current codegen. |
| exclude `Object.is_mutable`, `Object.is_pinnable`, `Object.is_foreign` subject types | their compact/pin/late-write contracts differ; the clean immutable-object argument (§4, §6) is what the pass is built on. Task/state objects are in effect excluded by `may_suspend` anyway. |
| exclude subjects with an array/`length_field` | a copy must rebuild the trailing storage; that is not a field store. |
| only the *inlined* fragment shape (§3.1) | class-subject copies that survive as `Call Foo$ctor` (inliner declined) are out — see §9. |
| refuse any `Call`/`NewObject`/unknown-allocating `RuntimeInvoke` inside the window | Proof 2, strict form. |
| refuse loop-carried / `Phi`-merged subjects whose every source is not also uniquely held | SSA uniqueness recursion; document, revisit after inlining statistics. |
| fragments may not **read** the fresh object's own fields (`ObjectField(n, f)` as a read) | derived-copy chains (`n.f2 = n.f0`) add def-chain chasing; safe v1 cut, natural extension later. |

---

## 9. Why -O2 (and the callee shape, as future work)

At -O1, IR inlining is off, so a *class*-subject copy — with or without §2's
fix — is still a `Call(Foo$ctor, …)`; the pass is **off below -O2**, so there
is no partial -O1 coverage to explain or special-case. Gating at -O2 gives the
pass a single, uniform, well-sampled shape and removes the earlier plan's -O1
budgeting entirely.

Future work: a **per-site specialisation** of the copy constructor would
extend the pass to -O0/-O1 and to -O2 sites the inliner declines. Prove the
constructor is a pure copy/rebuild (its body is exactly §3.1 with the subject
as parameter, applied only to field loads), clone it once as `Foo$modify`
whose stores target the subject parameter instead of a fresh `NewObject` *for
this call site* (the clone keeps the allocation for other callers), and
rewrite the site's call. This is deliberately *not* whole-function inlining.
(Check whether `--profile` suppresses IR inlining; if it does, the profiled
run is correct but finds nothing — the specialisation would also restore
coverage there.)

---

## 10. Testing plan

Follow the suite's end-to-end convention (`compiler/tests/`, compile a small
`.yafl`, run it, assert exit code):

- **-O0/-O1 regression**: pass is gated off; existing `test_with_expr.py` must
  pass unchanged.
- **The §2 bug fix**: a class-parity test mirroring
  `test_root_typed_subject_preserves_dynamic_leaf` — `Shape`/`Circle`,
  `with s(radius = …)` on a `Shape`-typed reference returns the dynamic
  `Circle` with its own fields carried; run at all -O levels.
- **Correctness across levels**: `with` programs (class subject, complex-enum
  subject, unchanged/guard-true path, replacement path, chained `with`,
  subject used in the RHS of a later expression — must *not* be rewritten
  there) compiled and run at -O2/-O3 with identical output, plus -O0/-O1
  parity. Include a `with` on a subject that *also* appears unmodified on a
  sibling branch (the ternary case) to prove no in-place write ever leaks to
  the un-changed path.
- **IR/C-emission assertions**: emit C with `-O2 -c` and assert (patterned on
  `test_mutable.py:26`) that the site contains no `object_new(obj_…)` for the
  copy, **no** `GC_WRITE_BARRIER` at the rerouted stores, and exactly one
  `gc_note_late_write` preceding the first surviving pointer-typed store.
- **GC stress** (patterned on `test_array_class.py`'s GC-interaction fills):
  force a major cycle via `gc_debug_major_now` between the subject's birth and
  the `with`, with a pointer-typed replacement and a surrogate such that a
  dangling young referent would immediately fault — proves the announce
  protects the young edge; and a second case with a scalar-only replacement
  asserting **no** announce is emitted. Run under valgrind.
- **Negative tests** (each must leave the allocation in place): subject passed
  into a call before the `with`; subject stored into a global; subject aliased
  to a second local used after the `with`; safe-point call (a `may_suspend`
  helper) inside the window; `[pinnable]`/`[mutable]`/foreign subject;
  subclass subject whose copy the inliner refuses.
- **Whole-suite** regression: `python -m unittest discover`.
- **Measurement**: allocation count before/after on a self-compile and on a
  representative stream fold (e.g. a `with`-heavy benchmark from `bench/`),
  plus a check that no affected vtable gains `is_mutable`.

---

## 11. Success criteria

- `with` on a uniquely-owned subject compiles, at -O2/-O3, to the direct
  in-place stores — zero allocations, **no barriers**, carried fields
  untouched, at most one `gc_note_late_write` announce per pointer-replaced
  fragment, the guard's unchanged path indistinguishable.
- No surviving use of the original after the mutation anywhere in any emitted
  function; the ternary Phi collapses to the identity.
- Class `with` preserves the dynamic class (§2) at every -O level.
- All existing tests pass; the new GC-stress tests hold under forced major
  cycles.

## 12. Open questions / risks

- Does `deadstores`/`trim` reliably delete the (now register-dead) `NewObject`
  if we don't, or must the pass drop it explicitly? Check `deadstores.py`
  treatment of side-effectful ops; the explicit delete in §5.1 is the safe
  plan.
- The announce's two atomic stores are on the else-arm hot path, and only for
  pointer-replacing fragments; measure. The page-youngness proof (§6 Part B)
  removes it entirely in the common build-and-modify case — decide in a
  follow-up whether the rule is worth proving.
- `saved_vars`/async interaction: confirm with a `with` whose *result* crosses
  a suspension that the mutated object is treated as an ordinary immutable
  value from the window's end onward (it is; the async frame roots it like any
  other value).
- Complex-enum boxes are `stack_promotion/promote_to_stack` candidates
  (`stack_promotion.py` skips `is_mutable`/`length_field` objects, so the
  promoted path is orthogonal); verify the order does not double-promote the
  same store.
- The §2 class-dispatch machinery is new (`union_repr` class-subject branch);
  verify arm binding, most-derived-first guard order, and the join-Phi result
  widening with a leaf arm and the static class fallback, since
  `needs_conversion(leaf → base)` is a passthrough and must remain one
  (`conversion.py:159-218`).
- `no_barrier` is a new load-bearing flag on `ObjectField`; make sure no other
  pass reads `fresh`/`no_barrier` off a copy in a way that assumes the two
  invariants are interchangeable, and that trim/AST comparison still treats
  both as compare-excluded.
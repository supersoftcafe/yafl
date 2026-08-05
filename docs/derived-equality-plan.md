# Derived `BasicEquality` for enums and tuples

Status: **COMPLETE — all phases shipped** (`ce267eb`..`d61ffd5`). Supersedes the "no auto-derived traits" position
for these two type kinds only — see *Scope* below.

Decision taken (user, 2026-08-03): **go for precise keys.** The imprecision of
the current fingerprints is the thing to remove; performance is the secondary
motive, not the driver.

## Why

Compound types cannot be `Dict` keys or `memoize` keys today, because
`BasicEquality<T>` (`==` plus `hashOf`) exists only where someone hand-wrote an
instance: the primitives, `String`, `Complex64/32`. Every compiler pass that
needs a compound key therefore builds a **string fingerprint** by hand.

`ceMemoKey` in `complex_enums.yafl` is the worst of these:

```
root # validLeaves # fieldNAMES # complexFlag S sortedVisited
```

It omits the field *types* — the very thing the pass rewrites. Two structurally
different specs collide, and it is sound only because of a pass-level invariant
(within one pass, embedded enum copies have been snapped to their canonical
`all_fields`). It is also used in `ceTableHit` as a stand-in for spec equality,
so that invariant is load-bearing in two places.

A precise key removes the invariant from the trusted set: key and argument
coincide, so the key carries everything needed to compute the value on a miss.

## Scope

Derive for **enums and tuples**. Not classes: a class is nominal and may carry
identity semantics that structural equality would silently override.

Deliberately NOT in scope: ordering (`<`), `Show`/formatting, or any other
trait. Equality and hash only.

## The derivation rule

Derive `BasicEquality<T>` iff every component type has the instance, or can
itself derive one:

- **tuple** — every entry type
- **enum** — every field type of every variant

That is ordinary constraint discharge; `solve_trait_constraint` already does
this work. Derivation fails, with the normal "no instance" error, when a
component is a function type (`SCallable` — functions are not comparable), a
foreign type, or an unbound generic placeholder.

The one case the solver cannot close on its own is a type whose derivation
requires its own instance — the recursive one. That is what phase 2 is for.

**On demand, not eagerly.** Synthesise an instance when the solver needs
`BasicEquality<Foo>` and finds none — never for every type in the program.
Tuples are structural and have no declaration site to annotate, so on-demand is
also the only option that works uniformly. Dedupe synthesised instances by the
type's uid so a program gets at most one per type; name them path-based from
the type, not from a counter.

## The recursive case

**A `[lazy]` let may reference itself directly.** That is the whole rule. A
lambda is just another expression type and gets no special treatment; there is
no "self-reference must be inside a lambda body" restriction.

The reason laziness is the enabling condition: a lazy expression can reference
itself through a cycle, a strict one cannot. Rejecting the strict case is a
separate check, and a complicated one — **deferred**, not part of this work.

```yafl
# sketch — the shape, not the final syntax
let [trait, lazy] eqFoo: BasicEquality<Foo> = instance BasicEquality<Foo>
  fun `==`(l: Foo, r: Foo): Bool
    ret ... eqFoo.`==`(l.child, r.child) ...
  fun hashOf(v: Foo): Int32
    ret ... eqFoo.hashOf(v.child) ...
```

Syntax can be tidied later; the semantics above are the part to get right.

The cycle is in the **instance**, not the data. Values stay acyclic, so a
derived `==` cannot diverge.

## Hash caching — in the memo node, not the object

A derived `hashOf` is O(size), too slow to pay on every probe of a trie walk.

The obvious fix — a lazy hash slot in the object header, as `string_t` has —
**does not work here**: enums and tuples are not always heap allocated. Simple
classes flatten to unboxed structs, tag elimination and immediate structs
remove the header, and those values have nowhere to put a cached word.

So cache the hash **in the cache node**, as an optimisation exclusively for
memoisation. `MemoNode` already carries `mnHash`, and `_walkNode` already tests
`n.mnHash == h && n.mnKey == k` — the int32 compare short-circuits, and the
full structural `==` runs only on a hash match.

**SUPERSEDED IN PART, 2026-08-04.** That is all true and still wanted, but it
is NOT sufficient: it caches the hash of keys already STORED, while the cost is
hashing the INCOMING query key, computed fresh on every lookup. Measured at
>13x on a trivial program. See *Why the query key is the cost* below — the
answer is `[hashed]` on the type (3b), which the object-model objection here
does not defeat, because a lazily cached SCALAR needs no CAS, no write barrier,
and survives compaction by being copied with the object.

Cost per lookup becomes one structural hash of the key, O(size), **with no
allocation** — against the fingerprint's string build plus hash, also O(size)
but allocating a fresh string every time whose header hash cache never gets
reused. So the precise key is expected to be cheaper as well as correct;
phase 4 measures whether that holds.

Out of scope: a bare `==` between two large values stays O(size) with no
caching. Only keyed lookup benefits.

The hash must be **stable across runs** — content only, never an address —
or codegen determinism regresses.

## What the first experiments established (2026-08-03)

**Generic ambient instances already work.** Verified end-to-end: a `Dict` keyed
on `Box<Int>`, with a hand-written

```yafl
instance [ambient] <T> System::BasicEquality<Box<T>> where System::BasicEquality<T>
```

compiles and returns the right value. Destructuring lets, unqualified
trait-method calls (`hashOf(x)` — qualifying it as `System::hashOf` FAILS, the
name comes through TRAIT scope), and `where`-constrained recursion into
components all behave.

**So tuples need no synthesis pass** — just stdlib instances per arity, in the
style memoize already uses for its 1/2/3 overloads. That removes the
architectural fork this plan was originally shaped around.

**The blocker, since RESOLVED in `5ce9ede`.** The suspects I listed were all
innocent, and so was the one I named: monomorphisation's discovery was fine.
The instance's PATTERN had already been mangled to `…$generic$unknown` before
discovery ever ran, because a tuple holding a placeholder passed the
concreteness gate. Lesson: when a pattern will not match, print the pattern —
I chased the matcher for hours when the pattern itself was destroyed.

**Done already:** an undischarged constraint is now a diagnostic naming the
constraint (`no instance of BasicEquality<(bigint,bigint)> (needed by
'hashOf')`) rather than the codegen `ValueError` — `report_undischarged_traits`
in `lowering/generics.py`, the recorded open bug. It is also the detection
point everything else needs.

**Enums remain the only thing standing between here and keys-for-everything,
and they need the SYNTHESIS pass after all.** Each enum is a distinct nominal
type, so no fixed set of stdlib instances can cover them the way arity-2/3
covers tuples. What is now known to work, and makes the pass tractable:
`instance` is a first-class node that lowers cleanly, recursive instances are
fine, and `report_undischarged_traits` is a ready-made detection point. The
shape: on a missing `BasicEquality<E>` for an enum, synthesise a
TraitInstanceStatement over its variants, append, re-converge, re-run. The
demand is only visible post-monomorphisation, so this iterates — but only when
something actually needs deriving, which is never for the bootstrap today.

## Phase 4 has a design tension to settle FIRST

The precise key must carry the field TYPES. Comparing those needs `Spec`
equality — and the ruling above forbids giving `Spec` a `BasicEquality`
instance, because `eqSpec` already means equality for `Spec` under another
spelling, and two meanings of `==` for one type is the ambiguity this plan
refuses.

So the key cannot simply contain `Spec`. The options, none free:

1. **A complete structural rendering** (`uidDeep(spec)`) as part of a String
   key. Unambiguous — a rendering is not an equality — and precise. But a full
   structural key is exactly what the in-file note records as already tried and
   timed out on the giant node/param graphs.
2. **A purpose-built key type holding the field types**, with equality supplied
   by a named function rather than `==`. Needs `Dict`/`memoize` to accept a
   comparator, which they do not today.
3. **Leave `ceMemoKey` alone** and treat phases 0-2 as the deliverable:
   compound keys now work for everyone else, which was the broader win.

`uid` is NOT a candidate for (1): for an enum it renders `enum(root)` only —
nominal, not structural, and so even lossier than the current fingerprint.

## Phases

0. **Undischarged constraint → diagnostic, not a codegen crash.** DONE
   (`ce267eb`, ported in `5ce9ede`).
1. **Tuples as keys.** DONE (`5ce9ede`). The blocker was not "monomorphisation
   ignores structural patterns" — it was that a tuple holding a placeholder
   was treated as CONCRETE, so the instance's pattern mangled to
   `…$generic$unknown` and no demand could unify against it.
   `__is_concrete_type_args` / `concreteArg` now reject any composite
   containing a placeholder, not just unions. `stdlib/tuples.yafl` supplies
   arity 2 and 3 as plain `instance … where` declarations — no synthesis pass
   and no syntax change, which is what the earlier experiments predicted.
2. **A `[lazy]` let may reference itself directly.** ALREADY WORKS — no
   implementation was needed. Verified and pinned by
   `TestRecursionCapabilities`: a self-referential `[lazy]` let compiles and
   runs, and so does a recursive `instance` on a recursive enum (members
   calling back into the instance being defined). Rejecting *strict*
   self-reference remains a separate, deferred check.
3. **Cheap lookups.** Node-cached hashes alone are NOT enough — see
   *Why the query key is the cost* below. Three parts, in order:
   3a. **Enum attribute grammar** (prerequisite, both compilers).
   3b. **`[hashed]`** — the compiler caches a type's structural hash.
   3c. Reference-equality shortcut inside `==`, so a deep compare is skipped
       when both sides are the same object.
4. **Migrate the fingerprint call sites.** DONE (`d61ffd5`). CeKey (spec +
   sorted visited, deep-compared) replaces `ceMemoKey` in both memos, both
   compilers. VERDICT: byte-identical C — the snapping invariant held, and is
   no longer load-bearing for correctness. Trivial compile 22.4s→17.2s;
   bootstrap emit 558.6s vs ~575s baseline.

Phases 1–3 are independently useful and independently gateable. Phase 4 is the
one that changes compiler behaviour, and it is the one that must be proved
byte-identical.

## Why the query key is the cost (measured 2026-08-04)

I built the dedicated key type in BOTH compilers — deep equality including
`all_fields` and `is_complex`, no `id()` — and measured it:

**a trivial program (`ret 0`) went from 22.4s to over 300s.** Reverted.

The reason is structural, and it reproduces the note already in
`complex_enums.yafl`: *"a full structural key re-created the collapse but paid
O(subtree) per call, which timed the giant node/param graphs out."*
`mark_complex_enums` is the pass that RESOLVES `NamedSpec` into embedded enum
copies, so while it runs, `all_fields` **is** the deeply-nested shared graph
the memo exists to collapse. A deep hash per lookup does exactly the work the
memo saves.

**`MemoNode.mnHash` does not help**, and neither does `Dict`'s per-entry hash.
Those cache the hash of keys ALREADY STORED. A lookup must hash the INCOMING
query key before it can find a bucket at all, and that is computed fresh every
call, hit or miss. Node-cached hashes make *comparison* cheap; nothing about
them reaches the query side.

So only two things can work: a cheap (shallow, collision-prone) hash resolved
by deep equality, or caching the structural hash ON THE SPEC so every key built
from it hashes in O(1).

## 3b — `[hashed]`, the compiler caches the hash (design settled 2026-08-04)

USER RULINGS: `[hashed]` must NOT imply `[mutable]` — pinning the spec graph
from compaction would be actively harmful, and a lost racy scalar store is a
benign recompute (exactly how `string_t`'s lazy hash already behaves under
compaction). And 3c becomes OPT-IN per type, which dissolves the NaN
reflexivity objection.

**Two-part mechanism, one orthogonal feature:**

1. `[hashed]` on an ENUM (v1 is enum-only — the target is `Spec`; classes can
   follow): the layout gains a hidden `$hash: Int32` immediately after `$tag`
   in `all_fields`, so every leaf shares the offset. `$tag` is the precedent
   for a synthetic field flowing through the whole enum machinery.
2. `[hashed]` on a FUNCTION of shape `(v: T): Int32`, T the hashed enum or a
   variant of it: the compiler wraps the body — read the slot; nonzero means
   return it; else run the original body, remap 0 to 1, store, return.

The function-level half exists because of the no-instance-for-`Spec` ruling:
`Spec`'s deep hash is a FREE function (`ckHashSpec`), not a trait method, so a
type-only annotation could never reach it. Wrapping the declared compute
function serves free functions and instance members identically — an instance
just writes `fun [hashed] hashOf(...)`. No peek/store primitives are exposed:
the slot is reachable only through the wrap, so no user code can observe the
0-versus-hash nondeterminism.

**Verified simplifications (read from the emitted C and the sources):**

- **No vtable change and no new runtime C.** The wrapped function knows its
  parameter's type statically and all leaves share the `$tag,$hash` prefix, so
  the wrap emits direct field access. The earlier `hash_offset`-in-vtable
  sketch is unnecessary.
- **Static singletons are emitted WITHOUT `const`**
  (`static <T>_t name_data = {...}`), so caching into a statically-allocated
  leaf works; no fieldless-variant restriction needed.
- **Stack promotion must exclude `[hashed]` enums** (a promoted value has no
  object to hold the slot) — one more entry in the existing exclusion list,
  alongside mutable/foreign/arrayed.

Reserved value: 0 means "not computed"; a compute that returns 0 is cached and
returned as 1, deterministically — the same reservation String documents.

Why this fixes the measurement: hashing a `Spec` walks its children, but each
child's hash is itself cached, so a node costs O(fanout) rather than
O(subtree), and the graph is hashed once across the program instead of once
per lookup.

Main implementation risk: every place that treats `$tag` specially (NewEnum
construction, covering-fields lookup, match lowering) must treat `$hash` the
same way, in BOTH compilers, or the gate catches the drift.

## 3a — enum attributes (PREREQUISITE)

The type that needs `[hashed]` most is `Spec`, which is an **enum** — and
**enums have no attribute syntax in either compiler**. Python's parser has no
`__parse_attributes` in front of `enum` and constructs `EnumStatement` with a
hardcoded `{}`; the port's `parseEnum` demands an ident immediately, so both
REJECT `enum [x] Foo` today (verified by running the same program through
each).

This is enabling machinery that already exists for classes rather than
inventing any: parser, node field, equality, rewrite, astdump — both compilers,
byte-identical C. It also unblocks `[mutable]` on enums, which shipped
class-only for exactly this reason.

## 3c — reference equality as a shortcut

`a == b` becomes `(a is b) || eq(a, b)`. For immutable values reference
equality implies value equality, so it can never change an answer and codegen
determinism is untouched.

Two things it commits to, both needing an explicit ruling:
- **`==` becomes reflexive by construction**, even where a user's instance is
  not. The classic counterexample is NaN, where IEEE says `NaN != NaN`.
- It is only meaningful for BOXED values; a flattened class or unboxed tag has
  no reference, and simply skips the shortcut.

It short-circuits EQUALITY only, never the hash, which is why it is the partner
of 3b rather than a substitute for it.

## Two questions resolved by principle

Both of the open decisions here fall out of **"ambiguity is an error"**, so
they are settled rather than deferred.

**Do NOT derive an instance for `Spec`.** `Spec` has no `BasicEquality` today —
equality is the named function `eqSpec`, which deliberately excludes
`all_fields`. Deriving would create a *second* notion of spec equality, spelled
`==`, disagreeing with `eqSpec`. One type, two meanings of equal, and a reader
cannot tell which is in play: that is the ambiguity, and no amount of care at
the call sites removes it.

They are genuinely different relations, so they get different names. `eqSpec`
stays as it is. The precise key becomes a **purpose-built key type** — a tuple
or enum naming exactly the inputs the resolution depends on (root, valid
leaves, complex flag, `visited`, **and the field types**). That type has one
unambiguous equality, structural, and it is the only thing derivation is asked
for. It also satisfies the goal directly: the key carries everything needed to
compute the value on a miss, because the key *is* the input.

The general rule this implies, and which the derivation must enforce:
**never synthesise an instance for a type that already has an equality of its
own, under any spelling.** Derivation fills a vacuum; it never competes.

**`ceTableHit` gets a real equality test.** Using a fingerprint as a stand-in
for spec equality is the same ambiguity in miniature — two different specs
compare "equal" and one silently borrows the other's resolution. With a precise
key the comparison becomes exact.

That makes the migration a **test of the invariant**, which is the useful
framing: if the pass-level invariant genuinely holds, exact matching selects
the same sites and the emitted C is byte-identical. If the C moves, the
invariant was false and we have found a latent bug rather than caused one.
Either outcome is informative, and `test_bootstrap_c` distinguishes them.

## Risks and open questions
- **No coherence checking** (recorded ruling on `instance`). Two instances for
  the same type can coexist, so the dedupe-by-uid step above is doing real
  work, not tidying.
- **Generic types** need an instance per monomorphisation; the derivation must
  run after generics are resolved, or be keyed on the monomorphised type.
- **Parity**: both compilers, byte-identical C, `test_bootstrap_c` as the
  oracle. Phase 4 changes key values and therefore cache hit patterns — the
  emitted C must not move.
- **`ceTableHit`** — resolved above; the C moving is the signal, not the
  failure.

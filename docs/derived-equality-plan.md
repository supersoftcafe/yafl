# Derived `BasicEquality` for enums and tuples

Status: **plan, not built.** Supersedes the "no auto-derived traits" position
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
full structural `==` runs only on a hash match. Nothing needs adding to the
object model; this phase is mostly confirming the derived `hashOf` feeds it.

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

Enums remain open; they are nominal and per-variant, so the stdlib route does
not obviously cover them.

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
2. **A `[lazy]` let may reference itself directly.** Unblocks recursive types.
   Rejecting *strict* self-reference is a separate, harder check — deferred.
3. **Hash cached in the memo node** (`MemoNode.mnHash`, already present), with
   the int32 short-circuit before structural `==`. No object-model change.
4. **Migrate the fingerprint call sites** — `ceMemoKey` in `complex_enums.yafl`
   and `simple_classes.yafl` — to a purpose-built key type, and re-measure.
   Baseline to beat: self-compile 689.9s wall / 677.2s user.

Phases 1–3 are independently useful and independently gateable. Phase 4 is the
one that changes compiler behaviour, and it is the one that must be proved
byte-identical.

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

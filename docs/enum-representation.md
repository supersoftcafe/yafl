# Enum representation (the enum-encoding principle)

Status: core principle, user-ruled 2026-08-23. Per-variant boxing (stage A)
implemented in both compilers. This document is the design record.

## The principle

1. **A closure is a struct.** `fun_t` is presented as a primitive but is a
   struct: a function pointer treated as a machine-word field with no GC
   link, plus a heap pointer visible to GC.
2. **An enum representation is a struct**: the minimal collection of fields —
   of any type — that can represent each of its variants, plus one
   discriminator field (`$tag`).
3. **Unless it exceeds a size threshold.** The threshold does not restrict
   field granularity: 8 bytes in sequence is 8 fields but only one word.
4. **The threshold is a named constant**: `_MAX_VALUE_STRUCT_WORDS = 8` in
   `lowering/complex_enums.py`, `maxValueStructWords` in
   `bootstrap/lower/ast/complex_enums.yafl`.
5. **A struct within an enum is deconstructed** into the enum's shared
   fields and reassembled when addressed. A closure deconstructs into its
   code word and environment pointer (`FunField`/`MakeFun` in the four value
   walkers); each shared field carries its own GC visibility.
6. **An enum within an enum is the same problem** — it is a struct within an
   enum, carried by value as its own pool-plus-tag struct.
7. **Circular enums are the exception**: they box (the complex-enum /
   breaker machinery).

The threshold is universal: after minimal fields plus a discriminator, an
enum IS a struct — and the same size rule governs all structured types
(tuples, combinations, small classes). Anything above it becomes a heap
object.

## Per-variant boxing (stage A)

The threshold applies **per variant type**, not per enum. A variant whose
payload exceeds 8 words is a heap object *everywhere it appears*: it
contributes a single pointer slot to its enum's pool, and its payload lives
in a per-leaf Object — the same Objects, vtables and field layout the
complex-enum path already emits. Variants at or under the threshold stay
inline in the flat tagged struct.

Why per variant: whole-enum boxing punishes the cheap common variants for a
rare wide sibling. Measured on the bootstrap, boxing whole enums at 8 words
cost +17% self-compile CPU (every `Op` allocation paid for `OpIfTask`'s
width). Per-variant boxing is also what makes the decision *type-level*: a
boxed variant is one pointer word in every union that contains it, so
widening between unions is always a straight slot copy, and combinations
are bounded by construction (every member is ≤ 8 words inline or one
pointer).

Mechanics (both compilers, kept in lockstep):

- `compute_boxed_leaves` (beside `compute_breakers`): child-first memoised
  width analysis over the value-containment graph, which is acyclic once
  breakers are removed. Widths are TRUE layout widths, mirrored from the
  flatten/slot-merge arithmetic with per-primitive-class counters: a leaf
  payload sums its fields' primitives; a pool or tagged combination takes
  per-class maxima over its variants plus a one-byte tag; collapsed
  pointer unions (all members one tagged pointer word, mutually
  distinguishable — a spec-level mirror of `_pointer_word_kind`) count one
  word; complex enums a pointer; closures two words. The one documented
  approximation: tags are counted as one byte (the global discriminator
  maximum fits i8; outgrowing it lags the estimate a byte per nesting,
  noise against a 64-byte threshold).
- Roots with interior-node (inherited) fields keep all leaves inline:
  inherited fields are read positionally across sibling carriers, which
  requires one shared representation.
- `enum_variant_types` answers `DataPointer` for a boxed leaf. That is the
  single substitution point — slot merging, GC masks, matching and widening
  all follow from the variant ctype unchanged.
- Flat roots with boxed leaves emit the never-instantiated root marker plus
  one Object per boxed leaf with discriminator 0: dispatch stays on `$tag`,
  and the discriminator registry (hence every tagged union's tag width) is
  untouched.
- `read_field` reads through the pointer slot into the leaf Object;
  `construct_enum_value` allocates the Object (ZeroOf for unwritten fields,
  so staticinit can still promote all-constant constructions) and stores
  the pointer in the leaf's slot. Match needs no changes: guards compare
  `$tag`, and arms bind the subject pool value as-is.

Ground truth: no enum leaf in stdlib+bootstrap exceeds 64 true bytes — the
widest pools are `Op` at 60B (7 pointer slots + 3 byte slots + a byte tag;
the widest inline variant, `OpIfTask`, is 57B) and `BeDef` — so with true
widths the rule fires on nothing in-tree and only on genuinely wide code.
History, for honesty: the analysis as FIRST landed (8f25eb8) used a
conservative estimator that charged collapsed `X|None` unions member+tag
and nested enum values a word of tag; that over-count boxed `OpCall` and
`BdPhi` in-tree, so that commit's byte-neutrality claim was wrong (the
self-compile carried both leaf objects; measured cost was nil — 281.2s CPU
against the 282.8s ledger). The counter rewrite above replaced it.
`tests/test_union_repr.py::TestWideVariantBoxing` pins the behaviour: a
9-pointer-word variant boxes, an exactly-8-word variant does not (strictly
greater-than), eight collapsed one-word unions (64B) stay inline, a
straddling pair around the threshold under true arithmetic lands on both
sides, and inline/boxed variants roundtrip standalone and nested in
combinations.

## Types narrow; the representation never does

`Dark` and `Shade` are different types in the language and one type in the
IR: the pool struct with its discriminator. A site that statically knows
the variant simply ignores the discriminator. This uniformity is
load-bearing, not a simplification: closure compatibility is
variance-based — a parameter of type `(:Car):Int` accepts a function of
type `(:Vehicle):Int` — and that assignment is a plain pointer copy only
because a `Car` argument and a `Vehicle` argument are the same IR type.
Per-view layouts would force an adapter thunk at every such assignment.
Consequently there are no representation conversions between views of one
enum: widening and narrowing are type-system facts with identical bytes.

Constructors return the leaf type: `Dark(7, "deep")` has type `Dark`, not
`Shade` (a construction builds exactly one variant). The value it builds
is still the pool struct, so this too is type-system only. Visible
consequences: a fresh construction feeds leaf-typed fields and parameters
directly; `ret Dark(...)` is exact where `Dark` is declared; a bare
`let s = Save(...)` is `Save`-typed, so a defensive `else` after full
coverage of such a value is a provably-dead-arm error (annotate the let
at the root to keep an un-narrowed value); and reading a construction's
own field is legal.

## Deferred

- **Stage B — breaker subsumption**: recursive variants boxing per-variant
  would break cycles without boxing whole enums (non-recursive variants of
  a recursive enum would inline). Needs its own arc.
- Oversize **tuples** and **combinations** as standalone values, and
  unifying the simple-class flattening cap onto the same constant.

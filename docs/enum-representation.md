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
  width estimation over the value-containment graph, which is acyclic once
  breakers are removed. Widths at spec level: sub-word scalars their true
  bytes, pointers a word, closures two words, tuples summed, nested flat
  enums their own pool estimate under decisions already made, combinations
  widest-member-plus-tag (conservative), complex enums a pointer.
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

Ground truth at the time of landing: no enum leaf in stdlib+bootstrap
exceeds 64 bytes (widest pools: `BeDef` 61B/12 slots, `Op` 60B/11), so the
rule is byte-neutral on the tree and fires only on genuinely wide code.
`tests/test_union_repr.py::TestWideVariantBoxing` pins the behaviour: a
9-pointer-word variant boxes, an exactly-8-word variant does not (strictly
greater-than), and inline/boxed variants roundtrip standalone and nested in
combinations.

## Deferred

- **Stage B — breaker subsumption**: recursive variants boxing per-variant
  would break cycles without boxing whole enums (non-recursive variants of
  a recursive enum would inline). Needs its own arc.
- Oversize **tuples** and **combinations** as standalone values, and
  unifying the simple-class flattening cap onto the same constant.

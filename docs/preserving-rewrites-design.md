# The `with` expression — copy-with-replacements, identity-preserving

Status: **design for discussion, not built.** Supersedes the earlier
`[preserving]`-attribute sketch (user: rejected — this replaces it).

## The construct

RULED (user, 2026-08-06): a leading `with` keyword, then the subject, then a
parenthesised named-replacement list — call-shaped, though it is not a call:

```yafl
ret match(sp)
  (e2: SEnum) => with e2(seParams  = rwSpecs(e2.seParams, w),
                         seComplex = true)
```

Grammar cost is minimal: `with` introduces a primary expression, and the
replacement list reuses the named-tuple-entry parse the call grammar already
has, so `name = value` entries and multi-line wrapping come free.

Semantics: the value of `subject with …` is a value of the subject's type
whose named fields carry the new values and whose UNNAMED fields carry the
subject's — the YAFL-native `dataclasses.replace`, which is what the Python
compiler is built on. The port's rewrite walks, today ten-argument positional
reconstructions, become one-line-per-changed-field mirrors of the Python they
port — the readability win is as large as the performance one.

RULED (user): subjects are class-typed AND enum-typed expressions —
including ROOT-typed enums. `with myColour(something = 1)` where the static
type is `Colour` but the instance is `Colour.Red` yields a `Colour.Red` with
the adjusted field. Replacement names MUST name fields visible at the
subject's STATIC type (the covering set); sub-type-only fields just get
copied along. This works because leaf layouts accumulate root-down, so a
covering field sits at the SAME offset in every leaf that carries it — the
same property that makes root-typed field READS work today. Lowering for a
boxed root-typed subject: vtable-sized copy of the leaf object, named fields
stored at their common offsets, and the copy's `$hash` slot ZEROED (its
content changed; the original keeps its cache when returned unchanged).
Value representations copy the struct and overwrite in place.

## Identity preservation — inside the lowering, not the language

The compiler lowers `with` as:

```
let $f1 = <replacement 1>          # each replacement evaluated ONCE, in order
…
ret SAME($f1, subject.f1) && SAME($f2, subject.f2) && …
  ? subject                        # nothing actually changed: the original
  : V(subject.a, $f1, subject.b, $f2, …)
```

Only the REPLACED fields are compared — the carried-over fields are the
original's by construction, no check needed. When every replacement turns out
to equal what was already there, the original object is returned and no
allocation happens. User code cannot observe which branch ran: the two
results are structurally identical, so the language's no-referential-identity
invariant holds by construction — identity exists only inside compiler-emitted
code, deciding between indistinguishable outcomes.

## `SAME` — "exactly the same", not just reference-equal

Per the user's direction, the internal comparison is broader than pointer
equality: it asks **is the representation bit-identical**, resolved per field
representation at codegen:

  * boxed (enum, class, String, Int)      — pointer compare;
  * unboxed scalar (Int32, Bool, floats)  — value compare;
  * value struct / tagged union — BYTE compare (memcmp of the two
    representations). A value struct may itself contain references; the byte
    compare treats those pointer words as part of the bytes, which is exactly
    reference-comparing them in place.

Padding caveat: struct padding bytes are not guaranteed equal, so a byte
compare may report "different" for representationally equal values. That is a
FALSE NEGATIVE only — the cost is one allocation that today happens
unconditionally — never a wrong answer. If measurement shows padding noise
matters, the fallback is field-wise `SAME` emission instead of memcmp; the
semantics are unchanged.

This same broadened comparison upgrades the existing internals: `[refeq]` on
a value-representation enum currently lowers to constant false (never
shortcut); under `SAME` semantics it becomes a byte compare — still sound
(bit-identical immutable values are equal) and strictly better.

## The convergence payoff, restated for this design

With the port's rewrite walks expressed as `with`:

  * an untouched subtree returns the ORIGINAL nodes at every level (each
    `with` sees its replacements SAME and yields its subject), so a quiescent
    pass allocates nothing;
  * `eqStmt`/`eqSpec` gain the `SAME` fast path at their heads, so comparing
    old-vs-new after a quiescent pass is O(1) per statement, and after a
    small change is O(changed spine).

This does not reduce the NUMBER of converge passes; it collapses the cost of
quiescent and near-quiescent ones — at self-compile scale, most of them. It
also directly attacks the port's allocation firehose (scavenger cost is
O(cycles × extent); fewer allocations, fewer cycles).

## Parity

Both compilers implement the feature in full — parser, node, check, lowering
— before any bootstrap source uses it; the dumps and the gate then compare
the new node byte-for-byte wherever it appears. Python's `with` lowering is
identical, including the SAME check (slightly stronger than CPython's
`dataclasses.replace`, which always allocates — the strengthening is
unobservable in output and shared by both compilers, so parity is by
construction).

## Open questions

ALL RESOLVED (user, 2026-08-06):

1. Syntax: `with subject(name = value, …)`.
2. Zero-replacement `with x()` is an AST/CHECK error, not a parse error.
3. Subjects: class-typed and enum-typed (root included, dynamic leaf
   preserved); names must match fields visible at the static type.
4. Both compilers implement the feature fully first; then the port's rewrite
   walks migrate file by file with RSS and scavenger cycles measured against
   the 689.9s / 2.8GB self-compile baseline; then the eqStmt/eqSpec SAME
   heads as a separate, measured step.

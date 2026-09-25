# One type merge

Status: IN PROGRESS — ruled 2026-09-25; see Progress for what has moved.

## Why

Inference combines two types in eight places, each with its own rules and its
own idea of what a hole is:

| Python (`pyast/typespec/algebra.py` unless noted) | port | what it does | callers |
|---|---|---|---|
| `meet(a, b)` | `meet` | symmetric hole-filling; placeholder = hole regardless of scope | refine, unify, inference.py |
| `refine` / `refine_widening` | `refine` / `refineWidening` | stored type vs fresh inference; widen only if strictly wider | lets, destructure, function return |
| `unify_generic(generic, concrete, names, mapping, in_scope)` | `unifyGeneric[In]` | bind a callee's own placeholders | 8 (inference, access, base, drops, generics, derive_eq, algebra ×2) |
| `converge(types)` | `convergeTypes` | widest member / enum root / one shared interface | branch_type, hints verdict |
| `join(a, b)` | `join` | set union (branch arms) | branch_type, coalesce |
| `branch_type` + `fits_shape` | `branchType` + `fitsShape` | arm typing, unbound-shape filling | match, ternary, coalesce |
| `hints.verdict` | `verdict` | reconcile a parameter's upper and lower bounds | inferred params |
| `trivially_assignable_from` | `assignableFrom` | three-valued assignability | 38 call sites |

The bugs found while moving `derive_eq` into the compile walk (2026-09-24/25)
all sit in the gaps between these:

- `rw(ss): List<Int> => match(ss) (le: ListEmpty) => ss  (lf: ListFull) => …`
  — the arm patterns give `ss` the lower bound `List` (no arguments) and
  `ret ss` gives the upper bound `List<Int>`; no function can say those are
  one type, so `ss` is typed only on passes where one bound happens to be
  missing. Change the pass order and it crashes codegen.
- `List()` beside a `List<Spec> | None` sibling, and `List()` against a
  `List<Int> | None` expected type — each needed its own "shape fits member"
  rule (`fits_shape`, `expectedMember`).
- `meet` treats an in-scope `T` (a real type inside its template) as a hole.

## The operation

    merge(left, right, bindings, resolver) -> (result, bindings', errors)
    port:  mergeSpecs(left, right, bindings, r)
               -> (spec: Spec|None, binds: List<Binding>, errs: Set<PErr>)

- **left** is the receiver ("must fit here"), **right** the value ("this is
  what arrived"): left must be assignable from right. The operation is
  DIRECTIONAL — it fills gaps and resolves hierarchy, it never widens.
- **bindings** maps placeholder names to types, supplied by the reference site
  (`T@4542 = Int`, `T@4542 = X@7f2a`, even `T@4542 = T@du83` — names are
  hash-qualified, so two scopes' `T` never alias). A placeholder listed as
  bindable is a NAMED hole: it binds once, and every further occurrence must
  agree. The updated bindings come back as part of the result — returned,
  never mutated in place (context down, results up). This is what lets
  `merge` replace `unify_generic`: the callee's declared type is `left`, the
  arguments are `right`, and the callee's type params are the bindable names.
- **result** is the best correct answer it can give — `None` when nothing can
  be merged. **errors** are every contradiction found, in the compiler's own
  error container. Nothing is gated on them: the caller adds them to its error
  list and carries on, like every other phase.

### Holes

One definition, scope-aware:

- `None` (nothing known yet);
- an unresolved `NamedSpec` (not compiled yet);
- a placeholder that does NOT resolve in the current scope and is not
  bindable (an unbound `List()`'s own `T`) — an ANONYMOUS hole;
- a bindable placeholder with no binding yet — a NAMED hole.

A placeholder that resolves in scope (a template's own `T`) is a REAL type:
it merges only with itself or with a hole.

A hole on either side yields the other side (a named hole also records the
binding).

### Rules by shape

| left | right | result | notes |
|---|---|---|---|
| hole | X | X | named hole binds |
| X | hole | X | |
| `Int` | `Int` | `Int` | ground leaves: equal or error |
| `Int` | `String` | — error | |
| `(X, ?)` | `(?, Y)` | `(X, Y)` | tuples pair through `bind_tuple_entries` (positional, then by name, defaults); a 1-tuple is its element |
| `Shape` (enum root) | `Circle` (view) | `Shape` | left assignable from right |
| `Circle` | `Shape` | None + error | a receiver narrower than the value: not assignable |
| `List<?>` | `List<Shape>` | `List<Shape>` | generic arguments are INVARIANT: they merge by hole-filling only — copy, don't refine |
| `List<Circle>` | `List<Shape>` | — error | views are distinct types (ruling 09-11) |
| `Pair<X, ?>` | `Pair<?, Y>` | `Pair<X, Y>` | |
| `List` (no arguments: a leaf pattern `ListFull`) | `List<Int>` | `List<Int>` | a generic spelled WITHOUT arguments is a shape: every argument a hole — the `rw` case |
| `List<?>` | `ListFull<T>` | `List<T>` | arguments follow the relation (enum views share the root's parameters) |
| `Automobile<?>` | `Car<X, Y>` | `Automobile<Y>` | right lifted to left's head through the POSITION MAP |
| `Car<?, ?>` | `Automobile<Y>` | None + error | the relation run backwards — as `Circle` / `Shape` |
| `Circle` | `Square` | None + error | sibling views: a contradiction |
| `A \| B` | `A` | `A \| B` | a union receiver accepts a member |
| `A \| ?` | `A \| B` | `A \| B` | a hole member absorbs the remainder (today's `meet`) |
| `(:P) : R` | `(:P') : R'` | `(:merge(P', P)) : merge(R, R')` | parameters reverse direction |

### Position maps

For every class/enum `C<P0..Pn>` and each ancestor `A`, the ancestor as `C`
sees it — `_all_parents` already stores exactly that, spelled over `C`'s own
placeholders (`Car<X,Y> : Automobile<Y>` records `Automobile<Y>`; a class
extending `Bar<Int>` records `Bar<Int>`). From it, per ancestor position:
`C`'s position `j` (a bare placeholder), a fixed type (`Int`), or a pattern
(`Bar<List<Y>>`).

- Lifting right (`Car<X,Y>`) to left's head (`Automobile`): substitute `C`'s
  arguments into the recorded ancestor spelling — no tracing.

Enum variants share the root's parameter list, so for them the map is the
identity. The maps are derived per pass and memoised on the root resolver
(Python `ResolverRoot`, port `RRoot`), like the merged member tables — never
stored on statements.

## What merge does not replace

- **Branch arms are peers**, not receiver and value: their type is a least
  upper bound (the ruling: converge on the common parent, union fallback), not
  a merge. It can share the position maps. `join`'s set semantics stay.
- **Assignability** (`trivially_assignable_from`) stays the checker's
  question — does this value fit this slot? — and keeps its three-valued
  answer. `merge` is about information, not permission.
- **`where`-driven binding** (`_infer_type_params_via_where`,
  `solve_trait_constraint`) stays; it feeds `bindings`.

## Plan

1. This note, ruled on.
2. The case table as tests — Python unit tests plus parity cases in
   `test_bootstrap_specs.py` so both compilers are held to one answer — red
   first.
3. Position maps (derived, memoised) in both compilers.
4. `merge` in both compilers.
5. Migrate callers one at a time — `refine`/`meet`, the hints verdict,
   `unify_generic`, `fits_shape`/`expectedMember`, `converge`'s inheritance
   step — each followed by the suite and a reviewed diff of the port's C
   before references are refreshed.
6. Delete what merge replaced.

Inference outcomes will change, so emitted C will change; each step's diff is
reviewed, not rubber-stamped.

## Rulings (2026-09-25)

1. **Errors.** Every contradiction is returned, in the compiler's own error
   container; the result is the best correct answer, `None` when nothing
   merges. Nothing is gated on errors — the caller collects them and carries
   on.
2. **Direction.** Strictly directional: left must be assignable from right. A
   backwards relation (`Car<?,?>` receiving `Automobile<Y>`) is `None` and an
   error, as `Circle` receiving `Shape` is. Checked against the inference
   sites that motivated bending it: with the orientation right (a declared
   parameter is the receiver of its argument; a receiver's expected type is
   the receiver of a callee's result) each is a forward merge. Revisit only
   with a concrete case that is not.
3. **A narrower receiver** (`Circle` receiving `Shape`): `None` and an error.
   Joining views is a different problem (branch arms), not this one.
4. **Sibling views** (`Circle` with `Square`): a contradiction.
5. **Named-hole agreement:** a bound placeholder meeting another type merges
   by the same rules — holes inside the binding fill (`Lex<?>` then
   `Lex<One>`), anything else is an error. A binding is never widened.
6. **Stored-vs-fresh widening** stays a separate policy, out of scope. A
   DECLARED slot has a receiver — the declaration — so it is
   `merge(declared, fresh)`. An INFERRED slot has none: the fresh inference is
   its only information, and treating the previous pass's partial answer as a
   receiver is exactly the latch that kept appearing. `refine_widening`'s
   "grow only when strictly wider", which is what guarantees convergence,
   stays as it is.
7. **Name:** `merge` (`mergeSpecs` in the port, where `merge` is taken by
   hints). "Meet" is lattice vocabulary and promises a symmetry this
   operation deliberately lacks; `meet` goes once its callers have moved.

## What building it added (2026-09-25)

Four refinements the port's own sources forced, each with a test:

1. **Which side is the callee's** (`callee_left`, port `calleeLeft`). A name in
   `bindings` is a hole only in the CALLEE's own spelling; it flips through
   callable parameters. On the other side the same hash-qualified name is the
   reference site's — its own type in scope, else a leaked unbound
   placeholder, an anonymous hole. Names alone cannot tell them apart: a
   nested call to the same generic (`put(acc, k, put(Dict(), ns, f))`) sees
   the outer call's unbound `V` under the very name of its own `V`.
2. **A binding is the caller's type.** Checking agreement with a bound value
   runs with no named holes: its placeholders are the reference site's
   (`S@drain = S@drain` in a self-recursive call is the caller's own `S`).
3. **Unions solve by set difference.** Ground members pair first; a single
   callee-side named hole then takes what is left — on the value side the
   receiver members nobody matched, on the receiver side the value members
   nobody placed (the stream combinators' `E | ParseError`). An anonymous
   receiver hole becomes what it absorbed. Several holes: no partition.
4. **Provisional views** (`widen_views`). A narrowed enum view in a STORED
   inference, or in a binding taken from an argument, is provisional — the
   documented rule `meet` used to implement by joining views. Only there does
   a receiver's view widen to the union of both views; everywhere else views
   stay distinct types.

## Progress

Moved to `merge` (both compilers):

- `refine` — the stored type receives the inference (provisional views); a
  generic spelled without arguments counts as a hole (`has_missing_arguments`).
  `meet` no longer used here.
- The hints verdict — a parameter's upper bound receives its lower bound
  (the `rw` case); the old common-parent step remains as the fallback on a
  contradiction, to go when the rest have moved.
- Use-site inference's RESULT step — the expected result receives the
  callee's result, the arguments' bindings pre-set; a contradiction no longer
  erases them. Replaced the hand-written union-member rule.

Found on the way and fixed (both compilers): a committed name whose lookup is
blocked for a pass reported no hints instead of UNSETTLED; an inferred let or
return updated from a body that was not yet settled; `refine_widening`
adopted a fresh type that still held holes; a ternary with no receiver never
converted its arms into its own type (codegen crash, present at HEAD).

Still to move: `unify_generic`'s parameter step (and its other six callers),
`fits_shape` in `branch_type`, `converge`'s inheritance step, the remaining
`meet` uses (`inference.py`'s monotone re-inference, `_unify`); then delete
`meet`, `fits_shape`, `_unify_union`.

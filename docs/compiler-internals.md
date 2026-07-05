# Compiler internals — theory of operation

This document explains the *ideas* the compiler is built on, for someone reading
the code for the first time. `architecture.md` covers the runtime and the big
external decisions (C backend, thread pool, task-based async); this covers how
`compiler/` itself thinks. File-level orientation lives in `compiler/CLAUDE.md`.

The pipeline:

```
source (.yafl)
  → tokenize()            parsing/tokenizer.py
  → parse()               parsing/parser.py      (produces the pyast/ AST)
  → compile fixpoint      compiler.py            (types refine until stable)
  → check                 every node's check()   (errors only, no rewriting)
  → AST lowering          lowering/*             (generics, lambdas, tail loops…)
  → global_codegen        pyast/*                (AST → IR OperationBundles)
  → IR lowering           lowering/*             (inline, sync-infer, async…)
  → C emission            codegen/gen.py         (piped through clang)
```

Everything up to C emission is written in a deliberately functional style:
immutable dataclasses, `dataclasses.replace` for every change, read-only
context flowing down, results flowing up. There is no global mutable state.
Learn that discipline once and every module reads the same way.


## 1. The node protocol

Every AST node — `Statement` and `Expression` alike — is a frozen-ish dataclass
with the same four methods:

| method | contract |
|---|---|
| `compile(resolver, …)` | One *rewrite step* toward a fixpoint. Returns a NEW node (never mutates) plus a list of statements to hoist to the top level. Must be **idempotent once stable**: compiling an already-resolved node returns an equal node. |
| `check(resolver, …)` | Errors only. Never rewrites. Runs once, after the fixpoint converges. |
| `generate(resolver)` / `generate_to(…)` | Emit IR (`OperationBundle`). Only runs on a fully-resolved tree; unresolved anything here is an upstream bug, not something to coerce around. |
| `search_and_replace(resolver, fn)` | Structural rewrite/visit. The one generic traversal; used by lowering passes and by read-only scans (pass a visitor that returns its argument). |

`generate_to` is `generate` for a sink with an expected type: it threads the
type down where a shared slot needs sizing (ternary/match merges, block
values) and **asserts** that no conversion is needed — it never coerces.
Representation changes (union boxing/widening, tuple rebuilds) exist in the
tree as explicit `ConvertExpression` nodes, inserted by `lowering/conversions.py` after
monomorphisation; that node's `generate` is the only caller of the
`pyast/expression/conversion.py` machinery.


## 2. The compile fixpoint

`compiler.py::__iterate_and_compile` is the heart:

```python
for iteration_count in range(1, _MAX_COMPILE_ITERATIONS + 1):
    resolver = g.ResolverRoot(statements, __collect_param_suggestions(statements))
    new_statements = [x for stmt in statements for x in __compile(stmt, resolver, None)]
    if new_statements == statements:
        break
    statements = new_statements
```

Each pass rewrites every statement once; the loop stops when a whole pass
changes nothing. There is no dependency ordering and no "phases" — a node that
cannot make progress this pass (a name that doesn't resolve yet, a generic
argument still unknown) simply returns itself unchanged and tries again next
pass, when some other node's progress may have unblocked it.

**The converged AST is the absolute source of truth for program correctness.**
Between the compile fixpoint (plus its check phase) and the generate stage, the
AST must yield no errors: every name resolved, every type ground where codegen
needs it, every semantically-required conversion present as an explicit node.
Downstream stages — lowering passes and `generate` — make **no semantic
decisions**: they do not resolve, infer, or coerce. In particular `generate`
never coerces: either the types already match, or a conversion node
(`ConvertExpression`) was inserted during compile because the conversion is
semantically correct there. A mismatch reaching `generate` is an upstream bug
and must fail loudly, not be papered over at emission time.

Two further consequences a newcomer must internalise:

**Statement equality is the termination test.** `new_statements == statements`
is ordinary dataclass `==`. Therefore every field participating in equality is
part of "program identity", and every field excluded with `compare=False` is
declaring *"changes to me must not keep the loop spinning"*. Excluding a field
is a convergence-contract decision, not a style choice — each such field
carries a comment saying why.

**Types only ever refine.** A stored type starts as a hole and monotonically
gains information; nothing overwrites ground facts. The three primitives:

- `meet(a, b)` — the most-refined common form of two partial types. A hole is
  refined by the other side; compounds meet element-wise; two ground leaves
  must be equal (`_CONFLICT` sentinel otherwise, internal to the type algebra).
- `refine(current, resolver, infer)` — THE rule for any statement that stores
  an inferred type across passes (an untyped `let`, an undeclared function
  return type). Gate: refinable only while `current` is missing or carries an
  out-of-scope placeholder. Threshold: adopt only a *concrete* inferred view
  (placeholder blanks may cross a statement boundary and fill later; unresolved
  names may not). Merge: `meet`. **If you add a new statement kind that caches
  a type, use `refine` — do not hand-roll a latch.** Both historical hand-rolled
  latches were bugs.
- `unify_generic(generic, concrete, names)` — match a generic signature against
  actual types to bind type parameters; partial results are kept and completed
  on later passes.


## 3. Type-system vocabulary

`pyast/typespec/specs.py` holds the spec classes; the algorithms over them
(`meet`, `refine`, `unify_generic`, `substitute_placeholders`,
`solve_trait_constraint`, …) are the *type algebra*
(`pyast/typespec/algebra.py`); the package `__init__` re-exports both so
callers just use `t.*`. The call-site inference family — what type arguments
should a USE of a generic carry? — lives in `pyast/inference.py`
(`use_site_type_params`, the compile-side consumer of the algebra).

| spec | meaning |
|---|---|
| `NamedSpec("Foo")` | An **unresolved name reference**. Exists only mid-fixpoint; reaching `generate` is a bug. |
| `GenericPlaceholderSpec("T@ab12cd")` | A **declared type parameter** — a blank. Real (abstract) inside the scope that declares it; a hole everywhere else. The `@hash6` of the declaration site makes every placeholder globally unique, so two `T`s never alias. |
| `BuiltinSpec`, `ClassSpec`, `EnumSpec`, `TupleSpec`, `CallableSpec`, `CombinationSpec` | Structural types. `CombinationSpec` is an ad-hoc union `A\|B`; `EnumSpec` is a declared union. |

Three *distinct* levels of "is this type finished?", each with one home:

| predicate | question | placeholder counts as… |
|---|---|---|
| `is_concrete()` | Are all **names** resolved? (context-free) | finished |
| `has_free_placeholders(spec, resolver)` | Does it carry a **blank that means nothing here**? (scope-aware) | finished iff it resolves in scope |
| `as_unique_id_str() is not None` | Is it **ground** — a nameable, monomorphised identity? | not finished |

Getting these confused causes latch bugs (adopting `Map<_,_,_,_>` as final) or
scope leaks (a callee's raw `T` landing in a foreign scope). When writing new
inference code, ask which of the three questions you actually mean.

Type inference itself is three paths, all riding the same fixpoint (no
separate constraint solver):

1. **Down** — the expected/recipient type flows into an expression
  (`CallExpression.compile` threads the actual argument tuple and expected
  result into the callee's generic-parameter unification).
2. **Up** — an expression's result type flows into its consumer (`get_type`).
3. **Sideways** — every call site emits a *suggestion* for the callee's
  untyped parameters (`compiler.__collect_param_suggestions`, a pure function
  of the AST recomputed each pass); declared types always win; disagreeing
  suggestions cancel.

`where`-clause constraints are discharged at the call site by matching against
the `[trait]` instances in scope (`solve_trait_constraint`, single-step —
combinator types thread their element/error parameters precisely so that no
recursion is needed). A class `where` is carried onto its synthesised
constructor, so constructing `Map(Count(1,5), dbl)` pins the phantom error
parameter with zero annotations.

### Design note: two where-discharge phases, deliberately separate

`where` constraints are solved in TWO places, and this is not unfinished
consolidation — a merge was considered and rejected. They answer different
questions, at different times, from different fact bases:

| | call-site (`typespec/algebra.py::solve_trait_constraint`) | mono-time (`lowering/generics.py::__bind_where_params`) |
|---|---|---|
| runs | inside the compile fixpoint, on the generic *template* | inside the monomorphisation worklist loop |
| question | what type **arguments** should this use carry? | which witness **instantiations** must exist, at what args? |
| facts available | the *declared* `[trait]` instances only (concrete + generic patterns) | declared concrete instances **plus `mono_map`** — the instantiations the loop has already created |
| composition | none needed: each combinator type threads its own params, so one match binds everything | supplied by the worklist itself — each new instantiation adds facts the next iteration consumes |
| name domain | structured `TypeSpec`s | `$generic$`-mangled names, round-tripped via `__reinflate`/`__remangle` |

The fact bases are the crux: pre-monomorphisation, the intermediate
instantiation facts in `mono_map` *do not exist yet* — they are produced by
the very loop the mono-time discharge runs in. A unified solver would have to
carry that growing state into the fixpoint (or the fixpoint's resolver into
the mono loop): an abstraction straddling two lifecycles, for two callers.
What genuinely can be shared already is: both phases delegate the strict
positional match to `bind_from_constraint_match` and the structural match to
`unify_generic`. If you feel the urge to unify further, that pressure is the
design telling you one of the phases has grown a responsibility it shouldn't
have — look for that instead.


## 4. Name resolution — the resolver onion

A `Resolver` answers `find_type(name)` / `find_data(name)` and a few context
queries. `ResolverRoot` indexes the top-level statements; every scope the
compiler enters adds ONE delegating layer that overrides exactly the aspect it
changes and forwards the rest:

- `AddScopeResolution` — a statement's imports (`System::` prefixes).
- `ResolverType` — a generic declaration's type parameters.
- `ResolverData` — a block's locals / a function's parameters.
- loop/block frames — read-only context for `recur` and block-scoped `return`.

Results carry their provenance: `Resolved(scope=GLOBAL|MEMBER|LOCAL|TRAIT,
trait_scope, owner_class)`, which downstream code uses to build `this.`
accesses or trait dispatch without re-deriving where a name came from.

Names are made unique early: the parser suffixes declarations with
`@` + `hash6(line_ref)` — **derived from the source position, never from a
counter**. The same input always produces the same names, at every stage
(IR variable names get structural *path* prefixes via
`OperationBundle.with_prefix`, same principle). If you find yourself wanting a
monotonic counter for a generated name, derive a path-based name instead.

`'@' in name` therefore signals "already resolved to a unique declaration" and
resolution code branches on it — bare names get ambiguity handling and import
expansion, hashed names are exact lookups.

Known wart: value bindings shadow lexically (`own if own else parent`), so a
class's own `next` method hides a trait `next` for its inner stream — that is
why the stdlib has the `streamNext` free helper. The fix belongs in trait
dispatch, not name lookup.


## 5. Code generation — OperationBundle

`generate` returns an `OperationBundle`: `stack_vars` (declarations),
`operations` (a flat op list — `Call`, `Move`, `Label`, `JumpIf`, `Phi`, …)
and `result_var`. Bundles compose with `+`; a parent marks a child's position
with `.with_prefix("cond")`, which prepends `cond/` to every internal name —
naming by structural path, so identical shapes generate identical C.

Two side channels flow up through bundles to the construct that consumes them:
`recur_sources` (a `[tail]` loop's back-edges, consumed by the enclosing
`LoopExpression`'s head Phi) and `exit_sources` (block-scoped `return`s,
consumed by the enclosing `BlockExpression`'s end Phi).

The IR is SSA for `StackVar`s (single definition; validated by
`ssa_validate` immediately after AST lowering and again just before emission).
Heap-field writes (`ObjectField`) don't count — async lowering relies on that.


## 6. The lowering pipeline and its ordering constraints

Ordering knowledge is commented where the ordering happens (`compiler.py`);
this is the collected summary. **AST-level**, after the fixpoint and checks:

| pass | must run… |
|---|---|
| `drops.insert_drops` | between convergence and the check phase (needs converged types to decide droppability; the checks then see the inserted `drop(x)` calls). Inserting triggers ONE re-convergence so the calls resolve. An unused `[linear]` binding with a `Drop` instance consumes by policy; without one, linearity errors as before. |
| `linearity.check_linearity` | on converged templates, pre-monomorphisation (each `<[linear] T>` body checked once). |
| `generics.convert_generic_to_concrete` | first transform; everything after assumes concrete types. |
| `conversions.insert_conversions` | after monomorphisation (conversions inside generic templates are undecidable before it), before tail loops (a recursive call's boxed args carry to the loop back-edge). Makes every representation change an explicit `ConvertExpression` — generate never coerces. |
| `tail_loop.lower_tail_loops` | before inlining/lambda conversion, while every self-call is still a direct, name-resolved call. |
| `ast_inline.inline_ast` | after tail loops (so it copies loops, not recursive calls). |
| `lower_lazy_lets` | before `lambdas` — the synthesised thunk closure must go through normal closure conversion. |
| `lambdas.convert_lambdas_to_functions` | after everything that synthesises lambdas. |
| `simple_classes.lower_simple_classes` | after lambdas (closure classes exist by now). |
| `block_exits.assign_block_exits` | **last** — after every pass that can create or copy blocks, so each block instance gets unique exit tags. |

**IR-level**, after `global_codegen`:

| pass | why there |
|---|---|
| `ssa_validate` | immediately, to catch generator bugs at the source. |
| `trim` → `globalfuncs` | dead-code removal runs between most passes; reachability from the entrypoint. |
| `inlining` (+`deadstores`, `staticinit`) | -O2/-O3 only, iterated to a shape fixpoint with trim in between. The -O3 single-caller round also runs `vtable_trim` and re-devirtualises: a devirtualised slot's dead vtable entry is what pins a trait witness's method above refcount 1 — removing it lets the fold cascade fuse a whole stream pipeline into its drain, no `[inline(always)]` needed. |
| `sync_inference` | proves which functions can never suspend (they keep the C stack convention). |
| `branch_threading` + `copy_propagation` | collapse ternary/match residue so tail calls become recognisable to async lowering. At -O1+ these iterate to a fixpoint with the three known-value stages below — each unlocks the next, and everything deleted here is a slot the state machine never saves. |
| `struct_folding` | fold field reads of locally-built structs (case-of-known-field); the bypassed pack falls to deadstores. |
| `known_tags` | resolve dispatch on statically-known `$tag`s (case-of-known-constructor): `JumpIf` hardens to `Jump` or evaporates. |
| `string_concat` | flatten `a + b + c` append chains into one exact-size `string_concat_n` allocation (no intermediates, no builder overhead). |
| `string_accumulation` | deforest loop-carried `acc + x` accumulators into in-place builder writes (`string_builder_reserve` + dangerous copy over a (buf, off) Phi pair) — naive accumulation loops become O(n); residual reads take exact-size snapshots. |
| _(shared)_ `ssa_defs` | not a stage — the SSA def-chain analysis library (single defs, read counts, static values) the three known-value stages query. |
| `sroa` | **every** -O level: splits projection-only aggregates so an async frame doesn't root dead sibling fields across a suspension. Space-correctness, not optimisation. |
| `async_lower` | the big one: outlines suspending functions into hot path + `$async` state machine (see `architecture.md`). The machine's body runs on ordinary C locals; state fields are read/written only at park (store the site's live set) and resume (reload it) — heap traffic and GC write barriers scale with suspensions taken, not ops executed, so a fused pipeline loop runs at hot-path speed. The resume joins are deliberately phi-lowered (dispatch loads write the same names the sync edge defines); `ssa_validate` exempts `*$async` from the single-definition check. |
| `uninit_check`, `ssa_validate` | final sanity before emission. |


## 7. Name-mangling glossary

| sigil | meaning | minted by |
|---|---|---|
| `name@Ab12Cd` | unique declaration id, `hash6` of the declaration's source position | parser |
| `name$generic$<sig>` | monomorphised instance of a generic | `lowering/generics.py` |
| `name$async` | the state-machine half of a suspended function | `lowering/async_lower.py` |
| `$asynccommon`, `$state`, `$sv_*` | async-lowering internals (shared cold path, state object, synthesised stack vars) | `lowering/async_lower.py` |
| `Lazy$<irmangle>` | per-IR-type lazy thunk stub class | `lowering/lazy_thunks.py` |
| `$par_site$` | outlined `__parallel__` fork-vs-chain helper | `lowering/async_lower.py` |
| `$tag`, `$s0…` | by-value tagged-union struct fields | `pyast/union_repr.py` / `codegen/typedecl.py` |
| `$pipe@Ab12Cd` | the capture-avoiding intermediate a `\|>`-lambda beta-block binds its argument to | parser (`__to_pipeline`) |
| `$drop_keep@Ab12Cd` | a drop-wrapped scope's saved result (computed before the drops run) | `lowering/drops.py` |
| `cond/`, `args/`, `expr/`… | structural path prefixes on IR names | `OperationBundle.with_prefix` |


## 8. Invariants that will surprise you

- **`EnumSpec.__eq__` excludes `type_params` and `all_fields`.** Two specs with
  the same root and active leaves are the same type; the excluded fields are
  metadata for the generics-redirect pass. Consequence: use `is` (not `==`) to
  detect stale spec copies, and `meet` descends enum `type_params` explicitly.
- **A union's `.types` is not canonically ordered** — only the *identity*
  (`as_unique_id_str`, a sorted id set) is canonical. Never match union members
  positionally; `meet` and member dispatch are set-based. `A|B|C` *is*
  `(A|B)|C`, and `Int|Int` *is* `Int`.
- **`compare=False` fields are convergence-contract exclusions** (§2). Adding
  one without a justifying comment is a review flag.
- **`Never` (an enum with no variants) is an ordinary type** whose only special
  fact is that it has no constructor. No collapsing, no assignability magic;
  `match` must still cover it.
- **Functions are async by default**; pure non-suspending recursion runs on the
  C stack and *can* overflow — deep loops must be `[tail]` (lowered to real
  loops) or folds.
- **`io_t` is single-threaded, one task per handle**; `worker_node_t` is
  single-use (one post, one fire).
- **The compile loop's non-convergence error is real**: if you make a
  `compile()` non-idempotent (e.g. minting a fresh name each pass), the loop
  raises after 100 iterations. Derive names from source positions or structure,
  and it cannot happen.


## 9. Suggested reading order

1. `compiler.py::__iterate_and_compile` — the fixpoint (10 lines).
2. `pyast/statement/base.py` `Statement` / `pyast/expression/base.py`
   `Expression` — the protocol.
3. `pyast/typespec/specs.py` header, then `pyast/typespec/algebra.py`
   (`meet`, `refine`, `unify_generic`) — the vocabulary of §3.
4. `pyast/resolver.py` — the onion; read `DelegatingResolver`'s docstring.
5. One simple node end-to-end: `pyast/expression/ternary.py` (compile → check
   → generate, with `generate_to` coercion and path-prefixed bundles).
6. `pyast/union_repr.py`'s module docstring — the union representation model.
7. `lowering/async_lower.py`'s header comment — the task lowering, alongside
   the async section of `architecture.md`.

Then pick any test in `compiler/tests/` (they are mostly end-to-end: compile a
small program, run it, assert the exit code) and step the pipeline with a
minimal `.yafl` file via `python main.py -c out.c input.yafl`.

# yafl Compiler — Review Notes
_Last reviewed: 2026-04-20_

## Open findings

### Critical

_(none currently open)_

### Major

**[major] `discriminators.get(..., 0)` silently assigns tag 0 on a missing key — `pyast/expression.py:876,982,988,1010`, `pyast/match.py:629,661`**
Six call sites use `discriminators.get(uid, 0)` when looking up the runtime tag value for a union variant.
Tag `0` is also the legitimately assigned discriminator for the first union type encountered, so if any variant's `as_unique_id_str()` returns `None` (valid for `GenericPlaceholderSpec`) or a UID not present in the discriminator dict, two distinct variants silently share tag 0.
In a well-typed program all variants should survive to codegen with concrete `as_unique_id_str()` values and should all be registered by `collect_discriminator_ids`. However, the fallback to 0 is a mis-compilation trap that will give no diagnostic — a `match` arm targeting the second variant will silently behave as if it were the first variant.
Suggested fix: replace `discriminators.get(uid, 0)` with a helper that raises `KeyError` with a descriptive message if the key is absent or `None`.
- **difficulty**: low
- **impact**: high (silent mis-compilation; affects every boxed union and every match expression)

**[major] `inlining.py` unguarded dict lookup `others[op.function.name]` — `lowering/inlining.py:34`**
The walrus expression `target := others[op.function.name]` executes unconditionally whenever all earlier short-circuit conditions are False. If `op.function.name` is not a key in `others` (e.g., after any pipeline reordering that puts inlining before trim, or after adding an `external=True` function whose name happens to be referenced by a GlobalFunction), the result is an obscure `KeyError`.
Currently safe only because `trim.py` is always run before inlining and `external=True` functions are only added by `globalinit` which runs after inlining. But the guard is purely implicit and ordering-dependent.
Suggested fix: add an explicit `op.function.name not in others or` early-exit condition before the walrus assignment.
- **difficulty**: low
- **impact**: medium (currently survivable; but any pipeline ordering change produces a silent crash rather than a compiler error)

Note: previously listed as minor; elevated to major because the walrus pattern obscures the missing guard and the fix is trivial.

**[major] `boxing.py` accesses private name-mangled method `expr._LambdaExpression__find_locals` — `lowering/boxing.py:237`**
The line `nested_resolver = g.ResolverData(resolver, expr._LambdaExpression__find_locals)` reaches inside `LambdaExpression` by name-mangling to access its private `__find_locals` method. This is a broken encapsulation boundary: it relies on CPython's specific double-underscore mangling convention, breaks silently if `LambdaExpression` is renamed or refactored, and crosses the lowering/AST boundary in an undocumented way.
Suggested fix: expose a public method `make_param_resolver(parent_resolver)` on `LambdaExpression` (or change `__find_locals` to `_find_locals`) that returns the appropriate `ResolverData`, and call that instead.
- **difficulty**: low
- **impact**: medium (fragile cross-module coupling; will silently break on refactor)

**[major] `CombinationSpec` and `TupleSpec` use mutable `list` fields in frozen dataclasses — `pyast/typespec.py:469,548`**
`CombinationSpec.types: list[TypeSpec]` and `TupleSpec.entries: list[TupleEntrySpec]` are `list` fields, yet both classes are declared `@dataclass(frozen=True)`. Frozen dataclasses should use `tuple` for sequences; a mutable list in a frozen dataclass can be mutated in place, bypassing the frozen guard. Additionally, `list` fields break `__hash__` (frozen dataclasses derive a hash from all fields, but lists are unhashable, so any code that tries to hash a `CombinationSpec` or `TupleSpec` will raise `TypeError` at runtime). Similar issue exists in `ClassStatement.statements: list[DataStatement]` and `ClassStatement.implements: list[t.TypeSpec]` (though those are non-frozen).
Suggested fix: change `types: list[TypeSpec]` and `entries: list[TupleEntrySpec]` to `tuple` in the two frozen dataclasses. Update all construction sites (straightforward since they're already created with list literals that can be wrapped in `tuple()`).
- **difficulty**: medium (many construction sites; risk of missed cases)
- **impact**: high (latent hash crash anywhere these types are put in sets/dicts; `CombinationSpec` is currently used as a set element in `_all_parents`)

### Minor

**[minor] Legacy `typing` imports use deprecated capitalized aliases in Python 3.9+ files — `codegen/gen.py:4`, `codegen/things.py:4`, `codegen/ops.py:5`, `codegen/typedecl.py:8`**
These files import `Optional`, `List`, `Dict`, `Tuple`, `Union` from `typing` — all deprecated since Python 3.9 in favour of the built-in `list[...]`, `dict[...]`, `tuple[...]`, `X | Y` forms. None of these modules have `from __future__ import annotations` to defer evaluation. The rest of the codebase (pyast, lowering) uses modern annotations correctly.
Suggested fix: add `from __future__ import annotations` to these four files and replace the legacy imports with built-in generics.
- **difficulty**: low
- **impact**: low (cosmetic/future-proofing; no runtime behaviour difference)

**[minor] `abstractproperty` is deprecated since Python 3.3 — `codegen/typedecl.py:6`**
`from abc import ABC, abstractmethod, abstractproperty` imports `abstractproperty`, which was deprecated in Python 3.3 (use `@property @abstractmethod` instead). It is imported but not used anywhere in the file (no `@abstractproperty` decorator appears).
Suggested fix: remove `abstractproperty` from the import; if abstract properties are ever needed, use `@property @abstractmethod`.
- **difficulty**: low
- **impact**: low (deprecated import only; no runtime effect)

**[minor] `TerneryExpression` is misspelled throughout — `pyast/expression.py:779`**
The class is named `TerneryExpression` (wrong: "ternery") instead of `TernaryExpression`. The misspelling is consistent (also in `boxing.py` and `parser.py`), but it will be a point of confusion for any new contributor.
Suggested fix: rename to `TernaryExpression` with `replace_all`. Low risk since it only appears in ~3 files.
- **difficulty**: low
- **impact**: low (readability only)

**[minor] Integer literal trimming in `parser.py` is error-prone to read — `parsing/parser.py:20–30`**
Even after fixing the off-by-one (see `Fixed`), the two-variable `triml/trimr` approach and the expression `len(value)-triml-trimr` are hard to audit. A named helper function `strip_prefix_and_suffix(value, prefix_len, suffix_len)` returning `value[prefix_len:len(value) if not suffix_len else len(value)-suffix_len]` would make intent obvious.
- **difficulty**: low
- **impact**: low (readability only)

**[minor] `TupleExpression.generate` uses reverse-reduce that requires reading bundle semantics — `pyast/expression.py:771`**
`reduce(lambda x, y: y + x, reversed(param_bundles), final_bundle)` is correct but opaque.
A comment explaining that `OperationBundle.__add__` picks the right operand's `result_var` (so the NewStruct must be the rightmost operand) would help future readers.
- **difficulty**: low
- **impact**: low (readability only)

**[minor] `NamedExpression.__post_init__`, `compile`, and `generate` have `if self.name == 'this': pass` stubs — `pyast/expression.py:355–356`, `409–410`, `480–481`**
These are no-op branches that appear to be debugging leftovers or planned but unimplemented special-cases. They add noise without effect.
- **difficulty**: low
- **impact**: low (noise/confusion only)

**[minor] `all_labels` computed but never used in `inlining.py` — `lowering/inlining.py:27`**
`all_labels: set[str] = {label.name for label in fn.ops if isinstance(label, Label)}` is built but never referenced in the function body. Dead computation.
Suggested fix: remove the line.
- **difficulty**: low
- **impact**: low (noise/confusion only)

**[minor] `__CUTOFF_COMPLEXITY = 10` in `inlining.py` is unexplained — `lowering/inlining.py:19`**
The value `10` is the op-count ceiling for inlining a callee. There is no comment explaining why 10 was chosen. The name says "complexity" but the check is purely on `len(ops)`, not on any structural measure of complexity. The `__` double-underscore prefix means it's never importable, which is fine, but the name might mislead a reader into thinking it measures something other than raw op count.
Suggested fix: rename to `_MAX_INLINE_OPS` and add a one-line comment.
- **difficulty**: low
- **impact**: low (readability only)

**[minor] `IfStatement` is declared but has no body and is never constructed — `pyast/statement.py:777–780`**
The class stub defines only three fields and no methods (`compile`, `check`, `generate`). Nothing in the codebase constructs or references it; the parser discards unexpected statement types before they reach the pipeline. Dead code that creates confusion about whether if-expressions are supported at the statement level.
Suggested fix: remove the class (or replace it with a `# TODO: if-statements not yet supported` comment if this is intentional future work).
- **difficulty**: low
- **impact**: low (noise/confusion only)

**[minor] `__compile` in `compiler.py` performs a redundant isinstance-list check — `compiler.py:192–199`**
Lines 192–193 use `any(1 for x in result if isinstance(x, list))` to validate, then lines 195–198 loop and check the same condition again. The second loop is unreachable — it tests the same condition that the `if` on line 192 already guards. Three `raise ValueError()` for the same invariant also means the error message is equally uninformative in all cases.
Suggested fix: collapse to a single check with a descriptive message.
- **difficulty**: low
- **impact**: low (noise/confusion only)

**[minor] `globalinit` emits duplicate lazy-init guards for the same global within one function — `lowering/globalinit.py:38`**
If the same lazy-init global is referenced N times in a function's ops, N independent `JumpIf / Call / Label` sequences are prepended. Each is runtime-correct (the flag prevents actual double-init), but the redundant code inflates the generated C. A `seen` set filtering duplicates would eliminate this.
- **difficulty**: low
- **impact**: low (generated-code quality only; correct output)

**[minor] `NothingExpression` is missing `compile`, `check`, and `generate` — `pyast/expression.py:709–715`**
`NothingExpression` is used by the parser (function bodies without a final return) and referenced in `ast_inline._is_cheap`. However, it only implements `search_and_replace`. Any code path that calls `.compile()`, `.check()`, or `.generate()` on it will raise `NotImplementedError` (inherited from `Expression`). Its `declarations` field is also never used anywhere.
Suggested fix: implement the missing three methods (compile → return self; check → return []; generate → return empty OperationBundle), and either use or remove the `declarations` field.
- **difficulty**: low
- **impact**: medium (latent crash if a NothingExpression ever reaches compile/check/generate; currently only survives because it's always inlined away or short-circuited in `_is_cheap`)

**[minor] `_si_counter` in `staticinit.py` is module-level and never reset — `lowering/staticinit.py:14`**
The `itertools.count()` instance is shared across all calls to `compile()` within a process (e.g., all test cases in a test suite run). The generated names `$si$0`, `$si$1`, etc. are internal and trimmed before output, so this does not affect correctness in production. However, snapshot tests that assert generated C output will see different counter values depending on test execution order.
Suggested fix: move `_si_counter` inside `promote_static_objects` (or reset it at the start of each top-level pass) so names are stable.
- **difficulty**: low
- **impact**: low (testing hazard only; no production correctness impact)

**[minor] `_inline_counter` in `ast_inline.py` is module-level and never reset — `lowering/ast_inline.py:270`**
Same pattern as `_si_counter` above. The counter `_inline_counter = [0]` is shared across all calls to `inline_ast()` in a process, making generated names non-deterministic across test runs.
Suggested fix: use `itertools.count()` scoped inside `inline_ast()` (passed down to `_fresh_suffix`), or reset at the start of each `inline_ast()` call.
- **difficulty**: low
- **impact**: low (test determinism only)

**[minor] `wrap = lambda expr: ...` in `ast_inline._try_inline_call_at_stmt` captures loop variable — `lowering/ast_inline.py:343,348,351`**
The three `wrap = lambda expr: dataclasses.replace(stmt, ...)` lambdas close over `stmt` from the enclosing scope. This is fine here since the lambdas are consumed immediately, but the pattern is easy to get wrong if the code is refactored to delay evaluation. A named helper or `functools.partial` would be clearer.
- **difficulty**: low
- **impact**: low (readability/fragility)

**[minor] `OperationBundle.append` raises `NotImplementedError` — `pyast/resolver.py:82–83`**
The method `append(self, other: OperationBundle) -> OperationBundle` is defined on `OperationBundle` with body `raise NotImplementedError()`, alongside a commented-out implementation. It was apparently displaced by `__add__`. This adds a confusing surface to the class API. Either implement or remove.
- **difficulty**: low
- **impact**: low (dead API noise)

**[minor] `_scan_sets` in `trim.py` uses single-character field names `g`, `o`, `f` — `lowering/trim.py:21–24`**
The fields `g` (globals), `o` (objects), `f` (functions) are undocumented single characters. Anyone reading the class must trace their usage to understand what they represent.
Suggested fix: rename to `globals`, `objects`, `functions` with a comment on the class.
- **difficulty**: low
- **impact**: low (readability only)

---

## Design decisions accepted as intentional

**`pyast/` imports `codegen/` directly**
The AST classes (`FunctionStatement`, `LetStatement`, etc.) directly construct and return codegen IR objects from their `generate()` and `global_codegen()` methods, and `pyast/resolver.py` houses `OperationBundle`. This collapses the AST→codegen boundary. It is a deliberate architectural tradeoff: having `generate()` live on the AST nodes keeps each node's full lifecycle (compile, check, generate) in one place. Reversing this would require a separate visitor/lowering pass for each node type.

**All lowering passes operate on `list[Statement]` (AST), not the codegen `Application`**
The split is clear: lowering passes 1–7 work at AST level and return `list[Statement]`;
post-codegen passes work on `Application`. The only exception is that `lowering/globalfuncs.py` and
`lowering/globalinit.py` are called at *both* levels (once at AST level, not at all; once at IR
level). Specifically `globalfuncs.discover_global_function_calls` and
`globalinit.add_ops_to_support_global_lazy_init` operate only on `Application` — they are IR-level
passes despite living in the `lowering/` directory. This naming is slightly misleading but the code
is correct.

**`simple_classes.py` checks standalone method references before lowering**
The `__exclude_standalone_method_refs` function counts `DotExpression` occurrences vs. immediately-called
ones to identify escaping method references. This is a correct and intentional soundness check.

**CPS continuation flattens multi-field struct returns — `lowering/cps.py:216–222`**
Continuation functions receive multi-field struct return values as individual flat parameters rather
than as a struct. This matches how `Call.to_c` passes `NewStruct` values (expanding each field as a
separate argument), making the generated C ABI-correct without requiring struct-passing conventions.

**`trim.py` recursion for reachability analysis**
`__removed_unused_stuff` is mutually recursive (iterates until `new_scan_sets` is empty). For a
well-formed program the set of reachable names is finite and bounded by the size of the `Application`,
so this terminates. Python's default stack depth is generous enough for programs of realistic size.

**`generics.py` iterates to fixpoint for transitive generic instantiation**
`__convert_generics_iterative` loops until no new specialisations are discovered. This is correct
for handling transitively-generic programs (e.g. `wrapper<T>` that calls `helper<T>`).

**`Application.union_discriminators` is set but never read from `Application`**
Discriminators are threaded through `ResolverDiscriminators` at codegen time, so the field on
`Application` is currently dead state. The fixer agent has noted this in its instructions. If
discriminators ever need to be available at IR-level passes (post-CPS), the field should be
properly copied; until then it is harmless dead state.

**`NewStruct.flatten` returns `[self]` plus the element-level flat lists — intentional self-inclusion**
The base class `RParam.flatten` returns `[self]` for leaf nodes (self-reference for scanning
purposes). The convention is that `flatten` returns "this node plus all nodes nested within me",
with each level responsible for including itself. The bug noted above (nested lists) is separate
from the self-inclusion pattern, which is consistent across all param types.

**`WideExpression.__widen_from_container` declares `result_var` only in the first arm's OperationBundle**
The `first_arm` flag at `pyast/expression.py:1027–1029` ensures `result_var` is included in
`stack_vars` exactly once. This is an idiomatic pattern in the codebase: `OperationBundle.stack_vars`
accumulates all `StackVar` declarations by concatenation; including a var in more than one bundle
would double-declare it in the emitted C. Including it in the first arm's bundle is correct.
The pattern is fragile-looking but intentional and correct given the always-at-least-one-arm invariant.

**`lambdas.py` uses Python recursion to handle nested lambdas**
`__convert_lambdas_to_functions` recurses to handle lambdas-inside-lambdas. For realistic programs
nesting depth is bounded by the source structure. Acceptable for a compiler that is not optimised
for deeply-nested functional style.

**`NothingExpression` is used by the parser for void function bodies**
`NothingExpression` is emitted by the parser at `parsing/parser.py:302` for function bodies that
have no trailing return expression. It is also explicitly handled in `ast_inline._is_cheap`. It is
not dead code; it intentionally represents "no value". Its missing `compile`/`check`/`generate`
implementations are still a problem (see open findings), but the class's existence is justified.

---

## Fixed

**[minor] `staticinit.py` counter initialization parses global names — `lowering/staticinit.py:147–148`**
_Fixed 2026-03-24._
Replaced the fragile `int(n.split("$si$")[1])` name-parsing counter with a module-level
`_si_counter = itertools.count()`.  Dropped the `counter: list[int]` parameter from
`_promote_one_function` and replaced `counter[0]` / `counter[0] += 1` with `next(_si_counter)`.

**[minor] Magic constant `4` in `simple_classes.py` field limit — `lowering/simple_classes.py:45`**
_Fixed 2026-03-24._
Introduced `_MAX_FLAT_STRUCT_FIELDS = 4` with a comment explaining the rationale (arbitrary
but reasonable cut-off: complex numbers and quaternions are optimised, matrices are not) and
replaced the bare `4` with the named constant.

**[major] `NewStruct.flatten` and `InitArray.flatten` return heterogeneous nested lists — `codegen/param.py:42,65`**
_Fixed 2026-03-24._
Both methods used `[item.flatten() for item in ...]`, producing nested sub-lists rather than a flat
`list[RParam]`; `globalinit.__add_global_init_ops` iterates `op.all_params()` with `isinstance(param,
GlobalVar)`, which never matches a sub-list, so `GlobalVar`s nested inside `NewStruct` parameters
silently skipped lazy-init guard insertion.
Fixed by changing both implementations to flattening comprehensions:
`[p for item in ... for p in item.flatten()]`.

**[major] `MatchArm.compile` silently discards hoisted statements — `pyast/match.py:45–46`**
_Fixed 2026-03-24._
`new_body, _ = self.body.compile(...)` and `new_type, _ = self.type_spec.compile(...)` both discarded
the `list[Statement]` return values, causing any global declarations hoisted from a match arm body
to be silently dropped.
Fixed by changing `MatchArm.compile` to return `tuple[MatchArm, list[Statement]]`, and updating
`MatchExpression.compile` to unpack all arm results and concatenate their statement lists alongside
the subject's hoisted statements.


**[minor] `DestructureStatement.add_namespace` uses `super(self)` instead of `super()` —
`pyast/statement.py:523`**
_Fixed 2026-03-23._
`super(self)` passes the instance as the type argument to `super()`, raising `TypeError` at
runtime whenever `add_namespace` is called on a `DestructureStatement`.
Fixed by replacing `super(self)` with the no-argument `super()` form.

**[major] `__calculate_saved_vars` in `cps.py` reads stale ops during iteration —
`lowering/cps.py:112–113`**
_Fixed 2026-03-23._
`calc()` read `fn.ops[index]` and `len(fn.ops)` instead of the current `ops` argument passed to
`do_a_pass`; because the only differing field between `fn.ops[i]` and `ops[i]` is `saved_vars`
(which `calc` overwrites anyway), the bug was behaviourally neutral, but still wrong.
Fixed by replacing `fn.ops[index]` with `ops[index]` and `len(fn.ops)` with `len(ops)` inside `calc`.



**[major] `Application` is a mutable open class; all lowering passes silently drop new fields —
`codegen/gen.py:20–26`, `lowering/*.py`**
_Fixed 2026-03-23._
Converted `Application` to a `@dataclass` (mutable, non-frozen) with `field(default_factory=dict)`
for all four public fields; updated all 9 pass-level construction sites to use
`dataclasses.replace(app, ...)`, which automatically copies `union_discriminators` (and any future
field) without requiring grep-based updates.

**[critical] Integer literal trimming off-by-one on right boundary — `parsing/parser.py:27`**
_Fixed 2026-03-23._
The slice `value[triml : len(value)-triml-trimr]` erroneously subtracted the prefix length from the
right boundary, silently mis-parsing any binary, octal, or hex literal with more than 4 content
characters (e.g. `0b11110000` parsed as `60` instead of `240`).
Fixed by changing the slice to `value[triml : len(value) if not trimr else len(value)-trimr]`.

**[major] `ReturnStatement.compile` silently discards statements produced by sub-expression —
`pyast/statement.py:554–555`**
_Fixed 2026-03-23._
`return dataclasses.replace(self, value=new_value), []` dropped any hoisted statements produced
by the return expression's `compile()` call.
Fixed by returning `stmts` instead of `[]`.

**[major] `__iterate_and_compile` has no termination guard — `compiler.py:180–188`**
_Fixed 2026-03-23._
The function recursed unconditionally whenever `new_statements != statements`, with no iteration
cap or depth limit, risking unbounded recursion if any compile pass was non-idempotent.
Fixed by converting from recursion to an explicit `for` loop with a `_MAX_COMPILE_ITERATIONS = 100`
cap; the loop's `else` clause raises `RuntimeError` with a descriptive message if the cap is hit.

**[minor] `iteration_count` parameter in `__iterate_and_compile` is unused — `compiler.py:180`**
_Fixed 2026-03-23._
The parameter was incremented and passed forward recursively but never used for logging or limiting.
Fixed together with the termination guard finding: replaced with a loop variable that names the
current iteration count and is referenced in the `RuntimeError` message.

**[major] `NamedSpec.check` always returns an error — `pyast/typespec.py:282–286`**
_Fixed 2026-03-23._
The `len(types) == 1` success case fell through to the final error return; added `if len(types) == 1: return []` before the fallthrough so a successfully-resolved `NamedSpec` correctly returns no errors.

**[minor] `integers.py` uses `Any` without importing it — `lowering/integers.py:17`**
_Fixed 2026-03-23._
Added `from typing import Any` to `lowering/integers.py` and corrected the lowercase `any`
annotation on `replace_integer_expression` to `Any`.

**[minor] `CallableSpec._compile` crashes on `result=None` — `pyast/typespec.py:71`**
_Fixed 2026-03-23._
`self.result and self.result.compile(resolver)` evaluated to `None` when `self.result` is `None`, which cannot be unpacked into `r, rglb`.
Fixed by replacing with `self.result.compile(resolver) if self.result else (None, [])`.

**[minor] Parser `test()` function is dead code — `parsing/parser.py:483–554`**
_Fixed 2026-03-23._
An ad-hoc inline test harness (~70 lines) with a commented-out call predating the `tests/` directory.
Fixed by deleting the `test()` function and its commented-out call site; added a regression test in `tests/test_parser.py` asserting the name is absent from the module.

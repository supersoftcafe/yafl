# yafl Compiler — Review Notes
_Last reviewed: 2026-03-23_

## Open findings

### Major

### Minor

**[minor] Integer literal trimming in `parser.py` is error-prone to read**
Even after fixing the off-by-one (see `Fixed`), the two-variable `triml/trimr` approach
and the expression `len(value)-triml-trimr` are hard to audit. A named helper function
`strip_prefix_and_suffix(value, prefix_len, suffix_len)` returning `value[prefix_len:len(value)-suffix_len or None]`
would make intent obvious.

**[minor] `TupleExpression.generate` uses reverse-reduce that requires reading bundle semantics —
`pyast/expression.py:618`**
`reduce(lambda x, y: y + x, reversed(param_bundles), final_bundle)` is correct but opaque.
A comment explaining that `OperationBundle.__add__` picks the right operand's `result_var` (so
the NewStruct must be the rightmost operand) would help future readers.

**[minor] `NamedExpression.__post_init__`, `compile`, and `generate` have `if self.name == 'this': pass` stubs —
`pyast/expression.py:316–317`, `370–371`, and `404–405`**
These are no-op branches that appear to be debugging leftovers or planned but unimplemented
special-cases. They add noise without effect.

**[minor] `inlining.py` performs an unguarded dict lookup on `app.functions` — `lowering/inlining.py:34`**
The walrus expression `target := others[op.function.name]` is evaluated inside a short-circuited `or`
chain that does NOT guard against missing keys — if none of the earlier conditions are `True`, the lookup
executes regardless of whether `op.function.name` is in `others`. Currently safe because trim runs before
inlining and `external=True` functions are only added by `globalinit` which runs after inlining. But the
missing guard (`op.function.name not in others`) makes the function fragile — any ordering change produces
an obscure `KeyError`.
Suggested fix: add `op.function.name not in others or` as an additional early-exit condition.
- **difficulty**: low
- **impact**: low (latent, not currently triggered)

**[minor] `all_labels` computed but never used in `inlining.py` — `lowering/inlining.py:27`**
`all_labels: set[str] = {label.name for label in fn.ops if isinstance(label, Label)}` is built
but never referenced in the function body. Dead computation.
Suggested fix: remove the line.
- **difficulty**: low
- **impact**: low (noise/confusion only)

**[minor] `IfStatement` is declared but has no body and is never constructed — `pyast/statement.py:630–633`**
The class stub defines only three fields and no methods (`compile`, `check`, `generate`). Nothing
in the codebase constructs or references it; the parser discards unexpected statement types before they
reach the pipeline. Dead code that creates confusion about whether if-expressions are supported at the
statement level.
Suggested fix: remove the class (or replace it with a `# TODO: if-statements not yet supported` comment
if this is intentional future work).
- **difficulty**: low
- **impact**: low (noise/confusion only)

**[minor] `__compile` in `compiler.py` performs a redundant isinstance-list check — `compiler.py:161–165`**
Lines 161–162 use `any(1 for x in result if isinstance(x, list))` to validate, then lines 163–165
loop and check the same condition again. The second loop is unreachable — it tests the same condition
that the `if` on line 161 already guards. Three `raise ValueError()` for the same invariant also
means the error message is equally uninformative in all cases.
Suggested fix: collapse to a single check with a descriptive message.
- **difficulty**: low
- **impact**: low (noise/confusion only)

**[minor] `globalinit` emits duplicate lazy-init guards for the same global within one function —
`lowering/globalinit.py:35–36`**
If the same lazy-init global is referenced N times in a function's ops, N independent
`JumpIf / Call / Label` sequences are prepended. Each is runtime-correct (the flag prevents
actual double-init), but the redundant code inflates the generated C. A `seen` set filtering
duplicates would eliminate this.
- **difficulty**: low
- **impact**: low (generated-code quality only; correct output)

---

## Design decisions accepted as intentional

**`pyast/` imports `codegen/` directly**
The AST classes (`FunctionStatement`, `LetStatement`, etc.) directly construct and return codegen
IR objects from their `generate()` and `global_codegen()` methods, and `pyast/resolver.py` houses
`OperationBundle`. This collapses the AST→codegen boundary. It is a deliberate architectural
tradeoff: having `generate()` live on the AST nodes keeps each node's full lifecycle (compile,
check, generate) in one place. Reversing this would require a separate visitor/lowering pass for
each node type.

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

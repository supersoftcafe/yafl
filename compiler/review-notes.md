# yafl Compiler — Review Notes
_Last reviewed: 2026-03-23_

## Open findings

### Minor

**[minor] Parser `test()` function is dead code — `parsing/parser.py:483–554`**
An ad-hoc inline test harness (~70 lines) with a commented-out call at line 554. This predates the
`tests/` directory and no longer runs.
Fix: remove or migrate to `tests/test_parser.py`.

**[minor] Magic constant `4` in `simple_classes.py` field limit — `lowering/simple_classes.py:45`**
The threshold `> 4` is unexplained. A named constant with a comment on its rationale would help.

**[minor] `staticinit.py` counter initialization parses global names — `lowering/staticinit.py:147–148`**
`[int(n.split("$si$")[1]) for n in app.globals if n.startswith("$si$")]` relies on naming
convention stability and will produce a duplicate or raise `ValueError` if any unrelated global
matches the prefix. A monotone module-level counter or an explicit parameter would be safer.

**[minor] Integer literal trimming in `parser.py` is error-prone to read**
Even after fixing the off-by-one (see critical finding), the two-variable `triml/trimr` approach
and the expression `len(value)-triml-trimr` are hard to audit. A named helper function
`strip_prefix_and_suffix(value, prefix_len, suffix_len)` returning `value[prefix_len:len(value)-suffix_len or None]`
would make intent obvious.

**[minor] `TupleExpression.generate` uses reverse-reduce that requires reading bundle semantics —
`pyast/expression.py:618`**
`reduce(lambda x, y: y + x, reversed(param_bundles), final_bundle)` is correct but opaque.
A comment explaining that `OperationBundle.__add__` picks the right operand's `result_var` (so
the NewStruct must be the rightmost operand) would help future readers.

**[minor] `NamedExpression.compile` and `generate` have `if self.name == 'this': pass` stubs —
`pyast/expression.py:370–371` and `403–405`**
These are no-op branches that appear to be debugging leftovers or planned but unimplemented
special-cases. They add noise without effect.

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

---

## Fixed

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

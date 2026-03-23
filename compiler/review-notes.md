# yafl Compiler — Review Notes
_Last reviewed: 2026-03-23_

## Open findings

### Major

**[major] `__iterate_and_compile` has no termination guard — `compiler.py:180–188`**
The function recurses unconditionally whenever `new_statements != statements`. Because equality is
Python object identity for mutable dataclasses, any compile pass that produces fresh-but-equivalent
nodes causes unbounded recursion. There is no iteration cap, visited-state check, or depth limit.
Fix: add a `max_iterations` cap (e.g. 100) and raise a descriptive error if exceeded; also add the
`iteration_count` parameter to log output so non-termination is diagnosable.

**[major] `FunctionStatement.__find_locals` filters on wrong variable in LetStatement loop —
`pyast/statement.py:165–166`**
```python
l = [g.Resolved(let.name, let, g.ResolvedScope.LOCAL)
     for x in self.statements if isinstance(x, LetStatement) for let in x.flatten()
     if g.match_names(x.name, names)]   # ← should be let.name, not x.name
```
For a `DestructureStatement`, `x.name` is the synthetic `_` root name, not the leaf names.
Destructuring inside function bodies will fail to resolve the bound variables.
Fix: `if g.match_names(let.name, names)`.

**[major] `Application` is a mutable open class; all lowering passes silently drop new fields —
`codegen/gen.py:20–26`, `lowering/*.py`**
Every lowering pass constructs a bare `Application()` and assigns only the three core fields
(`functions`, `objects`, `globals`). The `union_discriminators` field (gen.py:25) is silently
dropped by all 8 construction sites. Adding any future field requires updating 8+ files by grep.
In practice `union_discriminators` on `Application` is dead state (discriminators flow via
`ResolverDiscriminators`, not via `Application`); the field on `Application` should either be
removed or the passes should copy it. The structural fix is to make `Application` a frozen
dataclass with a `replace(...)` helper so omissions are caught at construction time.

**[major] `__calculate_saved_vars` in `cps.py` reads stale ops during iteration —
`lowering/cps.py:112–113`**
```python
def calc(index: int) -> Op:
    op = fn.ops[index]   # always the original pre-pass ops
    ...
```
The `iterate()` loop feeds the updated `ops` back for fixpoint, but `calc()` reads from `fn.ops`
(the original) rather than the current `ops` argument. Live sets are computed from the evolving ops
via `saved_set_at`, but then applied to the original ops via `dataclasses.replace`. The loop still
converges (live sets are monotone), but may over-approximate the heap-frame save set (saving more
variables across function calls than necessary), increasing GC pressure.
Fix: pass `ops` as a parameter to `calc` and `do_a_pass` and read from it inside `calc`.

**[major] `NamedSpec.check` always returns an error — `pyast/typespec.py:282–286`**
The `len(types) == 1` (resolution success) case falls through to the error return path. A
successfully-resolved `NamedSpec` still reports "Unresolved reference". This is currently harmless
only because the compile loop eliminates all `NamedSpec` before `check()` runs, but makes the
method semantically wrong.
Fix: add `case [_]: return []` before the final return.

---

### Minor

**[minor] `CallableSpec._compile` crashes on `result=None` — `pyast/typespec.py:71`**
```python
r, rglb = self.result and self.result.compile(resolver)
```
If `self.result` is `None`, the `and` evaluates to `None`, which cannot be unpacked.
Fix: `(r, rglb) = self.result.compile(resolver) if self.result else (None, [])`.

**[minor] `integers.py` uses `Any` without importing it — `lowering/integers.py:17`**
`from __future__ import annotations` suppresses the runtime NameError at module load, but mypy,
`get_type_hints()`, and similar tools will fail.
Fix: add `from typing import Any` or drop the annotation.

**[minor] `DestructureStatement.add_namespace` uses `super(self)` instead of `super()` —
`pyast/statement.py:523`**
`super(self)` is not the idiomatic Python 3 form and can break in non-standard execution
environments. Fix: `super().add_namespace(path)`.

**[minor] Parser `test()` function is dead code — `parsing/parser.py:483–554`**
An ad-hoc inline test harness (~70 lines) with a commented-out call at line 554. This predates the
`tests/` directory and no longer runs.
Fix: remove or migrate to `tests/test_parser.py`.

**[minor] `iteration_count` parameter in `__iterate_and_compile` is unused — `compiler.py:180`**
It is incremented and passed forward but never used for logging, limiting, or anything else. Remove
it or give it a purpose (see the termination guard finding above).

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

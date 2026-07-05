# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run all tests:**
```bash
python -m unittest discover
```

**Run a single test:**
```bash
python -m unittest test_compiler.Test.test_add
python -m unittest test_parser.Test.test_parse_simple_named_type
```

**Compile a yafl file:**
```bash
python main.py [-O 0|1|2|3] [-c out.c] [-a out.s] [-o binary] input.yafl
```
Output is C code piped through `clang` (requires `libyafl` at link time). Use `-c` to emit C without linking.

## Architecture

This is a compiler for **yafl**, a functional language, written in Python. The pipeline is:

```
Source (.yafl)
  → tokenize()           tokenizer.py
  → parse()              parser.py
  → compile() loop       compiler.py  (iterates until AST stabilises)
  → lowering passes      lowering/
  → codegen              codegen/
  → C source             (passed to clang)
```

### Key modules

**`pyast/`** — The typed AST used throughout compilation (theory of operation: `docs/compiler-internals.md`):
- `statement/` — `Statement` hierarchy, one kind per submodule: `base.py` (protocol + shared bases), `function.py`, `classdef.py`, `lets.py`, `types.py`, `control.py`. Statements have `compile()`, `check()`, and `generate()` methods.
- `expression/` — Expression nodes, same one-kind-per-submodule layout.
- `typespec/` — The type system: `specs.py` (representations: `BuiltinSpec`, `NamedSpec`, `TupleSpec`, `CombinationSpec`, `CallableSpec`, `ClassSpec`, `GenericPlaceholderSpec`) and `algebra.py` (`meet`, `refine`, `unify_generic`, `substitute_placeholders`, `solve_trait_constraint`).
- `resolver.py` — Name resolution (`Resolver`, `ResolverRoot`, `AddScopeResolution`, `OperationBundle`).

**`lowering/`** — transformation passes; the full ordered list with each pass's
ordering constraint lives in `docs/compiler-internals.md` §6. Highlights:
1. `drops.py` — affine auto-release: unused `[linear]` bindings consume via their `Drop` instance (runs between convergence and checks).
2. `generics.py` — Monomorphise generics (name-mangles as `name$generic$type_sig`).
3. `conversions.py` — insert explicit `ConvertExpression` nodes (generate never converts).
4. `tail_loop.py` / `ast_inline.py` — `[tail]` recursion → loops; AST-level inlining.
5. `strings.py` / `integers.py` — Lower literal constants.
6. `lower_lazy_lets.py` / `lambdas.py` — `[lazy]` thunking, then closure conversion.
7. `linearity.py` — linear-type checking (exactly-once, post-drops).
8. `inlining.py` / `async_lower.py` / `trim.py` and friends — IR-level: inline, task lowering (async by default, sync when provable), dead-code elimination between most passes.

**`codegen/`** — IR and C emission:
- `gen.py` — `Application` aggregates all functions/objects/globals and emits final C.
- `ir.py` — `Function`, `Object`, `Global` IR nodes.
- `typedecl.py` — C-level types: `Int`, `Struct`, `DataPointer`, etc.
- `ops.py` — Operation IR (`Call`, `Return`, `Label`, etc.).
- `param.py` — Parameter/variable IR (`StackVar`, `GlobalFunction`, `NewStruct`, etc.).
- `perfecthash.py` — Used for vtable dispatch.

**`compiler.py`** — Orchestrates the full pipeline. `compile(source, use_stdlib, just_testing)` is the primary entry point. The `__iterate_and_compile()` loop re-runs `stmt.compile()` on each statement until the AST converges, then runs all lowering passes.

**`parselib.py`** — Parser combinator library (`Parser`, `Result`, `Token`, `TokenKind`, `Error`).

### Language concepts

- **Namespaces** declared with `namespace Name`; names are qualified as `Namespace::Name`.
- **`typealias`** maps yafl names to built-in primitives (`__builtin_type__<bigint|str|bool|int32|…>`).
- **`__builtin_op__<type>("op_name", …)`** is the escape hatch for primitive operations.
- **Interfaces** are structural trait definitions; classes implement interfaces via `: Interface1|Interface2`.
- **Generics** use `fun f<TVal>(…): TVal where TraitInterface<TVal>` syntax; trait instances are declared as `let [trait] name: Trait<Type> = Impl()`.
- **Lambdas** use `(x: Type) => expr` and are lowered to named functions.
- **Pipeline operator** `|>` passes a value (or tuple) into a lambda/function.
- **Bind operator** `?>` is monadic bind for `T|None` types.
- **`match`** destructures union types.
- `main()` must return `System::Int` (bigint) with no parameters.

### stdlib

`stdlib/*.yafl` files are auto-loaded when `use_stdlib=True`. They define `System` namespace primitives (strings, console I/O, etc.).
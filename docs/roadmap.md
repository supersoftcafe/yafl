# Roadmap

This document tracks language features and their status: planned items, and completed ones marked **Implemented**. The language itself is described in the [Language Guide](guide.md) and the [Language Reference](reference.md).

## Control flow statements

`if`, `else if` and `else` are implemented, as statements. A branch does what
its block says, including `ret`, which leaves the function. A function body
still has to end with a `ret` of its own: an `if` / `else` whose branches all
return does not count as returning.

```
fun sign(n: Int): String
    if n < 0
        ret "negative"
    else if n == 0
        ret "zero"
    ret "positive"
```

Loops are planned. For now iteration is recursion (`[tail]` keeps it in constant
space) or a fold over a container.

- `for` loops for bounded iteration
- `break` for conditional early exit from loops

```
# Planned syntax
for item in collection
    process(item)
```

## Class-level generics

Implemented. Generic type parameters work on functions, interfaces, **and
classes** — the class itself can be parameterised and is monomorphised per
instantiation. `Array<T>` (`stdlib/System/Containers/array.yafl`) is a worked
example.

```
class Pair<A, B>(first: A, second: B)
    fun swap(): Pair<B, A>
        ret Pair<B, A>(second, first)
```

## String operations

Implemented. Strings are UTF-8 byte sequences, and the operations split cleanly
into a **byte layer** (the index currency — all O(1)) and a **codepoint layer**
built on top. See the [reference](reference.md#string-operations) for the full
list. The model in brief:

```
# byte layer — indices and slices are byte offsets, O(1)
length(s: String): Int                 # number of BYTES
slice(s: String, a: Int, b: Int): String
byteAt(s: String, i: Int): Int

# codepoint layer — UTF-8 aware, built on one strict decoder
# (a codepoint is an Int32 — every Unicode scalar fits; there is no `char`)
codepointAt(s: String, off: Int): Int32|None   # scalar at a byte offset
decode(s: String, off: Int): (cp: Int32, next: Int)|None
codepoints(s: String): List<Int32>
codepointCount(s: String): Int                 # number of characters, O(n)
isValidUtf8(s: String): Bool
```

`compare`/`==`/`<`/`>` are already correct at the codepoint level, because
byte-wise comparison of UTF-8 equals codepoint lexicographic order. Random
indexing *by codepoint* is deliberately not offered: on UTF-8 it is O(n), so the
functional idiom is to fold over `codepoints` or step with `decode` instead.
Normalisation-aware comparison (treating `é` and `e`+combining-accent as equal)
remains future work.

## Standard input

Implemented through the `System::IO` module: `readAll` reads a whole handle, and
`System::Stream` has stream stages over the text, such as `toLines`. The
`json_pretty` and `linenumbers` examples read stdin this way.

## List\<T\>

Implemented (`stdlib/System/Containers/list.yafl`): a persistent list with `prepend`/`append`,
`map`/`filter`/`fold`, `reverse`, `findIndex`, `partition`, `groupBy`, etc.
(Random indexed access was intentionally removed — use `Array<T>` for that.)
The other containers are `Array`, `Dict`, `Set`, `Bag` and `RRBTree`; see
[Containers](containers.md) for what each is for.

## Arrays

Implemented. An array is a trailing variable-length field of a `[final]` class,
sized by a named `Int32` field; the field presents as a first-class accessor
function and reads are bounds-checked. The stdlib wraps this as `Array<T>` with
the `[]` index operator (`a[i]` → `` `[]` ``(a, i)). See
[arrays in the reference](reference.md) and `stdlib/System/Containers/array.yafl`.

## Strong type inference

Planned (large). The goal is that user programs rarely need to declare the type
of anything — `let`s, parameters, and generic call sites all inferred. A concrete
motivator: a free generic operator/function currently infers its type parameters
only from the *expected* type, not from its argument types, so `a[i]` passed
straight into an overloaded callee with no expected type can't disambiguate. New
features should lean toward this rather than against it.

## Build, libraries & packaging

Implemented. Projects compile against discoverable libraries (a `yafl.toml`
manifest, as a folder or packaged as a `.yl`), the runtime is static-only, and
`yaflc` produces standalone binaries. Libraries are searched for in the `-L`
directories, then `YAFL_PATH`, then the install; one named as a library at an
earlier entry shadows it. The design and each decision are in
[Port library discovery](port-library-discovery-review.md).

## Linear types

Implemented. A `[linear]` class is a value the compiler requires to be consumed
exactly once on every code path, which is how a resource such as a file is
released without a finaliser. `System::IO::IO` is one:

```
class [linear,final] IO(_io: _IO)
```

A linear binding that is never used is released by an inserted `drop` when a
`Drop` instance for its type is in scope (see `Drop` in
`stdlib/System/traits.yafl`).

## IO sequencing

Implemented as the `?>` bind: `pair ?> f` calls `f(io, v)` when `pair` is a
successful `(io, v)`, and otherwise passes the error on with the same `io`. It
is specific to IO for now; a bind over any monad is deferred. (`with` is
spoken for: it is the copy-with-replacements expression, see
[The `with` expression](preserving-rewrites-design.md).)

## JSON parser (showcase)

Implemented — milestone reached. `System::Json` (`stdlib/System/Json/json.yafl`)
parses and prints JSON, as a value or as a stream, and `examples/json_pretty`
reads JSON from stdin and pretty-prints it, exercising recursive union types,
string inspection, stdin, and `List<T>`.

## Tooling

Implemented:

- `yaflc --test` builds a program's `[test]` functions into a test binary
  ([`[test]`](testing-proposal.md)).
- `yaflc --format` puts source in the one layout ([Source layout](style.md)).
- `yaflc --lsp` is a language server, with a VS Code client in `vscode-yafl/`
  ([Language server](language-server.md)).
- `yaflc --profile` ([Profiling](profiling-design.md)).

## Standard library additions

Implemented: `System::Args` (command lines), `System::Uri` (checked URIs,
percent-encoding and `file:` URIs), `System::Log`, `System::Json`,
`System::memoize`, and hex-digit helpers in `System`.

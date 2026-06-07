# Roadmap

This document tracks language features and their status — planned items, and recently-completed ones marked **Implemented**. The current state of the language is also described in [Language Design](lang_info.md).

## Control flow statements

Currently, YAFL supports the ternary expression (`condition ? a : b`) for conditional logic. Full control flow statements are planned:

- `if/else` blocks as statement-level constructs
- `for` loops for bounded iteration
- `break` for conditional early exit from loops

```
# Planned syntax
if x > 0
    doSomething(x)
else
    doSomethingElse()

for item in collection
    process(item)
```

## Class-level generics

Implemented. Generic type parameters work on functions, interfaces, **and
classes** — the class itself can be parameterised and is monomorphised per
instantiation. `Array<T>` (`stdlib/array.yafl`) is a worked example.

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

Implemented at the byte level through the `System::IO` module — the `json_pretty`
example reads the whole of stdin. A higher-level line reader is still a
nice-to-have (tracked in `TODO.md`).

## List\<T\>

Implemented (`stdlib/list.yafl`): a persistent list with `prepend`/`append`,
`map`/`filter`/`fold`, `reverse`, `findIndex`, `partition`, `groupBy`, etc.
(Random indexed access was intentionally removed — use `Array<T>` for that.)

## Arrays

Implemented. An array is a trailing variable-length field of a `[final]` class,
sized by a named `Int32` field; the field presents as a first-class accessor
function and reads are bounds-checked. The stdlib wraps this as `Array<T>` with
the `[]` index operator (`a[i]` → `` `[]` ``(a, i)). See
[arrays in the reference](reference.md) and `stdlib/array.yafl`.

## Strong type inference

Planned (large). The goal is that user programs rarely need to declare the type
of anything — `let`s, parameters, and generic call sites all inferred. A concrete
motivator: a free generic operator/function currently infers its type parameters
only from the *expected* type, not from its argument types, so `a[i]` passed
straight into an overloaded callee with no expected type can't disambiguate. New
features should lean toward this rather than against it.

## Build, libraries & packaging

Implemented. Projects compile against discoverable libraries (manifest + `.yl`
packages), the runtime is static-only, and `yafl` produces standalone binaries.
The full design and status are in [Build & packaging](build-and-packaging.md).

## Linear types

A `[linear]` annotation will allow values to be declared as single-use — the compiler will enforce at compile time that a linear value is consumed exactly once on every code path. This is the primary mechanism for preventing resource leaks (unclosed files, unreleased locks, etc.) without a garbage collector.

```
# Planned syntax
class [linear] FileHandle(path: String)

fun openFile(path: String): [linear] FileHandle
fun closeFile(handle: [linear] FileHandle): None
```

## IO sequencing

A `with` construct is planned as syntactic sugar for chaining sequential IO operations, eliminating the need to thread handles manually through each step:

```
# Planned syntax
with(openFile("data.txt"))
    line = read_line()
    process(line)
```

## JSON parser (showcase)

Implemented — milestone reached. `stdlib/json.yafl` is a full streaming JSON
parser, and `examples/json_pretty` reads JSON from stdin and pretty-prints it,
exercising recursive union types, string inspection, stdin, and `List<T>`.

# Roadmap

This document lists language features that are planned but not yet implemented. The current state of the language is described in [Language Design](lang_info.md).

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

Generic type parameters currently work on functions and interfaces. Generic classes — where the class itself is parameterised — are planned:

```
# Planned syntax
template <A, B>
    class Pair(first: A, second: B)
        fun swap(): Pair<B, A>
            ret Pair(second, first)
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

Reading from stdin is planned via the console module:

```
System::Console::read_line(): String|None
```

Returns `None` at end of input.

## List\<T\>

A generic linked-list type is planned, along with the standard higher-order functions:

```
cons(head: T, tail: List<T>): List<T>
map<A, B>(f: (:A):B, list: List<A>): List<B>
filter<T>(f: (:T):Bool, list: List<T>): List<T>
fold<A, B>(f: (:B, :A):B, init: B, list: List<A>): B
length<T>(list: List<T>): Int
append<T>(a: List<T>, b: List<T>): List<T>
reverse<T>(list: List<T>): List<T>
```

This feature depends on `for` loops being available first.

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

A JSON parser and pretty-printer is a planned end-to-end showcase that will exercise most of the language: recursive union types, string inspection, stdin reading, and `List<T>`. It is primarily a validation goal — when it compiles and runs correctly, the language has reached a meaningful milestone.

This feature depends on: control flow statements, string operations, stdin, and `List<T>`.

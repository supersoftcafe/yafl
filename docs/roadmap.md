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

Basic string introspection functions are planned:

```
length(s: String): Int           # Number of characters
char_at(s: String, i: Int): Int  # Unicode codepoint at index i
=(left: String, right: String): Bool  # Equality comparison
```

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

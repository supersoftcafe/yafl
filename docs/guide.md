# YAFL Language Guide

YAFL (Yet Another Functional Language) is a functional language that compiles to C. It is designed to be safe, concise, and implicitly parallel — the runtime uses a thread-per-core model so programs can take advantage of all available CPU threads without explicit threading. This guide walks through the language progressively, from a first program to its most advanced features. For a precise listing of every language construct and built-in, see the [Language Reference](reference.md).

## Your first program

```yafl
namespace Test

import System

fun createMessage(name: System::String): System::String
    ret "Hi " + name + ", how're you\n"

let message: System::String = Test::createMessage("Jeff")

fun main(): System::Int
    System::print(message)
    ret 0
```

Walking through this line by line:

- `namespace Test` — declares that everything in this file belongs to the `Test` namespace.
- `import System` — brings the `System` namespace into scope so that qualified names like `System::String` and `System::print` resolve correctly.
- `fun createMessage(...)` — a function declaration. Parameter types and the return type are explicitly written. `ret` is the return keyword.
- `let message: System::String = ...` — a top-level value binding. The type annotation is always required.
- `fun main(): System::Int` — the program entry point. It must take no parameters and return `System::Int`.
- `System::print(message)` — calls a function from the System module. Its return value is discarded.
- `ret 0` — returns zero as the exit code.

YAFL uses indentation to delimit blocks — function bodies, match arms, and class methods. There are no braces or `end` keywords.

## Namespaces and imports

Every source file declares a namespace at the top:

```yafl
namespace MyApp
```

All definitions in the file — functions, classes, interfaces, let bindings — belong to that namespace. To reference them from another file, prefix with the namespace name and `::`:

```yafl
MyApp::myFunction()
MyApp::MyClass
```

The `import` statement makes a namespace available in the current file:

```yafl
import System
import System::IO
```

After importing `System`, you use qualified names such as `System::String`, `System::print`. The `import` statement does not pull names into the unqualified scope — you always write the namespace prefix.

## Declaring values

Values are declared with `let`. Type annotations are always required:

```yafl
let greeting: System::String = "Hello, world"
let count: System::Int = 42
```

Top-level `let` bindings are lazily initialised the first time they are accessed.

Tuple destructuring unpacks multiple values at once:

```yafl
let (first, second) = computePair()
```

## Functions

Functions are declared with `fun`:

```yafl
fun add(a: System::Int, b: System::Int): System::Int
    ret a + b
```

The indented block after the signature is the function body. `ret` returns a value and ends the function. Multiple statements appear one per line:

```yafl
fun greet(name: System::String): System::None
    System::print("Hello, ")
    System::print(name)
    System::print("\n")
    ret None
```

Functions can be overloaded — multiple functions with the same name are allowed as long as they have different parameter types:

```yafl
fun describe(x: System::Int): System::String
    ret "an integer"

fun describe(x: System::String): System::String
    ret "a string"
```

## Types

### Built-in types

| Type | Description |
|------|-------------|
| `String` | UTF-8 text string, heap-allocated |
| `Int` | Arbitrary-precision integer (no overflow) |
| `Int32` | 32-bit signed integer (storage only) |
| `Float` | Arbitrary-precision floating point |
| `Float32` | 32-bit float (storage only) |
| `Float64` | 64-bit float (storage only) |
| `Bool` | Boolean: `true` or `false` |
| `None` | Unit type; represents the absence of a value |

All are accessed as `System::String`, `System::Int`, etc. after `import System`.

### Arithmetic promotion

The storage-only types (`Int32`, `Float32`, `Float64`) are automatically promoted to `Int` or `Float` before any arithmetic. All arithmetic therefore produces `Int` or `Float` — never a fixed-width type:

```yafl
let a: System::Int32 = 27
let b: System::Int32 = 100
let c: System::Int = a * b   # a and b are promoted to Int for the multiplication
```

### Type aliases

Introduce a new name for an existing type with `typealias`:

```yafl
typealias UserId : System::Int
```

## Tuples

Parentheses always mean tuple in YAFL. A single-element tuple `(T)` is equivalent to `T`, so parentheses can be used freely for grouping without introducing wrapper types.

```yafl
let pair: (System::Int, System::Int) = (3, 4)
let (x, y) = pair
```

The `*` prefix unpacks a tuple inline — useful for building larger tuples or passing arguments:

```yafl
let a = (2, 3, 4)
let b = (1, *a, 5, 6)         # b is (1, 2, 3, 4, 5, 6)
doSomething("Fred", *b)        # unpacks b as individual arguments
```

## Operators

All operators in YAFL are ordinary functions named with backtick identifiers. They follow exactly the same rules as any other function — they can be overloaded and passed as values:

```yafl
# Define + for a custom type
fun `+`(a: MyType, b: MyType): MyType
    ret combine(a, b)

# Pass + as a function value
fun applyTwice(f: (System::Int, System::Int):System::Int, x: System::Int): System::Int
    ret f(f(x, x), x)

let result = applyTwice(`+`, 5)
```

Standard operators available on `System::Int`:

| Operator | Meaning |
|----------|---------|
| `+` | Addition |
| `-` | Subtraction (binary) or negation (unary) |
| `*` | Multiplication |
| `/` | Integer division |
| `%` | Remainder |
| `<` | Less than |
| `>` | Greater than |
| `=` | Equality |

The `+` operator is also defined on `System::String` for concatenation.

## Expressions

### Ternary

The inline conditional expression evaluates one of two branches:

```yafl
let abs = x < 0 ? 0 - x : x
```

The condition is evaluated first; if true the first branch is returned, otherwise the second.

### Pipeline

The pipeline operator `|>` passes the left-hand value as the argument to the right-hand function, enabling left-to-right chaining:

```yafl
getUser(id) |> formatUser |> System::print
```

This is equivalent to `System::print(formatUser(getUser(id)))`.

### Bind

The bind operator `?>` chains operations that may return `None`. If the left side evaluates to `None`, the whole expression short-circuits to `None`; otherwise the inner value is bound and the right-hand expression is evaluated:

```yafl
findUser(id) ?> (user) => findProfile(user) ?> (profile) => profile.name
```

If any step in the chain returns `None`, the entire expression returns `None`.

## Lambda expressions and higher-order functions

Lambdas are anonymous functions written inline. They can be stored in variables and passed as arguments:

```yafl
let double = (x: System::Int) => x * 2
```

Callable types use the syntax `(:ParamType):ReturnType`:

```yafl
let double: (:System::Int):System::Int = (x: System::Int) => x * 2
```

Named functions and lambdas are interchangeable — both can be stored and passed as values:

```yafl
fun double(x: System::Int): System::Int
    ret x * 2

fun applyToFive(f: (:System::Int):System::Int): System::Int
    ret f(5)

let result = applyToFive(double)   # pass a named function
let result2 = applyToFive((n: System::Int) => n * 3)   # pass a lambda
```

## Union types

A union type allows a value to be one of several types, separated by `|`:

```yafl
fun divide(a: System::Int, b: System::Int): System::Int|System::None
    ret b = 0 ? None : a / b
```

Union types are commonly used for:

- Optional values: `T|None`
- Error returns: `T|System::Int` (where Int is a negative error code)
- Results with multiple possible types

## Pattern matching

`match` dispatches on the runtime type of a union value, binding the inner value in each arm:

```yafl
match(divide(10, 2))
    (System::None) => System::print("division by zero\n")
    (result)       => System::print(result)
```

Arms are indented beneath `match`. Each arm is `(pattern) => expression`. The first matching arm is taken. A pattern that names a type matches only that type; a pattern that names only a variable matches any value and binds it.

## Interfaces

Interfaces describe the functionality a type must provide — similar to Rust traits or Haskell type classes.

```yafl
interface Stringable<T>
    fun toString(t: T): System::String
```

An interface is implemented by declaring a class that satisfies it:

```yafl
class StringablePoint() : Stringable<Point>
    fun toString(t: Point): System::String
        ret "(" + System::String(t.x) + ", " + System::String(t.y) + ")"
```

Then a trait instance is registered with `let [trait]`:

```yafl
let [trait] stringable_point: StringablePoint = StringablePoint()
```

Functions can require a trait implementation via a `where` clause:

```yafl
fun printValue<T>(value: T): System::None where Stringable<T>
    System::print(toString(value))
    ret None
```

Interfaces can extend other interfaces:

```yafl
interface BasicMath<T> : BasicPlus<T>
    fun `*`(left: T, right: T): T
    fun `-`(left: T, right: T): T
    fun `/`(left: T, right: T): T
    fun `%`(left: T, right: T): T
```

There is no extension method syntax. Interfaces are the primary mechanism for polymorphism.

## Classes

Classes are product types — named groups of fields:

```yafl
class Point(x: System::Int, y: System::Int)
```

Fields are accessed with `.`:

```yafl
let p = Point(3, 4)
let px: System::Int = p.x
```

Classes can define methods and implement interfaces:

```yafl
class StringablePoint() : Stringable<Point>
    fun toString(t: Point): System::String
        ret "(" + System::String(t.x) + ", " + System::String(t.y) + ")"
```

The `[final]` attribute prevents a class from being subclassed and enables direct dispatch instead of vtable lookups:

```yafl
class [final] ImmutablePoint(x: System::Int, y: System::Int)
```

## Generic functions

Functions support generic type parameters declared in angle brackets:

```yafl
fun identity<T>(x: T): T
    ret x
```

Type parameters can be constrained by interfaces using a `where` clause:

```yafl
fun printValue<T>(value: T): System::None where Stringable<T>
    System::print(toString(value))
    ret None
```

Multiple constraints are separated by `|`:

```yafl
fun convert<T>(value: T): System::String where Stringable<T> | Comparable<T>
```

## Error handling

For operations that may fail, return a union type:

```yafl
fun parseInt(s: System::String): System::Int|System::None
```

The caller handles both cases using `match`:

```yafl
match(parseInt("42"))
    (System::None) => System::print("not a number\n")
    (n)            => System::print(n)
```

Or use the bind operator `?>` to propagate `None` through a chain:

```yafl
parseInt(raw) ?> (n) => process(n)
```

For genuinely unrecoverable errors — programming errors from which the caller cannot reasonably recover, such as integer division by zero — YAFL uses exceptions internally. These are not the primary error-handling mechanism. Use union types for expected failures.

## The System module

The `System` namespace provides the core types, utility functions, and IO primitives.

### Types

| Name | Description |
|------|-------------|
| `System::String` | UTF-8 string |
| `System::Int` | Arbitrary-precision integer |
| `System::Int32` | 32-bit integer (storage only) |
| `System::Bool` | Boolean (`true` / `false`) |
| `System::None` | Unit type; the value `None` |

### Console output

```yafl
System::print(str: System::String): System::None
System::print(int: System::Int): System::None
```

Both overloads are `[impure]` and `[sync]` — they have side effects but are safe to call from any thread.

### String utilities

```yafl
System::String(int: System::Int): System::String   # convert an integer to its decimal string
System::Char(int: System::Int): System::String     # convert a Unicode codepoint to a one-character string
```

### IO

IO functions live in the `System::IO` sub-namespace. Import with `import System::IO`:

```yafl
System::IO::stdin(): System::IO::IO
System::IO::stdout(): System::IO::IO
System::IO::stderr(): System::IO::IO
System::IO::open_read(path: System::String): System::IO::IO|System::Int
System::IO::open_write(path: System::String, truncate: System::Bool): System::IO::IO|System::Int
System::IO::create(path: System::String): System::IO::IO|System::Int
```

On failure the constructor functions return a negative `Int` error code rather than an `IO` handle. The `IO` class has three methods:

```yafl
read(length: System::Int): System::String|System::Int|System::None
write(data: System::String): System::Int|System::None
close(): System::Int|System::None
```

`None` is returned at end of file. An `Int` return value indicates a negative error code.

## Function attributes

Attributes in square brackets annotate declarations with compiler directives:

```yafl
fun [impure] writeLog(msg: System::String): System::None

fun [impure, sync] getTimestamp(): System::Int

fun [foreign("libc_write"), impure] sysWrite(fd: System::Int, data: System::String): System::Int

class [final] Point(x: System::Int, y: System::Int)
```

| Attribute | Meaning |
|-----------|---------|
| `[impure]` | The function has observable side effects |
| `[sync]` | The function is safe to call from any thread without additional synchronisation |
| `[foreign("name")]` | Binds to the C symbol `name` instead of generating YAFL code |
| `[final]` | Prevents the class from being subclassed; enables direct dispatch instead of vtable lookup |

Attributes can be combined: `[impure, sync]`.

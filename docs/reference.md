# YAFL Language Reference

This document is the authoritative reference for the YAFL language. It covers every construct, type, attribute, and built-in in a single-page listing. For a narrative introduction to the language, see the [Language Guide](guide.md).

## Source file structure

A YAFL source file has the following structure:

```
namespace <Name>       # optional, but conventional
import <Name>          # zero or more, one per line
<declarations>         # functions, classes, interfaces, let bindings
```

Indentation is significant — blocks are delimited by indentation level, not by braces or `end` keywords. Comments begin with `#` and run to end of line.

## Built-in types

All built-in types live in the `System` namespace.

| Type | Description | Notes |
|------|-------------|-------|
| `String` | UTF-8 string | Heap-allocated; supports `+` for concatenation |
| `Int` | Arbitrary-precision integer | No overflow; all integer arithmetic produces `Int` |
| `Int32` | 32-bit signed integer | Storage only; promoted to `Int` in arithmetic |
| `Float` | Arbitrary-precision floating point | All float arithmetic produces `Float` |
| `Float32` | 32-bit float | Storage only; promoted to `Float` in arithmetic |
| `Float64` | 64-bit float | Storage only; promoted to `Float` in arithmetic |
| `Bool` | Boolean | Literals: `true`, `false` |
| `None` | Unit type | Represents absence of a value; literal: `None` |

## Declarations

### `namespace`

```
namespace <Name>
```

Declares the namespace for all definitions in the current file. Must appear before any other declarations. All names defined in the file are accessible as `Name::thing` from other files.

### `import`

```
import <Name>
```

Brings a namespace into scope so its names can be used with the `Name::` prefix. After `import System`, you write `System::String` and `System::print`. Multiple `import` statements are allowed. Sub-namespaces are imported separately: `import System::IO`.

### `typealias`

```
typealias <Name> : <Type>
```

Introduces a new name for an existing type. The alias and the underlying type are fully interchangeable.

```yafl
typealias UserId : System::Int
```

### `let`

```
let <name>: <Type> = <expr>
let (<name1>, <name2>, ...) = <expr>
let [trait] <name>: <ImplClass> = <expr>
```

Binds a name to a value. Type annotations are required in the plain and destructuring forms. The `[trait]` form registers a class instance as a trait implementation for interface dispatch. Top-level `let` bindings are lazily initialised.

```yafl
let x: System::Int = 42
let (a, b) = computePair()
let [trait] str_point: StringablePoint = StringablePoint()
```

### `fun`

```
fun [<attributes>] <name>[<TypeParams>](<params>): <ReturnType> [where <Constraints>]
    <body>
```

Declares a function. The body is the following indented block. `ret` returns a value from the function.

- `<TypeParams>` — generic type parameters in angle brackets: `<T>`, `<A, B>`
- `<params>` — comma-separated `name: Type` pairs
- `where <Constraints>` — one or more interface constraints, separated by `|`

```yafl
fun add(a: System::Int, b: System::Int): System::Int
    ret a + b

fun identity<T>(x: T): T
    ret x

fun printAll<T>(value: T): System::None where Stringable<T>
    System::print(toString(value))
    ret None
```

Multiple functions with the same name are permitted provided their parameter types differ (overloading).

### `class`

```
class [<attributes>] <Name>(<fields>) [: <Interface>[, <Interface>...]]
    <method declarations>
```

Declares a class — a product type with named fields. Fields are accessed with `.`. The optional `: Interface` list specifies which interfaces this class implements. Methods are declared as `fun` inside the indented class body.

```yafl
class Point(x: System::Int, y: System::Int)

class StringablePoint() : Stringable<Point>
    fun toString(t: Point): System::String
        ret "(" + System::String(t.x) + ", " + System::String(t.y) + ")"
```

A class with no fields still requires empty parentheses: `class MyClass()`.

### `interface`

```
interface <Name>[<TypeParams>] [: <ParentInterface>[, <ParentInterface>...]]
    fun <name>(<params>): <ReturnType>
    ...
```

Declares an interface — a set of function signatures that implementing classes must provide. Interfaces can extend other interfaces by listing them after `:`.

```yafl
interface Stringable<T>
    fun toString(t: T): System::String

interface BasicMath<T> : BasicPlus<T>
    fun `*`(left: T, right: T): T
    fun `-`(right: T): T
    fun `-`(left: T, right: T): T
    fun `/`(left: T, right: T): T
    fun `%`(left: T, right: T): T
```

## Types

### Primitive types

See the [Built-in types](#built-in-types) table. All accessed as `System::<Name>`.

### Tuple types

```
(Type1, Type2, ...)
(name: Type, name: Type, ...)
```

An ordered sequence of typed values. Single-element tuples are equivalent to the contained type: `(T)` == `T`. This means parentheses can be used freely for grouping expressions without introducing wrapper types.

Named-field tuples use `name: Type` syntax and fields are accessed with `.`.

### Union types

```
Type1|Type2|Type3
```

A union type holds exactly one of its constituent types at runtime. The actual type must be extracted with `match` or the `?>` operator. Commonly used as `T|None` for optional values or `T|System::Int` for error codes.

### Callable types

```
(:ParamType):ReturnType
(ParamType1, ParamType2):ReturnType
```

The type of a function or lambda value. The leading `:` in the single-parameter form distinguishes a parameter type from a grouped expression (because `(T)` == `T`).

```yafl
let double: (:System::Int):System::Int = (x: System::Int) => x * 2
let add: (System::Int, System::Int):System::Int = (a: System::Int, b: System::Int) => a + b
```

### Generic type parameters

```
fun <name><T>(<params>): <ReturnType>
fun <name><T, U>(<params>): <ReturnType> where Interface<T>
```

Type variables are introduced in angle brackets after the function or interface name. They can be constrained with a `where` clause listing required interface implementations, separated by `|`.

## Expressions

### Literals

| Kind | Examples |
|------|---------|
| Integer | `0`, `42`, `1000000` |
| String | `"hello"`, `"line\n"`, `"tab\there"` |
| Boolean | `true`, `false` |
| Unit | `None` |

String escape sequences: `\n` (newline), `\t` (tab), `\\` (backslash), `\"` (quote).

### Qualified identifier

```
Namespace::Name
```

References a definition in an imported namespace. Namespaces can be nested: `System::IO::stdin`.

### Function call

```
<function>(<args>)
```

Arguments are comma-separated expressions. Operator expressions desugar to function calls: `a + b` is `` `+`(a, b) ``.

### Ternary

```
<condition> ? <then-expr> : <else-expr>
```

Evaluates `condition`; if true evaluates and returns `then-expr`, otherwise `else-expr`. Both branches must have compatible types.

### Pipeline

```
<value> |> <function>
```

Equivalent to `<function>(<value>)`. When the left side is a tuple, it is unpacked as arguments: `(a, b) |> f` is `f(a, b)`.

### Bind

```
<value> ?> (<name>) => <expr>
```

Monadic bind for `T|None` types. If `value` is `None`, the whole expression evaluates to `None`. Otherwise `name` is bound to the inner `T` value and `expr` is evaluated.

### Lambda

```
(<name>: <Type>, ...) => <expr>
```

An anonymous function. The body is a single expression. Lambdas capture their enclosing scope. They are interchangeable with named functions.

### `match`

```
match(<expr>)
    (<pattern>) => <result>
    (<pattern>) => <result>
    ...
```

Dispatches on the runtime type of a union value. Arms are indented beneath `match`. The first matching arm is taken.

- A pattern of the form `(TypeName)` matches only that type; the matched value is `TypeName`.
- A pattern of the form `(name)` matches any value and binds it to `name`.

```yafl
match(divide(10, 0))
    (System::None) => System::print("error\n")
    (result)       => System::print(result)
```

### Field access

```
<expr>.<field>
```

Accesses a named field of a class instance or named-field tuple.

### Tuple expression and unpacking

```
(<expr>, <expr>, ...)
(1, *tuple, 5)
```

Constructs a tuple. The `*` prefix unpacks a tuple inline — its elements are inserted at that position.

```yafl
let a = (2, 3, 4)
let b = (1, *a, 5)    # b is (1, 2, 3, 4, 5)
```

## Attributes

Attributes appear in square brackets before a declaration. Multiple attributes are comma-separated: `[impure, sync]`.

| Attribute | Applies to | Meaning |
|-----------|------------|---------|
| `[impure]` | Function, method | Has observable side effects; the compiler will not reorder or elide calls |
| `[sync]` | Function, method | Safe to call from any thread without additional synchronisation |
| `[foreign("symbol")]` | Function, method, class | Binds to the named C symbol; no YAFL body is compiled |
| `[final]` | Class | Prevents subclassing; enables direct dispatch instead of vtable lookup |
| `[trait]` | `let` binding | Marks this binding as a trait instance for interface dispatch |
| `[linear]` | Class, `let` binding | Planned — see [Roadmap](roadmap.md) |

## The System module

Import with `import System`. All names below are qualified as `System::<Name>`.

### Types

| Name | Kind | Description |
|------|------|-------------|
| `System::String` | `typealias` | Built-in UTF-8 string type |
| `System::Int` | `typealias` | Built-in arbitrary-precision integer |
| `System::Int32` | `typealias` | Built-in 32-bit integer |
| `System::Bool` | `typealias` | Built-in boolean type |
| `System::None` | `typealias` | Unit type; equivalent to `()` |

### Functions

| Signature | Attributes | Description |
|-----------|------------|-------------|
| `System::print(str: System::String): System::None` | `[impure, sync]` | Print a string to stdout |
| `System::print(int: System::Int): System::None` | `[impure, sync]` | Print an integer to stdout |
| `System::String(int: System::Int): System::String` | — | Convert an integer to its decimal string representation |
| `System::Char(int: System::Int): System::String` | — | Convert a Unicode codepoint to a one-character string |

### Interfaces

| Name | Extends | Methods |
|------|---------|---------|
| `System::BasicPlus<T>` | — | `` `+`(left: T, right: T): T `` |
| `System::BasicMath<T>` | `BasicPlus<T>` | `` `*` ``, `` `-` `` (unary and binary), `` `/` ``, `` `%` ``, `` `<` ``, `` `>` ``, `` `=` `` |

`System::Int` and `System::String` have built-in trait instances registered for these interfaces.

### IO (`System::IO`)

Import with `import System::IO`. All names below are qualified as `System::IO::<Name>`.

**Constructor functions:**

| Signature | Attributes | Description |
|-----------|------------|-------------|
| `System::IO::stdin(): System::IO::IO` | `[sync]` | Standard input handle |
| `System::IO::stdout(): System::IO::IO` | `[sync]` | Standard output handle |
| `System::IO::stderr(): System::IO::IO` | `[sync]` | Standard error handle |
| `System::IO::open_read(path: System::String): System::IO::IO\|System::Int` | `[impure]` | Open a file for reading |
| `System::IO::open_write(path: System::String, truncate: System::Bool): System::IO::IO\|System::Int` | `[impure]` | Open a file for writing |
| `System::IO::create(path: System::String): System::IO::IO\|System::Int` | `[impure]` | Create a new file |

On failure the constructor functions return a negative `System::Int` error code.

**`System::IO::IO` methods:**

| Signature | Description |
|-----------|-------------|
| `read(length: System::Int): System::String\|System::Int\|System::None` | Read up to `length` bytes; `None` at end of file; negative `Int` on error |
| `write(data: System::String): System::Int\|System::None` | Write data; returns bytes written or `None` on error |
| `close(): System::Int\|System::None` | Close the handle; returns `0` on success or `None` on error |

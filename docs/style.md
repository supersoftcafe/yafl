# YAFL Source Layout

YAFL has one layout. There are no options and no per-project settings: `yaflc --format` puts source in it, and
`yaflc --format-check` lists the files that are not in it (and fails if there are any). This page says what the
layout is, so that code written by hand starts close to it and nothing the formatter does is a surprise.

```
yaflc --format src/            # rewrite every .yafl file under src/ in place
yaflc --format-check src/      # list the ones not in the layout; exit 1 if any
```

The formatter reads the parse, not the text: what you wrote is printed back in its shortest spelling, laid out by
the rules below. Comments are kept, in order, and re-indented, but never rewrapped.

Every example on this page is checked by the test suite (`compiler/tests/test_bootstrap_format.py`): each is
already in the layout, so a change to the formatter that is not also made here fails the build.

## Lines and indents

- Lines are at most 120 columns. A line goes over only when there is nowhere to break it, such as a long string.
- A block (a function's statements, a class's members, a match's arms) is two in from the line that owns it.
- A line that continues the one before (wrapped arguments, an operator run, a pipeline stage, a ternary's `:`) is
  four in from the line the expression started on.

## The file

The namespace, then the imports, then the declarations, each separated by one blank line. Imports are sorted and
duplicates dropped, the `System` ones first, with one blank line between them and the rest.

```yafl
namespace Shapes

import System
import System::Containers

import Geometry::Points
```

## Declarations and blank lines

Declarations laid out on one line pack together. One that takes more than one line has a blank line on each side.
The same goes for the members of a class, enum or instance.

```yafl
let [const] ORIGIN_X: Int = 0
let [const] ORIGIN_Y: Int = 0
fun double(x: Int) => x * 2
fun half(x: Int) => x / 2

fun distance(a: Int, b: Int): Int
  ret a > b ? a - b : b - a

class Point(x: Int, y: Int)
  fun sum() => x + y
  fun diff() => x - y

  fun scaled(k: Int): Point
    let nx = x * k
    ret Point(nx, y * k)
```

A banner comment has two blank lines above it and one below.

```yafl
fun first() => 1


# ── the second part ──────────────────────────────────────────────────────────

fun second() => 2
```

Inside a block, a blank line the source had between two statements is kept (several become one). There is never
one before a block's first statement.

```yafl
fun total(a: Int, b: Int): Int
  let x = a * 2

  let y = b * 3
  ret x + y
```

## Function bodies: `=>` or `ret`

A body that is one value is written `=> e` only when the function declares no return type and `=> e` takes at most
two lines, the `fun` line included. Otherwise it is a block ending in `ret e`. Which way the source spelled it
makes no difference.

```yafl
fun inc(a: Int) => a + 1

fun dec(a: Int): Int
  ret a - 1

fun describe(alphaCondition: Bool, betaCondition: Bool, gammaCondition: Bool) =>
    anyOfThese(alphaCondition, betaCondition) || gammaCondition || alphaCondition && betaCondition

fun kind(x: Int|String|None)
  ret match(x)
    (i: Int) => "int"
    () => "other"
```

A lambda's body is always `=> e`: a lambda has no block form.

## Parameters and arguments

Parameters start straight after the `(` and wrap four in, as many to a line as fit. The `)` and the return type go
with the last parameter, so when they do not fit beside it, they move down together.

```yafl
fun [tail] scan(io: IO, path: String, lineNo: Int,
    found: List<String|FileError>): (io: IO, found: List<String|FileError>)
  let r = readLine(io)
  ret r
```

A call's arguments that do not fit break after the `(` and are filled four in. A `where` clause that does not fit
goes on a line of its own, four in.

```yafl
fun use(): Int
  let total = combine(
      1000000001, 1000000002, 1000000003, 1000000004, 1000000005, 1000000006, 1000000007, 1000000008, 1000000009)
  ret total
```

## Types and operators

A colon is tight on its left and has one space on its right (`x: Int`, `typealias Count: Int`). A union is tight:
`Int|String|None`. Binary operators have one space each side.

An operator run that does not fit puts each operator at the start of a line, four in.

```yafl
fun check(alphaCondition: Bool, betaCondition: Bool, gammaCondition: Bool, deltaCondition: Bool): Bool
  ret anyOf(alphaCondition, betaCondition, gammaCondition)
      || anyOf(betaCondition, gammaCondition, deltaCondition)
      || deltaCondition
```

## Ternaries

A single `c ? a : b` flows. After the condition, wrapped or not, it is laid out the first of these ways that fits:
`? a : b` on the condition's line; `? a` there and `: b` leading the next line; `?` and `:` each leading a line,
four in.

```yafl
fun check(alpha: Bool, beta: Bool, gamma: Bool, delta: Bool): Int
  ret alphaCondition(alpha, beta)
      && betaCondition(beta, gamma)
      && gammaCondition(gamma, delta)
      && deltaCondition(delta, alpha) ? 0 : 1

fun pick(alpha: Bool): String
  ret alpha ? "the first of two rather long strings, which takes up most of the line"
      : "and the second one, just as long"

fun chomp(line: String, n: Int): String
  ret n > 0 && byteAt(line, n - 1) == '\n'
      ? (n > 1 && byteAt(line, n - 2) == '\r' ? slice(line, 0, n - 2) : slice(line, 0, n - 1))
      : line
```

A chain (`a ? x : b ? y : z`) that does not fit has each condition and its result on a line, `:` leading every
line after the first. A ternary in a `?` branch is bracketed, though the grammar does not need it: `a ? (b ? c : d)
: e`.

```yafl
fun grade(score: Int): String
  let label = score > 90 ? "excellent work, top of the class"
      : score > 75 ? "good work, well above the middle"
      : score > 50 ? "a pass"
      : "not yet"
  ret label
```

## Pipelines

A pipeline that does not fit has every stage on a line of its own, four in. A lambda stage whose body is itself a
pipeline carries it on at the same depth. Three or more nested one-argument calls are written as a pipeline.

```yafl
fun long(xs: List<Int>): List<Int>
  ret xs
      |> (ys) => map(ys, (y) => y + 1)
      |> (ys) => filter(ys, (y) => y > 10)
      |> (ys) => map(ys, (y) => y * 2)
      |> (ys) => filter(ys, (y) => y < 100)

fun three(a: Int): Int
  ret a |> dbl |> inc |> dbl
```

## Match

Each arm is on a line of its own, two in, with one space before `=>`; arms are not aligned. Literal alternatives
that do not fit wrap with `|` leading each line.

```yafl
fun name(x: Int|String|None): String
  ret match(x)
    (i: Int) => "int"
    (s: String) => s
    () => "none"
```

## The shortest spelling

What the parser turns into something longer comes back as what it was: `a && b`, `a || b`, `x is T`, `a[i]`,
`a & ~b`. Brackets appear only where precedence needs them. Literals keep the spelling they were written in
(`0x1F`, `1_000_000`, `7i8`, `0.50`).

```yafl
fun both(a: Bool, b: Bool): Bool
  ret a && b

fun isInt(x: Int|String): Bool
  ret x is Int

fun parens(a: Int, b: Int, c: Int): Int
  ret (a + b) * c + a * b

let [const] MASK: Int = 0x1F
```

## Comments

A comment on a line of its own is re-indented to what follows it; a trailing comment is one space after the code.
Neither is rewrapped.

```yafl
# A leading comment.
fun f(a: Int): Int
  # Re-indented, not rewrapped:   spacing   kept.
  let b = a + 1 # trailing, one space before
  ret b
```

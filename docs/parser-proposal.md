# Proposal: a YAFL parser written in YAFL

> **Status:** design note / proposal. Nothing here is implemented. This sketches
> what a self-hosted parser for YAFL — written in YAFL — would look like if it
> followed the parser-combinator approach of the current Python `parselib`.

The compiler's hand-written recursive descent parser lives in `parsing/`, built on
the combinator library in `parsing/parselib.py`. That library is small and the
indentation handling is genuinely elegant, so the interesting question is whether
the same shape ports to YAFL itself. It does — and the places where it *doesn't*
port cleanly turn out to be the most instructive part.

This note records the design so the idea isn't lost. There is an existing worked
example of a recursive descent parser in the tree already: `stdlib/json.yafl` is a
full streaming JSON parser in the functional state-threading style. This proposal
is the combinator-library generalisation of that.


## Why combinators, and what `parselib` actually gives us

`parselib` leans on four overloaded operators:

| Operator | Meaning | `parselib` source |
|----------|---------|-------------------|
| `\|`     | ordered alternative | `Parser.__or__` |
| `&`      | sequence, flattening results into a tuple | `Parser.__and__` |
| `>>`     | map / transform the result | `Parser.__rshift__` |
| `[:]`    | repetition (`[1:]`, `[:10]`, `[5]`) | `Parser.__getitem__` |

plus the `block` combinator, which is the part that makes layout-as-syntax pleasant.

Three of these port directly. The fourth — `&` — needs care, because its power in
Python comes from *dynamic* variadic tuple flattening, which YAFL deliberately
cannot do. The resolution (a finite tower of typed overloads) is below.


## Token model

Layout is carried as **per-token metadata**, exactly as the current tokeniser does
(`Token.indent`, `Token.line_ref.line`). This is the whole trick behind clean
indentation handling: there is no separate `INDENT`/`DEDENT` token stream and no
lexer state machine — each token simply knows its column and line, and the parser
slices on that.

```yafl
namespace YAFL::Parse
import System

enum Tok
  enum TkIdent()
  enum TkSym()
  enum TkNum()
  enum TkStr()
  enum TkEof()

class [final] Token(kind: Tok, text: String, indent: Int, line: Int)
class [final] Error(line: Int, message: String)
```


## The result type and the parser type

A parse outcome must keep the remaining tokens on **both** the success and failure
paths — keeping `rest` on failure is what lets `orElse` backtrack and `many` stop
cleanly. Soft errors accumulate alongside, mirroring `parselib.Result.errors`.

```yafl
enum Parse<T>
  enum POk(value: T, rest: List<Token>, errs: List<Error>)
  enum PNo(rest: List<Token>, errs: List<Error>)
```

A parser is just a function `(List<Token>): Parse<T>`. Functions are data in YAFL,
so every combinator below takes parsers and returns a parser — no wrapper class is
required (though a `typealias`, if generic callable aliases are supported, would
make the signatures read better).


## Core combinators

```yafl
# `|` — try p, fall back to q on the ORIGINAL tokens.
fun orElse<T>(p: (List<Token>): Parse<T>, q: (List<Token>): Parse<T>): (List<Token>): Parse<T>
  fun run(toks: List<Token>): Parse<T>
    ret match(p(toks))
      (ok: POk) => ok
      (no: PNo) => q(toks)
  ret run

# `>>` — map over the result value.
fun pmap<A,B>(p: (List<Token>): Parse<A>, f: (A): B): (List<Token>): Parse<B>
  fun run(toks: List<Token>): Parse<B>
    ret match(p(toks))
      (ok: POk) => POk<B>(f(ok.value), ok.rest, ok.errs)
      (no: PNo) => PNo<B>(no.rest, no.errs)
  ret run

# Lift a value into a parser that consumes nothing.
fun pure<T>(v: T): (List<Token>): Parse<T>
  fun run(toks: List<Token>): Parse<T>
    ret POk<T>(v, toks, List<Error>())
  ret run
```

`many` (0+), `maybe`, and `delimited` follow `parselib` directly and are omitted
here for brevity.


## Bind is `?>`, and `?>` is not special

`?>` is **not** a privileged construct. The expression parser treats it like any
other binary operator (`parser.py` parses `a ?> b` and desugars it to a call of
`` `?>`(a, b) ``), then ordinary overload resolution picks the implementation. The
`?>` in `stdlib/io.yafl` is *just one overload* — its own comment notes it is
"IO-specific for now; a generic bind over any monad is deferred".

So we are free to add a `?>` overload for `Parse<T>` with exactly the
state-threading semantics a parser needs (keep `rest` on both arms):

```yafl
fun [inline] `?>`<A, B>(p: (List<Token>): Parse<A>,
                        f: (:A): (List<Token>): Parse<B>): (List<Token>): Parse<B>
  fun run(toks: List<Token>): Parse<B>
    ret match(p(toks))
      (no: PNo) => PNo<B>(no.rest, no.errs)
      (a: POk)  => match(f(a.value)(a.rest))
        (b: POk)  => POk<B>(b.value, b.rest, a.errs + b.errs)
        (n: PNo)  => PNo<B>(n.rest, a.errs + n.errs)
  ret run
```

With this overload, a rule that is *context sensitive* (a later parser depends on
an earlier result) reads top to bottom with each piece named:

```yafl
fun funDecl(toks: List<Token>): Parse<Decl>
  ret ( kw("fun") |> kept(ident()) ?> (name: String) =>
        parenList(param, ",")      ?> (ps: List<Param>) =>
        sym(":") |> kept(typeRef)  ?> (rt: TypeRef) =>
        block(many(statement))     ?> (body: List<Stmt>) =>
        pure<Decl>(DFun(name, ps, rt, body)) )(toks)
```


## Sequencing `&` is a finite tower of overloads

Python's `&` flattens results into a single tuple of *arbitrary* arity using
runtime `isinstance` reshaping — reflective, untyped, and exactly the sort of thing
YAFL rejects by design. The YAFL equivalent is **not** variadic generics; it is a
bounded family of arity-specific overloads, each fully typed, resolved by the arity
of the left operand's tuple type. The append helper that does the flattening is the
same idea:

```yafl
fun append<T1,T2>(v1: T1, v2: T2): (T1, T2) => (v1, v2)
fun append<T1,T2,T3>((v1, v2): (T1, T2), v3: T3): (T1, T2, T3) => (v1, v2, v3)
fun append<T1,T2,T3,T4>((v1, v2, v3): (T1, T2, T3), v4: T4): (T1, T2, T3, T4) => (v1, v2, v3, v4)
# …as far up as is worth writing
```

and `&` is the matching tower, each rung running both parsers and appending the
right result onto the (possibly already-tuple) left result:

```yafl
fun `&`<A,B>(p: (List<Token>): Parse<A>, q: (List<Token>): Parse<B>): (List<Token>): Parse<(A,B)>
  ret p ?> (a: A) => q ?> (b: B) => pure<(A,B)>(append(a, b))
fun `&`<A,B,C>(p: (List<Token>): Parse<(A,B)>, q: (List<Token>): Parse<C>): (List<Token>): Parse<(A,B,C)>
  ret p ?> (ab: (A,B)) => q ?> (c: C) => pure<(A,B,C)>(append(ab, c))
fun `&`<A,B,C,D>(p: (List<Token>): Parse<(A,B,C)>, q: (List<Token>): Parse<D>): (List<Token>): Parse<(A,B,C,D)>
  ret p ?> (abc: (A,B,C)) => q ?> (d: D) => pure<(A,B,C,D)>(append(abc, d))
```

`pA & pB & pC & pD` resolves left to right by arity — `(A,B)`, then the `(A,B)+C`
rung gives `(A,B,C)`, then `(A,B,C)+D` gives `(A,B,C,D)` — a flat tuple, entirely
statically. The same `funDecl` then reads in the positional `parselib` style with a
single assembling map at the end:

```yafl
fun funDecl(toks: List<Token>): Parse<Decl>
  ret ( (kw("fun") |> kept(ident()))
      & parenList(param, ",")
      & (sym(":") |> kept(typeRef))
      & block(many(statement))
      >> (name, ps, rt, body): (String, List<Param>, TypeRef, List<Stmt>)
           => DFun(name, ps, rt, body) )(toks)
```

So `&` and `?>` end up complementary: **`&`** accumulates a flat positional tuple
(assemble, then one map — the `parselib` style), while **`?>`** names each result
and is the tool for context-sensitive rules. `parselib` only ever had `&` because
Python's dynamism let one operator carry everything; YAFL gets to pick per rule.


## `block` — the indentation engine

This is the centrepiece and it ports almost verbatim from `parselib.block`. It
finds the span of tokens belonging to the current column, parses that slice in
isolation with a synthetic EOF appended, and resumes at the first token that
dedents back out. No stack, no INDENT/DEDENT tokens — purely a slice on the
per-token `indent`/`line` metadata.

```yafl
fun block<T>(inner: (List<Token>): Parse<T>): (List<Token>): Parse<T>
  fun run(toks: List<Token>): Parse<T>
    let head = _peek(toks)
    let span = _blockSpan(toks, head.indent, head.line, 0)
    let inside = append<Token>(take<Token>(toks, span), _eofAt(head.line))
    let rest = drop<Token>(toks, span)
    ret match(inner(inside))
      (ok: POk) => POk<T>(ok.value, rest, ok.errs)   # discard inner's EOF, resume at rest
      (no: PNo) => PNo<T>(rest, no.errs)
  ret run

# A token stays in the block unless it both starts a later line AND dedents to
# (or past) the opening column. Mirrors parselib.block's scan loop exactly.
fun [tail] _blockSpan(toks: List<Token>, indent: Int, line: Int, i: Int): Int
  let t = _at(toks, i)
  ret match(t.kind)
    (eof: TkEof) => i
    (other)      => t.line > line
        ? (t.indent <= indent ? i : _blockSpan(toks, indent, line, i + 1))
        : _blockSpan(toks, indent, line, i + 1)
```

The `[tail]` attribute keeps the scan off the C stack for pathologically long
blocks, the same defence `_skipWs` uses in `stdlib/json.yafl`.


## The AST

The node types are plain enums and `[final]` classes. The classes (`Param`,
`MatchArm`) double as "do not flatten me" markers — see the design note below.

```yafl
# ── Types ──────────────────────────────────────────────────────────
enum TypeRef
  enum TNamed(name: String, args: List<TypeRef>)   # Int, List<Expr>
  enum TUnion(members: List<TypeRef>)              # Expr|ParseError
  enum TTuple(fields: List<Param>)                 # (state: PState, v: Expr)

class [final] Param(name: String, ty: TypeRef)

# ── Expressions ────────────────────────────────────────────────────
enum Expr
  enum EInt(value: Int)
  enum EStr(value: String)
  enum EName(name: String)
  enum EField(target: Expr, field: String)              # a.b
  enum ECall(callee: Expr, args: List<Expr>)            # f(x, y)
  enum EUnary(op: String, operand: Expr)                # -a
  enum EBinary(op: String, lhs: Expr, rhs: Expr)        # a + b
  enum ETernary(cond: Expr, then: Expr, alt: Expr)      # c ? a : b
  enum ELambda(params: List<Param>, body: Expr)         # (x: T) => e
  enum EMatch(subject: Expr, arms: List<MatchArm>)      # match(x) ...

class [final] MatchArm(binder: String, ty: TypeRef, body: Expr)

# ── Statements / declarations ──────────────────────────────────────
enum Stmt
  enum SLet(name: String, ty: TypeRef, value: Expr)
  enum SRet(value: Expr)

enum Decl
  enum DFun(name: String, params: List<Param>, ret: TypeRef, body: List<Stmt>)
  enum DEnum(name: String, variants: List<Param>)
  enum DClass(name: String, fields: List<Param>)
```

The cycle `Expr → List<Expr> → _ListNode<Expr> → Expr` is exactly what
`mark_complex_enums` detects (see the note in `stdlib/json.yafl`), so these nodes
are heap-allocated automatically. The AST falls out of the same machinery the JSON
DOM already uses.


## Design notes and open questions

**Tuple flattening forbids tuple-valued results.** The `&` tower commits to "tuples
are accumulators, never values". The moment a parser legitimately *produces* a
tuple, `pX & pY` is ambiguous: the base rung (pair them → `((A0,A1), B)`) and the
append rung (spread → `(A0,A1,B)`) both match, and *ambiguity is an error*. This is
correct behaviour, but it means a genuinely tuple-valued sub-result must be wrapped
in a one-field class to opt out of spreading. `parselib`'s Python `&` makes the
identical commitment — but *silently*, via `as_tuple`, so there it is a latent bug
rather than a compile error. The AST classes (`Param`, `MatchArm`) already serve as
these "don't flatten me" wrappers, which is convenient.

**Why not reuse the IO `?>` directly.** The `stdlib/io.yafl` overload carries an
`IO` handle and propagates an `IOError` on the failure arm; a parser carries
`List<Token>` and must keep it on failure for recovery. Different carried state,
same operator — hence a dedicated `Parse<T>` overload rather than reuse.

**Token list vs streaming.** `stdlib/json.yafl` streams bytes from a *linear* `IO`
handle, which is why its `ParseState` is `[linear,final]` and every step threads
the handle by hand. A language parser tokenises first into a `List<Token>`, so the
state collapses to a plain non-linear cursor: free lookahead, free backtracking, no
linear discipline. The combinator library above assumes this token-list model.

**Operator precedence.** `?>` sits at a fixed precedence (below comparison, above
ternary). A bind body containing a `?:` ternary nests as wanted, but a bare
comparison to the right of `?>` binds tighter than the `?>` — worth a test before
relying on it.

**Open questions.**
- Does the type system support a generic callable `typealias Parser<T> = (List<Token>): Parse<T>`? It would clean up every signature here.
- How high should the `append` / `&` tower go before nesting or a record is preferable? Six to eight rungs covers essentially all real grammar rules.
- Error recovery: `parselib`'s `many(..., skip=...)` and `requires(...)` give resync points; the YAFL `many` needs an equivalent skip strategy to keep parsing past a bad rule.

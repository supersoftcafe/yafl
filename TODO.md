
# YAFL bootstrap compiler — remaining blockers

Ranked by how blocking they are to writing the compiler in YAFL itself.

## TOP PRIORITY — generic classes silently mis-type field reads

`DotExpression.get_type` (`pyast/expression.py:231`) does not substitute the
receiver's type arguments into the field's declared type. For a class
`Box<T>(value: T)` and a binding `b: Box<Int>`, `b.value` returns Box's `T`
placeholder verbatim instead of `Int`. So:

```
class Box<T>(value: T)
fun main(): Int
  let b = Box<Int>(42)
  ret b.value      # rejected — "Incorrect type"
```

is rejected, but

```
fun unbox<T>(b: Box<T>): T = b.value     # accepted
fun main(): Int = unbox<Int>(Box<Int>(42))
```

is accepted — *not* because the substitution worked, but because two
different `GenericPlaceholderSpec`s compare to `None` (undecided) under
`trivially_assignable_from`, and `BlockExpression.check` treats `None` as
acceptable (`expression.py:814` — `is False`, not `not …`). The comment on
`GenericPlaceholderSpec.trivially_assignable_from` defers safety to
"instantiation time" — but for the field-read case there *is* no later
catch, because monomorphisation rewrites generic functions and classes
but not the DotExpression's already-computed type.

Symptoms today:
- Generic classes can be defined and used through generic helpers
  (`unbox<T>(b: Box<T>): T`) but their fields cannot be read directly
  from concrete-typed contexts (`main`, top-level let, anywhere with
  concrete return types).
- That forced `stdlib/set.yafl` into the enum-wrapper-plus-match
  workaround instead of `class Set<T>(_d: Dict<T,()>)`. Same dodge will
  be needed for any future generic data class until this is fixed.
- The earlier-fixed `__find_locals` / `get_type` / `create_constructor`
  sites for `this`/constructor type params are necessary precursors but
  not sufficient — without DotExpression substitution, `b.value` still
  yields the placeholder.

The fix is structural, not a one-liner: `DotExpression.get_type` and
`DotExpression.check` need to take the receiver's `ClassSpec.type_params`,
zip them against the resolved class's `type_params`, build the same
`GenericPlaceholderSpec → concrete` mapping that `ClassStatement.compile`
already constructs for parent-class substitution (`statement.py:370-377`),
and apply it via `search_and_replace` to the field's declared type before
returning. The mapping needs to flow recursively when the field type is
itself a `ClassSpec` whose own type params reference the receiver's
placeholders (e.g. `class Box<T>(inner: List<T>)` → `b: Box<Int>` →
`b.inner` must yield `List<Int>`, not `List<T>`).

Two follow-up tasks once the substitution works:
1. Audit `LetStatement.check` and `ReturnStatement.check` for `not result`
   vs `is False` — they currently reject `None` (undecided) while
   `BlockExpression.check` accepts it. The inconsistency is what's been
   masking this bug.
2. Once `DotExpression` substitutes properly, revisit `stdlib/set.yafl`
   to use the cleaner `class Set<T>(_d: Dict<T,()>)` form.

## Follow-up — rewrite `Set<T>` as a class once generic field reads work

`stdlib/set.yafl` is currently a single-case enum wrapper
(`enum Set<T> with _SetWrap(d: Dict<T,()>)`) and every public function
(`add`, `contains`, `remove`, `size`) destructures it via `match`:

```yafl
fun add<T>(s: Set<T>, value: T): Set<T> where BasicEquality<T>
  ret match(s)
    (w: _SetWrap) => _SetWrap<T>(put<T,()>(w.d, value, ()))
```

The match dance is purely there to dodge the DotExpression substitution
bug above — `s._d` from a concrete-typed call site (e.g. another stdlib
function that calls `add<Int>(Set<Int>(), 5)`) returns the placeholder
type instead of `Dict<Int,()>`, so direct field access fails type-check.
Wrapping in an enum and destructuring via match coincidentally side-steps
the bug because `match` substitutes correctly.

Once `DotExpression.get_type` substitutes receiver type params (the TOP
PRIORITY item above), rewrite `set.yafl` to:

```yafl
class Set<T>(_d: Dict<T,()>)

fun Set<T>(): Set<T>
  ret Set<T>(Dict<T,()>())

fun add<T>(s: Set<T>, value: T): Set<T> where BasicEquality<T>
  ret Set<T>(put<T,()>(s._d, value, ()))
# ... etc ...
```

Each function drops the `match` boilerplate (3 lines → 2 lines each, four
functions). All 11 tests in `tests/test_set.py` should pass unchanged —
the rewrite is purely the public surface getting closer to what the user
wanted in the first place.

## Follow-up — optimal binding-order analysis (was: nested-fn codegen hazards)

The original "nested function calling its enclosing function" bug split
into two parts: (a) the hoist mis-classification that left dangling
references when a non-capturing sibling called a capturing one; (b) the
runtime crash when two capturing nested fns mutually called each other
through independent closures. The current fix (in `lowering/ast_inline.py`)
handles both — by running an SCC analysis over the sibling-call graph,
forcing non-capturing callers of capturing closures into closure form,
and coalescing mutually-recursive capturing SCCs into a single class
with one method per member so cross-calls route through `this`.

What remains is broader than nested fns or lambdas. It's an
**optimal-ordering / lazy-init problem** for any binding block.

A YAFL block is a series of uninterrupted `LetStatement` /
`FunctionStatement` declarations — anything with side effects is an
`ActionStatement` which by definition splits blocks. Within one block,
**any binding can reference any other**; that's the language's contract,
not a property tied to nested fns.

The hoist transform needs to honour that contract by *choosing* an
evaluation order:

1. **Reorder Let/Function statements so no recursive issue remains** —
   then ordinary sequential evaluation suffices. Topological sort over
   the dependency graph; works when the graph is a DAG.
2. **Reorder so only functions form recursive cycles** — then the
   mutual-class solution (current fix) handles those cycles; Lets stay
   plain sequential. Works when the cycles are confined to function
   bindings.
3. **No reorder eliminates the cycle (recursive Let↔Let or Let↔Fn
   cycles)** — fall back to lazy initialisation:
   - Push all the at-risk Lets/Fns into one mutual class.
   - Convert each at-risk Let into a member function (zero-arg
     thunk) that performs the lazy init and returns the value.
   - Member-function dispatch through `this` then resolves the cycle
     uniformly.

Edge cases that need (3) should be rare. The compiler should try (1)
first, fall back to (2), and only reach (3) as a last resort —
preferably with a diagnostic so the programmer knows they tripped it.

Witness for why (1)/(2) alone are insufficient:

```yafl
fun outer(f: String): String
  fun inner1(g: Int): String
    ret g < 1 ? f : inner2(g - 1)
  let x = "_x_"
  fun inner2(g: Int): String
    ret g < 1 ? x : inner1(g - 1)
  ret inner1(3)
```

`inner1` and `inner2` are mutually recursive and both visible to each
other and to the `let x`. `inner2` captures `x`. The current fix emits
the synthesised `let shared = MutualClass(f, x)` at the position of
the first SCC member (i.e. before `x`), so `x` is read-before-write at
the construction site. Reordering `x` before `inner1` resolves it here
(`x` doesn't depend on either fn), but the general case can construct
mutually-dependent Let/Let or Let/Fn cycles where no order works — that's
where lazy thunks land.

## Hard blockers (compiler cannot function without these)

- **argv / process args** — no way to read CLI input filenames today.
- **subprocess spawn** — need to invoke clang. Workaround: split into "yafl emits
  C, shell wrapper runs clang"; that means the YAFL binary alone isn't a
  self-contained compiler.

## Ergonomic blockers (possible but writing 5K lines of yafl would be brutal)

- **String builder / chunked concat** — codegen produces tens of KB per file;
  naive `+` is quadratic. YAFL strings are immutable.  Either a `List<String>`
  builder convention or a dedicated `StringBuilder`. The chunked-list pattern
  from `JsonBigStr` is the model.

## Stdlib gaps

- **Set** — symbol tables / seen-sets. Workable via `Dict<K, None>` but ugly at
  every call site.
- **Format strings / printf** — for diagnostics. Every Error today is built by
  `+`-concat.
- **More List ops** — `groupBy`, `fold`, `partition`, `findIndex`; writable but
  most compiler passes want them.
- **Path / filesystem** — read a directory, stat, exists. Today only
  `open_read` / `open_write` / `create` exist.

## Performance / scaling

- **Compiler self-throughput** — the Python compiler runs the suite in ~33 min
  today. A YAFL compiler will be slower (per-call dispatch through generics,
  allocation per AST node). It needs to compile itself in a tolerable time,
  gated on: generic monomorphisation cost, GC throughput under high
  allocation, and whether `[tail]` covers enough of the deep traversal paths.
- **Compile times scale with stdlib size** — every example pulls in the whole
  stdlib. As the stdlib grows to support bootstrap, compile times balloon.

# Tail-call optimisation — done

Both sync and async functions now get tail-call optimisation. The state
machine path re-expands `Call(musttail=True)` back into `Call + Return` via
`__unroll_musttail_for_state_machine` so the terminal-block writer's
`task_complete` sequence still fires; the hot path keeps the `musttail`
so clang emits `return foo(...)` and TCOs it. `strip_unused_operations`
treats `Call(musttail)` as a terminator and guards its worklist against
re-queuing seen indices, so cyclic CFGs converge.

Landed in `3c5f5c4`. The `stdlib/json.yafl` lookahead workaround
(`_strBody` bulk-consume of ~1 KiB per recursion) predates the fix and is
no longer needed for correctness — keep it as a perf win or simplify if a
profile says it doesn't matter.


# Another specific heap layout optimisation

```
enum List<T>
  enum ListEmpty()
  enum ListFull(front: _ListNode<T>, rear: _ListNode<T>)
```

Check if the ListEmpty() case uses runtime NULL in one of the fields as the signal, or if it
uses an extra field to distinguish. There is an optimisation opportuntiy here.

# JsonValue is complex

The C code backing JsonValue is super complex, and it even has been promoted to a class. In theory
this should not have been necessary, but will need an overhaul of how enums are encoded.

# Parallel grep

Regex search folder hierarchy. Initially explicitly use __parallel__ but later when auto
parallelisation is in remove explicit parallel usage.

# Folder for build of examples

Need to start formalization of build systems and dependencies.

# Parallel tuple construction

This is a core feature for supporting implicit parallelism. Any tuple construction would be
analysed for complexity, and if high each part could be pushed to a different worker. Additionally
sequences of non-dependent let statements could be grouped into tuple constructions so that
there are more parallel computation opportunities.

# Optimiser to reduce local variables

If different parts of a function use a variable declared as object_t*, but they don't overlap, 
they can share the same slot. This goes for heap frames for async functions as well, and of
course other types. This step would reduce heap usage. Doesn't really reduce stack usage as
the C compiler will do that anyway.

# Large strings

Heap only supports smaller objects, as a design choice. Larger strings will need to be
compound objects. Needs some thought.

# IO readline

Just what it says

# IO TTY input

Currently the IO module tries to fill the buffer, which means that TTY input beyond what is needed
must be entered, or CTRL-D pressed before the program will respond. Ideally we need to have a read
mode that does not fill the buffer, but rather only reads exactly what is needed to fullfil the
request.

# Tuple let grouping

A lowering pass groups all sequences of independent `let` bindings — those with
no data dependency between them — into a single tuple construct/destruct
statement. This is unconditional: every eligible sequence is grouped regardless
of cost. A later, separate pass will decide which grouped tuples to evaluate in
parallel based on a weighing function. The consequence is that independent `let`
bindings must not be assumed to have a defined evaluation order.

# Conditions
```
fun condition(x:int): int
  if x > 10:
    let r = 20
  else: # Else is required, otherwise 'r' might not be set
    let r = 10
  ret r
```
is functionally equivalent to
```
fun condition(x:int): int
  let r = x > 10 ? 20 : 10
  ret r
```
which suggests that condition blocks are compatible with the functional
paradigm if each block defines the same named values with the exact same
types, where the value is referenced downstream.

These are not mutations, but they look like mutation, and allow
the programmer to think in classical non-functional terms.

# Loops
```
fun loops(x:int): int
  # Required default value if the loop is empty.
  let a = 1
  for i in 0 to 3
    let a = a+x
  ret a
```
is functionally equivalent to
```
fun loops(x:int): int
  let a = 1
  let a0 = a+x
  let a1 = a0+x
  let a2 = a1+x
  ret a2
```
which suggests that loops are compatible wiaddth the functional paradigm if
the inner loop type of 'a' is identical to the outer loop type, where the
value is referenced downstream.
```
fun loops(x:int): int
  let a = 1
  for i in 0 to 3
    let a = a+x
    break if a > 20
  ret a
```
A break statement should be safe as well, and in terms of recursion is
the procedural equivalent of a return statement. It still obeys the
functional paradigm, but having it inside conditions might imply that
else blocks are not required. I think that making the break statement
itself a condition helps to avoid this anti-pattern.





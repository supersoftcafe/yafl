
# YAFL bootstrap compiler — remaining blockers

Ranked by how blocking they are to writing the compiler in YAFL itself.

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

- **subprocess spawn** — need to invoke clang. Workaround: split into "yafl emits
  C, shell wrapper runs clang"; that means the YAFL binary alone isn't a
  self-contained compiler.

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


# Generic class field reads — done

`DotExpression.get_type` and `DotExpression.check` now substitute the
receiver's `ClassSpec.type_params` into the field's declared type via
`_substitute_class_type_params` (`pyast/expression.py`). The substitution
flows recursively through nested `ClassSpec`s so `b: Box<Int>; b.inner`
yields `List<Int>` rather than the bare `T` placeholder.

`LetStatement.check` and `ReturnStatement.check` use `is False` to compare
trivially-assignable results, matching `BlockExpression.check`'s treatment
of `None` (undecided) as acceptable. Landed in `63f7de5`.

Follow-up `Set<T>` rewrite from enum-wrapper to `class Set<T>(_d: Dict<T,()>)`
also landed in `63f7de5`; field accesses (`s._d`) now type-check directly
and all four public functions dropped their `match` boilerplate.


# argv / process args — done

`stdlib/args.yafl` exposes `args(): List<String>` built on the foreign
helpers `sys_argc` / `sys_argv_at`. Callers get the user-supplied
positional args without the program path. Landed in `f9ad565`.


# StringBuilder — done

`stdlib/string.yafl` provides a `StringBuilder` for amortised-linear
string concatenation; `format` is the primary user. Eliminates the
O(n²) `+`-concat hazard for code that produces tens of KB of output
(notably codegen). Landed in `f9ad565`.


# format / printf — done

`stdlib/format.yafl` provides `format(template, args...)` with
per-arity overloads up to four arguments; each argument's value is
rendered via its `Show<T>` instance. Diagnostics and assertion
messages no longer need `+`-concat. Landed in `f9ad565`.


# Stdlib list ops & filesystem — done

`stdlib/list.yafl` now provides `findIndex<T>`, `partition<T>`, and
`groupBy<T,K>` alongside the existing `fold`/`map`/`filter`/etc.
`groupBy` returns `Dict<K, List<T>>` with `where BasicEquality<K>`.
All three are implemented in terms of `fold`.  An earlier draft used
direct cons-list recursion as a workaround for a lambda-lift bug; that
bug (collision on `lambda@<line_ref.hash6()>` across monomorphisations
of the same template) was fixed by switching the lambda-class naming
to a path-based scheme — `lowering/lambdas.py:__collect_lambda_paths`
records the enclosing-statement path for every `LambdaExpression` and
`__create_unique_name` mixes the path into the class name so two
monomorphisations of `fold<T,U>` produce two distinct classes.

`stdlib/fs.yafl` is new: `exists(path): Bool` (errors map to false),
`stat(path): FileInfo|IOError` with a public `class FileInfo(size,
mtime, isDir, isRegular, mode)`, plus a `[linear,final] Dir` cursor
(`openDir` / `next` / `[terminal] close`) and a `listDir(path):
List<String>|IOError` convenience that opens, drains, and closes the
handle.  All ops dispatch through the existing IO threadpool —
`io_thread.c`'s switch grew five new cases (`IO_OP_FS_EXISTS`,
`IO_OP_FS_STAT`, `IO_OP_DIR_OPEN`, `IO_OP_DIR_NEXT`, `IO_OP_DIR_CLOSE`)
and `io_job_t` carries a small `fs_aux: fs_file_info_t*` and `dir:
dir_t*` for those ops.  The `FileInfo` is pre-allocated on the worker
before STAT dispatch so the IO thread only writes scalar fields — the
allocation boundary rule from `[[feedback_io_design]]` is preserved.

Test coverage: `tests/test_runtime.py::TestListOps` (9 cases),
`tests/test_fs.py` (9 cases). The compiler suite is now 591 tests at
~18 min.


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






# YAFL bootstrap compiler — remaining blockers

Ranked by how blocking they are to writing the compiler in YAFL itself.

## Hard blockers (compiler cannot function without these)

- **argv / process args** — no way to read CLI input filenames today.
- **subprocess spawn** — need to invoke clang. Workaround: split into "yafl emits
  C, shell wrapper runs clang"; that means the YAFL binary alone isn't a
  self-contained compiler.
- **Recursive stack depth** — non-tail recursion blows the C stack. The
  `[tail]` attribute helps but only in tail position. The typechecker walks
  deep AST trees through arbitrary call paths. The async-tail-detection bug
  below is part of this.

## Ergonomic blockers (possible but writing 5K lines of yafl would be brutal)

- **Early return from BlockExpression** (see section below) — the
  "validate, validate, validate, build" pattern is the entire compiler. Without
  it every check becomes a nested `match`.
- **Conditions / Loops** (see sections below) — every multi-line branch becomes
  a ternary or a recursive helper. Both already designed; not implemented.
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

- **Compiler self-throughput** — the Python compiler runs the suite in ~10 min
  today. A YAFL compiler will be slower (per-call dispatch through generics,
  allocation per AST node). It needs to compile itself in a tolerable time,
  gated on: generic monomorphisation cost, GC throughput under high
  allocation, and whether `[tail]` covers enough of the deep traversal paths.
- **Compile times scale with stdlib size** — every example pulls in the whole
  stdlib. As the stdlib grows to support bootstrap, compile times balloon.

## Latent design

- **Linear types** (see section below) — not strictly needed, but a compiler
  opens many file handles and the leak hazard is real.
- **Reflection / compile-time derivation** — explicitly out of scope. Means
  every AST node type needs hand-written equality, hash, traverse, etc.;
  manageable but adds ~30% boilerplate to the AST module.

## Highest-leverage first

If picking two things to fix first to unblock real progress: **early return
from BlockExpression** and **a chunked-string builder convention**. Without
those, the compiler code reads like a Lisp transcribed into ternaries.


# Compiler bug — tail-call detection only enabled for sync functions

`async_lower.__discover_tail_calls` now identifies `Call → Return(register)`
patterns and sets `musttail`, which lets codegen emit `return foo(...)` and
clang TCO it (even at -O0). But the optimisation is currently gated on
`fn.sync` — async functions are skipped — because of two downstream issues
that the state-machine pass still has:

1. **State machine never completes the task.**  The terminal-block processing
   in `__create_state_machine_func` only emits `Move(task->result, …) +
   task_complete + ReturnVoid` when it sees a `Return` op. A tail-called
   function whose `Return` was removed by `__discover_tail_calls` falls off
   the end of the state machine without ever calling `task_complete`, leaking
   the in-flight task forever.

2. **CFG cycle hangs `strip_unused_operations`.**  The state machine for an
   async function whose terminal Call is musttail looks like:
   ```
   SwitchJump
   $resume$0:
     Call(_strBody, musttail)   ← was Call+Return; now Call only
   $case$1:
     Move (extract result)
     Jump $resume$0             ← cycle closes here
   ```
   `strip_unused_operations` walks this CFG one index at a time and treats
   `Call` as falling through to the next op. It also has a separate latent
   bug: it doesn't filter `to_see_indexes` against `seen_indexes`, so a
   cyclic CFG re-adds the same indices forever.

Two fixes need to land together to enable async tail calls:
  * In `__create_state_machine_func`, before processing the terminal block,
    expand any `Call(musttail=True)` back into `Call(register=tmp) +
    Return(tmp)` so the existing `task_complete` logic fires. The temp var
    needs to be added to the state object's field list.
  * In `things.strip_unused_operations`, filter `to_see_indexes -=
    seen_indexes` per outer iteration so cyclic CFGs converge. Also needs
    `Call(musttail)` treated like `Return` — no successor.

Workaround in `stdlib/json.yafl`: bulk-consume from a buffered lookahead so
each recursion processes ~1 KiB at once, dropping the depth from O(N bytes)
to O(N / 1024). Sync helpers (e.g. `_strScanDelim`) get the optimisation
already; async parser bodies would benefit if the two fixes above land.


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

# Linear types

A linear type is a type that once initiated must be used exactly once. Each use then creates a new instance
for the next function in the chain, finally terminating on a function that does not return a new instance.

This compiler level checking ensures that some handle that represents a resource can only be used by one
thread at a time and that it will be destroyed. The IO library is waiting for this to get language safety
for closing file handles.

# Early return from BlockExpression

To support more coding styles that are not anti-functional, an early return is not just acceptable, it
is very useful.

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





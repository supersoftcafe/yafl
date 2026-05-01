
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


# Compiler bug — Bool through async-state slots becomes struct vs int8_t

A function returning `Bool` that gets called from inside another function and
captured into the caller's async state slot triggers a codegen type mismatch:
the slot is declared `struct_anon_X_t` while the assignment site uses
`int8_t`. Repro: `_jsonShouldFlush(...): Bool` called from `_strAppend` (which
becomes a state machine because it transitively calls `read`) was the original
trigger; lifting the helper to top-level didn't help.

Workaround in stdlib/json.yafl: carry the flag as `Int` (0/1). The proper fix
is in either the boxing pass or the state-object field-type computation —
something is treating Bool as `Bool|None` (or similar union) at one site and
plain `bool` at the other.


# Compiler bug — nested ternaries returning Int literals box inconsistently

Repro (5 lines, no I/O):

```yafl
fun test(b: System::Int): System::Int
  ret b > 127 ? (b > 191 ? 0 : 1) : 0
```

clang errors with two distinct types (`struct_anon_0_t` from the inner
ternary, `object_t*` from the outer literal) being assigned to the same return
variable. The boxing pass wraps the inner ternary's result in a 1-tuple
(`{._0 = …}`) but leaves the outer `0` literal bare; both feed into the same
return slot. Fix is in `lowering/boxing.py` — likely the BoxExpression
recursion for nested match/ternary trees needs to either box uniformly across
all sibling branches or strip the wrap when the join point is a primitive.

Workaround: bind the inner ternary to a `let` first; each layer then has at
most one ternary, which the boxing pass handles correctly.


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





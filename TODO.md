
# YAFL bootstrap compiler — remaining blockers

Ranked by how blocking they are to writing the compiler in YAFL itself.

## TOP PRIORITY — deep method chaining: type-resolution gap

The PARSER half is **done** (2026-06-07): postfix `.field` / `(...)` / `[...]`
now form one left-associative chain (`parsing/parser.py`, `__parse_invoke` /
`__to_invokes` / `__parse_postfix_dot`), so `f().g()`, `a().b`, `m()[0].x` etc.
parse. End-to-end works for field-on-call (`pair().a`), method-on-constructor
(`Box(5).get()`), and index chains. Tests: `tests/test_postfix_chaining.py`.

**What remains (this is the important bit):** a method call whose receiver is
itself a *method-call result* — `Box(0).inc().get()` — still fails, crashing at
*generate* with "could not cast None to CallableSpec". Marked as an
`@unittest.expectedFailure` tripwire in `test_postfix_chaining.py`
(`..._KNOWN_GAP`); remove that marker when fixed.

**Root cause (confirmed 2026-06-07):** expression types are *recomputed* via
`get_type()` at GENERATE time, but by then the **Task lowering** (`async_lower.py`,
an AST pass — NOT "CPS") has rewritten every call's `return_type` to unit
(`TupleSpec()`): the result is delivered via the completion task. So
`DotExpression.generate`/`get_type` for the outer `.get` walks into the lowered
inner `inc()` call, gets the unit type, picks the wrong branch, returns `None`,
and `CallExpression.generate` casts that `None` (`call.py:72`). Verified: the
working let-decomposed form's lowered `inc` is *also* unit-typed — it works only
because the receiver is a `let`-bound variable whose type was pinned to
`ClassSpec(Box)` at COMPILE time (pre-lowering), so generate reads the pinned type
rather than recomputing through the lowered call. (My earlier "NamedSpec base"
note was wrong — disproven by tracing.)

**The proper fix is architectural (user's call):** the Task lowering runs at the
AST stage, which is *too early* — it mutates the AST's type semantics before
AST→IR codegen reads them. It belongs in the **IR stage** (splitting functions at
suspension points into heap-frame state machines is a control-flow/codegen
concern). Move it there and the AST stays cleanly typed through `check`/`generate`,
so this bug — and the whole "recompute types at generate on a lowered AST" class
of fragility — disappears. Large, careful project; not started.

**Band-aids if we need chaining sooner** (all compensate for the early lowering):
- (A) Pin resolved types onto nodes at compile and use them at generate instead
  of recomputing. `get_type` is shared between the compile fixpoint (must
  recompute) and generate (wants the pin), so separating the phases is the catch.
- (B) ANF-normalise postfix chains into `let` temporaries during compile
  (`a.b().c()` → `let t = a.b(); t.c()`), reusing the known-good let path.
- (C) Carry each call's true pre-lowering result type on the lowered call.

## Language & parser features

From a parser review (2026-06). Bit shifts (`<<`/`>>`, all integer types), a
`splitLines` helper, arrays (`Array<T>` + the `[]` index operator, built on
the array-as-final-class mechanism — `stdlib/array.yafl`), short-circuit
`&&` / `||`, and `if` / `else if` / `else` are now done; remaining:

- **`\u` / `\x` string escapes.** Strings are UTF-8 codepoints, but only
  `\n \r \t \0 \\ \" \'` decode — there is no way to write a non-ASCII codepoint
  as an escape. Add `\xNN` and `\u{…}` / `\uXXXX`.
- **`map` combinator (parser simplification).** ~30 of the parser's `__to_*`
  callbacks only transform `result.value` yet hand-thread
  `tokens`/`line_ref`/`errors`. A `Parser.map(f)` combinator would collapse
  them, leaving `>>` only for the few that add errors or inspect tokens.

Explicitly not planned: block comments (only `#` line comments) and multi-line
string literals.

## Lift the 16 KB per-object size cap — done

`_object_alloc` (`yafllib/object.c:350`) now allocates a dedicated multi-page run
for objects larger than one page (the `actual_size > MAX_OBJECT_SIZE` branch)
instead of calling `abort_on_too_large_object`, so strings/arrays grow past
16 KB. The scaffolding described below (page-count tracking, multi-page free,
compaction skip) is all wired in now.

**What's already there.** The scaffolding for multi-page allocations exists
but is partly disabled. `page_head_t.pages` (line 84) explicitly counts
"pages, including this one, in the complete allocation". `gc_page_alloc(page_count)`
(line 272) already takes a count, calls `memory_pages_alloc(page_count)`,
zeros all pages, stores the count. `gc_page_free` (line 312) routes
multi-page allocations straight to `memory_pages_free`, bypassing the
single-page quarantine. `gc_compact_page` (line 508) early-returns on
`pages > 1` — multi-page is never moved, so `[is_mutable]` invariants
come for free. The stubbed allocation path at lines 348–354 sketches the
alloc branch but is replaced with `abort_on_too_large_object`.

**The threat model the simple fix gets wrong.** Multi-page allocations have
only one valid object pointer — slot 0 of the head page. There are no real
interior pointers in YAFL data. The hazard is **spurious** interior pointers:
a stack word during conservative scanning that happens numerically to land
in a tail page. Today's checks fail unsafely: `memory_pages_is_heap` returns
true (the page is part of our address space); masking gives the tail page;
`bitmap_test(&page->head.objects, slot)` reads the first ~64 bytes of the
tail page **as a `bitmap_t`** — but those bytes are payload (string data).
For a long string the bit at `slot` will eventually be set by chance, and the
GC will treat the spurious address as a live object: read `object->vtable`,
dispatch, corrupt. In-band page validation cannot work for tail pages
because their first bytes are user payload.

**Side table for page state.** A **byte-per-page side table** maps every
page in the reserved heap region to one of `FREE`, `HEAD`, `TAIL`.
Validation in `gc_object_is_on_heap_slow` becomes a single lookup; the
magic-number tag goes away. `gc_page_alloc(N)` claims a run of N `FREE`
entries and marks `HEAD + (N-1) × TAIL`. N=1 is the normal path.
`gc_page_free` walks N entries back to `FREE`; single-page goes through
quarantine as today; multi-page decommits the pages and returns immediately.
`head.tag` is removed (the side table is now the authority).
`head.pages` stays — O(1) freeing without walking the table.
The existing bitmap-of-mapped-pages in `memory.c` collapses into the side
table.

**Pre-allocated virtual heap region**, JVM/Node-style: at startup,
`mmap(NULL, HEAP_VIRTUAL_MAX, PROT_NONE, MAP_NORESERVE | MAP_ANON | MAP_PRIVATE, -1, 0)`
a fixed range. All YAFL heap pages live inside it. Real memory only gets
billed on commit (`mprotect READ|WRITE` or `mmap(MAP_FIXED)` over the
reserved range). On `gc_page_free` for multi-page allocations,
`madvise(MADV_DONTNEED)` returns real RAM to the OS while keeping the
virtual range reserved — committed footprint tracks live large objects,
not peak. `HEAP_VIRTUAL_MAX` can be aggressive (16–64 GB on 64-bit Linux);
reserved-but-uncommitted pages cost effectively nothing. The side table
is then a flat `uint8_t[HEAP_VIRTUAL_MAX / GC_PAGE_SIZE]` (≤ 4 MB per GB
of virtual heap).

**Work to do.** Reserve the heap region at startup and rework `memory.c`
so all allocations commit within it. Introduce the side table; expose
`page_state_get(addr)` and a run-set operation. Replace
`gc_object_is_on_heap_slow`'s magic-tag check with the side-table lookup.
Enable the multi-page branch of `_object_alloc` — set `head.mutable`,
mark slot 0 in `head.objects`, link the head page into `new_pages`,
return `&page->slots[0]`. Drop `head.tag` and the existing
bitmap-of-mapped-pages. Tests: a 1 MB / 4 MB string survives a GC cycle
through a stack reference; a stack word whose value falls inside a tail
page does not register as a live object; RSS returns to baseline after
multi-page allocations are dropped; stress test interleaving single-page
and multi-page allocations during a GC cycle.

**Knock-on once this lands.** `abort_on_too_large_object` becomes
unreachable — remove it. The "Large strings" entry further down this file
is subsumed: `String` just works at any size, no rope wrapper needed.
`StringBuilder` is no longer load-bearing for safety; still a perf win
for many-concat workloads but no longer the only way to produce a large
string.


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

- **subprocess spawn — done.** `System::IO::run(program: String, args: List<String>):
  ProcessResult|IOError` (`stdlib/process.yafl`) spawns a PATH-resolved program
  through the IO threadpool (`posix_spawnp`, stdin = /dev/null), capturing stdout,
  stderr, and the exit code. A non-zero child exit is a successful `ProcessResult`,
  not an error; only a failure to start the program is `IOError`. argv crosses the
  foreign boundary as a single NUL-separated String (the separators double as the
  C-string terminators), split back out in `process_run` (`io.c` / `io_thread.c`,
  `IO_OP_SPAWN`); stdout/stderr captured into growable non-GC buffers via `poll()`
  (deadlock-free). Tests: `tests/test_process.py`. A YAFL-written compiler can now
  invoke clang directly.

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

# JsonValue is complex — resolved (note was stale)

DO NOT re-investigate. Reviewed 2026-06-07: the JsonValue encoding is fine and
not an issue. (For the record: it's the recursive `_ListNode` cons cell that gets
heap-promoted as the cycle-breaker, not JsonValue itself — JsonValue stays a flat
by-value tagged-union struct. The generated C looks verbose because of the
type-segregated shared-slot packing, but it's correct and works.)

There is a SEPARATE, genuine question about more efficient enum *packing* (the
flat-tagged-union slot layout vs a sum-of-products / boxed-per-variant encoding) —
deliberately deferred, not a bug. Don't conflate it with this stale note.

# Parallel grep

Regex search folder hierarchy. Initially explicitly use __parallel__ but later when auto
parallelisation is in remove explicit parallel usage.

# Build system, libraries & examples — done

Project-folder compilation, manifest-based libraries (`.yl` packages), the
installed `yafl` toolchain (static-only runtime), and the standalone `examples/`
project are implemented. See docs/build-and-packaging.md.

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

# Large strings — done

Resolved by multi-page object allocation (see "Lift the 16 KB per-object size
cap"): a large string is a single object spanning multiple pages — no
compound-object scheme needed.

# IO readline — done

`IO.readLine(): (io: IO, v: String|IOError)` is implemented in `stdlib/io.yafl`:
reads one byte at a time, stops at `\n`, skips `\r`, and returns a partial line
on EOF-with-bytes (EOFError only when no bytes were read). Note this is distinct
from the buffering issue below — readLine still goes through the buffer-filling
`read`, so on a TTY it shares the "IO TTY input" latency problem until that lands.

# IO TTY input — done

Fixed in `yafllib/io_thread.c` (IO_OP_REFILL): the read path used
`fread(io->buf, 1, IO_BUFFER_SIZE, …)`, which loops until the 8 KB buffer is full,
so interactive (TTY/pipe) reads blocked until 8 KB was typed or Ctrl-D. It now
uses a single `read()` syscall, which returns as soon as any input is available —
fixing the interactive block while preserving file read-ahead (so byte-at-a-time
`readLine` is still served from the buffer, not one syscall per byte). Test:
`tests/test_io_tty.py` (drives the process with a held-open stdin pipe).

# Tuple let grouping

A lowering pass groups all sequences of independent `let` bindings — those with
no data dependency between them — into a single tuple construct/destruct
statement. This is unconditional: every eligible sequence is grouped regardless
of cost. A later, separate pass will decide which grouped tuples to evaluate in
parallel based on a weighing function. The consequence is that independent `let`
bindings must not be assumed to have a defined evaluation order.

# Conditions (if / else if / else) — done

Implemented as `IfStatement` (`pyast/statement.py`). It is a **statement**, not
an expression — pure control flow yielding no value (the value-producing
conditional remains the ternary `?:`). `else` is optional; `else if` chains via
`ElseIfStatement` + `collapse_else_if`. Branches are pure scopes (a `let` inside
a branch is branch-local and does not escape); a branch ending in `ret` exits the
function, otherwise control falls through. Lowers to `JumpIf`/`Label`/`Jump` (no
Phi merge, distinct from the ternary). The condition must be `Bool`. Tests:
`tests/test_conditionals.py`, `tests/test_conditionals_runtime.py`.

DO NOT re-design or re-implement this — the design was re-derived from scratch in
discussion on 2026-06-07 only to find it already existed and matched. The original
"each block defines the same named values" sketch was NOT adopted: branch-local
`let`s do not escape, so an `else` is not required to "set" a downstream value.

# Loops — design under discussion, DO NOT implement

`[tail]` recursion (`lowering/tail_loop.py`) already covers the capability. Whether
to add surface loop syntax — and what it looks like — is an OPEN design question the
user is actively developing; we have not reached agreement. Do not implement or
re-propose a design until the user drives it. The sketch below is an early,
non-final note, not an agreed spec.

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

## `[tail]` on nested functions — done

Nested `[tail]` functions (and methods) are now lowered too (`lowering/tail_loop.py`),
so a `[tail]` loop can be written nested — capturing outer variables — instead of
a top-level helper that threads state through parameters.





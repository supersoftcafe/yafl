# Compiler-directed recycling — prototype

> **STATUS 2026-10-04: opt-in prototype, Python reference compiler only.**
> Off by default; with it off, generated C is byte-identical to before. Turn
> it on per compile with `--recycle` (or `YAFL_RECYCLE=1` in the compiler's
> environment). The bootstrap port does not implement it, and the full
> protocol has not been run with it on.

## 1. The idea

The collector is paced by **pages allocated** (`yafllib/object.c`, "PACING"):
every page the mutator takes buys a fixed slice of marking and pruning. A
transient object therefore costs GC work in proportion to the page space it
consumes, however briefly it lives. The bump pointer itself is cheap.

So if an object is provably dead *and* was never seen by anyone else, its slot
can be handed back and taken by the next allocation of the same size **without
moving the bump pointer**. A loop that replaces one object with the next then
runs in one or two slots instead of marching across the heap. It never
consumes page budget, so it never drives a cycle.

The work divides along one line:

* **The compiler proves ownership.** The object is unique and dead at this
  point. A wrong answer is a use-after-free.
* **The runtime checks only the collector's view.** The slot is on a page no
  cycle can be looking at. A slot that fails this check is left to the
  collector, which is always correct.

## 2. Runtime (`yafllib/yafl.h`, `yafllib/object.c`)

**Where reuse is safe: this thread's pages since its last root scan.** A
thread's bump pages sit on its `new_pages` list until its root scan moves them
into the collection pool (the `list_move` in the SCAN_ROOTS stage). Until then
no cycle scans or prunes them: this is the existing **birth protection**. A
slot there can change occupant without the collector ever noticing.

* Each thread has a recycle **epoch**: a globally unique, non-zero 32-bit
  number.
* Each page records the epoch of the thread it was handed to
  (`page_head.recycle_epoch`). The stamp is 0 for mutable pages, multi-page
  objects, relocation targets, and when recycling is off.
* **At the root scan**, in the same place the bump regions are reset (whether
  the thread itself does it or the thread scanning it while it is suspended),
  the thread's recycle lists are dropped and its epoch moves on. That single
  step retires every slot allocated before the scan. The dropped slots are
  simply garbage, and that same cycle sweeps them.

**Free lists.** Each thread keeps a LIFO per size class: 8 classes of 32-byte
slots, so up to 256 bytes, each 32 entries deep (`gc_recycle_tl`). The
allocation fast path pops a class's list before bumping, but only in code
compiled with `#define YAFL_RECYCLE`, which the compiler emits when the pass is
on. A popped slot is already in the page's `objects` bitmap. It owes only the
same snapshot-smear guard as any allocation: allocate black between a cycle
opening and this thread's root scan.

**The forms generated code calls.**
* `yafl_recycle(o)` and `yafl_recycle_if(o, owned)` push onto the free list.
  The `_if` form's `owned` flag is explained in §3.
* `yafl_reuse(token, owned, vt)` is the register form (§3.4). If the dead
  token is of class `vt` and on a current-epoch page, the token's slot becomes
  the new object. Otherwise it is an ordinary `object_new`.

These forms check only the page epoch and the per-thread `limit`. They avoid
extern globals deliberately: an earlier version that range-checked
`_memory_heap_base` kept three GOT pointers live across the loop and lost to
the baseline on register spills alone. The checked `object_recycle` (for
runtime code and tests) additionally rejects tagged scalars, NULL, static,
pinned, mutable and arrayed objects.

**Knobs.** All are read at the first thread's registration, which happens
before anything else runs.

| env | effect |
|---|---|
| `YAFL_RECYCLE=0` | recycling off: pages are stamped 0, so every recycle is a no-op |
| `YAFL_RECYCLE_POISON=1` | never reuse. Each recycled object gets a poison vtable of the same size (no pointer fields, every dispatch aborts, a discriminator no `match` arm carries), and its payload words become `0xDEADBEEF0`. A wrong "dead" verdict then faults instead of silently reading a stranger's fields. |
| `YAFL_GC_STATS=1` | adds `[GC RECYCLE] pushed= reused= flushed_unused= poisoned=` to the exit summary |

## 3. Compiler (`compiler/lowering/recycle.py`)

The pass runs once, on SSA, after the -O1+ known-value fixpoint and `sroa`, and
before `phi_removal`. It is intraprocedural.

1. **Copy webs.** A `Move` between two pointer locals keeps the same object,
   so locals are grouped by union-find. Each web has one **origin**, its only
   non-copy definition. Only two kinds of origin can be owned:
   * `NewObject` of an immutable, non-arrayed, non-pinnable, non-foreign class;
   * `Phi`.

   A Phi's ownership is a runtime fact: a tail loop seeded by the caller's
   object is unowned on entry and owned from the first back edge. So it travels
   in a parallel `Int(8)` Phi, the **ownership flag**, and the free becomes
   `yafl_recycle_if`.
2. **Never published.** Reading a field, a discriminator read and an
   is-instance test are reads. Anything else that lets the bare pointer go
   somewhere disqualifies the web for good: a heap store, a struct pack, a call
   argument, a runtime call, a return, a capture, or a virtual lookup's
   receiver. A Phi source is a **transfer** to the Phi's web, and is valid only
   if the source web is dead past that edge. An escaped source contributes
   flag 0.
3. **Not across a suspension.** A web live across a call that may suspend
   would be saved in the async frame, a heap object that outlives the free. It
   is disqualified.
4. **Freed where it dies.** Web liveness (backward, per op, with Phi sources
   counted as uses on their edge) finds every point where the web stops being
   live without being transferred. Each such point is handled in one of these
   ways:
   * **Next to an allocation of the same class in the block: reuse.** The dead
     object is passed straight to that `NewObject` as a **reuse token**
     (`NewObject.reuse`, `yafl_reuse`). This is Lean's reset/reuse, with the
     token in a register. If the allocation comes *before* the death and every
     later use is a plain field read, those reads hoist above the allocation.
     That is legal because the fields are immutable, and only reads whose
     static class is neither `[pinnable]` nor `[mutable]` move.
   * Otherwise **`yafl_recycle` after the dying op**.
   * A branch whose condition reads the dying web: the condition goes into a
     temp, then the free, then the branch. A `Return` that reads one of its
     fields is handled the same way.
   * On a branch **edge**: the free goes at the head of the dead successor
     when that successor has no other predecessor. Otherwise the object is left
     to the collector (counted as `missed_edges`; splitting the edge would
     recover it).
5. **Stack promotion first.** At -O1+, a `NewObject` web that is never
   published and never crosses a Phi is what `stack_promotion` dissolves into
   locals, which beats any recycling. It is left alone, because a free (a
   bare-pointer use) would block the promotion.

`YAFL_RECYCLE_DEBUG=1` prints, per function, the webs freed, then the totals
and a breakdown of why each `NewObject` web was disqualified.

### Why the reuse token matters

The first version freed through the lists only. On the loop benchmark it
removed every GC cycle and was still **25% slower** than the baseline. Each
iteration popped and pushed the same thread-local count byte and slot array,
which put two store-to-load forwards on the loop-carried critical path.
Handing the token over in a register removes that dependency (§4).

## 4. Measurements

All runs used 4 cores, the release runtime and `-O3`.

**Loop-carried replacement.** `drive(c.step(), …)` over a non-flattenable
interface implementation, 20M steps (`compiler/tests/test_recycle.py` has the
shape):

| | wall | GC cycles | pages allocated | GC time |
|---|---|---|---|---|
| baseline | ~131 ms | 5,020 | ~40,000 | 0.059 s |
| recycled, lists only | ~170 ms | 0 | ~0 | 0 |
| recycled, reuse token | **~85 ms** | 0 | ~0 | 0 |

Output is identical in every configuration, including under
`YAFL_RECYCLE_POISON=1` (20,000,000 poisoned, none touched afterwards).

**Real programs (`examples/`).** All nine examples at -O2 and -O3 produce
identical stdout and exit codes plain, recycled, and recycled under poison.
**But the pass fires zero times in all of them.** A whole program has only
about 30 `NewObject` sites left after -O3 inlining. Allocation is concentrated
in shared constructor-like functions, and those objects are **returned** to the
caller or stored. ylisp's disqualifications: Phi into a struct-packed union
value 10, returned 4, closure environment 3, stored 2, call argument 2.

Dynamically, a small ylisp workload (fib 23 plus list building) spends about
28% of its CPU in GC. Its allocations are 827k `VPair` (mostly evaluated
argument lists), 142k `VInt`, 99k `EnvBind` and 96k `VBool`. Nearly all are
built in one function and consumed in another.

## 5. What it would take to matter for real programs

In order of expected payoff:

1. **Interprocedural ownership.** Two function summaries, computed as a
   greatest fixpoint over direct calls:
   * **owned return**: every `Return` hands back an owned, otherwise-unpublished
     web;
   * **consumed parameter**: every call site passes an owned web that is dead
     after the call.

   A call result from an owned-return callee becomes an owned origin. An
   argument passed to a consumed parameter becomes a transfer. This targets
   `VBool` and `VInt` results consumed by a `match`, and the head cell of each
   argument list. Address-taken and virtual functions get no summary.
2. **Deep ownership for recursive data.** The tail of an argument list is
   extracted by a field read, so it is never statically owned. Two routes:
   * a per-field uniqueness summary ("this function's result has a unique
     `tail`");
   * the dynamic **sticky shared bit** from the design discussion: a per-page
     bitmap, written only by the owning thread for its own unscanned pages.
3. **Struct-packed unions at joins** (the biggest single disqualifier above):
   follow a web through a `NewStruct` pack and its unpack, the way `sroa`
   already reasons.
4. **Edge splitting** for frees on multi-predecessor edges.

The measure of success is the one that drives GC cost: **pages allocated per
unit of work**. On the bootstrap self-compile it is the pacing input, so it
predicts the CPU win directly.

## 6. Tests

* `yafllib/tests/test_recycle.c`, single-stepped:
  * acceptance and rejection rules;
  * slot reuse, LIFO order and size classes;
  * the root-scan flush retiring older slots;
  * poison mode.

  It also includes a free-running path-copying churn of about 220k recycles
  across automatic cycles, with the live structure verified under
  `YAFL_GC_POISON`.
* `compiler/tests/test_recycle.py`. Each program is compiled with the pass on,
  then run plain and under `YAFL_RECYCLE_POISON` + `YAFL_GC_POISON`, and must
  match the output with the pass off:
  * off-by-default emits nothing;
  * the loop-carried reuse token;
  * a loop seed that is read again after the loop (ownership flag 0 on entry);
  * published chains (nothing recycled);
  * branch-edge deaths at -O0 to -O3.

# Heap recycling: reusing dead objects without the collector — PARKED

> **STATUS 2026-10-04: parked.** This is the record of a design investigation
> and a working prototype. Nothing here is on `main` except this document.
>
> * **The prototype** (runtime plus an opt-in compiler pass) is on branch
>   `claude/recycling-prototype`, at commit `d82870d`. Its own detailed note is
>   `docs/recycling-prototype.md` on that branch.
> * **The verdict.** The runtime half is sound, cheap and tested. The
>   intraprocedural compiler half works on loop-carried objects, but barely
>   fires in real programs.
> * **The design that would matter** is caller-releases with escape summaries
>   (§6). It is specified below and is not implemented.

## 1. The question

The investigation began with the stream API (`compiler/stdlib/System/stream.yafl`).
Could the trait-based, monomorphised `Stream<S, T, E>` be replaced by a `Stream`
interface with virtual `next` and one implementation per source type? The
difficulty is that `next` stays monadic: it returns a *new* stream. Behind an
interface, each stage is a heap object, and it can no longer be flattened to a
value struct (`simple_classes` refuses anything that implements an interface).
So every element would allocate a new object per stage.

That widened into a general question: **can YAFL reuse the heap slot of an
object that is provably dead, instead of leaving it to the collector?**

## 2. Why allocation volume is the cost

The bump pointer is cheap. What costs CPU is that the collector is **paced by
pages allocated** (`yafllib/object.c`, "PACING"): each page the mutator takes
buys a fixed slice of marking and pruning. A transient object therefore costs
GC work in proportion to the page space it uses, however briefly it lives.
GHC's copying nursery makes dead objects free. YAFL's design has no equivalent,
so the lever is **not consuming page budget for objects that die immediately**.

## 3. Options considered for streams

| approach | per-element cost | notes |
|---|---|---|
| trait-based, monomorphised (today) | none once fused | flattened value structs; -O3 fuses the pipeline into its drain. No uniform type, so streams cannot be stored or chosen between dynamically. |
| `AnyStream` existential box over trait stages | one allocation and one dispatch at the box | Rust's `Box<dyn Iterator>`. The stages inside still fuse. Worth having regardless. |
| interface per stage | one allocation and one dispatch **per stage** | what this investigation tried to make free |
| push / internal iteration (`fold`, `forEach`) | one closure call per stage, no allocation | Java Streams, transducers. Loses `zip` and pausable pull. A virtual `fold` fast path on `AnyStream` is cheap to add. |
| chunked `next` | one allocation per chunk | conduit, Akka; suits IO-shaped pipelines |
| memoised lazy lists | a cons cell and a thunk per stage per element | rejected already, except at the IO leaf |

## 4. Two kinds of in-place update

**Monotone growth (the String trick).** A String is a value `(head, head_len)`.
An append writes only into slack past the buffer's `used` mark, which no
existing value can observe, and owning the end (`head_len == used`, under the
pin) is enough. That tolerates sharing: of two forks, the first to append
extends the buffer in place and the second copies (Erlang's binary append).

This generalises to anything append-shaped: array builders, an RRB-tree tail
buffer, append-only logs, hash-tree growth into empty slots. It needs no
compiler support. It **does not** apply to "returns a new self", which
*overwrites* fields and therefore needs real uniqueness.

**Overwrite** needs a proof that nobody else holds the object. That proof can
be:

* **static**: inferred ownership, `[linear]`, or escape analysis; or
* **dynamic**: refcount == 1 in Lean and Koka (YAFL has a tracing collector
  instead), or a one-bit **sticky shared** flag (Wise & Friedman) set wherever
  a reference is duplicated.

## 5. Where reuse is safe for the collector

The key runtime insight is that reuse is **reallocation**, not in-place
mutation.

* **Which pages.** A dead slot may take a new occupant if it sits on one of
  *this thread's pages allocated since its last root scan* (`new_pages`). Those
  pages are birth-protected: no cycle scans or prunes them until the root scan
  that takes them into the pool. So the collector never sees a slot change
  occupant.
* **The epoch.** Each thread has a recycle epoch, and each page is stamped with
  its owner's epoch.
* **The flush.** The root scan that takes the pages drops the thread's
  recycled-slot lists and advances its epoch, in the same place the bump
  regions are reset. Dropped slots are simply garbage, and that cycle sweeps
  them.
* **Nothing new to maintain.** Promotion already *checks* that a page's
  references are old (`gc_page_refs_are_old`), because compaction breaks age
  ordering. Reuse therefore adds no new remembered-set duty. A reallocated
  slot owes only the existing allocate-black guard: between a cycle opening
  and this thread's root scan, a new allocation is marked seen.
* **Why not mutate in place.** Overwriting an aged object would demote its
  page through the late-write path. Reallocating a young slot never touches an
  old page.
* **Why the window is large.** It covers the whole interval between the
  thread's root scans. With the scan ratio of 2 that is about half the live
  heap's worth of allocation, not one page.

## 6. The caller-releases design (not implemented)

The prototype's compiler half proved ownership *inside one function*. The
design that would reach real code splits the proof differently.

**Callee side: whole-program over method bodies only.** Each function
parameter, and each interface slot, gets an **escape summary**: *self does not
escape*. Every override uses `self` only through field reads, or as the
receiver or argument of other non-escaping calls, and returns something else.
A virtual slot's summary is the conjunction over the implementations listed in
its vtables; a devirtualised call uses its target's own summary. This says
nothing about callers, so **a fork anywhere cannot break it**.

**Call-site side: local.** If the argument is unique in the caller and dead
after the call, and the callee keeps no reference, the **caller releases it**
after the call returns. A caller that forks simply doesn't release at that
site.

**Reuse-flagged allocations.** Only flagged `NewObject` / `NewArray` sites try
the recycled-slot list, because there is a small cost. A natural choice is
allocations inside non-escaping-self method bodies; every other site stays a
plain bump.

### Problems the design must solve

1. **Sources that return `self` when exhausted.** `ArrayStream` and `Once`
   return `self` at end of stream. Two fixes:
   * the shallow release takes an identity guard, `if (r.stream != s) release(s)`;
   * or the property is strict ("never returns self") and those sources return
     a fresh object or a static sentinel instead.

   Problem 2 requires the strict form.
2. **Nested stages need deep release.** The outer caller releases only the
   outermost `Map`. Inside `Map.next`, the old `inner` is still referenced by
   `self`, so nothing releases it. The fix is a **vtable releasable-fields
   mask**: `release(s)` recurses into those fields, and keeps recursing even
   below a parent that isn't on a current-epoch page. A field `C.f` is
   releasable when:
   * every construction of `C` stores a unique, moved value into it;
   * every non-escaping method uses `self.f` only as a non-escaping receiver or
     argument, never storing or returning it.

   This needs the strict no-self-return property. Otherwise
   `inner.next()` may return `inner`, which `Map` then moves into the new `Map`,
   and deep release would free a live object.
3. **Field uniqueness is the one global property left.** One
   `Map(sharedStream, f)` anywhere makes `Map.inner` non-releasable everywhere.
   Shallow release survives; deep release is lost. Fix: **two vtables per
   class** (`Map`, `Map$unique`) with the same methods and different masks.
   Each construction site picks one, and type tests and `match` dispatch treat
   the pair as a single class.
4. **Release arrives one step late.** The caller releases after the call
   returns, but the flagged allocation inside `next` happens before that. So
   reuse comes from the *previous* step: a two-slot ping-pong per stage
   through the thread-local list.
   * The prototype measured this shape as **25% slower** than the bump
     allocator, from two store-to-load forwards per iteration on the list's
     count byte.
   * Fix: a single **spare-slot pointer per size class**, tried first. That is
     one forwarding hop, the same as the bump pointer's own dependency.
   * A hidden register-carried spare argument would be faster but changes the
     calling convention.
5. **Tuple and union flow.** `next` returns `(stream, value)`. Summaries and
   releases need field paths through `NewStruct`/`NewStructTyped` packs and
   `StructField` reads. This was the largest disqualifier in the bootstrap
   census (§7).
6. **Suspension.** The prototype disqualifies an object that is live across a
   call that may suspend. Relaxing that rests on one unverified claim: marking
   never reads the fields of an object on a birth-protected page mid-cycle.
   The fact that fresh stores need no barrier suggests the collector already
   guarantees it.

**Steady state for `Map(Filter(ArraySrc))` behind an interface.** Each step
the driver's call site deep-releases three slots, and the flagged allocations
in the next step pop them. Nothing is allocated per element, and a fork
affects only its own call site.

**Acceptance test.** An `AnyStream` pipeline driven for 10M steps through
virtual dispatch reaches zero GC cycles and runs no slower than the baseline.
A variant that forks once still recycles at every other site.

## 7. What the prototype established

*All results are for the code on branch `claude/recycling-prototype`.*

**Runtime.**
* Per-thread LIFO free lists keyed by size class, filled by the pass's frees.
  Generated code built with `#define YAFL_RECYCLE` pops them before bumping.
* `yafl_reuse(token, owned, vt)`: a dead object handed straight to a
  same-class allocation in a register (Lean's reset/reuse).
* `YAFL_RECYCLE_POISON=1` replaces reuse with a poison vtable and payload, as
  a use-after-free detector.
* `test_recycle.c`: about 220k recycles across automatic cycles, with the live
  structure intact under `YAFL_GC_POISON`.

**Compiler.**
* An intraprocedural pass on SSA, run before `phi_removal`.
* Copy webs with a `NewObject` or `Phi` origin. A Phi-carried ownership flag
  covers loops seeded by an unowned value.
* Liveness-placed frees, plus reuse-token pairing that hoists immutable field
  reads above the new allocation.
* Off by default, with byte-identical output.

**Measurements** (-O3, 4 cores):

| loop-carried replacement, 20M steps | wall | GC cycles | GC time |
|---|---|---|---|
| baseline | ~131 ms | 5,020 | 0.059 s |
| freed through the free lists only | ~170 ms | 0 | 0 |
| reuse token in a register | **~85 ms** | 0 | 0 |

**Real code.**
* The pass fires zero times in all nine examples, whose outputs are
  identical.
* In the bootstrap compiler it handles 13 of 2,927 allocation webs. The rest
  are disqualified because the object is:
  * passed as a direct call argument: 796
  * packed into a struct or union: about 580
  * captured in a closure environment: 298
  * stored into the heap: 237
  * returned: 173
  * live across a suspension: 64
* ylisp spends about 28% of its CPU in GC. Its allocations are 827k `VPair`,
  142k `VInt`, 99k `EnvBind` and 96k `VBool`, nearly all built in one function
  and consumed in another.

**Lessons.**
* Allocation in real YAFL code crosses function boundaries. Any useful proof
  is interprocedural, which is why §6 exists.
* Free-list round trips on a loop's critical path cost more than the bump
  pointer. Register tokens, or a single spare slot, are mandatory for hot
  reuse.
* Runtime helpers called from hot loops must not reference extern globals.
  Their GOT pointers stay live across the loop and cause spills; this alone
  lost to the baseline once.
* Recycling knobs must be read at the first thread's registration. `gc_start`
  runs only after every worker has registered, which is too late for thread 0.

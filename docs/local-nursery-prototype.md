# Thread-local nursery — minimal prototype and measurements

> **STATUS 2026-10-04: runtime-only prototype, opt-in, ONE worker only.**
> * Enable with `YAFL_LOCAL_GC=1` and `YAFL_THREADS=1`. With more than one
>   worker it declines and says so.
> * Off by default. The compiler is untouched and generated C is unchanged.
>   The runtime's only always-on cost is one extra thread-local test inside
>   `GC_WRITE_BARRIER`.
> * The background is `docs/heap-recycling-design.md` (on `main`).

## 1. The idea

The bump allocator is cheap. What costs is that every page bumped
**advances the pacing clock**, and that drives the global collector's work
(`object.c`, "PACING"), including for pages full of objects that died
microseconds after allocation.

A thread's pages since its last root scan are **birth-protected**: no cycle
scans or prunes them until that root scan takes them into the pool. So the
owning thread can trace them itself, at any safe point:

* **no handshake:** nothing else needs to stop or cooperate;
* **cost proportional to survivors:** dead objects are never touched;
* **immediate reuse:** every page holding nothing live is freed, and goes
  straight back as the next refill, still warm in cache;
* **no pacing charge for the dead:** reused pages don't touch the page
  allocator or the clock. The global collector is charged only for what
  survived.

## 2. Why a local trace is enough

Objects are immutable once built, so an object can only point at objects that
existed before it. Anything that can point *into* the nursery from outside is
therefore one of:

| source | how the prototype covers it |
|---|---|
| this thread's stack and registers | conservative scan, interior pointers resolved as in the root scan |
| declared roots (global and thread) | scanned every collection |
| **mutable** objects anywhere | **all** mutable objects are roots, via a registry of mutable pages. This is the conservative stand-in for an insertion barrier on runtime stores (see §6). |
| a slot written after a safe point into an *older* container (a construction straddling a root scan, a late pin, a builder link) | `GC_WRITE_BARRIER` calls `gc_local_note_slot`, plus hooks in `list_builder_link` and `yafl_cas_once` |
| an object the *global* collector already holds marked (root snapshot, allocate-black window) | treated as a root: that cycle will trace it |

* **Compaction.** When the nursery is active, compaction copies go to a
  separate relocation region. Their referrers are older objects.
* **What freeing guarantees.** Dead objects on surviving pages are struck out
  of the page's `objects` bitmap. Nothing can then resolve to them again: not
  a stale conservative stack word, and not a later global trace. A pointer they
  hold into a freed page is therefore never followed.

## 3. The mechanism (`yafllib/object.c`, "Thread-local nursery")

* **Collection** (`gc_local_collect`) runs at a page refill once the nursery
  has taken *trigger* pages. It takes the roots above, traces the nursery
  pages (a mark bitmap per page, owner-only), then sweeps:
  * a page with nothing marked goes to a thread-local page cache;
  * on the rest, dead objects leave the `objects` bitmap.
* **Promotion.** Surviving pages leave the nursery (their stamp is cleared),
  so the next collection traces only newer objects. The page being bumped
  into stays in the nursery.
* **The promotion hole, and its fix.** A late write (a list-builder link, a
  `once` publication, a construction straddling a safe point) can create an
  *old-to-new* edge while both objects are still in the nursery, so no barrier
  records it. Promoting the older object while the newer one stays would hide
  that edge. A trace-time rule fixes it: a survivor about to be promoted that
  points at the page staying behind gets that slot remembered. The first
  version missed this and failed. yaflc lost the tail of its token chain, and
  poison mode showed the dangling `ChainLink.next`.
* **Remembered slots** are filtered after every collection down to those
  still pointing into the nursery, and cleared at the root scan.
* **Pacing.**
  * Nursery refills come from the cache, or from the page allocator without a
    pacing step or clock tick. Near a full heap they fall back to the normal
    path.
  * After each collection, the *net* growth (fresh pages minus pages freed)
    is charged to the clock and stepped, as `gc_page_alloc` would have done.
* **Adapting.** A collection freeing under 25% of the nursery doubles the
  trigger, up to 1,024 pages; one freeing over 50% halves it again.
* **Doing no harm.** Four consecutive collections freeing under 5% at the
  maximum window stand the nursery down: refills revert to the normal path.
  It stands down for 16 root scans, doubling with each consecutive
  stand-down, and the counter resets after a productive collection.
* **At a thread's root scan** the nursery joins the pool (as before), and the
  thread takes a new epoch.

## 4. Measurements

* **Setup:** -O3, release runtime, one worker. Wall time is the median of
  9 runs for the small programs and 3 for the large ones.
* **Peak RSS** comes from a fresh probe process per run. Figures at 10.0 MB
  are that probe's own floor; json_pretty was cross-checked against the
  kernel's `VmHWM`. Output is identical in every case.

| program (input) | baseline | nursery | global GC cycles | nursery pages freed | peak RSS |
|---|---|---|---|---|---|
| loop benchmark (20M object replacements) | 124 ms | **87 ms (−30%)** | 8,064 → **0** | 97% | ≤10 → ≤10 MB |
| ylisp (fib 23 + list building) | 129 ms | **96 ms (−26%)** | 508 → **3** | 86% | ≤10 → 10.8 MB |
| raytracer (spheres.scene) | 189 ms | 189 ms | 491 → 14 | 86% | ≤10 → 13.9 MB |
| yaflc (3,000 generated functions) | 124 ms | 117 ms | 30 → 21 | 5% | 25.9 → 25.4 MB |
| yspell (60k-word dictionary) | 2.27 s | 2.24 s | 38 → 32 | ~0% (stood down) | 32.4 → 33.3 MB |
| json_pretty (53 MB file) | 18.9 s | 19.7 s (+4%) | 796k → 793k | 0% (stood down 16×) | 7.7 → 15 MB (VmHWM) |

A nursery collection is cheap where it pays off. On the loop benchmark it is
about 17 µs (1,260 collections in 21 ms), mostly the stack scan.

**Escape rates** (stores while the nursery is active, by container):
* **Older immutable containers** (the late-write case): 0 to 4 per *run* in
  every program.
* **Mutable containers, per nursery page:**

  | program | stores per page |
  |---|---|
  | ylisp | 0.02 |
  | raytracer | 0.24 |
  | yaflc | 0.3 |
  | yspell | 0.37 |
  | json_pretty | **92** (async state frames: it suspends on every IO read) |

## 5. What the numbers say

1. **Short-lived allocation is nearly free.** The loop benchmark and ylisp
   lose essentially all global collection, with no RSS cost, and these are
   ordinary functional programs. The pages the nursery reuses never leave the
   cache.
2. **Programs whose young data survives get nothing, and the guards keep it
   neutral.**
   * yspell builds a dictionary and yaflc builds an AST; most of what they
     allocate lives.
   * The adaptive window and the stand-down hold them within noise.
   * yaflc still pays for 5 collections that trace most of its AST (80 ms).
3. **Page-granular freeing fails on sparse survival.** json_pretty keeps
   roughly a third of its young objects for a while (its lazy token stream),
   spread across every page. Not one page is ever entirely dead.
4. **Treating every mutable object as a root fails on async-heavy code.**
   json_pretty's frames accumulate. Scanning all of them every collection,
   and keeping their referents alive, is what first made it 5× slower. The
   stand-down now contains the damage (+4% wall, +7 MB peak).

## 6. What it would take to go further

In order:

1. **Track escape properly instead of "all mutable objects are roots."**
   Record (and transitively mark as escaped) what is stored into mutable or
   runtime-visible places:
   * `GC_WRITE_BARRIER` sites (already hooked);
   * the `GC_MARK_SEEN` insertion points in `thread.c`, `task.c`, `io.c` and
     `lazy.c`;
   * the unbarriered queue linkage in `_queue_push`.

   This is the barrier-completeness work. Poison runs at small triggers, as
   used here, are the way to validate it. It's what async-heavy code (frames,
   tasks) needs.
2. **Evacuate survivors instead of keeping their pages.** A mostly-copying
   nursery:
   * pages referenced from the stack are pinned, as the root scan already
     does;
   * immutable objects make "either copy is fine" true;
   * precise referrers are known from the trace.

   This fixes sparse survival (json_pretty) and makes promoted pages dense.
3. **More than one worker.** Another thread's marker could be mid-trace
   through a pointer into a page freed here, so freed pages need a quarantine
   until the current mark phase ends, or a handshake.
4. **Stack watermarks**, so deep stacks aren't rescanned whole each time.
5. **Pacing integration.** The global clock now sees only survivors, so
   volume-based promotion and the tests that drive it with throwaway filler
   (`test_gc_gen`, `test_gc_late_pin_race`, which fail in nursery mode by
   design) need re-tuning around that.

## 7. Tests

* **Default suite:** all 26 C tests pass with the nursery off.
* **Nursery-mode variants:** 9 of the GC tests are registered again with
  `YAFL_LOCAL_GC=1 YAFL_LOCAL_GC_PAGES=2 YAFL_THREADS=1 YAFL_GC_POISON=1`. All
  pass: `test_gc`, `_stress`, `_ring`, `_min`, `_pressure`, `test_pin`,
  `test_large_objects`, `test_str`, `test_io_stress`.
* **Programs:** all six benchmark programs give byte-identical output to the
  baseline at triggers of 1, 4 and 32 pages under `YAFL_GC_POISON`.
* **Not run:** the Python compiler suite and the full protocol. No compiler
  change was made, but generated programs do pick up the new barrier macro and
  page layout through `yafl.h`.

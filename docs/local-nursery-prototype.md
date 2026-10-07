# Thread-local nursery — minimal prototype and measurements

> **STATUS 2026-10-05: on by default, any number of workers.**
> The compiler is untouched. The rest of this document is the history of how
> the design got here. The **current state** is:
>
> * **On by default**; `YAFL_LOCAL_GC=0` turns it off. Each worker collects its
>   own nursery on its own thread, while other workers keep running global
>   slices in parallel.
> * **Size: fixed, 64 pages (1 MiB),** set with `YAFL_LOCAL_GC_PAGES`. Measured
>   best or near best on all seven programs and on the self-compile. Larger
>   sizes lose on allocation-heavy programs once the nursery outgrows the
>   cache, and adaptive sizing bought nothing measurable, so it was removed.
> * **Stand-down kept:** after four collections that free under 5%, the nursery
>   switches off for 16, 32, 64… root scans. json_pretty takes 17.6 s with it
>   and 28.3 s without.
> * **Old-generation promotion volume** (a global-collector change that applies
>   with or without the nursery) is now steered by **mistakes**: old pages
>   forced back by late writes, or found churning by a major's re-trace. Over
>   1 mistake per 8 promotions doubles it; under 1 per 64 halves it. Its floor
>   is a constant 4,096 pages, set with `YAFL_GC_PROMOTE_FLOOR`. This replaces
>   max(8 × young survivors, heap/64), which fed back on itself.
> * **Self-compile, measured on one VM, 2 runs each:**
>
>   | promotion rule | no nursery | nursery |
>   |---|---|---|
>   | old | 269.0 s | 256.6 s (−5%) |
>   | new | 250.0 s (−7%) | **224.7 s (−16%)** |
>
>   Peak RSS is unchanged (1.28–1.46 GB), and all outputs are byte-identical.
>   On the seven programs the new rule is neutral, and the nursery is neutral
>   or better.
> * **Resolved: `test_gc_min` segfault** (once in about 2,300 runs). The
>   cause was another thread's conservative mark landing on an object while
>   its nursery was striking it as dead: the slot was struck while carrying a
>   mark bit, and the global marker later scanned it (or the prune
>   resurrected it). The global collector now ignores marks on slots that
>   hold no object. `test_gc_stale_mark` forces the race: under poison the
>   unfixed runtime crashed in 152 to 169 of 200 runs, and the fixed one in
>   0 of 600. ThreadSanitizer (gcc) found it.
> * **Escape barrier, cheap when nothing needs it.** A thread with an active
>   nursery takes the full path. Any other thread only escapes an overwritten
>   value sitting in an *active* nursery: it reads the old value first, then
>   the live-nursery count, so the count can't go stale across a nursery
>   start. A table of active epochs lets the escape return at once for pages
>   whose nursery has retired (callgrind had shown that check at 16% of
>   json_pretty's instructions). Measured on one VM:
>
>   | program (one worker, median) | nursery off | nursery on |
>   |---|---|---|
>   | b1 | 158 ms | 114 ms |
>   | ylisp | 147 ms | 113 ms |
>   | raytracer | 203 ms | 200 ms |
>   | yaflc | 137 ms | 131 ms |
>   | yspell | 2.72 s | 2.56 s |
>   | par | 698 ms | 412 ms |
>   | json_pretty | 22.7 s | 22.8 s |
> * **Interactions with the global collector** that must hold, each found by
>   measurement or a crash:
>   * charge every page handed to the global heap;
>   * repay the charged collector steps one per refill;
>   * collect before a root scan hands the nursery over;
>   * service root-scan requests at every refill;
>   * strike dead objects on every page type;
>   * escape lazy waiters and builder elements;
>   * keep pinned pages in the nursery;
>   * the global collector ignores marks on slots that hold no object.

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
| an **escaped** object: stored into a shared container, handed to the runtime, or published through a root | an `local_escaped` bit per object, set by whichever thread does the escaping (§3, "Escape tracking"). Escaped objects are roots. |
| a slot written after a safe point into an *older* container (a construction straddling a root scan, a late pin, a builder link) | the same barrier: an older container is shared, so what is stored into it escapes |
| an object the *global* collector already holds marked (root snapshot, allocate-black window) | treated as a root: that cycle will trace it |

* **Compaction.** When the nursery is active, compaction copies go to a
  separate relocation region. Their referrers are older objects.
* **What freeing guarantees.** Dead objects on surviving pages are struck out
  of the page's `objects` bitmap. Nothing can then resolve to them again: not
  a stale conservative stack word, and not a later global trace. A pointer they
  hold into a freed page is therefore never followed.

## 3. The mechanism (`yafllib/object.c`, "Thread-local nursery")

* **Escape tracking.**
  * A container is **private** when it is immutable, on this thread's
    nursery, and not escaped. A store into it needs nothing: an immutable
    field is never overwritten, so what it gains stays reachable from it and
    the trace finds it.
  * Every other container is **shared**, including every mutable object,
    because one reachable from an escaped object can be read by another worker
    before anything marks it escaped.
  * `GC_WRITE_BARRIER` runs *before* its store, so it sees the old value, not
    the new one. The **old value escapes at once**: whoever loses a slot to an
    overwrite, someone else may have read it. The **new value is pending**:
    the slot is read back and its value escaped at this thread's next barrier
    or collection.
  * That closes the cross-thread race. Another thread can only obtain a
    nursery object through a shared slot. If the slot still holds it at the
    flush, the flush escapes it; if anyone overwrote it first, that overwrite
    escaped it as an old value.
  * `GC_MARK_SEEN` (queues, completions, lazy publication), `gc_root_publish`
    and `gc_root_overwrite` escape their values too.
  * The barrier is gated on `gc_local_live`, a count of threads whose nursery
    is collecting right now. With every nursery stood down, the escape barrier
    costs one load and a not-taken branch.

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
* **The pages being bumped into stay** in the nursery, both the immutable and
  the mutable one. Objects allocated onto them after a collection are new and
  initialised by barrier-free fresh stores, so they must land on a page the
  nursery still traces. For the same reason a thread abandons both bump pages
  when its nursery first starts: they predate it. (Missing either of these
  failed yspell under poison with a dangling frame field.)
* **Remembered slots** are filtered after every collection down to those
  still pointing into the nursery, and cleared at the root scan.
* **Pacing.**
  * Nursery refills come from the cache, or from the page allocator without a
    pacing step or clock tick. Near a full heap they fall back to the normal
    path.
  * After each collection, every page **promoted** out of the nursery is
    charged to the clock and stepped, as `gc_page_alloc` would have done. Each
    page is promoted, and therefore charged, once.
  * The first version charged net growth instead (fresh pages minus pages
    freed). That missed survivors on *reused* cache pages: `par` promoted
    4,077 pages, charged 4, ran no global cycle at all, and its promoted and
    escaped garbage piled up (897 ms instead of 488 ms; 257 MB with four
    workers).
* **Adapting.** A collection freeing under 25% of the nursery doubles the
  trigger, up to 1,024 pages; one freeing over 50% halves it again.
* **Doing no harm.** Four consecutive collections freeing under 5% at the
  maximum window stand the nursery down: refills revert to the normal path.
  It stands down for 16 root scans, doubling with each consecutive
  stand-down, and the counter resets after a productive collection.
* **At a thread's root scan** the nursery joins the pool (as before), and the
  thread takes a new epoch.
* **Other workers** never read a nursery object's fields: a nursery page has
  `processed_by_epoch == 0`, so a remote mark or root scan only sets
  `atomic_seen` (and `pinned`), which the owner then treats as a root. Freed
  pages stay GC pages in the owner's cache, so a stray bit only over-retains.
  Pages go back to `mmap` (cache above 512 pages) only while no mark can be in
  flight, in stage IDLE or PRUNE.

## 4. Measurements

* **Setup:** -O3, release runtime. Wall time and CPU time are the median of
  9 runs (3 for json_pretty).
* **Peak RSS** comes from a fresh probe process per run. Figures at 10.0 MB
  are that probe's own floor; json_pretty was cross-checked against the
  kernel's `VmHWM`. Output is identical in every case.
* `par` is a `__parallel__` divide-and-conquer sum: 64 leaves of 1M steps,
  each step replacing a small object.
* Run-to-run noise is about ±10% on the 100 ms programs.

**One worker**

| program (input) | baseline | nursery | global GC cycles | nursery pages freed | peak RSS |
|---|---|---|---|---|---|
| loop benchmark (20M object replacements) | 129 ms | **82 ms (−36%)** | 8,097 → **0** | 97% | ≤10 → ≤10 MB |
| par | 506 ms | **304 ms (−40%)** | 25,914 → **98** | 97% | ≤10 → ≤10 MB |
| ylisp (fib 23 + list building) | 114 ms | **95 ms (−17%)** | 510 → 102 | 77% | ≤10 → ≤10 MB |
| raytracer (spheres.scene) | 194 ms | 173 ms | 480 → 63 | 85% | ≤10 → 11.5 MB |
| yaflc (3,000 generated functions) | 111 ms | 106 ms | 30 → 20 | 5% | 25.9 → 25.9 MB |
| yspell (60k-word dictionary) | 2.35 s | 2.36 s | 37 → 32 | 0% (stood down) | 32.5 → 33.5 MB |
| json_pretty (53 MB file) | 19.1 s | 19.8 s (+4%) | 797k → 649k | 0% (stood down 16×) | 9.9 → 13.3 MB |

**Four workers**

| program | baseline wall / CPU | nursery wall / CPU | global GC cycles | peak RSS |
|---|---|---|---|---|
| par | 288 / 1,100 ms | **111 / 415 ms (−62% CPU)** | 754 → 67 | 66.6 → **15.3 MB** |
| loop benchmark | 102 ms | 86 ms | 5,059 → 0 | ≤10 → ≤10 MB |
| ylisp | 104 ms | 94 ms | 319 → 85 | ≤10 → ≤10 MB |
| raytracer | 60 / 192 ms | 60 / 191 ms | 190 → 28 | 16.9 → 18.4 MB |
| yaflc | 103 ms | 114 ms | 24 → 19 | 25.5 → 26.1 MB |
| yspell | 2.38 s | 2.40 s | 35 → 31 | 33.8 → 33.9 MB |
| json_pretty | 19.4 s | 21.1 s (+9%) | 321k → 320k | 10.0 → 13.6 MB |

(The single-threaded programs run on one worker either way; with four
workers the others sit idle.)

A nursery collection is cheap where it pays off. On the loop benchmark it is
about 24 µs (1,265 collections in 30 ms), mostly the stack scan.

**Store classes** with the nursery on (barriered stores, whole run):

| program | private (nothing to do) | shared (escape barrier) | objects escaped |
|---|---|---|---|
| loop benchmark | 0 | 0 | 0 |
| ylisp | 0 | 76 | 25 |
| raytracer | 0 | 2,839 | 475 |
| yaflc | 28k | 125k | 123k |
| yspell | 71k | 33k | 32k |
| json_pretty | 0 | 4.4M while live | 0.97M |

### The self-compile (A/B/A/B)

* **Setup:** the port built at -O3 (`ybootstrap_O3`), mode `c1`, compiling
  stdlib plus bootstrap (2.47 MB of source). Default worker count (4),
  `YAFL_HEAP_SIZE=6G`.
* **Legs:** A = nursery off, B = `YAFL_LOCAL_GC=1`. Same binary; the only
  difference is the environment variable. Two runs per leg, legs in the
  order A, B, A, B.
* All 8 runs emit the same 49,548,133 bytes of C (sha256 prefix
  `0f8909645930da34`).

| leg | run 1 wall / CPU / peak RSS | run 2 wall / CPU / peak RSS |
|---|---|---|
| A | 311.5 s / 307.2 s / 1,470 MB | 316.4 s / 312.2 s / 1,388 MB |
| B | 299.5 s / 295.9 s / 1,238 MB | 301.5 s / 297.6 s / 1,254 MB |
| A | 439.5 s* / 429.6 s / 1,252 MB | 316.0 s / 312.1 s / 1,369 MB |
| B | 297.5 s / 294.0 s / 1,238 MB | 298.6 s / 295.2 s / 1,249 MB |

\* Outlier: system time 19.8 s against about 4 s for every other run.
That points to interference on the machine; the next run was normal.

* **Wall time:** median 316 s → **299 s (−5.4%)**. Every B run beats every
  A run.
* **Peak RSS:** A ranges 1,252–1,470 MB, B 1,238–1,254 MB. The nursery
  removes the variance and lowers the worst case by about 15%.

One extra run of each with `YAFL_GC_STATS=1` (slower: 368 s and 344 s):

| | nursery off | nursery on |
|---|---|---|
| global GC cycles | 45,198 | **15,991** |
| global GC time | 200 s | 163 s |
| pages through the page allocator | 6.30M | 4.81M |
| nursery collections | — | 40,067, freeing 40% of 3.46M pages |
| nursery time | — | 93 s (80.7M objects marked) |
| stores: private / shared | — | 238M / 3.7M |

The self-compile is a survival-heavy workload (an AST and IR that live for
whole passes), and the nursery still pays: about 1.4M pages are recycled
warm instead of feeding the global collector. Most of the nursery's own time
goes to tracing survivors before promoting them. That is the cost item 1 in
§6 (evacuating survivors) would attack.

### Nursery size, pacing, and two accounting faults

A size sweep on the self-compile showed speed rising with nursery size, but
so did peak memory: a fixed 64 MB nursery took 246 s at 2.85 GB. Re-pacing
the baseline (nursery off) with `YAFL_GC_STEP_PAGES` puts that on the same
speed/memory curve:

| baseline scan ratio r | wall | peak RSS |
|---|---|---|
| 4 (default) | 315–321 s | 1.25–1.34 GB |
| 3 | 261.5 s | 1.86 GB |
| 2 | 203.8 s | 5.77 GB (runs to the heap limit) |

So much of the large-nursery speed-up was the global collector running
less often. Charging one step per page handed to the global heap is still
the right rule. Two faults stopped the nursery from following it:

1. **Pages retired uncollected were never charged.** A thread's root scan
   hands every page taken since its last nursery collection to the global
   pool. Only promoted pages advanced the clock. With the default nursery,
   2.6M of 6.2M pages reached the global heap unfunded. These pages are now
   charged when retired.
2. **The old-generation promotion volume feeds back on itself.** It is set
   to 8 × the young survivors, on the same clock. With long cycles it
   climbed from 6,144 to 110k pages, and the young generation tripled.
   `YAFL_GC_PROMOTE_CAP` (a diagnostic) caps it. Capping it at the floor,
   6,144 pages, is what the measurements below use.

Single runs, all with byte-identical output:

| configuration | wall | peak RSS |
|---|---|---|
| baseline | 315–321 s | 1.25–1.34 GB |
| default nursery, both fixes | 260.7 s | 1.54 GB |
| fixed 16 MB nursery, retire charge only | 266.7 s | 1.43 GB |
| **fixed 16 MB nursery, both fixes** | **246.3 s** | **1.33 GB** |
| fixed 64 MB nursery, retire charge only | 238.2 s | 2.94 GB |

With both fixes, a fixed 16 MB nursery is about 23% faster than the
baseline at the same memory. It also beats the r = 3 baseline by 15 s while
using 530 MB less, so the gain is the nursery's own, not a pacing trade.

Still open:

* **Large nurseries.** Neither fix explains most of the 64 MB nursery's
  extra memory.
* **r = 2 runs to the heap limit even with the nursery off.** The pacing
  model's "a cycle over S pages completes within S/r allocations" doesn't
  hold on this workload. Requeues and growth of the live set are the
  suspects.
* **The cap is a diagnostic, not a policy.** It must be checked against
  yspell, whose churn the volume rule was written for. So must the adaptive
  nursery size: starting at 32 pages, it spends most of the run growing.

### Follow-up: confirming the self-compile gain, and checking it elsewhere

**Self-compile A/D/A/D:** A = nursery off; D = fixed 16 MB nursery with
`YAFL_GC_PROMOTE_CAP=6144`. Two runs per leg, same binary, all 8 outputs
byte-identical.

| leg | run 1 | run 2 |
|---|---|---|
| A | 319.0 s / 1,418 MB | 303.7 s / 1,316 MB |
| D | 248.7 s / 1,290 MB | 245.6 s / 1,343 MB |
| A | 300.8 s / 1,292 MB | 303.5 s / 1,492 MB |
| D | 244.7 s / 1,345 MB | 242.9 s / 1,279 MB |

The median goes from 303.6 s to **245.1 s (−19%)**, with lower and steadier
peak memory. Every D run beats every A run.

**The other programs:** one worker, median of 5 runs, all outputs identical.

| program | baseline | default nursery | fixed 16 MB + cap |
|---|---|---|---|
| b1 | 132 ms / 10 MB | 81 ms / 10 MB | 122 ms / 18 MB |
| ylisp | 112 ms / 10 MB | 98 ms / 10 MB | 90 ms / 22 MB |
| raytracer | 174 ms / 10 MB | 185 ms / 12 MB | 215 ms / 41 MB |
| yaflc | 100 ms / 26 MB | 97 ms / 26 MB | 112 ms / 23 MB |
| json_pretty | 18.4 s / 10 MB | 18.4 s / 13 MB | **37.7 s / 643 MB** |
| yspell | 2.23 s / 32 MB | 2.29 s / 34 MB | 2.19 s / 42 MB |
| par | 469 ms / 10 MB | 283 ms / 10 MB | **952 ms / 36 MB** |

**The fixed size causes the regression, not the cap.** Single runs:

| configuration | json_pretty | par |
|---|---|---|
| fixed 16 MB, no cap | 45.3 s | 0.99 s |
| default nursery + cap | 23.3 s | 0.43 s |

(The json_pretty figures had stats on, which slows them.) So a fixed
large nursery is a self-compile tuning, not a default. The default adaptive
nursery, with the charge at retirement, is the configuration that is
neutral or better everywhere. The open question is the adaptive policy
itself: the self-compile wants to start large, while json_pretty and par
want small or stood-down nurseries.

### A large nursery must never be worse than none

The fixed-size regressions above were three interactions with the global
collector, not costs inherent to a large nursery. All three are fixed:

1. **Root scans were serviced late.** A nursery refill never ran a
   collector step, so a pending root-scan request waited for the next
   nursery collection. Until a thread's roots are scanned, everything it
   allocates is born marked (allocate-black), and the nursery must keep
   marked objects. With 1,024 pages, par kept 14M objects instead of about
   1k. Requests are now serviced at every refill.
2. **Charged steps ran in one burst.** A global SATB cycle then stayed
   open across a whole nursery of mutator work, keeping everything live at
   its start plus everything overwritten during it. json_pretty, which
   overwrites async-frame fields on every read, reached 643 MB. The steps
   are now owed and repaid one per refill.
3. **The nursery was handed over uncollected.** A root scan passed young
   garbage to the global collector, whose extra cycles retired the next
   nursery sooner still. Each root scan now collects the nursery first, at
   a refill or a safe point.

After the fixes (one worker):

| | par | json_pretty |
|---|---|---|
| no nursery | 0.46 s / 11 MB | 17.5 s / 11 MB |
| default | 0.29 s / 11 MB | 16.8 s / 11 MB |
| fixed 16 MB | 0.41 s / 19 MB | 17.1 s / 19 MB |
| fixed 64 MB | 0.78 s / 67 MB | 17.6 s / 69 MB |

The one remaining loss is physical. A 64 MB nursery cycles par's allocation
through memory far larger than the cache, whereas no nursery keeps par's
heap under 1 MB.

The self-compile with these fixes (single runs, all outputs identical):

| | wall | peak RSS |
|---|---|---|
| baseline | 301.6 / 311.7 s | 1.34 / 1.26 GB |
| default nursery | 285.0 s | 1.35 GB |
| fixed 16 MB | 282.2 s | 1.43 GB |
| fixed 16 MB + promotion cap | **247.2 s** | 1.31 GB |

Part of the earlier fixed-size gain came from the late, bursty collection
these fixes removed. The promotion cap carries most of what remains.

### Soundness bugs found by the self-compile

The first A/B run crashed in leg B. Poison runs on a stdlib-plus-`yaflc.yafl`
input then reproduced it in seconds, and core dumps found four holes.
Neither the C tests nor the six benchmark programs had caught any of them.

1. **Dead mutable objects were never struck.** The sweep skipped mutable
   pages and multi-page objects, so a dead mutable frame stayed in the
   `objects` bitmap still pointing into freed pages. A stale stack word that
   resolved to it led the global marker into a reclaimed object. Dead
   objects there are now struck like any other.
2. **Lazy waiters didn't escape.** `lazy_thunk_enqueue` links a fresh
   waiter task into a shared `Lazy` by raw CAS, with no barrier. Fix 1
   exposed this (raytracer, 4 workers). The waiter now escapes before the
   CAS.
3. **Array builders.** A pinned array under construction takes its elements
   by plain stores across safe points, even across suspensions that resume
   on another worker. Promoting its page hid those stores. Now:
   * a page holding a live pinned object is marked to stay in the nursery
     (`local_stay`) during the root pass, *before* the trace, so promoted
     survivors' edges into it are remembered;
   * every in-flight array builder is a root of every nursery collection,
     from `array_builder_pin` until whichever primitive releases the pin;
   * at that release, elements the releasing thread's nursery cannot trace
     through the array escape.
4. **List segments were released by a different primitive.** They are
   pinned by `array_builder_pin` but unpinned by `list_builder_link` or
   `list_builder_seal`. Unregistering only at `array_builder_seal` left
   freed segments in the registry.

   *Later (2026-10-07): the builder registry is gone.* Builder element
   stores are now write-barriered like every other heap store, so the
   barrier reports each edge from a builder that has left the nursery, and
   builders are born pinned by their allocation (`array_create(…, true)`,
   `new_pinned` for list cells) rather than pinned by a separate call. The
   registry's global spinlock on every builder went with it. So did the
   rule that made a pinned object a root of every nursery collection and
   held its page in the nursery (`local_stay`): with every write into a
   pinned object barriered, it is live exactly when something references
   it, like any other object.

After the fixes, all 24 poison runs of the small input pass (1 and 4 workers;
nursery sizes 1, 4 and 32 pages), and two full poison self-compiles produce
byte-identical C.

## 5. What the numbers say

1. **Short-lived allocation is nearly free, and now on every worker.** The
   loop benchmark, `par` and ylisp lose most or all of their global
   collection. With four workers, `par` uses 62% less CPU and less than a
   quarter of the peak RSS: each worker reuses its own warm pages instead of
   feeding a shared collector.
2. **Escape tracking removed the async penalty's cause.** The old rule (every
   mutable object a root) made json_pretty 5× slower before the stand-down
   contained it. Escapes are now proportional to what is actually published.
3. **Programs whose young data survives get nothing, and the guards keep them
   near neutral.** yspell builds a dictionary and yaflc builds an AST; most
   of what they allocate lives. The adaptive window and the stand-down hold
   them within noise; yaflc still pays for 5 collections that trace most of
   its AST.
4. **Page-granular freeing fails on sparse survival.** json_pretty keeps
   roughly a third of its young objects for a while (its lazy token stream),
   spread across every page. Not one page is ever entirely dead, so the
   nursery stands down.
5. **The remaining json_pretty cost is the escape barrier.** Its async state
   frames take a shared store on almost every step. While any nursery is live,
   each is an out-of-line call. That is +4% with one worker and +9% with four
   (the barrier also runs while *other* workers' nurseries are live).

## 6. What it would take to go further

In order:

1. **Evacuate survivors instead of keeping their pages.** A mostly-copying
   nursery:
   * pages referenced from the stack are pinned, as the root scan already
     does;
   * immutable objects make "either copy is fine" true;
   * precise referrers are known from the trace;
   * escaped objects stay put (other threads may hold them).

   This fixes sparse survival (json_pretty) and makes promoted pages dense.
2. **A cheaper escape barrier.**
   * An inline filter in the macro: skip the call when the slot's page and
     the pending slot are both non-nursery.
   * Or pass the new value to the barrier (a compiler change), which removes
     the pending slot and its read-back.
3. **Stack watermarks**, so deep stacks aren't rescanned whole each time.
4. **Pacing integration.** The global clock now sees only promoted pages, so
   volume-based promotion and the tests that drive it with throwaway filler
   (`test_gc_gen`, `test_gc_late_pin_race`, which fail in nursery mode by
   design) need re-tuning around that.
5. **Memory-model rigour.** `gc_local_live` relies on its increment (a full
   barrier) preceding the nursery's first store, and on readers seeing it
   before they read a pointer that store published. That holds on x86-64
   (TSO) but wants explicit fences for weaker hardware.

## 7. Tests

* **Default suite:** all 26 C tests pass with the nursery off.
* **Nursery-mode variants:** 9 of the GC tests are registered again with
  `YAFL_LOCAL_GC=1 YAFL_LOCAL_GC_PAGES=2 YAFL_THREADS=1 YAFL_GC_POISON=1`. All
  pass: `test_gc`, `_stress`, `_ring`, `_min`, `_pressure`, `test_pin`,
  `test_large_objects`, `test_str`, `test_io_stress`.
* **Multi-worker C tests:** 15 threaded tests pass with 4 workers at triggers
  of 1, 2 and 8 pages under poison (run by hand, not registered).
* **Self-compile:** byte-identical C under poison with the nursery on
  (4 workers / 32 pages; 1 worker / 4 pages), and in all 8 timed runs.
* **Programs:** all six single-threaded benchmark programs give
  byte-identical output to the baseline at triggers of 1, 4 and 32 pages under
  `YAFL_GC_POISON`, with 1 and with 4 workers. `par` passed 30 of 30 poison
  runs with 4 workers at a trigger of 1 page.
* **One unexplained failure:** `test_gc_min2` (nursery off) failed once in a
  ctest run that overlapped a benchmark. It then passed 8 sequential runs and
  68 runs under heavy parallel load; its log was overwritten before it could
  be read.
* **Not run:** the Python compiler suite and the full protocol. No compiler
  change was made, but generated programs do pick up the new barrier macro and
  page layout through `yafl.h`.

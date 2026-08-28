# Heap-pressure profiling (massif + pprof)

Status: SHIPPED, both layers (yafllib/heapprof.c; runtime-only — no
compiler or port changes; layer 2 rides `--profile`'s shadow stack).

## The question it answers

Not "how many objects were allocated" — short-lived objects die in place,
are never visited by the collector, and cost almost nothing. The question
is what pushes RSS: bytes that SURVIVE collections, live-heap composition
over time, and reserved-but-not-live space. The measurement principle
follows: **instrument the collection boundary, never the allocation
count**. What the collector visits *is* heap pressure, by definition;
everything else never appears in the data.

## Layer 1 — live census by type → massif format

Per collection cycle, accumulate `live_bytes[vtable] += size` on the walk
the collector already performs: in the marker's first-mark path
(`!was_set` after the atomic fetch-set — exactly once per live object per
cycle). Marking is parallel, so the census is per-thread tables merged in
the exclusive prune tail — the same discipline as the CPU profiler's
counters. (Objects move only via compaction in this runtime; the
"scavenger" is the madvise page scavenger and touches no objects, so the
mark walk alone covers the live set.)

Output is **massif format** (read by ms_print and massif-visualizer),
emitted by libyafl directly — the same trick as emitting callgrind
without Valgrind, and necessary for the same reason: interposition-based
tools see one giant mmap when pointed at a bump allocator. One snapshot
per completed GC cycle, `heap_tree=detailed`, with a one-level tree: root
`(visited this cycle, by type)` over one child per type, weighted by
censused live bytes.

`mem_heap_B` = the allocator's page accounting at the cycle end;
`mem_heap_extra_B` = reserved − in-use — which surfaces the *other* real
RSS pusher: fragmentation and pages held but not serving live data.
`time=` uses milliseconds (`--time-unit=ms` semantics).

## Layer 2 — allocation-site `inuse_space` → pprof

Sampled site attribution, from three hooks and a dump:

- **Sampling rides the allocation SLOW PATH** (page acquisition), never
  the per-allocation fast path: a global byte countdown ticks per
  acquired page span, and when it crosses, the allocation that triggered
  the acquisition is recorded — `(address → stack, size)` in a global
  open-addressing table, the stack hash-consed from the allocating
  thread's own `--profile` shadow stack. The fast path is untouched
  (zero cost, on or off), and sampling is naturally size-proportional:
  an allocator's chance of triggering a refill is its byte share (the
  tcmalloc refill-sampling argument). Multi-page allocations hit their
  own slow-path arm and are always sampling candidates. Relocation
  allocations (compaction targets) are never sampled: the copy's
  original was sampled at birth and the forward hook re-keys its record
  — a sample would double-count and pollute the stack table with
  (GC)-suffixed variants of every mutator stack. Stored stacks are
  capped to the DEEPEST 32 frames with a `(truncated)` pseudo-frame
  standing for the elided ancestry — the cap is what makes hash-consing
  viable at compiler scale: recursion makes every depth of a walk a
  distinct full stack (an uncapped self-compile run exhausted the id
  pool and lost 13k records' stacks), while leaf-side windows of a
  recursive chain converge. Go's heap profiler caps for the same
  reason. Insert failures retry with a shrinking window (32 → 16 → 4 →
  leaf-only), and records whose stack is lost anyway aggregate under a
  bare `(truncated)` sample — attribution may shorten, totals never
  understate.
- **Compaction maintenance**: the evacuating GC thread, having published
  a forward word, tells the profiler `old → new`. The record is re-keyed
  in the next collection tail. (Compaction is the only object mover.)
- **Death**: at the exclusive prune tail of EVERY cycle, records are
  swept against the page `objects` bitmaps — which prune rewrites to
  exactly the survivor set. The test is exact for pages the cycle pruned
  (the young churn, where nearly all samples die) and conservative for
  old pages (their bitmaps keep dead entries until a major refreshes
  them, so stale records are kept, never lost); a major makes the sweep
  exact heap-wide. Sweeping every cycle matters: dropping only at majors
  let dead young records squat in the table and starved inserts — the
  first self-compile run lost a million samples that way. No object
  memory is ever read: freed pages read a zeroed tag (madvised, mapping
  intact). A freed-then-reused slot can alias a record to a new object —
  the standard, rare, bounded inaccuracy of every sampling heap
  profiler.

What remains at any dump point is the sampled LIVE set attributed to
allocation sites — Go's `inuse_space`/`inuse_objects` pair, scaled by the
standard estimator (a sampled object of size S stands for
`1/(1 − e^(−S/rate))` of its kind). Output is pprof's profile.proto,
hand-encoded (varint framing, interned string table, one Location+
Function per shadow-stack frame id from the `--profile` descriptors),
wrapped in a gzip container of stored deflate blocks — no compression
library. Stacks are the programmer-view logical stacks with the same
caveats as the CPU profiler: inlined functions attribute to their
absorber, and a resumed-after-park continuation starts at its `$async`
root until logical await-chain stitching ships.

Validation: the runtime unit test (`yafllib/tests/test_heapprof2.c`)
decodes the container and the protobuf against the spec and asserts
sampling, death, forwarding survival and per-site totals over the real
runtime; `tests/test_profile.py` asserts the end-to-end plumbing from a
compiled program. The `pprof` tool itself is not on the dev box — first
external-tool read should confirm rendering.

## How to read the output — and how NOT to

Three traps, each of which has already cost a wrong conclusion. Read this
before acting on either layer's ranking.

**1. A high `inuse_space` site is NOT a site that wastes memory.** Layer 2
attributes SURVIVING bytes to whichever site allocated the object that is
still live at the dump. When a value is rebuilt by a chain of passes, every
earlier copy is dead and only the LAST allocator is charged — so a rewriting
pass appears at the top of the ranking precisely because it produced the
final, wanted data. `inuse_space` answers "who allocated what is still
here", never "who allocates too much".

The corollary is the one that misleads: eliminating a pass's intermediate
copies does NOT move its `inuse_space` number, because those copies were
never counted in it. They were transient, and transient allocation is close
to free here by the same argument this document opens with — objects that
die before a collection visits them cost almost nothing. (Measured: making
the IR rewrites identity-preserving via `with` changed peak RSS and CPU by
nothing at all, 4 interleaved runs. The 44 MB charged to `rpReplaceParams`
was the IR itself, not waste.)

To find bytes worth eliminating, ask instead: is this data still REACHABLE
when it should not be, or is it larger than it needs to be? Retention and
representation move RSS; allocation churn does not.

**2. Layer 1's census counts only what the collector VISITED that cycle.**
Minor cycles skip the old generation entirely (`mark_object` returns early
on `page->head.old`), so most snapshots measure the young rotation alone.
On a self-compile the median snapshot censuses a couple of MB while the
majors — 3 snapshots out of 30,760 — census 400+ MB. **Always take the live
figure from a major**, i.e. from the largest snapshots, never from the
median or from an arbitrary one.

**3. `mem_heap_extra_B` is reserved-minus-in-use, not fragmentation.** With
a large `YAFL_HEAP_SIZE` it is dominated by the untouched remainder of the
reservation and tells you nothing about RSS. Compare `mem_heap_B` (in use)
against the census total to get the figure that matters: how much of the
in-use heap is actually live. On a self-compile that ratio is ~44%, and the
missing half — floating garbage plus partially-occupied pages — is a bigger
RSS contributor than any single type in the ranking.

## Interface

- `YAFL_HEAPPROF=<path>` enables layer 1 and names the massif output
  (default off; `massif.out.<pid>` when set empty).
- `YAFL_HEAPPROF_SAMPLE=<bytes>` additionally enables layer 2 in a
  `--profile` binary (refused with a stderr note otherwise); the pprof
  file is written beside the massif file as `<path>.heap.pb.gz`.
  Granularity is bounded below by the 16 KiB page size — rates smaller
  than a page sample every acquisition.
- Census/sampling branches are per-object `UNLIKELY(...)` tests on
  runtime flags — the CPU profiler's guard precedent. Zero when off.
- Dump at exit via the existing `atexit` reporting hook ordering
  (`gc_stats_report` precedent), idempotent.

## Non-goals

Allocation counts and cumulative alloc_space (misleading for a
generational collector); byte-exact site attribution (sampling suffices
at RSS scale); interop with interposition tools.

Note what the first of those implies, since the ranking makes it easy to
forget: neither layer measures allocation VOLUME, so neither can tell you
that a pass allocates too much. That is deliberate — volume is the metric
this design rejects — but it means "reduce the allocations at the top site"
is a conclusion the data cannot support. If you want to test an
allocation-churn hypothesis you need a different instrument (the GC's own
`allocs=`/`cycles=` counters, or CPU time), and you should expect the
answer to be "no measurable difference" unless the objects survive.

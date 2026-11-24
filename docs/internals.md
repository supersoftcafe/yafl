# Internals: the garbage collector and the page allocator

This is the map of the runtime's memory management as it is built, for someone about to read `yafllib/object.c` (the collector) and `yafllib/mmap.c` (the page allocator). It says how the parts fit and why; the comments in those files are the detail, and where this page and the code disagree, the code is right. The generational half has its own document, [generations-design.md](generations-design.md). Measurements and the reasoning behind a number are in the comment beside the constant.

## Background

The runtime is event driven: a worker thread per core runs the program, and a separate group of threads does async IO, so workers never block on IO. The compiler keeps work between suspension points short, and a worker regularly returns to its event loop. The collector depends on that: a thread's stack can be scanned at a point where little is live on it, and every thread reaches a safe point soon.

The heap is a map of 16 KiB pages (`GC_PAGE_SIZE`), sized by `YAFL_HEAP_SIZE` (1 GiB unless set). A heap is a maximum, not a target: pages the program has stopped using are handed back to the operating system. An object is a header word (its vtable, whose low bits carry flags such as pinned and old) followed by fields. The collector is precise about the heap: a descriptor says where an object's pointers are, and a pointer field with any low bit set is not a pointer (small integers are packed that way). Thread stacks and registers are scanned conservatively.

## No collector thread

Every allocating worker drives the collector, paced by its own allocation. A cycle moves through five stages:

```
IDLE -> START -> SCAN_ROOTS -> MARK_SWEEP -> PRUNE -> IDLE ...
```

- **START** and **SCAN_ROOTS** are exclusive: one executor at a time, under `fsa_lock`.
- **MARK_SWEEP** and **PRUNE** are parallel. Every caller becomes an executor, takes no lock, and claims work a page at a time. A claimed page is on no list and only its owner writes its marks, so a page is the unit of parallelism.
- Stages change when no page is in flight (`gc_pages_in_flight == 0`), never on the number of executors, which changes with every paced step.

Page lists are changed only under `gc_pool_lock`, in short sections. `fsa_lock` also covers thread registration, so a new thread knows which cycle its first root scan falls in.

### Roots

Globals are scanned as the collector leaves IDLE. Each thread is scanned at its own next safe point: from where it entered the collector, so the collector's own frames are not read. A thread that is suspended in IO is scanned by another. A page a conservative root reaches is not compacted that cycle.

### Write barrier

Marking runs while the program does. The barrier is hybrid. A store shades the value it overwrites, which is the snapshot-at-the-beginning guarantee (a deletion barrier, as in Yuasa). A thread whose root scan has not happened yet also shades the value it stores, because its stack may hold the only reference to an older object (an insertion half, as in Go's hybrid barrier). Once the thread has been scanned the second half stops.

## Pacing

Collection is proportional to allocation, exactly: each page allocated lets executors claim a bounded slice of the backlog, so aggregate work can never exceed aggregate allocation.

| Setting | Default | |
|---|---|---|
| scan | 6 pages per page allocated | `YAFL_GC_STEP_PAGES` |
| prune | 64 pages per page allocated | `YAFL_GC_PRUNE_PAGES` |
| dwell | 4096 pages (64 MiB) allocated between cycles | `YAFL_GC_IDLE_PAGES` |

Past half full, both ratios double each time the free heap halves, so the collector works harder the nearer the heap is to running out, and eases off as it empties. That is the one feedback on headroom. A reserve of pages is kept for compaction to evacuate into; when ordinary allocation reaches it the allocator stalls the caller into driving a cycle itself, and asks for a major cycle before it gives up. The dwell is the dial between CPU and memory: a longer one costs less CPU and holds more garbage.

## Marking by pages

Only pages with marks waiting are scanned. A page joins the scan list at its first mark, and a page that is never marked goes straight to prune. The details are in the `THE HAND-OFF` and `OPENING AND CLOSING` comments in `object.c`. In outline:

- **Stamps.** Each page carries a stamp placing it in the current cycle: queued (handed over this cycle), born (allocated after its thread's root scan, so outside the cycle and implicitly live), or white. A page is stamped once, at birth, so no walk over the pages is needed to open a cycle: every page is white the moment it opens.
- **The hand-off.** The first mark of a white page moves its stamp with one compare-and-swap, and only the winner pushes the page onto a lock-free stack. Executors take the whole stack under the pool lock and move its pages to the scan list. A mark from any source (roots, cards, black allocation, a scanner, a mutator's barrier) hands over in the same way.
- **Back-edges.** A mark on a page already scanned this cycle is scanned by the claim that found it, up to 4096 objects per page claimed (`GC_BACKEDGE_BUDGET`); past that the page goes back on the list once. Before this, one executor could follow a long chain of back-edges while the others allocated, and that chain was the peak memory of a 6G self-compile (#134).
- **Closing.** A barrier counts itself before it reads the "marking open" flag, and the mark tail lowers the flag and waits for every barrier inside its window. A cycle opens only at the end of START, once everything the opening writes is published by a release fence. Both exist because a barrier can act a while after it read the flag (`test_gc_late_mark`, `test_gc_late_old_mark`).

## Prune and compaction

Prune frees what was not marked. A page with nothing live goes back to the allocator. A sparse page is compacted: its live objects are copied to fresh pages and a forwarder is left behind, and pointers are rewritten the next time they are traced.

- A young page is a candidate at 33% occupancy or less (`YAFL_GC_COMPACT_PERCENT`; 0 turns compaction off), and any page in a sparse block (below) is a candidate whatever its occupancy, except a page compaction itself filled.
- Pages reachable from a conservative root are not moved.
- A cycle's compaction has a budget of evacuation-target pages, a share of the heap's free pages taken at the start of the cycle (25%, `YAFL_GC_COMPACT_FREE_PERCENT`). Targets bypass the reserve gate, and without a budget they ate the free runs that multi-page allocations need (#135).
- An object that is fully initialised before the next allocation or checkpoint can be moved safely: during a move two copies may briefly exist while pointers are rewritten.
- Old pages are offered to compaction only by a major cycle, and their copies land on pages born old.

## Generations

A page is young until it has stayed stable across a volume of allocation, then old for good. A minor cycle traces the young pages, the mutable set and the carded old objects; a major traces everything. A card is one bit per object that records an old object that may point at a young one. This is the whole of [generations-design.md](generations-design.md).

A major runs when the old generation has grown to 125% of its size after the last major (`YAFL_GC_MAJOR_GROWTH`, with a floor so small programs never run one), or when it has grown by more than the heap has free, or on request. The second rule is what keeps old garbage from filling the heap at a small `YAFL_HEAP_SIZE`.

## The page allocator

`mmap.c` hands the collector pages. Most objects are one page or less; a larger object takes a run of pages. The map is divided into blocks of 32 pages, each with a count of its live pages, and one density rule applies at every heap size:

- **A single page goes where pages are densest:** a free page in the fullest block that has any, warm before cold, then a page the pool set aside, then a block that is empty, and only then a fresh page. The densest block is found through a density index (per live count, a bitmap of the blocks holding it) rather than by scanning.
- **Compaction drains sparse blocks.** "Sparse" is relative: at the start of every cycle the threshold is retaken as the live count that covers the sparsest 25% of the partly filled blocks (`YAFL_GC_SPARSE_SHARE`; 0 turns the rule off). So there are always blocks to drain and blocks to fill.
- **A run looks for a window** in sparse or empty blocks among the singles before it grows its own band of the map.

This was added because multi-page allocations aborted with 8-22% of the heap free: the free space was all one-page holes between single pages (#134). Concentrating reuse has a second effect, that pages untouched across a stretch of allocation age and can be returned to the operating system. A scavenger does that, keeping 256 pages (4 MiB) of warm slack and returning at most 1024 pages a cycle.

## Finding out what it is doing

- `YAFL_GC_STATS=1` prints `[GC]`, `[GC TIME]` and `[GC BLOCKS]` lines. It takes locks to count, so it is not for timing.
- Heap profiling (`yafllib/heapprof.c`) is described in [heap-profiling-design.md](heap-profiling-design.md).
- The tests are in `yafllib/tests/`, many of them stepped: they drive the stages by hand, and some use a probe build to stop inside a window that is a few instructions wide. `gc_soak.py` runs them all under varied settings for a stated time. Run `make` in `build/` after any runtime change, since `ctest` never builds.

## History

Earlier versions of this page were a to-do list for a collector that was not built yet. That one was not a copy of the design here. The thread-local nursery ([local-nursery-prototype.md](local-nursery-prototype.md)) was tried and removed; the dwell between cycles took most of what it gave.

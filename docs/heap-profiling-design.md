# Heap-pressure profiling (massif + pprof)

Status: design. Runtime-only (libyafl), like profiling M2 — no compiler or
port changes except that allocation-site attribution rides `--profile`'s
shadow stack.

## The question it answers

Not "how many objects were allocated" — short-lived objects die in place,
are never visited by the collector, and cost almost nothing. The question
is what pushes RSS: bytes that SURVIVE collections, live-heap composition
over time, and reserved-but-not-live space. The measurement principle
follows: **instrument the collection boundary, never the allocation
count**. What the scavenger copies and what the marker visits *is* heap
pressure, by definition; everything else never appears in the data.

## Layer 1 — live census by type → massif format

Per collection, accumulate `live_bytes[vtable] += size` on walks the
collector already performs:

- **Full (mark) cycles**: in `gc_fsa_mark_sweep$mark_object`, on the
  first-mark path only (`!was_set` after the atomic fetch-set — exactly
  once per live object per epoch). Size is
  `vt->object_size + vt->array_el_size * len`; the type name is
  `vtable->name`.
- **Scavenges**: in the copy path, per survivor copied — survivor bytes by
  type (the nursery's dead majority is never touched).

Marking and scavenging are parallel, so the census is per-thread arrays
merged at collection end — the same discipline as the CPU profiler's
counters (plain per-thread stores, merged single-threaded at the safe
point that ends the cycle).

Output is **massif format** (`massif.out.<pid>`, read by ms_print and
massif-visualizer), emitted by libyafl directly — the same trick as
emitting callgrind without Valgrind, and necessary for the same reason:
interposition-based tools see one giant mmap when pointed at a bump
allocator. One snapshot per collection:

- scavenges → `heap_tree=empty` snapshots (totals only, near-free), giving
  the fine-grained heap-over-time curve;
- full cycles → `heap_tree=detailed` with a one-level tree: root
  `(heap)`, one child per type name, weighted by live bytes.

`mem_heap_B` = live bytes from the census (full cycles) or the allocator's
in-use accounting (scavenge points); `mem_heap_extra_B` =
`memory_total_pages()·page_size − mem_heap_B` — which surfaces the *other*
real RSS pusher: fragmentation and mutable pages exempt from compaction.
`time=` uses milliseconds (`--time-unit=ms` semantics).

## Layer 2 — allocation-site `inuse_space` → pprof

Sampled site attribution: every Nth allocated KB (default 64KiB,
`YAFL_HEAPPROF_SAMPLE` overrides, 0 disables), record
`(stack-id, address, size)` in a per-thread open-addressing table — the
stack hash-consed from `--profile`'s existing shadow stack, so layer 2
requires a `--profile` binary. At each collection, walk the sample table:
forwarded objects update their address (the same forwarding lookup the
collector just published — during the window before forwarding data is
discarded), dead objects drop. Compaction relocations are handled by the
same walk.

What remains is, at any dump point, the sampled LIVE set attributed to
allocation sites: exactly Go's `inuse_space`/`inuse_objects` pair, scaled
by the sampling rate. Output is the pprof gzipped protobuf (hand-encoded:
varint framing, string table, one `Location` per shadow-stack frame id,
`Function` records from the `--profile` descriptor table), readable by
`pprof` including flamegraphs and web UI.

## Interface

- `YAFL_HEAPPROF=<path>` enables layer 1 and names the massif output
  (default off; `massif.out.<pid>` when set empty).
- `YAFL_HEAPPROF_SAMPLE=<bytes>` enables layer 2 in a `--profile` binary
  (pprof written beside the massif file as `<path>.heap.pb.gz`).
- Census branches are per-object `UNLIKELY(...)` tests on a runtime flag —
  the M1 precedent (`yafl_prof_enter`'s NULL guard); measured overhead is
  reported with the first shipped run.
- Dump at exit via the existing `atexit` reporting hook ordering
  (`gc_stats_report` precedent).

## Non-goals

Allocation counts and cumulative alloc_space (misleading for a scavenging
collector); byte-exact site attribution (sampling suffices at 64KiB for
RSS-scale questions); interop with interposition tools.

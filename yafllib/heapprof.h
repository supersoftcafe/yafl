// Heap-pressure profiling, layer 1: live census by TYPE at the collection
// boundary, emitted in massif format (see docs/heap-profiling-design.md).
// Short-lived objects are never visited by the collector and never appear;
// what the marker visits and the scavenger copies IS heap pressure.
//
// Enabled by YAFL_HEAPPROF=<path> ("" = massif.out.<pid> in CWD). The
// census hooks are per-object UNLIKELY branches on yafl_heapprof_enabled
// (the CPU profiler's guard precedent); marking is parallel, so counts
// accumulate per thread and merge in the exclusive prune tail.
#ifndef YAFL_HEAPPROF_H
#define YAFL_HEAPPROF_H

#include <stdbool.h>
#include <stddef.h>

struct vtable;

extern bool yafl_heapprof_enabled;

// Read the environment, allocate the global table, register the atexit
// dump. Called once from gc initialisation.
void yafl_heapprof_init(void);

// Per-thread census storage. Called from gc_declare_thread for every
// worker; a no-op unless enabled.
void yafl_heapprof_thread_init(void);

// One LIVE object visited this cycle (first-mark or scavenge-copy).
// Lock-free: touches only the calling thread's table.
void yafl_heapprof_census(const struct vtable *vt, size_t bytes);

// Cycle boundary, called single-threaded from the exclusive prune tail:
// merge the per-thread tables into the cycle snapshot, append it to the
// massif stream, reset the per-thread tables. `in_use_bytes` /
// `reserved_bytes` feed mem_heap_B context (the census covers what this
// cycle VISITED; page accounting covers the whole heap).
void yafl_heapprof_cycle_end(size_t in_use_bytes, size_t reserved_bytes);

// Flush and close the massif stream (atexit); also writes the layer-2
// pprof file when sampling is enabled.
void yafl_heapprof_dump(void);

// ── layer 2: allocation-site inuse_space (pprof) ───────────────────────────
//
// Sampled site attribution, enabled by YAFL_HEAPPROF_SAMPLE=<bytes> in a
// --profile binary (the shadow stack is the site source) alongside
// YAFL_HEAPPROF. Sampling happens at the allocation SLOW PATH — page
// acquisition — so the fast path is untouched and sampling is naturally
// size-proportional (an allocator's chance of triggering a refill is its
// byte share). Records are maintained at collection boundaries: compaction
// re-keys them through the published forward word, and after a major —
// when prune has rewritten every objects bitmap to the live set — records
// whose start slot is no longer an object are dropped. The dump scales by
// the standard sampling estimator and writes <massif-path>.heap.pb.gz.
extern bool yafl_heapprof_sample_enabled;

// The slow-path hook: `addr`/`object_bytes` are the allocation that
// triggered the acquisition of `acquired_bytes` of fresh pages. Counts the
// acquisition against the sampling debt; records the object when it
// crosses. Called on the allocating thread (its shadow stack is current).
void yafl_heapprof_sample_alloc(void *addr, size_t object_bytes,
                                size_t acquired_bytes);

// Compaction published `new_addr` as the forward target of `old_addr`.
// Called by the evacuating GC thread, at most once per object per cycle.
void yafl_heapprof_sample_forwarded(void *old_addr, void *new_addr);

// Collection boundary (exclusive prune tail): re-key forwarded records and
// drop records whose start slot is no longer a live object. The page-bitmap
// test is exact for pages this cycle pruned and conservative (keeps stale)
// for old pages until a major refreshes them.
void yafl_heapprof_sample_sweep(void);

// Test introspection: live record count; *live_bytes gets their byte sum.
size_t yafl_heapprof_sample_records(size_t *live_bytes);

#endif

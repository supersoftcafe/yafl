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

// Flush and close the massif stream (atexit).
void yafl_heapprof_dump(void);

#endif

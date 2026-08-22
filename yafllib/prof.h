// yafllib/prof.h — the sampling profiler's runtime-internal interface.
//
// See docs/profiling-design.md. The public surface generated code uses (the
// descriptor struct, the thread-local, the inline enter/leave fast paths and
// yafl_prof_init) lives in yafl.h; this header is for the runtime's own hooks:
// per-thread registration, the exit dump, and the pseudo-frames the collector
// pushes so GC time is visible in profiles.
//
// Same safety contract as log.h: nothing here allocates on the YAFL heap, and
// the sampling handler itself never calls malloc.
#pragma once

#include "yafl.h"

// Pseudo-frame ids, appended by the runtime after the program's N function
// ids. Their descriptors are runtime-owned; they appear in output as the
// parenthesised names below (file "??", line 0).
enum {
    YAFL_PROF_RES_GC        = 0,   // (GC)         — all collector work (gc_fsa)
    YAFL_PROF_RES_SCAVENGE  = 1,   // (scavenger)  — madvise scavenger, inside (GC)
    YAFL_PROF_RES_TRUNCATED = 2,   // (truncated)  — frames lost past the shadow-stack cap
    YAFL_PROF_RES_RUNTIME   = 3,   // (runtime)    — samples with an empty shadow stack
                                   //                (dispatch loop, between tasks)
    YAFL_PROF_RESERVED      = 4,
};

// True once yafl_prof_init has run (i.e. the program was compiled with
// --profile). Runtime call sites gate their pseudo-frame pushes on this.
extern bool yafl_prof_enabled;

// Called from gc_declare_thread for every worker thread (after the profiler is
// initialised — generated main() runs yafl_prof_init before thread_start).
// Allocates the thread's counter/stack/sample tables, wires the yafl_prof_tl
// fast-path pointers, and arms this thread's CPU-time sampling timer.
// No-op when profiling is off.
HIDDEN void yafl_prof_thread_init(void);

// Merge every thread's tables and write the callgrind + folded output files.
// Registered via atexit by yafl_prof_init; idempotent.
HIDDEN void yafl_prof_dump(void);

// Push/pop a reserved pseudo-frame on the calling thread's shadow stack, so
// sampled runtime work is attributed to a named frame rather than smeared over
// whatever YAFL function happened to trigger it.
HIDDEN void yafl_prof_runtime_push(uint32_t reserved_id);
HIDDEN void yafl_prof_runtime_pop(void);

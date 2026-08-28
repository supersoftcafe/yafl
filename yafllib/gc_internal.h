// Internal module header for the collector: object.c owns the machine,
// gc_stats.c owns the counters and reporting, gc_debug.c owns the poison
// dangle check and the exit-time heap hunt. Everything here is private to
// those three translation units — nothing in this header is API.
#ifndef GC_INTERNAL_H
#define GC_INTERNAL_H

#define OBJECT_HEADER_EXCLUSIONS
#include "yafl.h"
#include <setjmp.h>
#include <time.h>

// Intrusive circular list node (page lists; primitives live in object.c).
typedef struct list_element {
    struct list_element *next;
    struct list_element *prev;
} list_element_t;

// ── Core collector state (defined in object.c) ──────────────────────────────

enum gc_stage {
    GC_STAGE_NOT_STARTED,
    GC_STAGE_IDLE,       // Nothing happening, waiting for GC to start
    GC_STAGE_START,      // First setup
    GC_STAGE_SCAN_ROOTS, // Trying to scan stack. Globals scanned as we exited idle.
    GC_STAGE_MARK_SWEEP, // Walk the graph, mark things as seen and scan as we go
    GC_STAGE_PRUNE
};

enum thread_state {
    THREAD_STATE_RUNNING,               // Busy running, don't interrupt
    THREAD_STATE_SUSPENDED,             // IO is in progress, so an external thread could scan this thread
    THREAD_STATE_SUSPENDED_SCAN,        // Thread is suspended, an external thread is scanning this one
    THREAD_STATE_EXITED
};

struct gc_thread_info {
    gc_alloc_tl_t *alloc;   // = &gc_alloc_tl of this thread (set at registration)
    int_fast32_t lag_counter;
    bool in_relocation;  // set while compaction evacuates objects: its target
                         // allocations may use the relocation reserve

    struct gc_thread_info *next;

    thread_roots_declaration_func_t thread_roots_declaration_func;
    void* thread_roots_context;

    bool roots_scanned;
    _Atomic(enum thread_state) thread_state;

    list_element_t  new_pages; // Circular list of pages waiting for next GC

    object_t **stack_lower_ptr; // Numerically lower pointer to the stack
    object_t **stack_upper_ptr; // Numerically higher pointer to the stack
    jmp_buf    saved_registers; // Expensive way to save the registers for GC
    // setjmp is NOT a sufficient register capture for a conservative scan:
    // glibc PTR_MANGLEs rsp, rip AND RBP in the jmp_buf (XOR with the
    // pointer guard). At -O2, with frame pointers omitted, rbp is a general
    // callee-saved register — an object referenced ONLY from rbp at a safe
    // point scans as garbage and gets swept live (test_large_objects SEGV,
    // test_gc_pressure DANGLE). The callee-saved set is dumped RAW here as
    // well; caller-saved registers are already spilled to the scanned stack
    // by the C ABI before any call into the runtime.
    void      *saved_callee_regs[8];
};

extern thread_local struct gc_thread_info gc_thread_info;
extern _Atomic(struct gc_thread_info*) threads;
extern _Atomic(enum gc_stage) stage;
extern uint32_t epoch;

extern list_element_t pages_to_scan;
extern list_element_t pages_to_prune;
extern list_element_t old_pages;

extern _Atomic(bool)     gc_pool_lock_word;
extern _Atomic(uint64_t) gc_alloc_clock;
extern _Atomic(uint64_t) gc_cycle_count;
extern _Atomic(size_t)   gc_old_page_count;
extern _Atomic(size_t)   gc_dirty_old_count;
extern thread_local size_t mark_worklist_count;

extern bool gc_poison_enabled;
// Manual-stepping debug mode (EXPORTed for tests): allocation-driven pacing
// is disabled; the test drives the collector via gc_debug_step().
extern bool gc_debug_manual_mode;
extern bool gc_stats_enabled;

bool gc_object_is_on_heap_slow(object_t *object);

// mmap.c provides these (no public header of its own).
extern size_t memory_watermark(void);
extern size_t memory_total_pages(void);
extern size_t memory_count(void);
extern void memory_pool_stats(size_t* hits, size_t* steals, size_t* stale,
                              size_t* misses, size_t* warm_at_miss);
extern void memory_pool_release_cycle(void);
extern void memory_pool_release_stats(size_t* released, size_t* retained, size_t* lost,
                                      unsigned* pct);

// Page-pool lock: guards pages_to_scan / pages_to_prune list surgery only —
// O(1) critical sections, taken once per page claimed/linked. A CAS spinlock
// beats a futex here: the hold time is shorter than a syscall path.
static inline void gc_pool_lock(void) {
    // Test-and-TEST-and-set with pause: waiters spin on a plain read and only
    // CAS when the lock looks free. A bare CAS loop had 12 waiters hammering
    // the line with locked RMWs, stealing it from each other AND from the
    // holder's release — measured at T=12 as 76% of ALL cross-core HITM
    // traffic and ~47% of total cycles (perf c2c, 2026-07-08). The pause
    // keeps a waiting SMT sibling from starving the holder.
    for (;;) {
        bool expected = false;
        if (atomic_compare_exchange_weak_explicit(&gc_pool_lock_word, &expected, true,
                                                  memory_order_acquire, memory_order_relaxed))
            return;
        do { __builtin_ia32_pause(); }
        while (atomic_load_explicit(&gc_pool_lock_word, memory_order_relaxed));
    }
}
static inline void gc_pool_unlock(void) {
    atomic_store_explicit(&gc_pool_lock_word, false, memory_order_release);
}

// Iterate the (possibly windowed) pointer map of `vt` over the object at
// `obj`: binds `m` to each window's mask word and `slots` to the window's
// base, so the classic bit loop reads `slots[__builtin_ctzll(m)]`. Window 0
// is the inline word — the overwhelmingly common single-window case runs
// exactly the pre-window code. `break` inside the bit loop behaves as
// before; `return`/`continue` in the caller's own loop work unchanged.
#define GC_FOR_EACH_PTR_WINDOW(vt, obj, m, slots) \
    for (unsigned _w = 0, _nw = (vt)->object_pointer_masks ? (vt)->object_pointer_mask_words : 1; _w < _nw; _w++) \
        for (ptr_mask_t m = _w ? (vt)->object_pointer_masks[_w] : (vt)->object_pointer_locations, _o = 1; _o; _o = 0) \
            for (object_t **slots = (object_t**)(obj) + (size_t)_w * 64; _o; _o = 0)

// ── Stats module (gc_stats.c) ────────────────────────────────────────────────
// Counters are bumped by the collector hot paths (object.c), read and printed
// by gc_stats.c. All gated on gc_stats_enabled at the increment sites.

enum { GC_LAT_BUCKETS = 20 };

extern _Atomic(uint64_t) gc_stat_mark_steps, gc_stat_pages_popped, gc_stat_requeued,
                         gc_stat_rq_drain, gc_stat_rq_repro, gc_stat_overflows,
                         gc_stat_prune_steps, gc_stat_pages_freed, gc_stat_page_allocs,
                         gc_stat_majors, gc_stat_cons_seeds;
extern _Atomic(uint64_t) gc_prof_objs, gc_prof_ptrs, gc_prof_passes, gc_prof_drained;
extern _Atomic(uint64_t) gc_prof_drain_pages;
extern size_t gc_occ_hist_pages[10], gc_occ_hist_dead[10], gc_occ_hist_promo[10];
extern _Atomic(uint64_t) gc_prof_block_multipage, gc_prof_block_mutable, gc_prof_block_compacted;
#define GC_FWD_AGE_BUCKETS 16
extern size_t gc_fwd_age[GC_FWD_AGE_BUCKETS], gc_fwd_freed;
extern _Atomic(uint64_t) gc_prof_mut_fwd_hops, gc_prof_stack_held_husk;
extern _Atomic(uint64_t) gc_prof_promote_ok, gc_prof_promote_dirty, gc_prof_block_unstable,
                         gc_prof_block_volume, gc_prof_block_kind, gc_prof_defer;
extern _Atomic(uint64_t) gc_prof_t_drain, gc_prof_t_pages, gc_prof_t_merge, gc_prof_t_live, gc_prof_t_prune_rest;
extern _Atomic(uint64_t) gc_stat_stage_ns[8];
extern _Atomic(uint64_t) gc_stat_lat[8][GC_LAT_BUCKETS];
extern _Atomic(uint64_t) gc_stat_fsa_calls;
extern struct timespec   gc_stats_t0;

static inline uint64_t gc_tsc(void) { unsigned lo, hi; __asm__ volatile("rdtsc" : "=a"(lo), "=d"(hi)); return ((uint64_t)hi << 32) | lo; }
#define GC_STAT_BUMP(c)\
    do { if (UNLIKELY(gc_stats_enabled))\
             atomic_fetch_add_explicit(&(c), 1, memory_order_relaxed);\
    } while (false)

// Charge the time since `last` (an rdtsc reading) to profile accumulator
// `acc`, then advance `last` to now — the per-section "lap" used to attribute
// mark/prune time. Companion to GC_STAT_BUMP: stats-gated, so it compiles to
// nothing measurable when YAFL_GC_STATS is off. `last` is passed explicitly
// rather than captured, so the macro reads no hidden local.
#define GC_PROF_LAP(acc, last)\
    do { if (UNLIKELY(gc_stats_enabled)) {\
             uint64_t _now = gc_tsc();\
             (acc) += _now - (last);\
             (last) = _now;\
         } } while (false)

// Occupancy survey accumulators/snapshots (defined in gc_stats.c; filled by
// object.c's gc_occupancy_account during PRUNE when stats are on).
extern size_t gc_occ_pages[2], gc_occ_live[2], gc_occ_sparse[2], gc_occ_sparse_free[2], gc_occ_large;
extern size_t gc_snap_pages[2], gc_snap_live[2], gc_snap_sparse[2], gc_snap_sparse_free[2], gc_snap_large;
extern size_t gc_occ_sparse_fwd, gc_occ_sparse_pin, gc_occ_sparse_oth;
extern size_t gc_snap_sparse_fwd, gc_snap_sparse_pin, gc_snap_sparse_oth;

void gc_stats_tick(void);    // sampled [GC] progress line (called per 512 page allocs)
void gc_stats_report(void);  // [GC TIME] exit summary (atexit when stats enabled)

// ── Debug module (gc_debug.c) ────────────────────────────────────────────────

void gc_dbg_dangle_check(object_t *object);  // poison-mode UAF edge verifier
void gc_hunt_run(void);                      // YAFL_GC_HUNT exit-time heap census

#endif

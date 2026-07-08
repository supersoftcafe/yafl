// GC statistics: the counters (bumped by object.c's hot paths, always gated
// on gc_stats_enabled there) and the two reporters — the sampled [GC]
// progress line and the [GC TIME] exit summary. Split from object.c so the
// collector core stays free of formatting and clock plumbing.
#include "gc_internal.h"
#include <stdio.h>

// --- GC diagnostics (set YAFL_GC_STATS to enable; prints to stderr).
// A sampled progress line every 512 page allocations, plus a [GC TIME]
// summary at exit: time inside gc_fsa per stage vs wall and process CPU.
extern size_t memory_watermark(void);
_Atomic(uint64_t) gc_stat_mark_steps   = 0;  // gc_fsa_mark_sweep() invocations
_Atomic(uint64_t) gc_stat_pages_popped = 0;  // pages popped + scanned in mark-sweep
_Atomic(uint64_t) gc_stat_requeued     = 0;  // page_needs_scan() — re-scan requeues
_Atomic(uint64_t) gc_stat_rq_drain     = 0;  //   ...from post-scan atomic-seen drain
_Atomic(uint64_t) gc_stat_rq_repro     = 0;  //   ...from reprocess-ring drain
_Atomic(uint64_t) gc_stat_overflows    = 0;  // reprocess-ring overflow whole-heap rescans
_Atomic(uint64_t) gc_stat_prune_steps  = 0;  // gc_fsa_prune() invocations
_Atomic(uint64_t) gc_stat_pages_freed  = 0;  // gc_page_free() calls
_Atomic(uint64_t) gc_stat_page_allocs  = 0;  // gc_page_alloc() calls
_Atomic(uint64_t) gc_stat_majors       = 0;  // major (full-heap) cycles completed
_Atomic(uint64_t) gc_stat_cons_seeds   = 0;  // objects seeded live by conservative scan
/* Fine-grained mark/prune profiling (stats-gated, single FSA thread): object
   and pointer tallies, promotion outcomes, and tsc per mark/prune section —
   printed at exit as [GC PROF]/[GC PROMO] alongside the stats. */
_Atomic(uint64_t) gc_prof_objs, gc_prof_ptrs, gc_prof_passes, gc_prof_drained;
_Atomic(uint64_t) gc_prof_promote_ok, gc_prof_promote_dirty, gc_prof_block_unstable,
                gc_prof_block_volume, gc_prof_block_kind, gc_prof_defer;
_Atomic(uint64_t) gc_prof_t_drain, gc_prof_t_pages, gc_prof_t_merge, gc_prof_t_live, gc_prof_t_prune_rest;
// gc_tsc / GC_STAT_BUMP / GC_PROF_LAP: gc_internal.h

// Nanoseconds spent inside gc_fsa, per stage (index = enum gc_stage). All GC
// work happens there, single-threaded under fsa_lock, so the sum is total
// collector time. Excludes mutator-side barrier checks and allocator memsets.
_Atomic(uint64_t) gc_stat_stage_ns[8];
// Per-call latency histogram: log2(ns) buckets per stage (see gc_fsa's exit
// timing block and the [GC LAT] report). The bucket index uses
// __builtin_clzll, whose operand is unsigned long long; pin that to uint64_t
// (the type of the value being bucketed) so the width the log2 maths assumes
// can never silently diverge from clzll's operand on some future platform.
_Static_assert(sizeof(unsigned long long) == sizeof(uint64_t),
               "__builtin_clzll operand must be 64-bit for the [GC LAT] log2 bucketing");
_Atomic(uint64_t) gc_stat_lat[8][GC_LAT_BUCKETS];
_Atomic(uint64_t) gc_stat_fsa_calls = 0;
struct timespec   gc_stats_t0;

// Page-occupancy survey (stats only): accumulated over each PRUNE as surviving
// pages stream past, snapshotted at cycle end. Index 0 = immutable, 1 = mutable.
// "Sparse" = under 25% live — candidates for any future reclamation of
// mostly-empty pages. Live slot counts use the objects/seen bitmaps alone
// (object extent = start bit to next start bit), never vtables.
size_t gc_occ_pages[2], gc_occ_live[2], gc_occ_sparse[2], gc_occ_sparse_free[2], gc_occ_large;
size_t gc_snap_pages[2], gc_snap_live[2], gc_snap_sparse[2], gc_snap_sparse_free[2], gc_snap_large;
// Why is an immutable sparse page sparse? fwd = compacted earlier, only
// forwarders remain (lazy-fixup residue); pin = conservative root pinned it
// this cycle; oth = eligible but blocked some other way (object-count guard).
size_t gc_occ_sparse_fwd, gc_occ_sparse_pin, gc_occ_sparse_oth;
size_t gc_snap_sparse_fwd, gc_snap_sparse_pin, gc_snap_sparse_oth;

void gc_stats_report(void) {
    gc_hunt_run();
    struct timespec t1, cpu;
    clock_gettime(CLOCK_MONOTONIC, &t1);
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &cpu);
    double wall = (t1.tv_sec - gc_stats_t0.tv_sec) + (t1.tv_nsec - gc_stats_t0.tv_nsec) / 1e9;
    double cpus = cpu.tv_sec + cpu.tv_nsec / 1e9;
    double gc = 0, mark, prune, roots;
    for (unsigned i = 0; i < 8; ++i) gc += atomic_load(&gc_stat_stage_ns[i]) / 1e9;
    roots = atomic_load(&gc_stat_stage_ns[GC_STAGE_SCAN_ROOTS]) / 1e9;
    mark  = atomic_load(&gc_stat_stage_ns[GC_STAGE_MARK_SWEEP]) / 1e9;
    prune = atomic_load(&gc_stat_stage_ns[GC_STAGE_PRUNE]) / 1e9;
    fprintf(stderr,
        "[GC TIME] gc=%.3fs (roots=%.3f mark=%.3f prune=%.3f other=%.3f) "
        "wall=%.3fs cpu=%.3fs | gc/wall=%.1f%% gc/cpu=%.1f%% | fsa_calls=%llu cycles=%llu\n",
        gc, roots, mark, prune, gc - roots - mark - prune,
        wall, cpus,
        wall > 0 ? 100.0 * gc / wall : 0.0,
        cpus > 0 ? 100.0 * gc / cpus : 0.0,
        (unsigned long long)atomic_load(&gc_stat_fsa_calls),
        (unsigned long long)atomic_load(&gc_cycle_count));

    // Per-call latency distribution by stage: percentile bounds read off the
    // log2 histogram (a bucket b means "< 2^(b+1) ns"). The spread between
    // p50 and p99 is the call-cost (un)predictability we tune pacing for.
    static const char *lat_name[8] = {
        [GC_STAGE_SCAN_ROOTS] = "roots", [GC_STAGE_MARK_SWEEP] = "mark",
        [GC_STAGE_PRUNE] = "prune" };
    for (unsigned s = 0; s < 8; ++s) {
        if (!lat_name[s]) continue;
        uint64_t n = 0;
        for (unsigned b = 0; b < GC_LAT_BUCKETS; ++b) n += atomic_load(&gc_stat_lat[s][b]);
        if (n == 0) continue;
        unsigned p50 = 0, p90 = 0, p99 = 0, pmax = 0;
        uint64_t acc = 0;
        for (unsigned b = 0; b < GC_LAT_BUCKETS; ++b) {
            uint64_t c = atomic_load(&gc_stat_lat[s][b]);
            if (c == 0) continue;
            acc += c;
            if (p50 == 0 && acc * 2 >= n)       p50 = b + 1;
            if (p90 == 0 && acc * 10 >= n * 9)  p90 = b + 1;
            if (p99 == 0 && acc * 100 >= n * 99) p99 = b + 1;
            pmax = b + 1;
        }
        fprintf(stderr, "[GC LAT] %-5s calls=%llu p50<2^%uns p90<2^%u p99<2^%u max<2^%u\n",
                lat_name[s], (unsigned long long)n, p50, p90, p99, pmax);
    }

    // Page-occupancy snapshot of the last completed cycle. "sparse" = <25%
    // live; its KB figure is the space those pages are wasting.
    const char* cls_name[2] = { "imm", "mut" };
    char occ_line[256]; size_t off = 0;
    for (int cls = 0; cls < 2; ++cls) {
        double pct = gc_snap_pages[cls]
            ? 100.0 * (double)gc_snap_live[cls] / ((double)gc_snap_pages[cls] * SLOTS_PER_PAGE) : 0.0;
        off += (size_t)snprintf(occ_line + off, sizeof occ_line - off,
            "%s: n=%zu live=%.0f%% sparse=%zu (waste %zu KB) | ",
            cls_name[cls], gc_snap_pages[cls], pct,
            gc_snap_sparse[cls],
            gc_snap_sparse_free[cls] * sizeof(slot_t) / 1024);
    }
    fprintf(stderr, "[GC PROMO] ok=%llu dirty=%llu unstable=%llu volume=%llu kind=%llu defer=%llu\n",
            (unsigned long long)gc_prof_promote_ok, (unsigned long long)gc_prof_promote_dirty,
            (unsigned long long)gc_prof_block_unstable, (unsigned long long)gc_prof_block_volume,
            (unsigned long long)gc_prof_block_kind, (unsigned long long)gc_prof_defer);
    fprintf(stderr, "[GC PROF] objs=%llu ptrs=%llu drained=%llu passes=%llu | tsc: drain=%llu merge=%llu pages=%llu live=%llu prune_rest=%llu\n",
            (unsigned long long)gc_prof_objs, (unsigned long long)gc_prof_ptrs,
            (unsigned long long)gc_prof_drained, (unsigned long long)gc_prof_passes,
            (unsigned long long)gc_prof_t_drain, (unsigned long long)gc_prof_t_merge,
            (unsigned long long)gc_prof_t_pages, (unsigned long long)gc_prof_t_live,
            (unsigned long long)gc_prof_t_prune_rest);
    fprintf(stderr, "[GC PAGES] last cycle: %slarge=%zu pages | imm-sparse: fwd=%zu pin=%zu oth=%zu | old=%zu dirty=%zu pages majors=%llu\n",
            occ_line, gc_snap_large,
            gc_snap_sparse_fwd, gc_snap_sparse_pin, gc_snap_sparse_oth,
            gc_old_page_count, gc_dirty_old_count,
            (unsigned long long)atomic_load(&gc_stat_majors));
    size_t scav_ret, scav_rec, scav_cold, scav_rec_runs;
    memory_scavenge_stats(&scav_ret, &scav_rec, &scav_cold, &scav_rec_runs);
    fprintf(stderr, "[GC SCAV] returned=%zu reclaimed=%zu (runs=%zu) cold_now=%zu (pages)\n",
            scav_ret, scav_rec, scav_rec_runs, scav_cold);
}

void gc_stats_tick(void) {
    if (LIKELY(!gc_stats_enabled)) return;
    uint64_t n = atomic_fetch_add_explicit(&gc_stat_page_allocs, 1, memory_order_relaxed) + 1;
    if ((n & 511) != 0) return;   // sample every 512 page allocations
    // Pool-locked: parallel executors splice pages_to_scan concurrently, and
    // an unlocked walk reads torn links (first genuine-multicore crash found —
    // stats-path only, but a SEGV is a SEGV).
    unsigned scanq = 0;
    gc_pool_lock();
    for (list_element_t *n = pages_to_scan.next; n != &pages_to_scan && scanq < 9999; n = n->next)
        scanq++;
    gc_pool_unlock();
    size_t scav_ret, scav_rec, scav_cold, scav_rec_runs;
    memory_scavenge_stats(&scav_ret, &scav_rec, &scav_cold, &scav_rec_runs);
    fprintf(stderr,
        "[GC] allocs=%llu watermark=%llu live=%llu cycles=%llu stage=%d epoch=%u "
        "wl=%u scanq=%u "
        "mark_steps=%llu popped=%llu requeued=%llu overflows=%llu "
        "rq_drain=%llu rq_repro=%llu prune_steps=%llu freed=%llu "
        "scav_ret=%zu scav_rec=%zu cold=%zu\n",
        (unsigned long long)n,
        (unsigned long long)memory_watermark(),
        (unsigned long long)memory_count(),
        (unsigned long long)atomic_load(&gc_cycle_count),
        (int)stage, (unsigned)epoch,
        (unsigned)mark_worklist_count, scanq,
        (unsigned long long)atomic_load(&gc_stat_mark_steps),
        (unsigned long long)atomic_load(&gc_stat_pages_popped),
        (unsigned long long)atomic_load(&gc_stat_requeued),
        (unsigned long long)atomic_load(&gc_stat_overflows),
        (unsigned long long)atomic_load(&gc_stat_rq_drain),
        (unsigned long long)atomic_load(&gc_stat_rq_repro),
        (unsigned long long)atomic_load(&gc_stat_prune_steps),
        (unsigned long long)atomic_load(&gc_stat_pages_freed),
        scav_ret, scav_rec, scav_cold);
}


// DEBUG: when set, allocation does NOT drive the GC FSA, so a test can step the
// collector by hand (gc_debug_step) and pin down exact interleavings.
// gc_debug_manual_mode: defined in object.c (collector control, not stats)


#include <pthread.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

#include "test_framework.h"

// Internal accessors — not declared in yafl.h because they exist only for
// tests and the [GC POOL] diagnostic line.
extern size_t memory_watermark(void);
extern size_t memory_total_pages(void);
extern void memory_pool_stats(size_t* hits, size_t* steals, size_t* stale,
                              size_t* misses, size_t* warm_at_miss);
extern void memory_pool_release_cycle(void);
extern void memory_pool_release_stats(size_t* released, size_t* retained, size_t* lost,
                                      unsigned* pct);


// Each test captures the watermark at its start; allocations may grow it by at
// most the total pages claimed (upper bound), and reuse cycles must not grow
// it at all. The "<=" form makes the tests order-independent: a later test may
// observe pages already freed by an earlier one and reuse them, in which case
// the watermark grows by less than the claimed total.


// Sanity: allocating single pages grows the watermark by at most N. Freeing
// and re-allocating must not grow it further.
TEST(single_page_watermark_tracks_live_set)
    enum { N = 256 };
    void* pages[N];
    size_t start_wm = memory_watermark();

    for (int i = 0; i < N; ++i)
        pages[i] = memory_pages_alloc(1);

    size_t after_alloc = memory_watermark();
    ASSERT(after_alloc - start_wm <= N);

    // Free every other page.
    for (int i = 0; i < N; i += 2)
        memory_pages_free(pages[i], 1);

    // Watermark must not have moved — frees never grow the heap.
    ASSERT(memory_watermark() == after_alloc);

    // Re-allocate; the new singles must reuse the just-freed slots without
    // extending the watermark at all.
    for (int i = 0; i < N; i += 2)
        pages[i] = memory_pages_alloc(1);
    ASSERT(memory_watermark() == after_alloc);

    for (int i = 0; i < N; ++i)
        memory_pages_free(pages[i], 1);
TEST_END()


// Churn: many alloc-free cycles with a fixed live set. The watermark must stay
// bounded by (initial + live set + a small constant), not grow with the number
// of cycles.
TEST(alloc_free_churn_does_not_grow_heap)
    enum { LIVE = 64, CYCLES = 4096 };
    void* live[LIVE];
    size_t start_wm = memory_watermark();

    for (int i = 0; i < LIVE; ++i)
        live[i] = memory_pages_alloc(1);

    size_t after_fill = memory_watermark();

    // Each cycle: free one live page, then alloc a new one. With first-fit
    // reuse this hammers the same slot indefinitely.
    for (int c = 0; c < CYCLES; ++c) {
        int slot = c % LIVE;
        memory_pages_free(live[slot], 1);
        live[slot] = memory_pages_alloc(1);
    }

    ASSERT(memory_watermark() == after_fill);

    for (int i = 0; i < LIVE; ++i)
        memory_pages_free(live[i], 1);

    (void)start_wm;
TEST_END()


// Multi-page allocations: same property holds when each allocation is a run
// of N contiguous pages.
TEST(multi_page_watermark_tracks_live_set)
    enum { RUNS = 64, RUN_PAGES = 3 };
    void* runs[RUNS];
    size_t start_wm = memory_watermark();

    for (int i = 0; i < RUNS; ++i)
        runs[i] = memory_pages_alloc(RUN_PAGES);

    size_t after_fill = memory_watermark();
    ASSERT(after_fill - start_wm <= RUNS * RUN_PAGES);

    // Free even runs, allocate replacements — they should slot back in.
    for (int i = 0; i < RUNS; i += 2)
        memory_pages_free(runs[i], RUN_PAGES);

    for (int i = 0; i < RUNS; i += 2)
        runs[i] = memory_pages_alloc(RUN_PAGES);

    ASSERT(memory_watermark() == after_fill);

    for (int i = 0; i < RUNS; ++i)
        memory_pages_free(runs[i], RUN_PAGES);
TEST_END()


// Mixed sizes can fragment. Allocate singles and triples interleaved, free in
// a pattern that produces holes, then allocate replacements. The watermark
// may grow a bit beyond the strict live set (fragmentation overhead) but
// must not grow with the number of churn cycles.
TEST(mixed_sizes_bounded_by_fragmentation)
    enum { ROUNDS = 32, PER_ROUND = 8 };
    void* singles[ROUNDS * PER_ROUND] = {0};
    void* triples[ROUNDS * PER_ROUND] = {0};

    for (int r = 0; r < ROUNDS; ++r) {
        for (int i = 0; i < PER_ROUND; ++i) {
            singles[r * PER_ROUND + i] = memory_pages_alloc(1);
            triples[r * PER_ROUND + i] = memory_pages_alloc(3);
        }
    }

    size_t peak_after_fill = memory_watermark();

    // Churn: free triples then re-alloc them; watermark should stay flat
    // because all the holes are exactly the right size.
    for (int cycle = 0; cycle < 8; ++cycle) {
        for (int i = 0; i < ROUNDS * PER_ROUND; ++i) {
            memory_pages_free(triples[i], 3);
            triples[i] = memory_pages_alloc(3);
        }
        ASSERT(memory_watermark() == peak_after_fill);
    }

    for (int i = 0; i < ROUNDS * PER_ROUND; ++i) {
        memory_pages_free(singles[i], 1);
        memory_pages_free(triples[i], 3);
    }
TEST_END()


// Concurrent allocators must not balloon the heap. Threads each do a fixed
// number of alloc-free cycles in parallel; the watermark at the end must be
// bounded by (peak concurrent live set + small slack), not by total throughput.
#define CONCURRENT_THREADS 8
#define CONCURRENT_CYCLES  2000
#define CONCURRENT_LIVE    16

static _Atomic(int) _start_gun;

static void* _churn_thread(void* arg) {
    (void)arg;
    while (!atomic_load(&_start_gun)) { /* spin */ }

    void* live[CONCURRENT_LIVE];
    for (int i = 0; i < CONCURRENT_LIVE; ++i)
        live[i] = memory_pages_alloc(1);

    for (int c = 0; c < CONCURRENT_CYCLES; ++c) {
        int slot = c % CONCURRENT_LIVE;
        memory_pages_free(live[slot], 1);
        live[slot] = memory_pages_alloc(1);
    }

    for (int i = 0; i < CONCURRENT_LIVE; ++i)
        memory_pages_free(live[i], 1);

    return NULL;
}

TEST(concurrent_churn_bounded_watermark)
    size_t start_wm = memory_watermark();
    atomic_store(&_start_gun, 0);

    pthread_t threads[CONCURRENT_THREADS];
    for (int i = 0; i < CONCURRENT_THREADS; ++i)
        pthread_create(&threads[i], NULL, _churn_thread, NULL);

    atomic_store(&_start_gun, 1);

    for (int i = 0; i < CONCURRENT_THREADS; ++i)
        pthread_join(threads[i], NULL);

    // Peak concurrent live set is CONCURRENT_THREADS * CONCURRENT_LIVE pages.
    // Allow a generous slack for transient CAS-loss advances and bump races.
    size_t peak_live = CONCURRENT_THREADS * CONCURRENT_LIVE;
    size_t slack     = CONCURRENT_THREADS * 4;
    size_t grew_by   = memory_watermark() - start_wm;

    if (grew_by > peak_live + slack) {
        printf("\n    watermark grew by %zu pages; peak_live=%zu slack=%zu\n",
               grew_by, peak_live, slack);
    }
    ASSERT(grew_by <= peak_live + slack);
TEST_END()


// Construct a heap state where the only free region in the active heap lies
// beyond MAX_SCAN_PROBES from where the per-thread cursor will reset to (0).
// A correct allocator must still reach those free pages — bumping the
// watermark once per allocation would balloon the heap indefinitely.
//
// MAX_SCAN_PROBES is a private constant in mmap.c, so we use generous
// margins. After this test fills FILL pages and frees a hole at HOLE_START,
// the per-thread cursor is at FILL. The next allocation resets the cursor
// to 0 (because cursor + 1 > FILL). With a 4096-probe cap, walking from 0
// covers [0, 4096); a hole at HOLE_START > 4096 is unreachable.
TEST(scan_cap_reaches_holes_beyond_cap_distance)
    enum { FILL = 6000, HOLE_START = 4500, HOLE_SIZE = 200, CYCLES = 4096 };

    size_t start_wm = memory_watermark();

    void* pages[FILL];
    for (int i = 0; i < FILL; ++i)
        pages[i] = memory_pages_alloc(1);

    // Carve out the only free region in [0, watermark) at a position
    // strictly past the cap distance from 0.
    for (int i = HOLE_START; i < HOLE_START + HOLE_SIZE; ++i) {
        memory_pages_free(pages[i], 1);
        pages[i] = NULL;
    }

    size_t after_carve_wm = memory_watermark();

    // Alloc-and-free in a tight loop. Each cycle puts the page right back;
    // a correct allocator reuses pages from the hole and never grows the
    // watermark. A broken cap-allocator bumps once per cycle.
    for (int c = 0; c < CYCLES; ++c) {
        void* p = memory_pages_alloc(1);
        memory_pages_free(p, 1);
    }

    size_t after_churn_wm = memory_watermark();

    if (after_churn_wm > after_carve_wm + 64) {
        printf("\n    watermark grew by %zu pages over %d alloc/free cycles\n",
               after_churn_wm - after_carve_wm, CYCLES);
    }
    ASSERT(after_churn_wm - after_carve_wm <= 64);

    for (int i = 0; i < FILL; ++i)
        if (pages[i] != NULL) memory_pages_free(pages[i], 1);

    (void)start_wm;
TEST_END()


// REUSE REGRESSION: a free page must be reused however far it sits from the
// scan cursor. The previous test churns ONE page at a time, so after the first
// bump the cursor is parked next to the hole and every later cycle finds it.
// Sustained allocation does not get that luck: the cursor is reset to 0 once
// per scavenge epoch (every 256 pages claimed), so on a heap whose live prefix
// is longer than the probe budget, the first allocation after every epoch tick
// walks the budget over live markers, gives up, and extends the watermark —
// while thousands of free pages sit just past where it stopped looking.
//
// Measured on a self-compile before the per-thread page pool: 62% of ALL
// watermark bumps (33,561 of 53,972) happened with WARM free pages below the
// watermark, a mean of 1,869 of them (29 MiB). The cost is not the bump
// itself — the scavenger hands the abandoned pages back — but the churn it
// creates: 742 MiB returned to the OS over a 240 s slice, 55% of it faulted
// straight back in.
//
// So: claim a dense prefix, free a block beyond the budget, and re-allocate
// exactly that many DISTINCT pages. Every one must come from the free block.
TEST(reuse_reaches_free_pages_across_epoch_cursor_resets)
    // HOLE_START must clear MAX_SCAN_PROBES (4096, private to mmap.c) with
    // margin; HOLE_SIZE must span many epoch ticks (256 claims each) so the
    // test measures the sustained case rather than a single cold start.
    enum { FILL = 12000, HOLE_START = 8000, HOLE_SIZE = 3000 };

    void** pages = malloc(FILL * sizeof(void*));
    ASSERT(pages != NULL);
    for (int i = 0; i < FILL; ++i)
        pages[i] = memory_pages_alloc(1);

    // Free one contiguous block, well past the budget from the bottom. It is
    // the only free region below the watermark — asserted, not assumed, since
    // a hole left by an earlier test would let the scan succeed and make this
    // pass for the wrong reason.
    for (int i = HOLE_START; i < HOLE_START + HOLE_SIZE; ++i) {
        memory_pages_free(pages[i], 1);
        pages[i] = NULL;
    }

    size_t hole_index = (size_t)(((char*)pages[HOLE_START - 1] - _memory_heap_base)
                                 / GC_PAGE_SIZE) + 1;
    ASSERT(hole_index > 4096);
    for (size_t p = 0; p < hole_index; ++p) {
        if (!memory_pages_is_alloc_head(_memory_heap_base + p * GC_PAGE_SIZE)) {
            printf("\n    free page at index %zu below the hole at %zu"
                   " — precondition broken, run this test earlier\n", p, hole_index);
            ASSERT(false);
        }
    }

    // Assert on the allocator's own accounting, not on watermark arithmetic.
    // A watermark delta depends on where the epoch boundary happens to fall
    // relative to this loop: on a virgin heap the same scenario grew the
    // watermark by 24 pages, and inside the full test binary it grew by 0 —
    // the defect was present both times. `premature` counts bumps taken while
    // a warm free page was going spare, which is exactly the defect.
    size_t hits0, steals0, stale0, miss0, warm0;
    size_t hits1, steals1, stale1, miss1, warm1;
    memory_pool_stats(&hits0, &steals0, &stale0, &miss0, &warm0);
    size_t before = memory_watermark();

    void** reused = malloc(HOLE_SIZE * sizeof(void*));
    ASSERT(reused != NULL);
    for (int k = 0; k < HOLE_SIZE; ++k)
        reused[k] = memory_pages_alloc(1);

    memory_pool_stats(&hits1, &steals1, &stale1, &miss1, &warm1);
    size_t grew_by = memory_watermark() - before;
    if (miss1 != miss0 || grew_by != 0) {
        printf("\n    %zu scans fell through (mean %.0f warm pages going spare)"
               " and %zu pages of growth, while %d free pages waited past the"
               " scan budget (pool hits %zu)\n",
               miss1 - miss0,
               miss1 > miss0 ? (double)(warm1 - warm0) / (double)(miss1 - miss0) : 0.0,
               grew_by, HOLE_SIZE, hits1 - hits0);
    }
    // The pool must serve every one of them: not one allocation may fall
    // through to the bounded scan while the pages it needs are pooled.
    ASSERT(miss1 == miss0);
    ASSERT(grew_by == 0);
    // ...and they must have come from the pool, not from a lucky scan.
    ASSERT(hits1 - hits0 == (size_t)HOLE_SIZE);

    for (int k = 0; k < HOLE_SIZE; ++k)
        memory_pages_free(reused[k], 1);
    for (int i = 0; i < FILL; ++i)
        if (pages[i] != NULL) memory_pages_free(pages[i], 1);
    free(reused);
    free(pages);
TEST_END()


// THE RELEASE RULE: pages that go a whole cycle unwanted are handed back, and
// the fraction is the knob. Asserted as an identity rather than a count, so it
// holds whatever YAFL_GC_RELEASE_PCT is set to and whatever else other tests
// have left in the pool:
//
//     drained == surplus * pct / 100      and      surplus == drained + retained
//
// At pct=0 that forces drained==0 (nothing released); at pct=100 it forces
// retained==0 (the plain rule, everything aged goes back). The drain being
// TOTAL is what makes it an identity at all — a per-call page budget would
// leave "scheduled" and "released" differing by an unknowable amount.
TEST(release_rule_hands_back_the_configured_fraction)
    enum { N = 4096 };
    void** pages = malloc(N * sizeof(void*));
    ASSERT(pages != NULL);
    for (int i = 0; i < N; ++i) pages[i] = memory_pages_alloc(1);
    for (int i = 0; i < N; ++i) memory_pages_free(pages[i], 1);   // -> fresh

    size_t rel0, ret0, lost0; unsigned pct;
    memory_pool_release_stats(&rel0, &ret0, &lost0, &pct);

    // First rotation moves fresh -> aged; the pages are not surplus yet.
    memory_pool_release_cycle();
    size_t rel1, ret1, lost1; memory_pool_release_stats(&rel1, &ret1, &lost1, &pct);

    // Churn a pool's worth so the ALLOCATION CLOCK advances past the horizon —
    // the release deliberately does nothing until enough demand has gone by to
    // make "nobody took this page" mean something. Back-to-back calls with no
    // allocation between them are a no-op by design.
    for (int i = 0; i < N; ++i) pages[i] = memory_pages_alloc(1);
    for (int i = 0; i < N; ++i) memory_pages_free(pages[i], 1);

    // Now the first batch has sat through a pool's worth of demand unclaimed.
    memory_pool_release_cycle();
    size_t rel2, ret2, lost2; memory_pool_release_stats(&rel2, &ret2, &lost2, &pct);

    size_t drained  = (rel2 - rel1) + (lost2 - lost1);
    size_t retained = ret2 - ret1;
    size_t surplus  = drained + retained;

    if (surplus < N || drained != surplus * pct / 100) {
        printf("\n    pct=%u surplus=%zu drained=%zu retained=%zu (expected drained=%zu)\n",
               pct, surplus, drained, retained, surplus * pct / 100);
    }
    ASSERT(surplus >= (size_t)N);              // the pages we freed are in there
    ASSERT(drained == surplus * pct / 100);    // the knob decides, exactly
    ASSERT(surplus == drained + retained);     // nothing went missing

    free(pages);
TEST_END()


// FRAGMENTATION REGRESSION: keep one single page alive between every run,
// then free all the runs. Under a single shared fresh-allocation watermark
// the kept singles pepper the address space at RUN-page intervals, so after
// the frees no window wider than RUN exists anywhere — and a request for
// 2*RUN pages aborts out-of-memory even though ~98% of the heap is free
// (the self-host stage3 abort: the final 83MB output string). With
// two-ended fresh allocation (singles bump bottom-up, runs claim top-down
// from the end of the map) the kept singles pack the bottom, the freed run
// band at the top re-merges, and the big run is trivially satisfied.
TEST(interleaved_singles_and_runs_leave_a_run_window)
    enum { RUN = 64 };
    // Force heap init so total is known, without perturbing the layout.
    void* probe = memory_pages_alloc(1);
    memory_pages_free(probe, 1);
    size_t total = memory_total_pages();

    // Fill until fewer than 2*RUN pages of virgin space remain under the old
    // single-watermark layout: M singles + M runs of RUN pages, leaving
    // total - M*(RUN+1) < 2*RUN virgin pages so the final request cannot be
    // satisfied by a watermark bump.
    size_t m = total / (RUN + 1);
    void** singles = malloc(m * sizeof(void*));
    void** runs    = malloc(m * sizeof(void*));
    ASSERT(singles != NULL && runs != NULL);

    for (size_t i = 0; i < m; ++i) {
        singles[i] = memory_pages_alloc(1);
        runs[i]    = memory_pages_alloc(RUN);
    }
    for (size_t i = 0; i < m; ++i)
        memory_pages_free(runs[i], RUN);

    // ~98% of the heap is free now; a run twice the churn size must be
    // satisfiable without aborting.
    void* big = memory_pages_alloc(2 * RUN);
    ASSERT(big != NULL);
    memory_pages_free(big, 2 * RUN);

    for (size_t i = 0; i < m; ++i)
        memory_pages_free(singles[i], 1);
    free(singles);
    free(runs);
TEST_END()


int main(void) {
    struct test_results results = {0};
    struct test_results* _r = &results;

    printf("=== mmap watermark test ===\n");
    // Runs FIRST: it sizes its fill from the total heap, so it needs the
    // virgin map before other tests latch the band watermarks.
    RUN(interleaved_singles_and_runs_leave_a_run_window);
    // Second: it asserts that nothing below its hole is free, which only holds
    // while the low region is still packed by its own fill.
    RUN(reuse_reaches_free_pages_across_epoch_cursor_resets);
    RUN(single_page_watermark_tracks_live_set);
    RUN(alloc_free_churn_does_not_grow_heap);
    RUN(multi_page_watermark_tracks_live_set);
    RUN(mixed_sizes_bounded_by_fragmentation);
    RUN(concurrent_churn_bounded_watermark);
    RUN(scan_cap_reaches_holes_beyond_cap_distance);
    // Last: it drives release cycles, which take pages other tests freed.
    RUN(release_rule_hands_back_the_configured_fraction);

    PRINT_RESULTS("mmap", _r);
    return results.failed == 0 ? 0 : 1;
}

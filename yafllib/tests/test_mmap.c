
#include <pthread.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

#include "test_framework.h"

// Internal accessor — not declared in yafl.h because it exists only for tests.
extern size_t memory_watermark(void);


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


int main(void) {
    struct test_results results = {0};
    struct test_results* _r = &results;

    printf("=== mmap watermark test ===\n");
    RUN(single_page_watermark_tracks_live_set);
    RUN(alloc_free_churn_does_not_grow_heap);
    RUN(multi_page_watermark_tracks_live_set);
    RUN(mixed_sizes_bounded_by_fragmentation);
    RUN(concurrent_churn_bounded_watermark);
    RUN(scan_cap_reaches_holes_beyond_cap_distance);

    PRINT_RESULTS("mmap", _r);
    return results.failed == 0 ? 0 : 1;
}

// Busy and sparse blocks (#134): once the two bands have met, a single page
// fills a hole in a busy block before it touches a nearly-free one, so a
// block that compaction is draining stays drained for a run.
//
// A small heap, filled with single pages until the singles watermark reaches
// the top of the map: the bands have met. Then two whole blocks are thinned:
// one keeps 4 of its 32 pages (sparse), the other keeps 28 (busy). The sparse
// block's pages are freed LAST, so the page pool would hand them out first.

#include "../yafl.h"   // first: sets the POSIX feature-test macros (setenv)
#include <stdlib.h>

#include "test_framework.h"

extern size_t memory_watermark(void);
extern size_t memory_total_pages(void);
extern void   memory_blocks_retarget(void);

enum { BLOCK = 32, KEEP_SPARSE = 4, FREE_BUSY = 4 };

static size_t block_of(void* page) {
    return (size_t)((char*)page - _memory_heap_base) / GC_PAGE_SIZE / BLOCK;
}

TEST(single_pages_prefer_busy_blocks)
    void* probe = memory_pages_alloc(1);
    size_t total = memory_total_pages();
    void** pages = calloc(total, sizeof(void*));
    ASSERT(pages != NULL);
    size_t n = 0;
    pages[n++] = probe;
    while (memory_watermark() < total)
        pages[n++] = memory_pages_alloc(1);

    // Two blocks every one of whose pages this test holds.
    size_t full[2];
    int found = 0;
    for (size_t i = 0; i < n && found < 2; ++i) {
        size_t block = block_of(pages[i]);
        size_t mine = 0;
        for (size_t k = 0; k < n; ++k)
            mine += block_of(pages[k]) == block;
        if (mine == BLOCK && (found == 0 || full[0] != block))
            full[found++] = block;
    }
    ASSERT(found == 2);
    size_t busy = full[0], sparse = full[1];

    // Thin the busy block first, then the sparse one. (Freeing may itself
    // take a page, for the pool's own bookkeeping; the busy block has holes
    // to spare for that.)
    int freed = 0;
    for (size_t i = 0; i < n && freed < FREE_BUSY; ++i) {
        if (block_of(pages[i]) == busy) {
            memory_pages_free(pages[i], 1);
            pages[i] = NULL;
            freed++;
        }
    }
    int kept = 0;
    for (size_t i = 0; i < n; ++i) {
        if (pages[i] != NULL && block_of(pages[i]) == sparse) {
            if (kept < KEEP_SPARSE) {
                kept++;
            } else {
                memory_pages_free(pages[i], 1);
                pages[i] = NULL;
            }
        }
    }

    // The collector retakes the sparse threshold at the start of every cycle;
    // there is no collector here, so take it now.
    memory_blocks_retarget();

    // Two new single pages: neither may come from the sparse block.
    void* a = memory_pages_alloc(1);
    void* b = memory_pages_alloc(1);
    ASSERT(block_of(a) != sparse);
    ASSERT(block_of(b) != sparse);

    memory_pages_free(a, 1);
    memory_pages_free(b, 1);
    for (size_t i = 0; i < n; ++i)
        if (pages[i] != NULL)
            memory_pages_free(pages[i], 1);
    free(pages);
TEST_END()


int main(void) {
    struct test_results results = {0};
    struct test_results* _r = &results;

    // 256 pages, 8 blocks: small enough to fill. Set before the first
    // allocation sizes the heap.
    setenv("YAFL_HEAP_SIZE", "4m", 0);

    printf("=== mmap blocks test ===\n");
    RUN(single_pages_prefer_busy_blocks);

    PRINT_RESULTS("mmap blocks", _r);
    return results.failed == 0 ? 0 : 1;
}

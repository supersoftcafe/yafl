
#include "yafl.h"   // must be first: sets the POSIX feature-test macros

#include <pthread.h>
#include <sys/mman.h>
#include <unistd.h>
#include <string.h>


EXPORT noreturn void abort_on_out_of_memory() {
    log_error_and_exit("Aborting due to memory allocation failure", stderr);
}

static noreturn void abort_on_invalid_size() {
    log_error_and_exit("Aborting due to malformed YAFL_HEAP_SIZE environment variable", stderr);
}



enum {
    PAGE_MARKER_FREE = 0,
    PAGE_MARKER_HEAD = 1,
    PAGE_MARKER_BODY = 2,
};

// Phase-1 scan budget: probe at most this many page positions before giving up
// and extending the watermark. Bounds allocation latency to a constant
// independent of heap size; in exchange the heap may inflate modestly under
// heavy fragmentation, then plateau as reuse catches up within the larger
// active region. Increase if profiling shows premature bumps; decrease if
// allocation latency dominates.
enum { MAX_SCAN_PROBES = 4096 };


static pthread_once_t   pages_once = PTHREAD_ONCE_INIT;
static _Atomic(uint8_t)*pages_info = NULL;
static char*            pages_heap = NULL;
static size_t           total_page_count;       // Total mmap size of the heap allocation
static _Atomic(size_t)  upper_watermark = 0;    // Highest page index ever part of an allocation
static _Atomic(size_t)  alloc_count = 0;        // Track real heap usage
static _Atomic(size_t)  madvise_count = 0;      // Countdown to the next madvise, unmap pages

// Per-thread starting offset for the page scan. Begins at 0 so the first
// allocation by any thread packs near the bottom of the heap; concurrent
// threads disperse naturally via CAS losses on the page-marker bytes. Only
// ever read or written by its owning thread — no atomic, no cache-line
// contention.
static thread_local size_t alloc_cursor = 0;


static size_t get_size_of_heap() {
    const char* env_heap_size = getenv("YAFL_HEAP_SIZE");
    size_t heap_size;

    if (env_heap_size == NULL || !env_heap_size[0]) {
        heap_size = 1024ULL * 1024ULL * 1024ULL;
    } else {
        size_t len = strlen(env_heap_size);
        for (size_t index = 0; index + 1 < len; ++index) {
            char chr = env_heap_size[index];
            if (chr < '0' || chr > '9')
                abort_on_invalid_size();
        }

        size_t multiplier;
        switch (env_heap_size[len-1]) {
            case 'g': case 'G':
                multiplier = 1024ULL * 1024ULL * 1024ULL;
                break;
            case 'm': case '0': case '1': case '2': case '3': case '4':
            case 'M': case '5': case '6': case '7': case '8': case '9':
                multiplier = 1024ULL * 1024ULL;
                break;
            case 'k': case 'K':
                multiplier = 1024ULL;
                break;
            default:
                abort_on_invalid_size();
        }

        long long int number = atoll(env_heap_size);
        if (number <= 0)
            abort_on_invalid_size();

        heap_size = multiplier * (size_t)number;
    }

    return heap_size;
}


static void* allocate_lazy_heap(size_t size) {
    void *ptr = mmap(NULL, size + GC_PAGE_SIZE, PROT_READ | PROT_WRITE, MAP_ANONYMOUS | MAP_PRIVATE, -1, 0);
    if (ptr == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
    return (void*)((((uintptr_t)ptr) + GC_PAGE_SIZE - 1) &~ (GC_PAGE_SIZE - 1));
}


static void init() {
    size_t heap_size = get_size_of_heap();

    total_page_count = heap_size / GC_PAGE_SIZE;

    pages_heap = allocate_lazy_heap(heap_size);
    pages_info = allocate_lazy_heap(total_page_count);
}


// Tentatively claim [idx, idx+n): head first via CAS FREE→HEAD, then bodies via
// CAS FREE→BODY. On any per-cell collision, roll back the cells already taken
// and report failure. The partially built run is never observable as a live
// allocation because the caller has not yet seen the returned pointer; the GC
// only inspects pages it has been handed.
static bool try_claim_run(size_t idx, size_t n) {
    uint8_t expected = PAGE_MARKER_FREE;
    if (!atomic_compare_exchange_strong_explicit(
            &pages_info[idx], &expected, PAGE_MARKER_HEAD,
            memory_order_acq_rel, memory_order_relaxed))
        return false;

    for (size_t j = 1; j < n; ++j) {
        expected = PAGE_MARKER_FREE;
        if (!atomic_compare_exchange_strong_explicit(
                &pages_info[idx + j], &expected, PAGE_MARKER_BODY,
                memory_order_acq_rel, memory_order_relaxed)) {
            while (--j > 0)
                atomic_store_explicit(&pages_info[idx + j], PAGE_MARKER_FREE, memory_order_release);
            atomic_store_explicit(&pages_info[idx], PAGE_MARKER_FREE, memory_order_release);
            return false;
        }
    }
    return true;
}


// Phase 1 helper: scan within [0, snapshot) for a free run and claim it via the
// CAS chain. Returns the page index on success, SIZE_MAX on exhaustion.
//
// `step_budget` caps the number of page positions probed. The bound makes
// allocation latency O(step_budget) rather than O(snapshot).
//
// On both success and budgeted failure, `alloc_cursor` is left pointing at the
// next position to inspect. On failure that means subsequent allocations
// continue the walk from where this one gave up — without this, a bounded
// scan that always restarts at 0 could repeatedly miss the same free region
// further along and bump the watermark indefinitely.
static size_t scan_within(size_t snapshot, size_t page_count, size_t step_budget) {
    if (snapshot < page_count)
        return SIZE_MAX;

    if (alloc_cursor + page_count > snapshot)
        alloc_cursor = 0;

    size_t i = alloc_cursor;
    size_t steps_remaining = snapshot < step_budget ? snapshot : step_budget;

    while (steps_remaining > 0) {
        if (i + page_count > snapshot) {
            i = 0;
            continue;  // wrap is a free operation, not a probe
        }

        if (atomic_load_explicit(&pages_info[i], memory_order_relaxed) != PAGE_MARKER_FREE) {
            i += 1;
            steps_remaining -= 1;
            continue;
        }

        // Probe the rest of the window. If page i+j is not FREE, every window
        // starting in i+1..i+j would still include it, so we can skip the
        // cursor past the obstruction in one step rather than crawling.
        size_t j = 1;
        while (j < page_count
                && atomic_load_explicit(&pages_info[i + j], memory_order_relaxed) == PAGE_MARKER_FREE)
            j += 1;

        if (j < page_count) {
            size_t advance = j + 1;
            i += advance;
            steps_remaining = steps_remaining > advance ? steps_remaining - advance : 0;
            continue;
        }

        if (try_claim_run(i, page_count)) {
            alloc_cursor = i + page_count;
            return i;
        }

        // Lost the race for this window; nudge the cursor and try again.
        i += 1;
        steps_remaining -= 1;
    }

    alloc_cursor = i;
    return SIZE_MAX;
}


EXPORT void* memory_pages_alloc(size_t page_count) {
    assert(page_count > 0);

    // pthread_once' own fast path is a single relaxed load; an outer
    // pages_heap-NULL check would race with the non-atomic write inside init().
    pthread_once(&pages_once, init);

    while (true) {
        // Phase 1: reuse free pages within the existing active region.
        size_t snapshot = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
        size_t idx = scan_within(snapshot, page_count, MAX_SCAN_PROBES);
        if (idx != SIZE_MAX) {
            atomic_fetch_add_explicit(&alloc_count, page_count, memory_order_relaxed);
            return pages_heap + idx * GC_PAGE_SIZE;
        }

        // Phase 2: no reusable run inside the probe budget; extend the active
        // region. CAS-loop bounds growth to total_page_count without
        // overshooting and never advances past the heap end even under
        // concurrent bumps.
        size_t cur = snapshot;
        size_t end;
        while (true) {
            // Overflow-safe bounds check: `cur + page_count` could wrap if a
            // caller asked for a pathological page_count.
            if (page_count > total_page_count - cur) {
                // The heap is too full to bump. The bounded Phase-1 scan may
                // have missed a usable hole further along, so do a last-ditch
                // unbounded scan before declaring OOM.
                size_t last = scan_within(cur, page_count, SIZE_MAX);
                if (last != SIZE_MAX) {
                    atomic_fetch_add_explicit(&alloc_count, page_count, memory_order_relaxed);
                    return pages_heap + last * GC_PAGE_SIZE;
                }
                abort_on_out_of_memory();
            }
            end = cur + page_count;
            if (atomic_compare_exchange_weak_explicit(
                    &upper_watermark, &cur, end,
                    memory_order_acq_rel, memory_order_relaxed))
                break;
        }

        if (try_claim_run(cur, page_count)) {
            // Deliberately do not move alloc_cursor here. scan_within parked
            // it just past where it gave up; preserving that lets the next
            // allocation resume the walk and find any free region further
            // along, instead of redoing the same fruitless probes from the
            // bump location.
            atomic_fetch_add_explicit(&alloc_count, page_count, memory_order_relaxed);
            return pages_heap + cur * GC_PAGE_SIZE;
        }
        // A concurrent scanner that observed our new watermark snuck in and
        // claimed the freshly exposed pages first. The watermark advance is
        // not wasted — those pages now belong to whoever claimed them — so
        // loop and re-enter Phase 1 against the larger region.
    }
}

EXPORT void memory_pages_free(void* ptr, size_t page_count) {
    assert(page_count > 0);
    assert(memory_pages_is_alloc_head(ptr));
    assert(((uintptr_t)ptr & (GC_PAGE_SIZE-1)) == 0);

    ptrdiff_t offset = ((char*)ptr - pages_heap) / GC_PAGE_SIZE;
    size_t watermark = atomic_load_explicit(&upper_watermark, memory_order_relaxed);
    assert((size_t)(offset + page_count) <= watermark);

    // Caller claimed `page_count` pages. The page immediately following the
    // run must be either HEAD (next allocation), FREE, or past the watermark.
    // Anything else means the caller has truncated a multi-page allocation
    // and would leave dangling BODY markers no scanner could ever reclaim.
    if ((size_t)(offset + page_count) < watermark) {
        uint8_t after = atomic_load_explicit(&pages_info[offset + page_count], memory_order_relaxed);
        assert(after == PAGE_MARKER_HEAD || after == PAGE_MARKER_FREE);
    }

    // Count backwards so that head is the last thing released
    for (ptrdiff_t index = (ptrdiff_t)page_count; --index >= 0; ) {
        uint8_t expected = (index == 0) ? PAGE_MARKER_HEAD : PAGE_MARKER_BODY;
        assert(atomic_load_explicit(&pages_info[offset + index], memory_order_relaxed) == expected);

        // madvise BEFORE publishing FREE: while the marker is still HEAD/BODY
        // no allocator can claim this page, so MADV_DONTNEED cannot race with
        // a peer thread writing into freshly reused storage.
        if ((atomic_fetch_add_explicit(&madvise_count, 1, memory_order_relaxed) & 1023) == 0)
            madvise((char*)ptr + GC_PAGE_SIZE * index, GC_PAGE_SIZE, MADV_DONTNEED);

        atomic_store_explicit(&pages_info[offset + index], PAGE_MARKER_FREE, memory_order_release);
    }

    atomic_fetch_sub_explicit(&alloc_count, page_count, memory_order_relaxed);
}

EXPORT bool memory_pages_is_alloc_head(void* ptr) {
    ptrdiff_t offset = ((char*)ptr - pages_heap) / GC_PAGE_SIZE;
    return offset >= 0
        && (size_t)offset < atomic_load_explicit(&upper_watermark, memory_order_relaxed)
        && atomic_load_explicit(&pages_info[offset], memory_order_relaxed) == PAGE_MARKER_HEAD;
}

EXPORT size_t memory_count() {
    return alloc_count;
}

EXPORT size_t memory_watermark() {
    return atomic_load_explicit(&upper_watermark, memory_order_relaxed);
}


